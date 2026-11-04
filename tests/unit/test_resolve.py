import os
from pathlib import Path
import zipfile
import pytest

from mark_engine.domain.models import DocType, ElrMeta
from mark_engine.documents.resolve import resolve_documents
from tests.fixtures.make_pdfs import make_pdf


def test_happy_path_resolved(month_tree: Path, tmp_path: Path):
    elr_folder = month_tree / "1_JAN" / "ADI2601001"
    elr_folder.mkdir(parents=True)

    abs_pdf = elr_folder / "ABS066854-ENG-1.pdf"
    make_pdf(abs_pdf, ["ABS066854 cover", "Brand/Marking diagram"])

    slr_pdf = elr_folder / "SLR232022.pdf"
    make_pdf(slr_pdf, ["SPECIAL INSTRUCTIONS\nLine 1: TEST", "Scheduled Lot ID\n7284173.1"])

    meta = ElrMeta(
        elr_no="ADI2601001",
        cust_bom_no="ABS066854",
        cust_bom_revision="ENG-1",
        cust_req_no="SLR232022",
    )

    work_dir = tmp_path / "work"
    res = resolve_documents(meta, month_tree, ["1_JAN"], work_dir)

    assert res.decision == "RESOLVED"
    assert res.hold_reason is None
    assert res.abs is not None
    assert res.abs.number == "ABS066854"
    assert res.abs.revision == "ENG-1"
    assert res.abs.doc_type == DocType.ABS
    assert len(res.slr) == 1
    assert res.slr[0].number == "SLR232022"


def test_bom_na_holds(month_tree: Path, tmp_path: Path):
    elr_folder = month_tree / "1_JAN" / "ADI2601002"
    elr_folder.mkdir(parents=True)

    abs_pdf = elr_folder / "ABS066854.pdf"
    make_pdf(abs_pdf, ["ABS066854 cover", "Brand/Marking diagram"])
    slr_pdf = elr_folder / "SLR232022.pdf"
    make_pdf(slr_pdf, ["SPECIAL INSTRUCTIONS\nLine 1: TEST"])

    meta = ElrMeta(
        elr_no="ADI2601002",
        cust_bom_no="N/A",
        cust_bom_revision=None,
    )

    work_dir = tmp_path / "work"
    res = resolve_documents(meta, month_tree, ["1_JAN"], work_dir)

    assert res.decision == "HOLD"
    assert res.hold_reason == "BOM_MISSING_IN_ORACLE"


def test_missing_slr_holds_even_without_cust_req_no(month_tree: Path, tmp_path: Path):
    elr_folder = month_tree / "1_JAN" / "ADI2601003"
    elr_folder.mkdir(parents=True)

    abs_pdf = elr_folder / "ABS066854A.pdf"
    make_pdf(abs_pdf, ["ABS066854 cover", "Brand/Marking diagram"])

    meta = ElrMeta(
        elr_no="ADI2601003",
        cust_bom_no="ABS066854",
        cust_bom_revision="A",
        cust_req_no=None,
    )

    work_dir = tmp_path / "work"
    res = resolve_documents(meta, month_tree, ["1_JAN"], work_dir)

    assert res.decision == "HOLD"
    assert res.hold_reason == "SLR_NOT_FOUND"


def test_trs_holds(month_tree: Path, tmp_path: Path):
    elr_folder = month_tree / "1_JAN" / "ADI2601004"
    elr_folder.mkdir(parents=True)

    abs_pdf = elr_folder / "ABS066854A.pdf"
    make_pdf(abs_pdf, ["ABS066854 cover", "Brand/Marking diagram"])
    slr_pdf = elr_folder / "SLR232022.pdf"
    make_pdf(slr_pdf, ["SPECIAL INSTRUCTIONS\nLine 1: TEST"])
    trs_pdf = elr_folder / "TRS999999.pdf"
    make_pdf(trs_pdf, ["Test Requirement Specification\nTRS999999"])

    meta = ElrMeta(
        elr_no="ADI2601004",
        cust_bom_no="ABS066854",
        cust_bom_revision="A",
    )

    work_dir = tmp_path / "work"
    res = resolve_documents(meta, month_tree, ["1_JAN"], work_dir)

    assert res.decision == "HOLD"
    assert res.hold_reason == "TRS_OUT_OF_SCOPE"


def test_picks_revision_matching_oracle(month_tree: Path, tmp_path: Path):
    elr_folder = month_tree / "1_JAN" / "ADI2601005"
    elr_folder.mkdir(parents=True)

    abs_a = elr_folder / "ABS066854A.pdf"
    make_pdf(abs_a, ["ABS066854 Rev A", "Brand/Marking diagram"])
    abs_b = elr_folder / "ABS066854B.pdf"
    make_pdf(abs_b, ["ABS066854 Rev B", "Brand/Marking diagram"])

    slr_pdf = elr_folder / "SLR232022.pdf"
    make_pdf(slr_pdf, ["SPECIAL INSTRUCTIONS\nLine 1: TEST"])

    meta = ElrMeta(
        elr_no="ADI2601005",
        cust_bom_no="ABS066854",
        cust_bom_revision="B",
    )

    work_dir = tmp_path / "work"
    res = resolve_documents(meta, month_tree, ["1_JAN"], work_dir)

    assert res.decision == "RESOLVED"
    assert res.abs is not None
    assert res.abs.revision == "B"
    assert Path(res.abs.path).name == "ABS066854B.pdf"
    assert any(ref.revision == "A" for ref, _ in res.rejected)


def test_revision_name_mismatch_single_abs(month_tree: Path, tmp_path: Path):
    elr_folder = month_tree / "1_JAN" / "ADI2601006"
    elr_folder.mkdir(parents=True)

    abs_a = elr_folder / "ABS066854A.pdf"
    make_pdf(abs_a, ["ABS066854 Rev A", "Brand/Marking diagram"])

    slr_pdf = elr_folder / "SLR232022.pdf"
    make_pdf(slr_pdf, ["SPECIAL INSTRUCTIONS\nLine 1: TEST"])

    meta = ElrMeta(
        elr_no="ADI2601006",
        cust_bom_no="ABS066854",
        cust_bom_revision="ENG-2",
    )

    work_dir = tmp_path / "work"
    res = resolve_documents(meta, month_tree, ["1_JAN"], work_dir)

    assert res.decision == "RESOLVED"
    assert res.abs is not None
    assert res.abs.revision == "A"
    assert "REVISION_NAME_MISMATCH" in res.steps


def test_two_abs_no_revision_match_holds(month_tree: Path, tmp_path: Path):
    elr_folder = month_tree / "1_JAN" / "ADI2601007"
    elr_folder.mkdir(parents=True)

    abs_a = elr_folder / "ABS066854A.pdf"
    make_pdf(abs_a, ["ABS066854 Rev A", "Brand/Marking diagram"])
    abs_b = elr_folder / "ABS066854B.pdf"
    make_pdf(abs_b, ["ABS066854 Rev B", "Brand/Marking diagram"])

    slr_pdf = elr_folder / "SLR232022.pdf"
    make_pdf(slr_pdf, ["SPECIAL INSTRUCTIONS\nLine 1: TEST"])

    meta = ElrMeta(
        elr_no="ADI2601007",
        cust_bom_no="ABS066854",
        cust_bom_revision="C",
    )

    work_dir = tmp_path / "work"
    res = resolve_documents(meta, month_tree, ["1_JAN"], work_dir)

    assert res.decision == "HOLD"
    assert res.hold_reason == "REVISION_UNREADABLE"


def test_slr_conflict_holds(month_tree: Path, tmp_path: Path):
    elr_folder = month_tree / "1_JAN" / "ADI2601008"
    elr_folder.mkdir(parents=True)

    abs_a = elr_folder / "ABS066854A.pdf"
    make_pdf(abs_a, ["ABS066854 Rev A", "Brand/Marking diagram"])

    slr_1 = elr_folder / "SLR232021.pdf"
    make_pdf(slr_1, ["SPECIAL INSTRUCTIONS\nLine 2: AAA\nScheduled Lot ID\n111111.1"])

    slr_2 = elr_folder / "SLR232022.pdf"
    make_pdf(slr_2, ["SPECIAL INSTRUCTIONS\nLine 2: BBB\nScheduled Lot ID\n222222.2"])

    meta = ElrMeta(
        elr_no="ADI2601008",
        cust_bom_no="ABS066854",
        cust_bom_revision="A",
        cust_req_no=None,
    )

    work_dir = tmp_path / "work"
    res = resolve_documents(meta, month_tree, ["1_JAN"], work_dir)

    assert res.decision == "HOLD"
    assert res.hold_reason == "SLR_CONFLICT"


def test_order_and_mtime_independent(tmp_path: Path):
    tree1 = tmp_path / "tree1"
    tree2 = tmp_path / "tree2"
    work1 = tmp_path / "work1"
    work2 = tmp_path / "work2"

    for tree in [tree1, tree2]:
        (tree / "1_JAN" / "ADI2601009").mkdir(parents=True)

    # In tree1, create ABS then SLR
    abs1 = tree1 / "1_JAN" / "ADI2601009" / "ABS066854A.pdf"
    make_pdf(abs1, ["ABS066854 Rev A", "Brand/Marking diagram"])
    slr1 = tree1 / "1_JAN" / "ADI2601009" / "SLR232022.pdf"
    make_pdf(slr1, ["SPECIAL INSTRUCTIONS\nLine 1: TEST"])

    # In tree2, copy identical bytes, but create in opposite order and set different mtimes
    slr2 = tree2 / "1_JAN" / "ADI2601009" / "SLR232022.pdf"
    slr2.write_bytes(slr1.read_bytes())
    abs2 = tree2 / "1_JAN" / "ADI2601009" / "ABS066854A.pdf"
    abs2.write_bytes(abs1.read_bytes())

    os.utime(slr2, (1000, 1000))
    os.utime(abs2, (5000, 5000))

    meta = ElrMeta(
        elr_no="ADI2601009",
        cust_bom_no="ABS066854",
        cust_bom_revision="A",
    )

    res1 = resolve_documents(meta, tree1, ["1_JAN"], work1)
    res2 = resolve_documents(meta, tree2, ["1_JAN"], work2)

    assert res1.decision == res2.decision == "RESOLVED"
    assert res1.hold_reason == res2.hold_reason is None
    assert res1.abs.sha256 == res2.abs.sha256
    assert [s.sha256 for s in res1.slr] == [s.sha256 for s in res2.slr]
    assert res1.steps == res2.steps


def test_same_rev_different_content_holds(month_tree: Path, tmp_path: Path):
    elr_folder = month_tree / "1_JAN" / "ADI2601010"
    elr_folder.mkdir(parents=True)

    abs1 = elr_folder / "ABS066854A.pdf"
    make_pdf(abs1, ["ABS066854 Rev A Version 1", "Brand/Marking diagram"])

    sub = elr_folder / "archive"
    sub.mkdir()
    abs2 = sub / "ABS066854A.pdf"
    make_pdf(abs2, ["ABS066854 Rev A Version 2", "Brand/Marking diagram"])

    slr_pdf = elr_folder / "SLR232022.pdf"
    make_pdf(slr_pdf, ["SPECIAL INSTRUCTIONS\nLine 1: TEST"])

    meta = ElrMeta(
        elr_no="ADI2601010",
        cust_bom_no="ABS066854",
        cust_bom_revision="A",
    )

    work_dir = tmp_path / "work"
    res = resolve_documents(meta, month_tree, ["1_JAN"], work_dir)

    assert res.decision == "HOLD"
    assert res.hold_reason == "SAME_REV_DIFFERENT_CONTENT"


def test_bom_not_found_holds(month_tree: Path, tmp_path: Path):
    elr_folder = month_tree / "1_JAN" / "ADI2601011"
    elr_folder.mkdir(parents=True)

    abs_pdf = elr_folder / "ABS066854A.pdf"
    make_pdf(abs_pdf, ["ABS066854 Rev A", "Brand/Marking diagram"])

    slr_pdf = elr_folder / "SLR232022.pdf"
    make_pdf(slr_pdf, ["SPECIAL INSTRUCTIONS\nLine 1: TEST"])

    meta = ElrMeta(
        elr_no="ADI2601011",
        cust_bom_no="ABS099999",
        cust_bom_revision="A",
    )

    work_dir = tmp_path / "work"
    res = resolve_documents(meta, month_tree, ["1_JAN"], work_dir)

    assert res.decision == "HOLD"
    assert res.hold_reason == "BOM_NOT_FOUND"


def test_no_folder_holds(month_tree: Path, tmp_path: Path):
    meta = ElrMeta(
        elr_no="ADI2601999",
        cust_bom_no="ABS066854",
        cust_bom_revision="A",
    )

    work_dir = tmp_path / "work"
    res = resolve_documents(meta, month_tree, ["1_JAN"], work_dir)

    assert res.decision == "HOLD"
    assert res.hold_reason == "NO_FOLDER"


def test_archive_error_holds(month_tree: Path, tmp_path: Path):
    elr_folder = month_tree / "1_JAN" / "ADI2601012"
    elr_folder.mkdir(parents=True)

    # Malicious zip with path traversal
    zip_path = elr_folder / "corrupt.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../evil.pdf", b"bad content")

    meta = ElrMeta(
        elr_no="ADI2601012",
        cust_bom_no="ABS066854",
        cust_bom_revision="A",
    )

    work_dir = tmp_path / "work"
    res = resolve_documents(meta, month_tree, ["1_JAN"], work_dir)

    assert res.decision == "HOLD"
    assert res.hold_reason == "ARCHIVE_ERROR"


def test_doc_type_ambiguous_holds(month_tree: Path, tmp_path: Path):
    elr_folder = month_tree / "1_JAN" / "ADI2601013"
    elr_folder.mkdir(parents=True)

    ambiguous_pdf = elr_folder / "ambiguous.pdf"
    make_pdf(ambiguous_pdf, ["ABS066854 SPECIAL INSTRUCTIONS", "Brand/Marking diagram"])

    meta = ElrMeta(
        elr_no="ADI2601013",
        cust_bom_no="ABS066854",
        cust_bom_revision="A",
    )

    work_dir = tmp_path / "work"
    res = resolve_documents(meta, month_tree, ["1_JAN"], work_dir)

    assert res.decision == "HOLD"
    assert res.hold_reason == "DOC_TYPE_AMBIGUOUS"


def test_slr_merged_identical(month_tree: Path, tmp_path: Path):
    elr_folder = month_tree / "1_JAN" / "ADI2601014"
    elr_folder.mkdir(parents=True)

    abs_a = elr_folder / "ABS066854A.pdf"
    make_pdf(abs_a, ["ABS066854 Rev A", "Brand/Marking diagram"])

    slr_1 = elr_folder / "SLR232021.pdf"
    make_pdf(slr_1, ["SPECIAL INSTRUCTIONS\nLine 2: AAA\nScheduled Lot ID\n111111.1"])

    slr_2 = elr_folder / "SLR232022.pdf"
    make_pdf(slr_2, ["SPECIAL INSTRUCTIONS\nLine 2: AAA\nScheduled Lot ID\n111111.1"])

    meta = ElrMeta(
        elr_no="ADI2601014",
        cust_bom_no="ABS066854",
        cust_bom_revision="A",
        cust_req_no=None,
    )

    work_dir = tmp_path / "work"
    res = resolve_documents(meta, month_tree, ["1_JAN"], work_dir)

    assert res.decision == "RESOLVED"
    assert len(res.slr) == 2
    assert "MERGED_IDENTICAL" in res.steps


def _rev_conflict_folder(month_tree: Path, elr: str) -> None:
    f = month_tree / "6_JUN" / elr
    f.mkdir(parents=True)
    make_pdf(f / "ABS068387B.pdf", ["ABS068387 Rev B", "Brand/Marking diagram"])
    make_pdf(f / "ABS068387C.pdf", ["ABS068387 Rev C", "Brand/Marking diagram"])
    make_pdf(f / "SLR240001.pdf", ["SPECIAL INSTRUCTIONS\nLine 1: TEST"])


def test_product_no_revision_conflict_holds(month_tree: Path, tmp_path: Path):
    """Mark Eng 2026-11-04 (09 Q2, ADI2606077/078): CUST_BOM_REVISION B but PRODUCT_NO says rev C
    -> do not guess, HOLD for review and say why."""
    _rev_conflict_folder(month_tree, "ADI2606077")
    meta = ElrMeta(elr_no="ADI2606077", cust_bom_no="ABS068387", cust_bom_revision="B",
                   product_no="ADMFS7201-ABS068387C-A")
    res = resolve_documents(meta, month_tree, ["6_JUN"], tmp_path / "work")
    assert res.decision == "HOLD"
    assert res.hold_reason == "REVISION_CONFLICT"
    assert res.hold_detail == "CUST_BOM_REVISION=B but PRODUCT_NO ADMFS7201-ABS068387C-A has rev C"


def test_product_no_same_revision_resolves(month_tree: Path, tmp_path: Path):
    _rev_conflict_folder(month_tree, "ADI2606035")
    meta = ElrMeta(elr_no="ADI2606035", cust_bom_no="ABS068387", cust_bom_revision="B",
                   product_no="ADMFS7201-ABS068387B-A")
    res = resolve_documents(meta, month_tree, ["6_JUN"], tmp_path / "work")
    assert res.decision == "RESOLVED" and res.abs.revision == "B"


def test_product_no_eng_revision_is_not_a_conflict(month_tree: Path, tmp_path: Path):
    """ADI2601052: CUST_BOM_REVISION 'ENG-1' vs PRODUCT_NO '...ABS065954B-ENG-1-A' is a format difference."""
    f = month_tree / "1_JAN" / "ADI2601052"
    f.mkdir(parents=True)
    make_pdf(f / "ABS065954-ENG-1.pdf", ["ABS065954 Rev ENG-1", "Brand/Marking diagram"])
    make_pdf(f / "SLR240002.pdf", ["SPECIAL INSTRUCTIONS\nLine 1: TEST"])
    meta = ElrMeta(elr_no="ADI2601052", cust_bom_no="ABS065954", cust_bom_revision="ENG-1",
                   product_no="ADUM7250-ABS065954B-ENG-1-A")
    res = resolve_documents(meta, month_tree, ["1_JAN"], tmp_path / "work")
    assert res.hold_reason != "REVISION_CONFLICT"


def test_bom_letter_plus_eng_revision_matches_file(month_tree: Path, tmp_path: Path):
    """Oracle splits the revision: CUST_BOM_NO ABS034529D + CUST_BOM_REVISION ENG-1 = file rev D-ENG-1
    (user 2026-11-04, ADI2602100) -> same revision, no REVISION_NAME_MISMATCH."""
    f = month_tree / "2_FEB" / "ADI2602100"
    f.mkdir(parents=True)
    make_pdf(f / "ABS034529D-ENG-1.pdf", ["ABS034529 Rev D-ENG-1", "Brand/Marking diagram"])
    make_pdf(f / "SLR240003.pdf", ["SPECIAL INSTRUCTIONS\nLine 1: TEST"])
    meta = ElrMeta(elr_no="ADI2602100", cust_bom_no="ABS034529D", cust_bom_revision="ENG-1",
                   product_no="LT3012ECPC-AQZ")
    res = resolve_documents(meta, month_tree, ["2_FEB"], tmp_path / "work")
    assert res.decision == "RESOLVED"
    assert "REVISION_NAME_MISMATCH" not in res.steps


def test_bom_letter_plus_eng_picks_matching_file(month_tree: Path, tmp_path: Path):
    f = month_tree / "1_JAN" / "ADI2601052"
    f.mkdir(parents=True)
    make_pdf(f / "ABS065954B-ENG-1.pdf", ["ABS065954 Rev B-ENG-1", "Brand/Marking diagram"])
    make_pdf(f / "ABS065954E-ENG-1.pdf", ["ABS065954 Rev E-ENG-1", "Brand/Marking diagram"])
    make_pdf(f / "SLR240004.pdf", ["SPECIAL INSTRUCTIONS\nLine 1: TEST"])
    meta = ElrMeta(elr_no="ADI2601052", cust_bom_no="ABS065954B", cust_bom_revision="ENG-1")
    res = resolve_documents(meta, month_tree, ["1_JAN"], tmp_path / "work")
    assert res.decision == "RESOLVED" and Path(res.abs.path).name == "ABS065954B-ENG-1.pdf"


def test_oracle_revision_letter_e_with_eng():
    """BOM letter 'E' + 'ENG-1' must give 'E-ENG-1' (ADI2606066), not stay 'ENG-1'."""
    from mark_engine.documents.resolve import _oracle_revision
    assert _oracle_revision("ABS065954E", "ENG-1") == "E-ENG-1"
    assert _oracle_revision("ABS065954E", "E-ENG-1") == "E-ENG-1"
    assert _oracle_revision("ABS065744", "B") == "B"
    assert _oracle_revision("ABS034529D", "ENG-1") == "D-ENG-1"


def test_revision_mismatch_gives_user_reason(month_tree: Path, tmp_path: Path):
    """D-25: Oracle rev B but only rev C in the folder (ABS065744) -> review with the cause."""
    f = month_tree / "3_MAR" / "ADI2603024"
    f.mkdir(parents=True)
    make_pdf(f / "ABS065744C.pdf", ["ABS065744 Rev C", "Brand/Marking diagram"])
    make_pdf(f / "SLR240005.pdf", ["SPECIAL INSTRUCTIONS\nLine 1: TEST"])
    meta = ElrMeta(elr_no="ADI2603024", cust_bom_no="ABS065744", cust_bom_revision="B")
    res = resolve_documents(meta, month_tree, ["3_MAR"], tmp_path / "work")
    assert res.decision == "RESOLVED"
    assert res.review_detail == "REVISION_MISMATCH: Oracle ABS065744 rev B but folder has only ABS065744C (rev C)"


def test_product_no_other_abs_gives_user_reason(month_tree: Path, tmp_path: Path):
    f = month_tree / "6_JUN" / "ADI2606076"
    f.mkdir(parents=True)
    make_pdf(f / "ABS068387B.pdf", ["ABS068387 Rev B", "Brand/Marking diagram"])
    make_pdf(f / "SLR240006.pdf", ["SPECIAL INSTRUCTIONS\nLine 1: TEST"])
    meta = ElrMeta(elr_no="ADI2606076", cust_bom_no="ABS068387", cust_bom_revision="B",
                   product_no="ADMFS7201-ABS071101-ENG-2-A")
    res = resolve_documents(meta, month_tree, ["6_JUN"], tmp_path / "work")
    assert "PRODUCT_NO_ABS_MISMATCH" in res.steps
    assert res.review_detail.startswith("PRODUCT_NO_ABS_MISMATCH: PRODUCT_NO ADMFS7201-ABS071101-ENG-2-A names ABS071101")
