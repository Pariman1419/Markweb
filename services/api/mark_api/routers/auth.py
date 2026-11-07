"""Authentication endpoints."""
from datetime import datetime, timedelta, timezone
import hashlib
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mark_api.auth import login_state, new_token, verify_password
from mark_api.deps import audit_ctx, current_user, get_cookie_name, get_repo, safe_audit
from mark_api.logging import log_event
from mark_api.metrics import metrics
from mark_api.repo import Repo
from mark_api import deps
from mark_engine.adapters.redis_cache import invalidate_session, invalidate_user_sessions, session_cache_lock

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(req: LoginRequest, request: Request, repo: Repo = Depends(get_repo)):
    now = datetime.now(timezone.utc)
    username = req.username.strip().lower()
    user = repo.user_by_name(username)

    if not user:
        safe_audit(repo, None, "auth.login_failed", request, detail={"reason": "unknown_user"})
        log_event("auth.login_failed")
        metrics.inc("login_failed")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    state = login_state(user, now)
    if state == "LOCKED":
        safe_audit(repo, user["user_id"], "auth.login_failed", request, detail={"reason": "locked"})
        log_event("auth.locked", user_id=user["user_id"])
        metrics.inc("login_failed")
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account locked")
    if state == "INACTIVE":
        safe_audit(repo, user["user_id"], "auth.login_failed", request, detail={"reason": "inactive"})
        metrics.inc("login_failed")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive")

    if not verify_password(user["password_hash"], req.password):
        with session_cache_lock:
            # Drop trust before the database write: it may commit and then fail
            # before the caller can observe the new account state.
            invalidate_user_sessions(deps.get_redis(), user["user_id"])
            repo.record_login(user["user_id"], False)
            updated_user = repo.user_by_id(user["user_id"]) or {}
            if login_state(updated_user, now) == "LOCKED":
                repo.delete_user_sessions(user["user_id"])
        failed_count = updated_user.get("failed_count", (user.get("failed_count", 0) or 0) + 1)
        safe_audit(repo, user["user_id"], "auth.login_failed", request, detail={"reason": "bad_password", "failed_count": failed_count})
        log_event("auth.login_failed", user_id=user["user_id"])
        metrics.inc("login_failed")
        if login_state(updated_user, now) == "LOCKED":
            locked_until = updated_user.get("locked_until")
            iso_str = locked_until.isoformat() if hasattr(locked_until, "isoformat") else str(locked_until)
            safe_audit(repo, user["user_id"], "auth.locked", request, detail={"locked_until": iso_str})
            log_event("auth.locked", user_id=user["user_id"])
            metrics.inc("login_locked")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Rotate session: delete old session if present
    sess_cookie_name = get_cookie_name("mark_session")
    old_cookie = request.cookies.get(sess_cookie_name) or request.cookies.get("mark_session")
    if old_cookie:
        old_hash = hashlib.sha256(old_cookie.encode("utf-8")).hexdigest()
        with session_cache_lock:
            invalidate_session(deps.get_redis(), old_hash)
            repo.delete_session(old_hash)

    # Login ok
    repo.record_login(user["user_id"], True)
    raw_sess, sess_digest = new_token()
    raw_csrf, csrf_digest = new_token()
    expires_at = now + timedelta(hours=8)
    repo.create_session(sess_digest, user["user_id"], csrf_digest, expires_at)
    safe_audit(repo, user["user_id"], "auth.login_ok", request)
    log_event("auth.login_ok", user_id=user["user_id"])
    metrics.inc("login_ok")

    resp = JSONResponse(
        {
            "status": "ok",
            "user": {
                "user_id": user["user_id"],
                "username": user["username"],
                "display_name": user["display_name"],
                "role": user["role"],
            },
        }
    )
    secure = os.getenv("MARK_COOKIE_SECURE", "false").lower() in ("true", "1")
    sess_cookie = get_cookie_name("mark_session")
    csrf_cookie = get_cookie_name("mark_csrf")

    resp.set_cookie(
        key=sess_cookie,
        value=raw_sess,
        max_age=28800,
        path="/api",
        httponly=True,
        samesite="strict",
        secure=secure,
    )
    resp.set_cookie(
        key=csrf_cookie,
        value=raw_csrf,
        max_age=28800,
        path="/",
        httponly=False,
        samesite="strict",
        secure=secure,
    )
    return resp


@router.post("/logout")
def logout(request: Request, user: dict[str, Any] = Depends(current_user), repo: Repo = Depends(get_repo)):
    sess = getattr(request.state, "session", None)
    if sess:
        with session_cache_lock:
            invalidate_session(deps.get_redis(), sess["token_hash"])
            repo.delete_session(sess["token_hash"])
    safe_audit(repo, user["user_id"], "auth.logout", request)
    log_event("auth.logout", user_id=user["user_id"])

    resp = JSONResponse({"status": "ok"})
    secure = os.getenv("MARK_COOKIE_SECURE", "false").lower() in ("true", "1")
    sess_cookie = get_cookie_name("mark_session")
    csrf_cookie = get_cookie_name("mark_csrf")

    resp.set_cookie(key=sess_cookie, value="", max_age=0, path="/api", httponly=True, samesite="strict", secure=secure)
    resp.set_cookie(key=csrf_cookie, value="", max_age=0, path="/", httponly=False, samesite="strict", secure=secure)
    return resp


@router.get("/me")
def me(user: dict[str, Any] = Depends(current_user), repo: Repo = Depends(get_repo)):
    if "display_name" not in user:
        user = repo.user_by_id(user["user_id"]) or user
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "display_name": user.get("display_name", user["username"]),
        "role": user["role"],
    }
