"""Scan, ELR lookup, oracle check, recheck, and notification endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from mark_api.deps import current_user, get_repo, require_any_role, require_scope, safe_audit
from mark_api.repo import Repo, ScanLockConflict
from mark_engine.adapters.oracle_client import connect_actl
from mark_engine.history.decide import decide
from mark_engine.history.fingerprint import oracle_fp
from mark_engine.select import pending_reason
from services.worker.oracle_source import (
    fetch_one,
    fetch_pending_step,
    fetch_window,
    to_engine,
)

logger = logging.getLogger("mark_api.scans")
router = APIRouter(tags=["scans"])


class ScanRequest(BaseModel):
    source: Literal["airflow", "initial"]
    from_ts: datetime | None = None
    to_ts: datetime | None = None


@router.post("/scans", status_code=status.HTTP_201_CREATED)
def trigger_scan(
    req: ScanRequest,
    request: Request,
    user: dict[str, Any] = Depends(require_scope("scan:write")),
    repo: Repo = Depends(get_repo),
) -> dict[str, Any]:
    """Trigger an airflow or initial scan for new/changed ELRs."""
    # 1. Enforce single active scan via single connection advisory lock
    try:
        with repo.hold_scan_lock():
            review_step = os.environ.get("MARK_REVIEW_STEP", "6")
            now = datetime.now(timezone.utc)
            from_ts = req.from_ts
            to_ts = req.to_ts

            if req.source == "airflow":
                if from_ts is None:
                    # Requirement (4): looks at source in ('airflow', 'initial')
                    last_scan = repo.last_successful_scan()
                    if last_scan and last_scan.get("to_ts"):
                        t_val = last_scan["to_ts"]
                        if t_val.tzinfo is None:
                            t_val = t_val.replace(tzinfo=timezone.utc)
                        from_ts = t_val - timedelta(minutes=5)
                    else:
                        from_ts = now - timedelta(days=1)
                if to_ts is None:
                    to_ts = now
            else:  # initial
                to_ts = now

            # Requirement (2): Create single scan row at start with finished_at=null
            scan_id = repo.create_scan(
                source=req.source,
                requested_by=user.get("username", "api_token"),
                from_ts=from_ts,
                to_ts=to_ts,
            )

            counts = {
                "found": 0,
                "queued": 0,
                "unchanged": 0,
                "skipped": 0,
                "same_as_rev": 0,
            }

            conn_oracle = None
            try:
                conn_oracle = connect_actl()
            except Exception as exc:
                logger.warning("connect_actl unavailable: %s", exc)
            try:
                try:
                    if req.source == "airflow":
                        rows = fetch_window(conn_oracle, from_ts, to_ts) if conn_oracle is not None else []
                    else:  # initial
                        rows = fetch_pending_step(conn_oracle, review_step) if conn_oracle is not None else []
                finally:
                    if hasattr(conn_oracle, "close"):
                        try:
                            conn_oracle.close()
                        except Exception:
                            pass

                counts["found"] = len(rows)

                for row in rows:
                    meta, _, _ = to_engine(row)
                    elr_no = meta.elr_no
                    p_reason = pending_reason(meta, review_step)
                    ofp = oracle_fp(row)

                    prev_keys = repo.get_previous_revisions(elr_no)
                    dec = decide(p_reason, prev_keys, ofp, docs_fp=None, manual=False)

                    if dec.action == "skip_not_eligible":
                        counts["skipped"] += 1
                    elif dec.action == "skip_unchanged":
                        counts["unchanged"] += 1
                    elif dec.action == "skip_same_as_rev":
                        counts["same_as_rev"] += 1
                    elif dec.action == "check":
                        if repo.enqueue_work_item(scan_id, elr_no, reason="scan"):
                            counts["queued"] += 1

                # Requirement (2): On completion, UPDATE finished_at and counts
                repo.finish_scan(scan_id, counts)

                safe_audit(
                    repo,
                    user.get("user_id"),
                    "scan.started",
                    request,
                    detail={"source": req.source, "scan_id": scan_id, "counts": counts},
                )

                return {"scan_id": scan_id, "counts": counts}

            except Exception as scan_exc:
                logger.exception("Scan failed: %s", scan_exc)
                repo.fail_scan(scan_id, str(scan_exc), counts=counts)
                raise

    except ScanLockConflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A scan is already running",
        )


@router.post("/scans/retry")
def retry_scan(
    request: Request,
    user: dict[str, Any] = Depends(require_scope("scan:write")),
    repo: Repo = Depends(get_repo),
) -> dict[str, Any]:
    """Re-enqueue ELRs whose latest revision is HOLD or unapproved for doc re-evaluation."""
    requeued = repo.requeue_unapproved_step6()
    safe_audit(repo, user.get("user_id"), "scan.retry", request, detail={"requeued": requeued})
    return {"requeued": requeued}


@router.get("/elrs/lookup")
def lookup_elr(
    elr: str = Query(..., description="ELR Number to lookup"),
    user: dict[str, Any] = Depends(current_user),
    repo: Repo = Depends(get_repo),
) -> dict[str, Any]:
    """Lookup ELR revision history, status, and queued state."""
    elr_clean = elr.strip().upper()
    return repo.get_elr_history(elr_clean)


@router.post("/elrs/{elr}/oracle-check")
def oracle_check_elr(
    elr: str,
    request: Request,
    user: dict[str, Any] = Depends(current_user),
    repo: Repo = Depends(get_repo),
) -> dict[str, Any]:
    """Check a single ELR against Oracle and enqueue if eligible."""
    elr_clean = elr.strip().upper()
    conn_oracle = None
    try:
        conn_oracle = connect_actl()
    except Exception as exc:
        logger.warning("connect_actl unavailable: %s", exc)

    try:
        row = fetch_one(conn_oracle, elr_clean) if conn_oracle is not None else None
        if not row:
            repo.add_notification(elr_clean, "not_in_oracle", message=f"ELR {elr_clean} not found in Oracle")
            safe_audit(repo, user.get("user_id"), "elr.oracle_check", request, elr_no=elr_clean, detail={"found": False})
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"not_found_in_oracle: ELR {elr_clean} not found",
            )

        meta, _, _ = to_engine(row)
        review_step = os.environ.get("MARK_REVIEW_STEP", "6")
        p_reason = pending_reason(meta, review_step)

        if p_reason is not None:
            repo.add_notification(elr_clean, "not_eligible", message=f"ELR {elr_clean} not eligible: {p_reason}")
            safe_audit(
                repo,
                user.get("user_id"),
                "elr.oracle_check",
                request,
                elr_no=elr_clean,
                detail={"eligible": False, "reason": p_reason},
            )
            return {"queued": False, "reason": p_reason}

        queued = repo.enqueue_work_item(None, elr_clean, reason="user")
        safe_audit(
            repo,
            user.get("user_id"),
            "elr.oracle_check",
            request,
            elr_no=elr_clean,
            detail={"queued": queued},
        )
        return {"queued": queued}

    finally:
        if hasattr(conn_oracle, "close"):
            try:
                conn_oracle.close()
            except Exception:
                pass


@router.post("/elrs/{elr}/recheck")
def recheck_elr(
    elr: str,
    request: Request,
    user: dict[str, Any] = Depends(require_any_role(["engineer", "mark_eng_approver", "admin"])),
    repo: Repo = Depends(get_repo),
) -> dict[str, Any]:
    """Manually force re-check for an ELR (bypasses unchanged skips)."""
    elr_clean = elr.strip().upper()
    queued = repo.enqueue_work_item(None, elr_clean, reason="recheck")
    safe_audit(repo, user.get("user_id"), "elr.recheck", request, elr_no=elr_clean, detail={"queued": queued})
    return {"queued": queued}


@router.get("/notifications")
def get_notifications(
    unread: int = Query(0, description="1 to filter unread only"),
    user: dict[str, Any] = Depends(current_user),
    repo: Repo = Depends(get_repo),
) -> list[dict[str, Any]]:
    """List system notifications."""
    return repo.list_notifications(user["user_id"], unread_only=bool(unread))


@router.post("/notifications/{id}/read")
def read_notification(
    id: int,
    request: Request,
    user: dict[str, Any] = Depends(current_user),
    repo: Repo = Depends(get_repo),
) -> dict[str, Any]:
    """Mark a notification as read by current user."""
    ok = repo.mark_notification_read(id, user["user_id"])
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return {"ok": True}
