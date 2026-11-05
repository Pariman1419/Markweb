"""Workflow and approval guards."""
from typing import Any
from mark_api.grouping import classify_line


def approve_blockers(lines: list[dict[str, Any]], latest_reviews: dict[int, dict[str, Any]]) -> list[int]:
    """Returns line numbers classified ERROR that lack a non-draft review with both reason and corrected_mark."""
    blockers: list[int] = []
    for line in lines:
        line_no = int(line["line_no"])
        status = line.get("status") or line.get("final_status") or ""
        warning = line.get("warning") or ""
        if classify_line(status, warning) == "ERROR":
            rev = latest_reviews.get(line_no)
            if not rev or rev.get("is_draft", False):
                blockers.append(line_no)
                continue
            if not (rev.get("reason") and rev.get("corrected_mark")):
                blockers.append(line_no)
    return sorted(blockers)
