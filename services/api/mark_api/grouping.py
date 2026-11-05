"""Grouping and aggregation for lines and jobs."""
from collections import Counter, defaultdict
from typing import Any, Literal


def classify_line(status: str, warning: str = "") -> Literal["TRUE", "WARNING", "ERROR", "NONE"]:
    status = (status or "").strip()
    warning = (warning or "").strip()

    if status in ("MATCH", "MATCH_SLR", "MATCH_LOT"):
        return "WARNING" if warning else "TRUE"
    if status in ("MATCH_SHIFT", "NEEDS_REVIEW"):
        return "WARNING"
    if status in ("DIFF", "DB_EMPTY", "NOT_MARKED"):
        return "ERROR"
    return "NONE"


def classify_job(processing_status: str) -> Literal["HOLD", "FAILED", "DONE"]:
    ps = (processing_status or "").strip().upper()
    if ps == "HOLD":
        return "HOLD"
    if ps == "FAILED":
        return "FAILED"
    return "DONE"


def _elr_to_month(elr: str) -> str:
    if len(elr) >= 7 and elr.startswith("ADI"):
        yy = elr[3:5]
        mm = elr[5:7]
        return f"20{yy}-{mm}"
    return "UNKNOWN"


def summarize(lines: list[dict[str, Any]], jobs: list[dict[str, Any]]) -> dict[str, Any]:
    # 1. Cards
    true_count = 0
    warning_count = 0
    error_count = 0
    hold_count = 0

    error_causes_counter: Counter[str] = Counter()
    hold_causes_counter: Counter[str] = Counter()
    warning_causes_counter: Counter[str] = Counter()

    monthly_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"TRUE": 0, "WARNING": 0, "ERROR": 0})

    for line in lines:
        status = line.get("status") or line.get("final_status") or ""
        warning = line.get("warning") or ""
        grp = classify_line(status, warning)
        month = _elr_to_month(line.get("elr_no", ""))

        if grp == "TRUE":
            true_count += 1
            if month != "UNKNOWN":
                monthly_counts[month]["TRUE"] += 1
        elif grp == "WARNING":
            warning_count += 1
            if month != "UNKNOWN":
                monthly_counts[month]["WARNING"] += 1
            w_cause = warning.split(":")[0].strip() or "WARNING"
            warning_causes_counter[w_cause] += 1
        elif grp == "ERROR":
            error_count += 1
            if month != "UNKNOWN":
                monthly_counts[month]["ERROR"] += 1
            err_cause = (line.get("detail") or status).split(";")[0].split(":")[0].strip() or "ERROR"
            error_causes_counter[err_cause] += 1

    for job in jobs:
        ps = classify_job(job.get("processing_status", ""))
        month = _elr_to_month(job.get("elr_no", ""))
        if ps == "HOLD":
            hold_count += 1
            raw_hr = job.get("hold_reason") or "UNKNOWN"
            h_cause = raw_hr.split(":")[0].strip() or "HOLD"
            hold_causes_counter[h_cause] += 1
        elif ps == "FAILED":
            error_count += 1
            if month != "UNKNOWN":
                monthly_counts[month]["ERROR"] += 1
            raw_hr = job.get("hold_reason") or "JOB_FAILED"
            f_cause = raw_hr.split(":")[0].strip() or "FAILED"
            error_causes_counter[f_cause] += 1

    total_lines = true_count + warning_count + error_count
    total_elrs = len(jobs)

    def _calc_pct(num: int, denom: int) -> float:
        return round(100.0 * num / denom, 1) if denom > 0 else 0.0

    def _top(c: Counter[str]) -> str:
        most = c.most_common(1)
        return most[0][0] if most else ""

    cards = {
        "TRUE": {
            "count": true_count,
            "pct": _calc_pct(true_count, total_lines),
            "top_cause": "",
        },
        "WARNING": {
            "count": warning_count,
            "pct": _calc_pct(warning_count, total_lines),
            "top_cause": _top(warning_causes_counter),
        },
        "ERROR": {
            "count": error_count,
            "pct": _calc_pct(error_count, total_lines),
            "top_cause": _top(error_causes_counter),
        },
        "HOLD": {
            "count": hold_count,
            "pct": _calc_pct(hold_count, total_elrs),
            "top_cause": _top(hold_causes_counter),
        },
    }

    monthly = [
        {"month": m, "TRUE": v["TRUE"], "WARNING": v["WARNING"], "ERROR": v["ERROR"]}
        for m, v in sorted(monthly_counts.items())
    ]

    error_causes = [
        {"cause": cause, "count": cnt}
        for cause, cnt in sorted(error_causes_counter.items(), key=lambda x: (-x[1], x[0]))
    ]
    hold_causes = [
        {"cause": cause, "count": cnt}
        for cause, cnt in sorted(hold_causes_counter.items(), key=lambda x: (-x[1], x[0]))
    ]

    return {
        "cards": cards,
        "monthly": monthly,
        "error_causes": error_causes,
        "hold_causes": hold_causes,
    }
