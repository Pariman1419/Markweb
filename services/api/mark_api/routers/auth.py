"""Authentication endpoints."""
from datetime import datetime, timedelta, timezone
import hashlib
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mark_api.auth import login_state, new_token, verify_password
from mark_api.deps import current_user, get_cookie_name, get_repo
from mark_api.logging import log_event
from mark_api.repo import Repo

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
        log_event("auth.login_failed", username=username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    state = login_state(user, now)
    if state == "LOCKED":
        log_event("auth.locked", user_id=user["user_id"])
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account locked")
    if state == "INACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive")

    if not verify_password(user["password_hash"], req.password):
        repo.record_login(user["user_id"], False)
        log_event("auth.login_failed", user_id=user["user_id"])
        updated_user = repo.user_by_id(user["user_id"])
        if updated_user and login_state(updated_user, now) == "LOCKED":
            log_event("auth.locked", user_id=user["user_id"])
            repo.delete_user_sessions(user["user_id"])
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Rotate session: delete old session if present
    sess_cookie_name = get_cookie_name("mark_session")
    old_cookie = request.cookies.get(sess_cookie_name) or request.cookies.get("mark_session")
    if old_cookie:
        old_hash = hashlib.sha256(old_cookie.encode("utf-8")).hexdigest()
        repo.delete_session(old_hash)

    # Login ok
    repo.record_login(user["user_id"], True)
    raw_sess, sess_digest = new_token()
    raw_csrf, csrf_digest = new_token()
    expires_at = now + timedelta(hours=8)
    repo.create_session(sess_digest, user["user_id"], csrf_digest, expires_at)
    repo.audit(user["user_id"], "auth.login_ok")
    log_event("auth.login_ok", user_id=user["user_id"])

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
        repo.delete_session(sess["token_hash"])
    repo.audit(user["user_id"], "auth.logout")
    log_event("auth.logout", user_id=user["user_id"])

    resp = JSONResponse({"status": "ok"})
    secure = os.getenv("MARK_COOKIE_SECURE", "false").lower() in ("true", "1")
    sess_cookie = get_cookie_name("mark_session")
    csrf_cookie = get_cookie_name("mark_csrf")

    resp.set_cookie(key=sess_cookie, value="", max_age=0, path="/api", httponly=True, samesite="strict", secure=secure)
    resp.set_cookie(key=csrf_cookie, value="", max_age=0, path="/", httponly=False, samesite="strict", secure=secure)
    return resp


@router.get("/me")
def me(user: dict[str, Any] = Depends(current_user)):
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
    }
