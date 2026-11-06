"""Workflow endpoints: reviews and approvals."""
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mark_api.deps import audit_ctx, current_user, get_repo, require
from mark_api.grouping import classify_job
from mark_api.logging import log_event
from mark_api.repo import Repo
from mark_api.workflow import approve_blockers
from mark_engine.adapters.redis_cache import notify_revision

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
def add_review(req: ReviewRequest, request: Request, user: dict[str, Any] = Depends(require("review")), repo: Repo = Depends(get_repo)):
    # line_review's FK is (run_id, elr_no, abs_no, side, line_no) -> mark_logic.line_result, so the key must come
    # from the line row itself: the job/snapshot abs (e.g. "ABS071169-ENG-2") differs from line_result.abs_no.
    line = next((l for l in repo.lines_for_elr(req.run_id, req.elr_no) if l.get("line_no") == req.line_no), None)
    if line is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="line not found")

    rev_id = repo.add_review(
        run_id=req.run_id,
        elr_no=req.elr_no,
        abs_no=line["abs_no"],
        side=line["side"],
        line_no=req.line_no,
        reason=req.reason or "OTHER",
        note=req.note or "",
        corrected_mark=req.corrected_mark or "",
        reviewer_id=user["user_id"],
        is_draft=req.is_draft,
    )
    notify_revision(req.run_id, req.elr_no, None)
    repo.audit(
        user["user_id"],
        "review.saved",
        run_id=req.run_id,
        elr_no=req.elr_no,
        line_no=req.line_no,
        detail={"reason": req.reason, "is_draft": req.is_draft},
        **audit_ctx(request),
    )
    log_event("review.saved", run_id=req.run_id, elr_no=req.elr_no, line_no=req.line_no)
    return {"status": "ok", "review_id": rev_id}


@router.post("/approvals")
def add_approval(req: ApprovalRequest, request: Request, user: dict[str, Any] = Depends(require("approve")), repo: Repo = Depends(get_repo)):
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
    notify_revision(req.run_id, req.elr_no, None)
    repo.audit(user["user_id"], "approval.saved", run_id=req.run_id, elr_no=req.elr_no, detail={"decision": req.decision}, **audit_ctx(request))
    log_event("approval.saved", run_id=req.run_id, elr_no=req.elr_no, decision=req.decision)
    return {"status": "ok", "approval_id": app_id, "decision": req.decision}
