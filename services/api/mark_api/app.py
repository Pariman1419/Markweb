"""FastAPI main application with CSRF protection, metrics, logging, and security headers."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import secrets
import time
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from mark_api.auth import csrf_ok
from mark_api.deps import get_cookie_name, get_repo, require, session_for_token
from mark_api.logging import current_request_id, log_event
from mark_api.metrics import metrics
from mark_api.repo import Repo
from mark_api.routers import admin, auth, mark, scans, validation, workflow, ws
from mark_engine.adapters.redis_cache import get_redis, get_worker_heartbeat

app = FastAPI(title="Mark API", version="0.3.0")


def _same_origin(origin: str, request: Request) -> bool:
    """Origin's host:port equals the Host the browser addressed (NGINX and the Vite proxy keep it)."""
    from urllib.parse import urlsplit
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    return urlsplit(origin).netloc.lower() == host.lower()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or f"req_{secrets.token_hex(8)}"
        request.state.request_id = req_id
        current_request_id.set(req_id)

        # 1. CORS check
        origin = request.headers.get("origin")
        allowed_origins = [o.strip() for o in os.getenv("MARK_CORS_ORIGINS", "").split(",") if o.strip()]

        if request.method == "OPTIONS":
            resp = Response(status_code=200)
            if origin and origin in allowed_origins:
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Access-Control-Allow-Credentials"] = "true"
                resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRF-Token, X-Request-ID"
                resp.headers["Access-Control-Max-Age"] = "600"
            resp.headers["X-Request-ID"] = req_id
            return resp

        # 2. CSRF check for unsafe methods
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            path = request.url.path
            auth_header = request.headers.get("authorization", "")
            # Login and Bearer token requests are exempt
            # spec §11: an unsafe request from a browser must come from this site's own origin.
            if origin and not _same_origin(origin, request) and origin not in allowed_origins:
                return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "Origin not allowed"},
                                    headers={"X-Request-ID": req_id})
            if not path.endswith("/auth/login") and not auth_header.startswith("Bearer "):
                csrf_header = request.headers.get("x-csrf-token")
                csrf_cookie_name = get_cookie_name("mark_csrf")
                csrf_cookie = request.cookies.get(csrf_cookie_name) or request.cookies.get("mark_csrf")

                if not csrf_header or not csrf_cookie or not csrf_ok(csrf_cookie, csrf_header):
                    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "CSRF validation failed"})

                # Also verify session csrf_hash if session cookie is present
                sess_cookie_name = get_cookie_name("mark_session")
                sess_token = request.cookies.get(sess_cookie_name) or request.cookies.get("mark_session")
                if sess_token:
                    repo = request.app.dependency_overrides.get(get_repo, get_repo)()
                    token_hash = hashlib.sha256(sess_token.encode("utf-8")).hexdigest()
                    res = session_for_token(repo, token_hash, sliding=False)
                    if res:
                        session_data, _ = res
                        header_hash = hashlib.sha256(csrf_header.encode("utf-8")).hexdigest()
                        if session_data.get("csrf_hash") != header_hash:
                            return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "CSRF token does not match session"})

        t0 = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - t0) * 1000.0

        # Attach X-Request-ID
        response.headers["X-Request-ID"] = req_id

        # Attach CORS if allowed
        if origin and origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"

        # Record metrics and log
        # spec §15: metrics and logs key on the route template (/api/elrs/{elr}), not the raw path.
        matched = request.scope.get("route")
        template = getattr(matched, "path", None)
        route = (template if template.startswith("/api") else "/api" + template) if template else request.url.path
        metrics.record_request(response.status_code, duration_ms, route)
        user = getattr(request.state, "user", None) or {}
        log_event("http.request", method=request.method, route=route, status=response.status_code,
                  duration_ms=round(duration_ms, 1), client_ip=request.headers.get("x-real-ip") or (request.client.host if request.client else None),
                  user_id=user.get("user_id"), role=user.get("role"))

        return response


app.add_middleware(RequestContextMiddleware)


@app.get("/api/worker/status")
def worker_status(user: dict[str, Any] = Depends(require("read"))):
    client = get_redis()
    heartbeat = get_worker_heartbeat(client)
    worker_state = "alive" if heartbeat else "unknown"
    if not heartbeat and client is not None:
        try:
            if client.ping():
                worker_state = "degraded"
        except Exception:
            pass
    return {"status": worker_state, "heartbeat": heartbeat}

# Include routers under /api
app.include_router(auth.router, prefix="/api")
app.include_router(scans.router, prefix="/api")
app.include_router(mark.router, prefix="/api")
app.include_router(validation.router, prefix="/api")
app.include_router(workflow.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(ws.router, prefix="/api")
app.include_router(ws.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/ready")
def ready(repo: Repo = Depends(get_repo)):
    # 1. DB ping
    try:
        repo._execute("select 1", fetch_one=True)
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")

    # 2. MARK_FILES_ROOT check
    files_root = Path(os.getenv("MARK_FILES_ROOT", "data/files"))
    if not files_root.exists() or not os.access(files_root, os.R_OK):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Files root not readable")

    return {"status": "ready"}


@app.get("/api/metrics")
def get_metrics(user: dict[str, Any] = Depends(require("metrics")), repo: Repo = Depends(get_repo)):
    try:
        active = repo.active_sessions()
    except Exception:
        active = None
    return metrics.snapshot(active)
