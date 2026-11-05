import pytest
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
