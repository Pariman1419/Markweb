import io
import zipfile
from pathlib import Path
import pytest

from mark_engine.domain.models import DocType
from mark_engine.documents.locate import find_elr_folders
from mark_engine.documents.fingerprint import fingerprint_folder
from mark_engine.documents.classify import classify
from tests.fixtures.make_pdfs import make_pdf


def test_exact_folder_found(month_tree: Path):
    folder = month_tree / "3_MAR" / "ADI2603012"
    folder.mkdir()

    results = find_elr_folders(month_tree, "ADI2603012", ["3_MAR"])
    assert results == [(folder, "exact")]

    # Non-existent ELR should return empty
    assert find_elr_folders(month_tree, "ADI2603999", ["3_MAR"]) == []

    # Non-existent month should be handled gracefully
    assert find_elr_folders(month_tree, "ADI2603012", ["99_NONEXIST"]) == []


def test_range_folder_found(month_tree: Path):
    folder = month_tree / "3_MAR" / "ADI2603011-14"
    folder.mkdir()

    # Inside range
    assert find_elr_folders(month_tree, "ADI2603011", ["3_MAR"]) == [(folder, "range")]
    assert find_elr_folders(month_tree, "ADI2603012", ["3_MAR"]) == [(folder, "range")]
    assert find_elr_folders(month_tree, "ADI2603013", ["3_MAR"]) == [(folder, "range")]
    assert find_elr_folders(month_tree, "ADI2603014", ["3_MAR"]) == [(folder, "range")]

    # Outside range
    assert find_elr_folders(month_tree, "ADI2603010", ["3_MAR"]) == []
    assert find_elr_folders(month_tree, "ADI2603015", ["3_MAR"]) == []


def test_annotated_folder_flagged(month_tree: Path):
    folder = month_tree / "5_MAY" / "ADI2605073 Cancle"
    folder.mkdir()

    results = find_elr_folders(month_tree, "ADI2605073", ["5_MAY"])
    assert results == [(folder, "annotated")]


def test_slr_inside_zip(tmp_path: Path):
    elr_folder = tmp_path / "ADI2601001"
    elr_folder.mkdir()
    extract_dir = tmp_path / "extracted"

    # Make a PDF in memory / temp, pack into zip
    pdf_tmp = tmp_path / "raw" / "SLR123456.pdf"
    make_pdf(pdf_tmp, ["SPECIAL INSTRUCTIONS\nLine 1: TEST"])

    zip_path = elr_folder / "SLR123456.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(pdf_tmp, arcname="SLR123456.pdf")

    results = fingerprint_folder(elr_folder, extract_dir)
    assert len(results) == 1
    found_pdf, sha = results[0]
    assert found_pdf.name == "SLR123456.pdf"
    assert found_pdf.exists()
    assert len(sha) == 64


def test_zip_slip_rejected(tmp_path: Path):
    elr_folder = tmp_path / "ADI2601002"
    elr_folder.mkdir()
    extract_dir = tmp_path / "extracted"

    zip_path = elr_folder / "malicious.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.pdf", b"malicious content")
    zip_path.write_bytes(buf.getvalue())

    with pytest.raises(ValueError, match="(?i)zip slip|unsafe"):
        fingerprint_folder(elr_folder, extract_dir)


def test_zip_bomb_member_limit(tmp_path: Path):
    elr_folder = tmp_path / "ADI2601004"
    elr_folder.mkdir()
    extract_dir = tmp_path / "extracted"

    zip_path = elr_folder / "many_members.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(51):
            zf.writestr(f"file_{i}.txt", b"x")
    zip_path.write_bytes(buf.getvalue())

    with pytest.raises(ValueError, match="(?i)zip bomb.*member"):
        fingerprint_folder(elr_folder, extract_dir)


def test_duplicate_sha_dropped(tmp_path: Path):
    folder = tmp_path / "ADI2601003"
    folder.mkdir()
    extract_dir = tmp_path / "extracted"

    # Two files with exact same content
    p1 = folder / "doc1.pdf"
    p2 = folder / "doc2.pdf"
    make_pdf(p1, "IDENTICAL CONTENT FOR TESTING")
    p2.write_bytes(p1.read_bytes())

    results = fingerprint_folder(folder, extract_dir)
    assert len(results) == 1
    assert results[0][0] in (p1, p2)


def test_classify_abs_slr_trs(tmp_path: Path):
    # ABS document: ABS\d{6} and any page has Brand/Marking
    abs_pdf = tmp_path / "spec_abs.pdf"
    make_pdf(abs_pdf, ["ABS071457 Specification Page 1", "Page 2: Brand/Marking layout"])
    doc_type, num = classify(abs_pdf)
    assert doc_type == DocType.ABS
    assert num == "ABS071457"

    # SLR document: SPECIAL INSTRUCTIONS or Scheduled Lot ID
    slr_pdf = tmp_path / "spec_slr.pdf"
    make_pdf(slr_pdf, ["SPECIAL INSTRUCTIONS\nLine 1: TEST\nSLR246826"])
    doc_type, num = classify(slr_pdf)
    assert doc_type == DocType.SLR
    assert num == "SLR246826"

    # TRS document: Test Requirement or TRS\d+
    trs_pdf = tmp_path / "spec_trs.pdf"
    make_pdf(trs_pdf, ["Test Requirement Specification\nTRS123456"])
    doc_type, num = classify(trs_pdf)
    assert doc_type == DocType.TRS


def test_classify_abs_brand_marking_on_page_3(tmp_path: Path):
    abs_pdf = tmp_path / "spec_abs_3page.pdf"
    make_pdf(
        abs_pdf,
        [
            "ABS071457 Cover Page",
            "General Dimensions",
            "Brand / Marking Pin 1 layout",
        ],
    )
    doc_type, num = classify(abs_pdf)
    assert doc_type == DocType.ABS
    assert num == "ABS071457"


def test_classify_other_generic(tmp_path: Path):
    pdf = tmp_path / "generic.pdf"
    make_pdf(pdf, ["Hello world, no marking info"])
    doc_type, num = classify(pdf)
    assert doc_type == DocType.OTHER
    assert num is None


def test_trs_named_abs_is_trs(tmp_path: Path):
    pdf = tmp_path / "ABS999999.pdf"
    make_pdf(pdf, ["Test Requirement Specification\nDevice specs"])
    doc_type, num = classify(pdf)
    assert doc_type == DocType.TRS
    assert num == "ABS999999"


def test_ambiguous_doc_is_other(tmp_path: Path):
    # Both ABS markers (ABS\d{6} + Brand/Marking) and SLR markers (SPECIAL INSTRUCTIONS)
    pdf = tmp_path / "ambiguous.pdf"
    make_pdf(pdf, ["ABS123456 SPECIAL INSTRUCTIONS", "Brand/Marking details"])
    doc_type, num = classify(pdf)
    assert doc_type == DocType.OTHER
    assert num == "AMBIGUOUS"


def test_nested_other_elr_folder_excluded(tmp_path: Path):
    """2_FEB/ADI2602092/ADI2602095/ holds ADI2602095's ABS+SLR; they must not resolve for ADI2602092."""
    folder = tmp_path / "2_FEB" / "ADI2602092"
    nested = folder / "ADI2602095"
    sub = folder / "old"
    nested.mkdir(parents=True)
    sub.mkdir()
    (folder / "ABS066254A.pdf").write_bytes(b"%PDF-own-abs")
    (nested / "SLR231729.pdf").write_bytes(b"%PDF-other-elr-slr")
    (sub / "SLR218462.pdf").write_bytes(b"%PDF-own-sub")
    names = {p.name for p, _ in fingerprint_folder(folder, tmp_path / "x")}
    assert names == {"ABS066254A.pdf", "SLR218462.pdf"}


def test_nested_same_elr_folder_kept(tmp_path: Path):
    folder = tmp_path / "2_FEB" / "ADI2602092"
    (folder / "ADI2602092 rev2").mkdir(parents=True)
    (folder / "ADI2602092 rev2" / "SLR1.pdf").write_bytes(b"%PDF-same")
    assert [p.name for p, _ in fingerprint_folder(folder, tmp_path / "x")] == ["SLR1.pdf"]
