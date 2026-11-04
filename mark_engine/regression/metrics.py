from __future__ import annotations

from typing import Sequence

from mark_engine.domain.models import (
    ElrMeta,
    JobResult,
    LineStatus,
    OracleMark,
    ProcessingStatus,
)

COMPARED_STATUSES = frozenset({
    LineStatus.MATCH,
    LineStatus.MATCH_SLR,
    LineStatus.MATCH_SHIFT,
    LineStatus.MATCH_LOT,
    LineStatus.DIFF,
    LineStatus.NEEDS_REVIEW,
})

MATCH_ALL_STATUSES = frozenset({
    LineStatus.MATCH,
    LineStatus.MATCH_SLR,
    LineStatus.MATCH_SHIFT,
    LineStatus.MATCH_LOT,
})

ALL_STATUSES = (
    LineStatus.MATCH,
    LineStatus.MATCH_SLR,
    LineStatus.MATCH_SHIFT,
    LineStatus.MATCH_LOT,
    LineStatus.DIFF,
    LineStatus.NEEDS_REVIEW,
    LineStatus.DB_EMPTY,
    LineStatus.NOT_MARKED,
    LineStatus.NOT_COMPARABLE,
    LineStatus.NOT_MEASURABLE,
    LineStatus.NOT_ELIGIBLE,
)

AUTO_PREFIXES = ("ADI2605", "ADI2606")
HUMAN_CROP_PREFIXES = ("ADI2601", "ADI2602", "ADI2603", "ADI2604")


def get_layout_source(job: JobResult) -> str:
    """Returns the layout source cohort ('auto' or 'human_crop') for a job."""
    if job.layout_source in ("auto", "human_crop"):
        return job.layout_source
    if any(job.elr_no.startswith(p) for p in AUTO_PREFIXES):
        return "auto"
    return "human_crop"


def compute_independence(
    jobs: Sequence[JobResult],
    blank_jobs: Sequence[JobResult] | None = None,
) -> float | None:
    """Fraction of jobs whose ExpectedMark is identical when re-run with a blank OracleMark.

    Returns None when no blank re-run was supplied (independence not measured) — never a
    default 1.0, so a missing check cannot pass the D-03 gate.
    Jobs are paired by elr_no; a job without a blank counterpart counts as not independent.
    """
    if blank_jobs is None:
        return None
    if not jobs:
        return 1.0
    blank_by_elr = {b.elr_no: b for b in blank_jobs}
    match_count = 0
    for j in jobs:
        b = blank_by_elr.get(j.elr_no)
        if b is not None and j.expected == b.expected:
            match_count += 1
    return match_count / len(jobs)


def _compute_subset(
    jobs: Sequence[JobResult],
    in_scope_elrs: set[str],
    blank_jobs: Sequence[JobResult] | None = None,
) -> dict:
    total_jobs = len(jobs)
    coverage_elr_denom = len(in_scope_elrs)

    # Numerator for coverage_elr: DONE and has at least one line with a compared status
    coverage_elr_num = 0
    hold_count = 0

    status_counts: dict[str, int] = {s.value: 0 for s in ALL_STATUSES}
    compared_lines = 0
    match_lines = 0
    total_oracle_lines = 0

    for job in jobs:
        if job.processing_status == ProcessingStatus.HOLD:
            hold_count += 1

        has_compared_line = False
        for c in job.comparisons:
            # Count status
            c_status = c.status
            if c_status in status_counts:
                status_counts[c_status.value] += 1
            elif hasattr(c_status, "value") and c_status.value in status_counts:
                status_counts[c_status.value] += 1
            elif str(c_status) in status_counts:
                status_counts[str(c_status)] += 1

            if c.oracle is not None and str(c.oracle).strip() != "":
                total_oracle_lines += 1

            if c_status in COMPARED_STATUSES or (hasattr(c_status, "name") and c_status in COMPARED_STATUSES):
                compared_lines += 1
                has_compared_line = True
                if c_status in MATCH_ALL_STATUSES or (hasattr(c_status, "name") and c_status in MATCH_ALL_STATUSES):
                    match_lines += 1

        if job.processing_status == ProcessingStatus.DONE and has_compared_line:
            coverage_elr_num += 1

    coverage_elr = (coverage_elr_num / coverage_elr_denom) if coverage_elr_denom > 0 else 0.0
    coverage_line = (compared_lines / total_oracle_lines) if total_oracle_lines > 0 else 0.0
    hold_rate = (hold_count / total_jobs) if total_jobs > 0 else 0.0
    oracle_agreement = (match_lines / compared_lines) if compared_lines > 0 else 0.0

    ind = compute_independence(jobs, blank_jobs=blank_jobs)

    result = {
        "coverage_elr": coverage_elr,
        "coverage_elr_num": coverage_elr_num,
        "coverage_elr_denom": coverage_elr_denom,
        "coverage_line": coverage_line,
        "coverage_line_num": compared_lines,
        "coverage_line_denom": total_oracle_lines,
        "hold_rate": hold_rate,
        "hold_count": hold_count,
        "total_jobs": total_jobs,
        "oracle_agreement": oracle_agreement,
        "oracle_agreement_num": match_lines,
        "oracle_agreement_denom": compared_lines,
        "needs_review_lines": status_counts.get(LineStatus.NEEDS_REVIEW.value, 0),
        "independence": ind,
        "status_counts": status_counts,
    }
    # Also expose status counts at top level for convenience
    for k, v in status_counts.items():
        result[k] = v

    return result


def compute(
    jobs: Sequence[JobResult],
    oracle_snapshot: dict[str, tuple[ElrMeta, OracleMark]] | None = None,
    elr_prefixes: Sequence[str] | None = None,
    *,
    blank_jobs: Sequence[JobResult] | None = None,
) -> dict:
    """Computes all regression metrics across jobs and split by layout_source."""
    prefixes = tuple(elr_prefixes) if elr_prefixes else ()

    if oracle_snapshot is not None:
        if prefixes:
            in_scope_elrs = {elr for elr in oracle_snapshot.keys() if any(elr.startswith(p) for p in prefixes)}
        else:
            in_scope_elrs = set(oracle_snapshot.keys())
    else:
        if prefixes:
            in_scope_elrs = {j.elr_no for j in jobs if any(j.elr_no.startswith(p) for p in prefixes)}
        else:
            in_scope_elrs = {j.elr_no for j in jobs}

    overall = _compute_subset(jobs, in_scope_elrs, blank_jobs=blank_jobs)

    # Split by layout_source
    auto_jobs: list[JobResult] = []
    human_crop_jobs: list[JobResult] = []

    for j in jobs:
        source = get_layout_source(j)
        if source == "auto":
            auto_jobs.append(j)
        else:
            human_crop_jobs.append(j)

    auto_in_scope = {e for e in in_scope_elrs if any(e.startswith(p) for p in AUTO_PREFIXES)}
    human_in_scope = {e for e in in_scope_elrs if not any(e.startswith(p) for p in AUTO_PREFIXES)}

    overall["by_layout_source"] = {
        "auto": _compute_subset(auto_jobs, auto_in_scope),
        "human_crop": _compute_subset(human_crop_jobs, human_in_scope),
    }

    return overall
