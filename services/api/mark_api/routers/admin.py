"""Admin endpoints: users, unlock, activity, and events."""
from datetime import date, datetime, timedelta, timezone
from typing import Any


from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from mark_api.auth import login_state
from mark_api.deps import current_user, get_repo, require, safe_audit
from mark_api.logging import log_event
from mark_api.repo import Repo

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require("admin"))])

# Asia/Bangkok is UTC+7 with no DST; a fixed offset avoids needing tzdata on Windows.
BKK_TZ = timezone(timedelta(hours=7))


def _resolve_date_range(from_d: date | None, to_d: date | None) -> tuple[date, date]:
    now_bkk = datetime.now(BKK_TZ).date()
    if to_d is None:
        to_d = now_bkk
    if from_d is None:
        from_d = to_d - timedelta(days=13)

    if from_d > to_d:
        raise HTTPException(status_code=422, detail="from must be <= to")
    if (to_d - from_d).days > 92:
        raise HTTPException(status_code=422, detail="Date range cannot exceed 92 days")

    return from_d, to_d


@router.get("/users")
def list_users(repo: Repo = Depends(get_repo)) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    users = repo.admin_users()
    for u in users:
        u["state"] = login_state(u, now)
    return users


@router.post("/users/{user_id}/unlock")
def unlock_user(
    user_id: int,
    request: Request,
    current_admin: dict[str, Any] = Depends(require("admin")),
    repo: Repo = Depends(get_repo),
) -> dict[str, str]:
    ok = repo.unlock_user(user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    safe_audit(repo, current_admin["user_id"], "admin.unlock", request, detail={"target_user_id": user_id})
    log_event("admin.unlock", admin_id=current_admin["user_id"], target_user_id=user_id)
    return {"status": "ok"}


@router.get("/activity")
def get_activity(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    run_id: int | None = Query(None),
    repo: Repo = Depends(get_repo),
) -> dict[str, Any]:
    date_from, date_to = _resolve_date_range(from_date, to_date)
    if run_id is None:
        runs = repo.runs()
        run_id = max((r["run_id"] for r in runs), default=0) if runs else 0

    return repo.activity(date_from, date_to, run_id)


@router.get("/events")
def get_events(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    user_id: int | None = Query(None),
    action: str | None = Query(None),
    page: int = Query(1, ge=1),
    repo: Repo = Depends(get_repo),
) -> list[dict[str, Any]]:
    date_from, date_to = _resolve_date_range(from_date, to_date)
    return repo.audit_events(date_from, date_to, user_id, action, page)
