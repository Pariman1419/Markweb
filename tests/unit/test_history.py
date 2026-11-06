import pytest
from pathlib import Path, PureWindowsPath, PurePosixPath
from mark_engine.domain.models import DocType, DocumentRef, DocumentResolution, JobResult, ProcessingStatus, ExpectedMark, ExpectedLine, LineComparison, LineStatus, Side
from mark_engine.history.fingerprint import (
    ORACLE_FP_FIELDS,
    oracle_fp,
    docs_fp,
    version_fp,
    result_fp,
    changed_oracle_fields,
)
from mark_engine.history.decide import Decision, RevisionKey, decide


def test_oracle_fp_ignores_field_order_and_trailing_spaces():
    row1 = {
        "PRODUCT_NO": "AD12345 ",
        "CUST_ASSY_LOT": "LOT999",
        "TOP_MARK1": "LINE1  ",
        "STATUS": "A",
    }
    row2 = {
        "STATUS": "A",
        "TOP_MARK1": "LINE1",
        "CUST_ASSY_LOT": "LOT999 ",
        "PRODUCT_NO": "AD12345",
    }
    assert oracle_fp(row1) == oracle_fp(row2)
    assert len(oracle_fp(row1)) == 64


@pytest.mark.parametrize("field", ORACLE_FP_FIELDS)
def test_oracle_fp_changes_on_each_field(field):
    base_row = {f: f"val_{f}" for f in ORACLE_FP_FIELDS}
    modified_row = dict(base_row)
    modified_row[field] = f"changed_{field}"
    assert oracle_fp(base_row) != oracle_fp(modified_row)


def test_docs_fp_changes_with_revision_file():
    ref_abs_v1 = DocumentRef(path="abs_rev1.pdf", sha256="hash_abs_1", doc_type=DocType.ABS)
    ref_abs_v2 = DocumentRef(path="abs_rev2.pdf", sha256="hash_abs_2", doc_type=DocType.ABS)
    ref_slr = DocumentRef(path="slr.pdf", sha256="hash_slr_1", doc_type=DocType.SLR)

    res_none = docs_fp(None)
    assert len(res_none) == 64

    res1 = docs_fp(DocumentResolution(elr_no="ELR001", decision="RESOLVED", abs=ref_abs_v1, slr=(ref_slr,)))
    res2 = docs_fp(DocumentResolution(elr_no="ELR001", decision="RESOLVED", abs=ref_abs_v2, slr=(ref_slr,)))
    assert res1 != res2
    assert res1 != res_none

    # Order of SLR documents does not alter fp (order invariance)
    ref_slr2 = DocumentRef(path="slr2.pdf", sha256="hash_slr_2", doc_type=DocType.SLR)
    res_multi_a = docs_fp(DocumentResolution(elr_no="ELR001", decision="RESOLVED", abs=ref_abs_v1, slr=(ref_slr, ref_slr2)))
    res_multi_b = docs_fp(DocumentResolution(elr_no="ELR001", decision="RESOLVED", abs=ref_abs_v1, slr=(ref_slr2, ref_slr)))
    assert res_multi_a == res_multi_b


def test_docs_fp_same_for_unc_and_posix_mount():
    """Task 2 Step 1: UNC and Posix mount paths produce identical docs_fp when roots are provided."""
    work_dir_a = PureWindowsPath(r"C:\work\ADI2607006")
    roots_a = (PureWindowsPath(r"\\th1srnas03\ELR\ADI"), work_dir_a)
    ref_abs_a = DocumentRef(
        path=r"\\th1srnas03\ELR\ADI\ELR Online 2026\7_JUL\ADI2607006\ABS047695C.pdf",
        sha256="sha_abs_common",
        doc_type=DocType.ABS,
    )
    res_a = DocumentResolution(elr_no="ADI2607006", decision="RESOLVED", abs=ref_abs_a, slr=())

    work_dir_b = PurePosixPath("/tmp/work/ADI2607006")
    roots_b = (PurePosixPath("/mnt/elr/ADI"), work_dir_b)
    ref_abs_b = DocumentRef(
        path="/mnt/elr/ADI/ELR Online 2026/7_JUL/ADI2607006/ABS047695C.pdf",
        sha256="sha_abs_common",
        doc_type=DocType.ABS,
    )
    res_b = DocumentResolution(elr_no="ADI2607006", decision="RESOLVED", abs=ref_abs_b, slr=())

    fp_a = docs_fp(res_a, roots=roots_a)
    fp_b = docs_fp(res_b, roots=roots_b)
    assert fp_a == fp_b


def test_docs_fp_extracted_slr_relative_to_work_dir():
    """Task 2 Step 1: Extracted SLR paths relative to different work_dirs produce identical docs_fp."""
    work_dir_a = PureWindowsPath(r"C:\work\ADI2607006")
    roots_a = (PureWindowsPath(r"\\th1srnas03\ELR\ADI"), work_dir_a)
    ref_slr_a = DocumentRef(
        path=r"C:\work\ADI2607006\extracted\abc123sha\SLR245168.pdf",
        sha256="sha_slr_common",
        doc_type=DocType.SLR,
    )
    res_a = DocumentResolution(elr_no="ADI2607006", decision="RESOLVED", abs=None, slr=(ref_slr_a,))

    work_dir_b = PurePosixPath("/app/work/ADI2607006")
    roots_b = (PurePosixPath("/mnt/elr/ADI"), work_dir_b)
    ref_slr_b = DocumentRef(
        path="/app/work/ADI2607006/extracted/abc123sha/SLR245168.pdf",
        sha256="sha_slr_common",
        doc_type=DocType.SLR,
    )
    res_b = DocumentResolution(elr_no="ADI2607006", decision="RESOLVED", abs=None, slr=(ref_slr_b,))

    fp_a = docs_fp(res_a, roots=roots_a)
    fp_b = docs_fp(res_b, roots=roots_b)
    assert fp_a == fp_b


def test_docs_fp_without_roots_unchanged():
    """Task 2 Step 1: docs_fp without roots matches the exact existing implementation hex."""
    ref_abs = DocumentRef(path="abs.pdf", sha256="hash_abs", doc_type=DocType.ABS)
    ref_slr = DocumentRef(path="slr.pdf", sha256="hash_slr", doc_type=DocType.SLR)
    res = DocumentResolution(elr_no="ELR001", decision="RESOLVED", abs=ref_abs, slr=(ref_slr,))
    expected_hex = "9a47bd32ffad40321e5f17f73932a2dfa9ce0cc30510d78a6564bd3739e3cb68"
    assert docs_fp(res) == expected_hex
    assert docs_fp(res, roots=()) == expected_hex


def test_version_fp():
    v1 = version_fp("0.1.0", "exp09")
    v2 = version_fp("0.1.1", "exp09")
    v3 = version_fp("0.1.0", "trocr-exp08a")
    assert len(v1) == 64
    assert v1 != v2
    assert v1 != v3


def test_result_fp():
    job1 = JobResult(
        elr_no="ELR001",
        processing_status=ProcessingStatus.DONE,
        expected=ExpectedMark(
            elr_no="ELR001",
            lines=(ExpectedLine(side=Side.TOP, line_no=1, text="AD999"),),
            rule_version="R0",
            engine_version="0.1.0",
        ),
        comparisons=(
            LineComparison(side=Side.TOP, line_no=1, expected="AD999", oracle="AD999", status=LineStatus.MATCH),
        )
    )
    job2 = JobResult(
        elr_no="ELR001",
        processing_status=ProcessingStatus.DONE,
        expected=ExpectedMark(
            elr_no="ELR001",
            lines=(ExpectedLine(side=Side.TOP, line_no=1, text="AD999"),),
            rule_version="R0",
            engine_version="0.1.0",
        ),
        comparisons=(
            LineComparison(side=Side.TOP, line_no=1, expected="AD999", oracle="AD999-DIFF", status=LineStatus.DIFF),
        )
    )
    assert result_fp(job1) != result_fp(job2)


@pytest.mark.parametrize(
    "pending_reason,prev,oracle,docs,manual,expected_action,expected_changed,expected_same_as",
    [
        # 1. Manual trigger overrides anything
        (None, [RevisionKey(1, "o1", "d1")], "o1", "d1", True, "check", "manual", None),
        ("STEP_NOT_READY", [], "o1", "d1", True, "check", "manual", None),
        # 2. Not eligible / pending reason
        ("CUST_REQ_EMPTY", [], "o1", "d1", False, "skip_not_eligible", None, None),
        # 3. New ELR (no previous revisions)
        (None, [], "o1", "d1", False, "check", "new", None),
        # 4. Unchanged vs latest revision (exact match)
        (None, [RevisionKey(1, "o1", "d1")], "o1", "d1", False, "skip_unchanged", None, None),
        # 4b. Unchanged with cheap-first probe (docs_fp not probed, oracle matches latest)
        (None, [RevisionKey(1, "o1", "d1")], "o1", None, False, "skip_unchanged", None, None),
        # 5. Same as older revision (e.g. data reverted to rev 1 when current is rev 2)
        (None, [RevisionKey(1, "o1", "d1"), RevisionKey(2, "o2", "d2")], "o1", "d1", False, "skip_same_as_rev", None, 1),
        # 6. Changed oracle only
        (None, [RevisionKey(1, "o1", "d1")], "o2", "d1", False, "check", "oracle", None),
        # 7. Changed docs only
        (None, [RevisionKey(1, "o1", "d1")], "o1", "d2", False, "check", "docs", None),
        # 8. Changed both oracle and docs
        (None, [RevisionKey(1, "o1", "d1")], "o2", "d2", False, "check", "both", None),
    ],
)
def test_decide_table(pending_reason, prev, oracle, docs, manual, expected_action, expected_changed, expected_same_as):
    dec = decide(pending_reason=pending_reason, prev=prev, oracle_fp=oracle, docs_fp=docs, manual=manual)
    assert dec.action == expected_action
    assert dec.changed == expected_changed
    assert dec.same_as_rev == expected_same_as


def test_changed_oracle_fields_names_only():
    old = {"PRODUCT_NO": "AD123", "TOP_MARK1": "ABC", "STATUS": "A"}
    new = {"PRODUCT_NO": "AD123", "TOP_MARK1": "DEF", "STATUS": "C"}
    diff = changed_oracle_fields(old, new)
    assert diff == ["TOP_MARK1", "STATUS"]
