"""Workflow endpoints: reviews and approvals."""
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mark_api.deps import current_user, get_repo, require
from mark_api.grouping import classify_job
from mark_api.logging import log_event
from mark_api.repo import Repo
from mark_api.workflow import approve_blockers

router = APIRouter(tags=["workflow"])


class ReviewRequest(BaseModel):
    run_id: int
    elr_no: str
    line_no: int
    reason: str | None = None
    note: str | None = None
    corrected_mark: str | None = None
    is_draft: bool = False


class ApprovalRequest(BaseModel):
    run_id: int
    elr_no: str
    decision: Literal["APPROVED", "REJECTED"]


@router.post("/reviews")
def add_review(req: ReviewRequest, user: dict[str, Any] = Depends(require("review")), repo: Repo = Depends(get_repo)):
    snapshot = repo.snapshot(req.run_id, req.elr_no)
    abs_no = snapshot.get("abs_file", "") if snapshot else ""

    rev_id = repo.add_review(
        run_id=req.run_id,
        elr_no=req.elr_no,
        abs_no=abs_no or "ABS",
        side="TOP",
        line_no=req.line_no,
        reason=req.reason or "OTHER",
        note=req.note or "",
        corrected_mark=req.corrected_mark or "",
        reviewer_id=user["user_id"],
        is_draft=req.is_draft,
    )
    repo.audit(
        user["user_id"],
        "review.saved",
        run_id=req.run_id,
        elr_no=req.elr_no,
        line_no=req.line_no,
        detail={"reason": req.reason, "is_draft": req.is_draft},
    )
    log_event("review.saved", run_id=req.run_id, elr_no=req.elr_no, line_no=req.line_no)
    return {"status": "ok", "review_id": rev_id}


@router.post("/approvals")
def add_approval(req: ApprovalRequest, user: dict[str, Any] = Depends(require("approve")), repo: Repo = Depends(get_repo)):
    if req.decision == "APPROVED":
        # Check if job is HOLD
        snapshot = repo.snapshot(req.run_id, req.elr_no)
        ps = "DONE"
        if snapshot and "processing_status" in snapshot:
            ps = snapshot["processing_status"]
        else:
            job = repo.job(req.run_id, req.elr_no) if hasattr(repo, "job") else None
            if job:
                ps = job.get("processing_status", "DONE")

        if classify_job(ps) == "HOLD":
            return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"reason": "HOLD"})

        lines = repo.lines_for_elr(req.run_id, req.elr_no)
        latest_revs = repo.latest_reviews(req.run_id, req.elr_no)
        blockers = approve_blockers(lines, latest_revs)
        if blockers:
            return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"blocked_lines": blockers})

    app_id = repo.add_approval(req.run_id, req.elr_no, req.decision, user["user_id"])
    repo.audit(user["user_id"], "approval.saved", run_id=req.run_id, elr_no=req.elr_no, detail={"decision": req.decision})
    log_event("approval.saved", run_id=req.run_id, elr_no=req.elr_no, decision=req.decision)
    return {"status": "ok", "approval_id": app_id, "decision": req.decision}
