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
from mark_api.deps import get_cookie_name, get_repo, require
from mark_api.logging import log_event
from mark_api.repo import Repo
from mark_api.routers import auth, mark, validation, workflow

app = FastAPI(title="Mark API", version="0.3.0")


class InProcessMetrics:
    def __init__(self):
        self.requests = {
            "total": 0,
            "2xx": 0,
            "3xx": 0,
            "4xx": 0,
            "5xx": 0,
        }
        self.login_ok = 0
        self.login_failed = 0
        self.login_locked = 0
        self.rate_limited = 0
        self.durations: dict[str, list[float]] = {}

    def record_request(self, status_code: int, duration_ms: float, route: str):
        self.requests["total"] += 1
        cls = f"{status_code // 100}xx"
        if cls in self.requests:
            self.requests[cls] += 1
        self.durations.setdefault(route, []).append(duration_ms)


metrics = InProcessMetrics()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or f"req_{secrets.token_hex(8)}"
        request.state.request_id = req_id

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
                    repo = get_repo()
                    token_hash = hashlib.sha256(sess_token.encode("utf-8")).hexdigest()
                    res = repo.session_user(token_hash)
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
        route = request.url.path
        metrics.record_request(response.status_code, duration_ms, route)

        return response


app.add_middleware(RequestContextMiddleware)

# Include routers under /api
app.include_router(auth.router, prefix="/api")
app.include_router(mark.router, prefix="/api")
app.include_router(validation.router, prefix="/api")
app.include_router(workflow.router, prefix="/api")


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
def get_metrics(user: dict[str, Any] = Depends(require("metrics"))):
    return {
        "requests": metrics.requests,
        "login_ok": metrics.login_ok,
        "login_failed": metrics.login_failed,
        "login_locked": metrics.login_locked,
        "rate_limited": metrics.rate_limited,
    }
