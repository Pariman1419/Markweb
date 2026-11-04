from mark_engine.domain.models import (
    ApprovalStatus,
    ElrMeta,
    ExpectedLine,
    ExpectedMark,
    JobResult,
    LineComparison,
    LineStatus,
    OracleMark,
    ProcessingStatus,
    Side,
    VerificationStatus,
)
from mark_engine.regression.metrics import compute, compute_independence


def test_metrics_counts():
    # Job 1: auto, 2 lines (1 MATCH, 1 DIFF)
    j1 = JobResult(
        elr_no="ADI2605001",
        processing_status=ProcessingStatus.DONE,
        verification_status=VerificationStatus.HAS_DIFF,
        approval_status=ApprovalStatus.NOT_REVIEWED,
        layout_source="auto",
        expected=ExpectedMark(
            elr_no="ADI2605001",
            lines=(
                ExpectedLine(Side.TOP, 1, "ABC"),
                ExpectedLine(Side.TOP, 2, "XYZ"),
            ),
            rule_version="1.0.0",
            engine_version="1.0.0",
        ),
        comparisons=(
            LineComparison(Side.TOP, 1, "ABC", "ABC", LineStatus.MATCH, (), ""),
            LineComparison(Side.TOP, 2, "XYZ", "XYW", LineStatus.DIFF, (), ""),
        ),
    )

    # Job 2: human_crop, 1 line (1 MATCH_LOT)
    j2 = JobResult(
        elr_no="ADI2601001",
        processing_status=ProcessingStatus.DONE,
        verification_status=VerificationStatus.MATCH_ALL,
        approval_status=ApprovalStatus.NOT_REVIEWED,
        layout_source="human_crop",
        expected=ExpectedMark(
            elr_no="ADI2601001",
            lines=(ExpectedLine(Side.TOP, 1, "LOT1"),),
            rule_version="1.0.0",
            engine_version="1.0.0",
        ),
        comparisons=(
            LineComparison(Side.TOP, 1, "LOT1", "LOT1", LineStatus.MATCH_LOT, (), ""),
        ),
    )

    # Job 3: HOLD, auto cohort (ADI2605 prefix), 1 line NOT_MEASURABLE
    j3 = JobResult(
        elr_no="ADI2605002",
        processing_status=ProcessingStatus.HOLD,
        hold_reason="SLR_NOT_FOUND",
        verification_status=None,
        approval_status=ApprovalStatus.NOT_REVIEWED,
        layout_source="none",
        expected=None,
        comparisons=(
            LineComparison(Side.TOP, 1, None, "ABC", LineStatus.NOT_MEASURABLE, (), "SLR_NOT_FOUND"),
        ),
    )

    jobs = [j1, j2, j3]

    oracle_snapshot = {
        "ADI2605001": (
            ElrMeta(elr_no="ADI2605001"),
            OracleMark("ADI2605001", ((Side.TOP, 1, "ABC"), (Side.TOP, 2, "XYW"))),
        ),
        "ADI2601001": (
            ElrMeta(elr_no="ADI2601001"),
            OracleMark("ADI2601001", ((Side.TOP, 1, "LOT1"),)),
        ),
        "ADI2605002": (
            ElrMeta(elr_no="ADI2605002"),
            OracleMark("ADI2605002", ((Side.TOP, 1, "ABC"),)),
        ),
        "ADI2601002": (
            ElrMeta(elr_no="ADI2601002"),
            OracleMark("ADI2601002", ((Side.TOP, 1, "EXTRA"),)),
        ),
    }

    prefixes = ["ADI2601", "ADI2605"]
    m = compute(jobs, oracle_snapshot, prefixes)

    # Denominator: 4 ELRs in snapshot with prefixes
    # Numerator: jobs 1 and 2 (DONE with compared status lines) -> 2
    assert m["coverage_elr"] == 2 / 4
    assert m["coverage_elr_num"] == 2
    assert m["coverage_elr_denom"] == 4

    # Coverage line: compared lines (3: MATCH, DIFF, MATCH_LOT) / total non-empty oracle lines (4)
    assert m["coverage_line"] == 3 / 4
    assert m["coverage_line_num"] == 3
    assert m["coverage_line_denom"] == 4

    # Hold rate: 1 HOLD out of 3 total jobs
    assert m["hold_rate"] == 1 / 3

    # Oracle agreement: total MATCH* (MATCH + MATCH_LOT = 2) / compared lines (3)
    assert abs(m["oracle_agreement"] - (2 / 3)) < 1e-6

    # Status counts
    assert m["MATCH"] == 1
    assert m["DIFF"] == 1
    assert m["MATCH_LOT"] == 1
    assert m["NOT_MEASURABLE"] == 1
    assert m["needs_review_lines"] == 0

    # Independence
    assert m["independence"] == 1.0

    # Layout source split
    assert "auto" in m["by_layout_source"]
    assert "human_crop" in m["by_layout_source"]

    auto_m = m["by_layout_source"]["auto"]
    # 2 in-scope ELRs in snapshot for auto (ADI2605001, ADI2605002)
    assert auto_m["coverage_elr_denom"] == 2
    assert auto_m["coverage_elr_num"] == 1  # j1
    assert auto_m["hold_rate"] == 1 / 2  # j3 is hold out of [j1, j3]


def test_independence_detects_leak():
    j1 = JobResult(
        elr_no="ADI2605001",
        processing_status=ProcessingStatus.DONE,
        expected=ExpectedMark(
            elr_no="ADI2605001",
            lines=(ExpectedLine(Side.TOP, 1, "ABC"),),
            rule_version="1.0.0",
            engine_version="1.0.0",
        ),
    )

    # Blank job produces different expected text because generator leaked oracle
    j1_blank = JobResult(
        elr_no="ADI2605001",
        processing_status=ProcessingStatus.DONE,
        expected=ExpectedMark(
            elr_no="ADI2605001",
            lines=(ExpectedLine(Side.TOP, 1, "DIFFERENT"),),
            rule_version="1.0.0",
            engine_version="1.0.0",
        ),
    )

    score_leak = compute_independence([j1], blank_jobs=[j1_blank])
    assert score_leak == 0.0

    # Identity check gives 1.0
    score_clean = compute_independence([j1], blank_jobs=[j1])
    assert score_clean == 1.0
