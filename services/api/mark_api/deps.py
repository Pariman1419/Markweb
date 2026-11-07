"""FastAPI dependencies: repository, auth, and permissions."""
from datetime import datetime, timezone
import hashlib
import os
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status

from mark_api.auth import can, login_state, session_status, session_valid
from mark_api.logging import log_event
from mark_api.repo import Repo
from mark_engine.adapters.redis_cache import cache_session, get_redis, session_touch_due

_global_repo: Repo | None = None


def session_for_token(repo: Repo, token_hash: str, *, sliding: bool = True):
    return cache_session(get_redis(), token_hash, 900,
                         lambda: repo.session_user(token_hash), sliding=sliding)


def get_repo() -> Repo:
    global _global_repo
    if _global_repo is None:
        _global_repo = Repo()
    return _global_repo


def get_cookie_name(base: str) -> str:
    secure = os.getenv("MARK_COOKIE_SECURE", "false").lower() in ("true", "1")
    if not secure:
        return base
    # spec §17: __Host- requires Path=/, so only the CSRF cookie (Path=/) can carry it;
    # the session cookie keeps Path=/api and uses __Secure-.
    if base == "mark_session":
        return "__Secure-mark_session"
    if base == "mark_csrf":
        return "__Host-mark_csrf"
    return base


def audit_ctx(request: Request) -> dict[str, str | None]:
    client_ip = request.headers.get("x-real-ip") or (request.client.host if request.client else None)
    req_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id")
    return {"client_ip": client_ip, "request_id": req_id}


def safe_audit(repo: Repo, user_id: int | None, action: str, request: Request, **kw: Any) -> None:
    try:
        repo.audit(user_id, action, **audit_ctx(request), **kw)
    except Exception:
        log_event("db.error", where="audit", action=action)




def current_user(request: Request, authorization: str | None = Header(None), repo: Repo = Depends(get_repo)) -> dict[str, Any]:
    now = datetime.now(timezone.utc)

    # 1. Check Bearer token (for metrics)
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization[7:].strip()
        digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        tok = repo.token_by_hash(digest)
        if tok:
            exp = tok.get("expires_at")
            if exp and (exp.replace(tzinfo=timezone.utc) if exp.tzinfo is None else exp) < now:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
            user_info = {
                "user_id": tok.get("created_by", 0),
                "username": tok.get("name", "api_token"),
                "display_name": tok.get("name", "API Token"),
                "role": "metrics_token",
                "scopes": tok.get("scopes", []),
            }
            request.state.user = user_info
            return user_info
        # A Bearer request never falls back to the session cookie (it skips CSRF in the middleware).
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # 2. Check Session Cookie
    sess_cookie_name = get_cookie_name("mark_session")
    token = request.cookies.get(sess_cookie_name) or request.cookies.get("mark_session")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    res = session_for_token(repo, token_hash)
    if not res:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    session, user = res
    status_val = session_status(session, now)
    if status_val != "ok":
        safe_audit(repo, user["user_id"], "auth.session_expired", request, detail={"why": status_val})
        repo.delete_session(token_hash)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    state = login_state(user, now)
    if state == "LOCKED":
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account locked")
    if state == "INACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive")

    if session_touch_due(get_redis(), token_hash):
        repo.touch_session(token_hash)
    request.state.session = session
    request.state.user = user
    return user


def require(action: str):
    def _require(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        role = user.get("role", "")
        if not can(role, action):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Action '{action}' forbidden for role '{role}'")
        return user
    return _require


def require_scope(scope: str):
    def _require_scope(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        scopes = user.get("scopes", [])
        if scope not in scopes:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Token missing required scope '{scope}'")
        return user
    return _require_scope


def require_any_role(roles: list[str]):
    def _require_roles(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        role = user.get("role", "")
        if role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Role '{role}' not in allowed roles")
        return user
    return _require_roles
