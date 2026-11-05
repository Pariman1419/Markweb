"""G0: Pending Mark Engineer review selector."""
from __future__ import annotations

import os

from mark_engine.domain.models import ElrMeta


def pending_reason(meta: ElrMeta, review_step: str) -> str | None:
    """Check if an ELR is pending Mark Engineer review.

    Returns None if eligible to process, else a reason code:
    - 'STATUS_C': Status is C (closed)
    - 'NOT_MARK_REVIEW_STEP': CURRENT_STEP does not match review_step
    """
    if meta.status and meta.status.strip().upper() == "C":
        return "STATUS_C"
    current = (meta.current_step or "").strip()
    if current != review_step.strip():
        return "NOT_MARK_REVIEW_STEP"
    return None


def review_step_from_env() -> str:
    """Get the configured Mark Engineer review step number from environment."""
    return os.environ.get("MARK_REVIEW_STEP", "6")
