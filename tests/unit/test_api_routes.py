import json
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import sys
from typing import Any
import pytest
from fastapi.testclient import TestClient

API_DIR = Path(__file__).resolve().parents[2] / "services" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from mark_api.app import app
from mark_api.deps import get_repo
from mark_api.auth import hash_password, new_token


from mark_api.routers.validation import clear_dashboard_cache


class FakeRepo:
    def __init__(self):
        self.call_count = 0
        self.lines_call_count = 0
        self.users: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.api_tokens: dict[str, dict[str, Any]] = {}
        self.runs_data = [{"run_id": 18, "period": "2026-07..2026-11", "created_at": "2026-11-05T00:00:00Z"}]
        self.lines_data: dict[int, list[dict[str, Any]]] = {
            18: [
                {
                    "run_id": 18,
                    "elr_no": "ADI2607001",
                    "abs_no": "ABS071290",
                    "side": "TOP",
                    "line_no": 1,
                    "expected": "MARK1",
                    "oracle": "MARK1",
                    "status": "MATCH",
                    "warning": "",
                    "detail": "",
                    "compare_rules": "EXACT",
                },
                {
                    "run_id": 18,
                    "elr_no": "ADI2607001",
                    "abs_no": "ABS071290",
                    "side": "TOP",
                    "line_no": 2,
                    "expected": "MARK2",
                    "oracle": "DIFF",
                    "status": "DIFF",
                    "warning": "",
                    "detail": "DIFF",
                    "compare_rules": "DIFF",
                },
            ]
        }
        self.jobs_data: dict[int, list[dict[str, Any]]] = {
            18: [
                {
                    "run_id": 18,
                    "elr_no": "ADI2607001",
                    "abs_no": "ABS071290",
                    "processing_status": "DONE",
                    "hold_reason": "",
                },
                {
                    "run_id": 18,
                    "elr_no": "ADI2607002",
                    "abs_no": "ABS071291",
                    "processing_status": "HOLD",
                    "hold_reason": "BOM_NOT_FOUND: x",
                },
            ]
        }
        self.snapshots_data: dict[tuple[int, str], dict[str, Any]] = {
            (18, "ADI2607001"): {
                "run_id": 18,
                "elr_no": "ADI2607001",
                "top_mark_id": 25077,
                "layout_code": "ZE",
                "abs_file": "ABS071290",
                "abs_sha256": "sha_abs_01",
                "image_path": "abs/18/sha_abs_01.png",
                "oracle_top_raw": ["MARK1", "DIFF", "", "", ""],
                "layout_cells": None,
                "slr_files": [],
                "slr_instructions": [],
                "line_extra": {},
                "processing_status": "DONE",
                "hold_reason": "",
            },
            (18, "ADI2607002"): {
                "run_id": 18,
                "elr_no": "ADI2607002",
                "top_mark_id": None,
                "layout_code": None,
                "abs_file": "ABS071291",
                "abs_sha256": None,
                "image_path": None,
                "oracle_top_raw": ["", "", "", "", ""],
                "layout_cells": None,
                "slr_files": [],
                "slr_instructions": [],
                "line_extra": {},
                "processing_status": "HOLD",
                "hold_reason": "BOM_NOT_FOUND: x",
            },
        }
        self.reviews_data: list[dict[str, Any]] = []
        self.approvals_data: list[dict[str, Any]] = []
        self.audit_data: list[dict[str, Any]] = []

        # Seed initial user
        self.users["engineer1"] = {
            "user_id": 1,
            "username": "engineer1",
            "display_name": "Engineer One",
            "role": "engineer",
            "password_hash": hash_password("ValidPassword123!"),
            "active": True,
            "failed_count": 0,
            "locked_until": None,
        }
        self.users["admin1"] = {
            "user_id": 2,
            "username": "admin1",
            "display_name": "Admin One",
            "role": "admin",
            "password_hash": hash_password("ValidPassword123!"),
            "active": True,
            "failed_count": 0,
            "locked_until": None,
        }

    def runs(self) -> list[dict[str, Any]]:
        self.call_count += 1
        return self.runs_data

    def lines(self, run_id: int) -> list[dict[str, Any]]:
        self.call_count += 1
        self.lines_call_count += 1
        return self.lines_data.get(run_id, [])

    def jobs(self, run_id: int) -> list[dict[str, Any]]:
        self.call_count += 1
        return self.jobs_data.get(run_id, [])

    def job(self, run_id: int, elr: str) -> dict[str, Any] | None:
        self.call_count += 1
        for j in self.jobs_data.get(run_id, []):
            if j["elr_no"] == elr:
                return j
        return None

    def lines_for_elr(self, run_id: int, elr: str) -> list[dict[str, Any]]:
        self.call_count += 1
        return [l for l in self.lines_data.get(run_id, []) if l["elr_no"] == elr]

    def snapshot(self, run_id: int, elr: str) -> dict[str, Any] | None:
        self.call_count += 1
        return self.snapshots_data.get((run_id, elr))

    def latest_reviews(self, run_id: int, elr: str) -> dict[int, dict[str, Any]]:
        self.call_count += 1
        out = {}
        for r in self.reviews_data:
            if r["run_id"] == run_id and r["elr_no"] == elr:
                out[r["line_no"]] = r
        return out

    def add_review(self, run_id: int, elr_no: str, abs_no: str, side: str, line_no: int,
                   reason: str, note: str, corrected_mark: str, reviewer_id: int, is_draft: bool) -> int:
        self.call_count += 1
        rev_id = len(self.reviews_data) + 1
        self.reviews_data.append({
            "review_id": rev_id,
            "run_id": run_id,
            "elr_no": elr_no,
            "abs_no": abs_no,
            "side": side,
            "line_no": line_no,
            "reason": reason,
            "note": note,
            "corrected_mark": corrected_mark,
            "reviewer_id": reviewer_id,
            "is_draft": is_draft,
            "created_at": datetime.now(timezone.utc),
        })
        return rev_id

    def add_approval(self, run_id: int, elr_no: str, decision: str, user_id: int) -> int:
        self.call_count += 1
        app_id = len(self.approvals_data) + 1
        self.approvals_data.append({
            "approval_id": app_id,
            "run_id": run_id,
            "elr_no": elr_no,
            "decision": decision,
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc),
        })
        return app_id

    def latest_approval(self, run_id: int, elr: str) -> dict[str, Any] | None:
        self.call_count += 1
        matches = [a for a in self.approvals_data if a["run_id"] == run_id and a["elr_no"] == elr]
        return matches[-1] if matches else None

    def audit(self, user_id: int | None, action: str, run_id: int | None = None,
              elr_no: str | None = None, line_no: int | None = None, detail: Any = None,
              *, client_ip: str | None = None, request_id: str | None = None) -> int:
        self.call_count += 1
        audit_id = len(self.audit_data) + 1
        self.audit_data.append({
            "audit_id": audit_id,
            "user_id": user_id,
            "action": action,
            "run_id": run_id,
            "elr_no": elr_no,
            "line_no": line_no,
            "detail": detail,
            "client_ip": client_ip,
            "request_id": request_id,
            "created_at": datetime.now(timezone.utc),
        })
        return audit_id

    def user_by_name(self, username: str) -> dict[str, Any] | None:
        return self.users.get(username.lower())

    def user_by_id(self, user_id: int) -> dict[str, Any] | None:
        for u in self.users.values():
            if u["user_id"] == user_id:
                return u
        return None

    def record_login(self, user_id: int, ok: bool) -> None:
        u = self.user_by_id(user_id)
        if not u:
            return
        if ok:
            u["failed_count"] = 0
            u["locked_until"] = None
        else:
            u["failed_count"] = u.get("failed_count", 0) + 1
            if u["failed_count"] >= 5:
                u["locked_until"] = datetime.now(timezone.utc) + timedelta(minutes=15)

    def create_session(self, token_hash: str, user_id: int, csrf_hash: str, expires_at: datetime) -> None:
        self.sessions[token_hash] = {
            "token_hash": token_hash,
            "user_id": user_id,
            "csrf_hash": csrf_hash,
            "expires_at": expires_at,
            "last_seen_at": datetime.now(timezone.utc),
        }

    def session_user(self, token_hash: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        sess = self.sessions.get(token_hash)
        if not sess:
            return None
        u = self.user_by_id(sess["user_id"])
        if not u:
            return None
        return sess, u

    def touch_session(self, token_hash: str) -> None:
        if token_hash in self.sessions:
            self.sessions[token_hash]["last_seen_at"] = datetime.now(timezone.utc)

    def delete_session(self, token_hash: str) -> None:
        self.sessions.pop(token_hash, None)

    def delete_user_sessions(self, user_id: int) -> None:
        to_del = [k for k, v in self.sessions.items() if v["user_id"] == user_id]
        for k in to_del:
            self.sessions.pop(k, None)

    def active_sessions(self) -> int:
        return len(self.sessions)

    def token_by_hash(self, token_hash: str) -> dict[str, Any] | None:
        return self.api_tokens.get(token_hash)

    def admin_users(self) -> list[dict[str, Any]]:
        res = []
        for u in self.users.values():
            logins = [a['created_at'] for a in self.audit_data if a['action'] == 'auth.login_ok' and a['user_id'] == u['user_id']]
            last_login = max(logins) if logins else None
            res.append({
                'user_id': u['user_id'],
                'username': u['username'],
                'display_name': u['display_name'],
                'role': u['role'],
                'active': u['active'],
                'failed_count': u.get('failed_count', 0),
                'locked_until': u.get('locked_until'),
                'last_login_at': last_login,
            })
        return res

    def unlock_user(self, user_id: int) -> bool:
        for u in self.users.values():
            if u['user_id'] == user_id:
                u['failed_count'] = 0
                u['locked_until'] = None
                return True
        return False

    def activity(self, date_from: Any, date_to: Any, run_id: int) -> dict[str, Any]:
        return {
            'per_user_day': [],
            'run_progress': {'run_id': run_id, 'total_elrs': 402, 'approved': 0, 'rejected': 0, 'undecided': 402},
            'auth_per_day': [],
        }

    def audit_events(self, date_from: Any, date_to: Any, user_id: int | None, action: str | None, page: int) -> list[dict[str, Any]]:
        return []


@pytest.fixture
def fake_repo():
    return FakeRepo()


@pytest.fixture
def client(fake_repo):
    app.dependency_overrides[get_repo] = lambda: fake_repo
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _login(client, username="engineer1", password="ValidPassword123!"):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    csrf_token = resp.cookies.get("mark_csrf")
    return csrf_token


def test_requires_login(client):
    resp = client.get("/api/runs")
    assert resp.status_code == 401


def test_login_then_dashboard(client):
    csrf = _login(client)
    resp = client.get("/api/dashboard?run=18")
    assert resp.status_code == 200
    cards = resp.json()["cards"]
    assert set(cards.keys()) == {"TRUE", "WARNING", "ERROR", "HOLD"}


def test_elr_detail_hold_without_image(client):
    _login(client)
    resp = client.get("/api/elrs/ADI2607002?run=18")
    assert resp.status_code == 200
    data = resp.json()
    assert data["image_available"] is False
    assert data["job"]["processing_status"] == "HOLD"


def test_approve_blocked_then_allowed(client):
    csrf = _login(client)
    # Line 2 is DIFF without review -> approve blocked with 409
    resp = client.post(
        "/api/approvals",
        json={"run_id": 18, "elr_no": "ADI2607001", "decision": "APPROVED"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409
    assert resp.json()["blocked_lines"] == [2]

    # Post a non-draft review with reason and corrected mark
    rev_resp = client.post(
        "/api/reviews",
        json={
            "run_id": 18,
            "elr_no": "ADI2607001",
            "line_no": 2,
            "reason": "DB_WRONG",
            "note": "Correction",
            "corrected_mark": "NEW_MARK",
            "is_draft": False,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert rev_resp.status_code == 200

    # Now approve succeeds
    resp2 = client.post(
        "/api/approvals",
        json={"run_id": 18, "elr_no": "ADI2607001", "decision": "APPROVED"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp2.status_code == 200


def test_latest_decision_wins_and_all_audited(client, fake_repo):
    csrf = _login(client)
    # Review line 2 first
    client.post(
        "/api/reviews",
        json={
            "run_id": 18,
            "elr_no": "ADI2607001",
            "line_no": 2,
            "reason": "DB_WRONG",
            "note": "Fix",
            "corrected_mark": "NEW",
            "is_draft": False,
        },
        headers={"X-CSRF-Token": csrf},
    )

    client.post("/api/approvals", json={"run_id": 18, "elr_no": "ADI2607001", "decision": "APPROVED"}, headers={"X-CSRF-Token": csrf})
    client.post("/api/approvals", json={"run_id": 18, "elr_no": "ADI2607001", "decision": "REJECTED"}, headers={"X-CSRF-Token": csrf})
    client.post("/api/approvals", json={"run_id": 18, "elr_no": "ADI2607001", "decision": "APPROVED"}, headers={"X-CSRF-Token": csrf})

    latest = fake_repo.latest_approval(18, "ADI2607001")
    assert latest is not None and latest["decision"] == "APPROVED"
    approval_audits = [a for a in fake_repo.audit_data if a["action"] == "approval.saved"]
    assert len(approval_audits) == 3


def test_file_traversal_404(client, fake_repo):
    _login(client)
    fake_repo.snapshots_data[(18, "TRAV")] = {
        "run_id": 18,
        "elr_no": "TRAV",
        "abs_sha256": "x",
        "image_path": "../x",
    }
    resp = client.get("/api/files/abs/18/TRAV")
    assert resp.status_code == 404


def test_reviews_are_per_run(client, fake_repo):
    csrf = _login(client)
    # Save a review on run 18
    client.post(
        "/api/reviews",
        json={
            "run_id": 18,
            "elr_no": "ADI2607001",
            "line_no": 1,
            "reason": "OTHER",
            "note": "Review run 18",
            "corrected_mark": "VAL",
            "is_draft": False,
        },
        headers={"X-CSRF-Token": csrf},
    )
    # Setup run 19 for the same ELR
    fake_repo.snapshots_data[(19, "ADI2607001")] = dict(fake_repo.snapshots_data[(18, "ADI2607001")], run_id=19)
    fake_repo.lines_data[19] = [dict(fake_repo.lines_data[18][0], run_id=19)]
    fake_repo.jobs_data[19] = [dict(fake_repo.jobs_data[18][0], run_id=19)]

    resp19 = client.get("/api/elrs/ADI2607001?run=19")
    assert resp19.status_code == 200
    assert 1 not in resp19.json()["reviews"]


def test_hold_cannot_be_approved(client):
    csrf = _login(client)
    # Attempt approve on HOLD
    resp = client.post(
        "/api/approvals",
        json={"run_id": 18, "elr_no": "ADI2607002", "decision": "APPROVED"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409
    assert resp.json().get("reason") == "HOLD"

    # Reject on HOLD is allowed
    resp2 = client.post(
        "/api/approvals",
        json={"run_id": 18, "elr_no": "ADI2607002", "decision": "REJECTED"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp2.status_code == 200


def test_five_failures_lock(client):
    for _ in range(5):
        resp = client.post("/api/auth/login", json={"username": "engineer1", "password": "WrongPassword!"})
        assert resp.status_code == 401
    # 6th attempt with correct password
    resp6 = client.post("/api/auth/login", json={"username": "engineer1", "password": "ValidPassword123!"})
    assert resp6.status_code == 423


def test_post_without_csrf_403(client):
    _login(client)
    resp = client.post(
        "/api/reviews",
        json={"run_id": 18, "elr_no": "ADI2607001", "line_no": 1, "reason": "OTHER", "note": "x", "corrected_mark": "y", "is_draft": False},
    )
    assert resp.status_code == 403


def test_engineer_cannot_read_metrics(client, fake_repo):
    _login(client, username="engineer1")
    resp = client.get("/api/metrics")
    assert resp.status_code == 403

    # Fake API token with metrics:read
    raw_tok = "tok_test_metrics_12345"
    digest = hashlib.sha256(raw_tok.encode("utf-8")).hexdigest()
    fake_repo.api_tokens[digest] = {
        "token_id": 1,
        "name": "metrics_token",
        "scopes": ["metrics:read"],
        "expires_at": None,
    }

    client_no_cookies = TestClient(app)
    resp_tok = client_no_cookies.get("/api/metrics", headers={"Authorization": f"Bearer {raw_tok}"})
    assert resp_tok.status_code == 200
    assert "requests" in resp_tok.json()


def test_request_id_echoed(client):
    resp = client.get("/api/health", headers={"X-Request-ID": "test-req-id-123"})
    assert resp.headers.get("X-Request-ID") == "test-req-id-123"


def test_elr_detail_fixed_query_count(client, fake_repo):
    _login(client)
    fake_repo.call_count = 0
    resp = client.get("/api/elrs/ADI2607001?run=18")
    assert resp.status_code == 200
    assert fake_repo.call_count <= 4


def test_dashboard_without_redis_uses_database(client, fake_repo, monkeypatch):
    monkeypatch.setattr("mark_api.routers.validation.get_redis", lambda: None)
    clear_dashboard_cache()
    _login(client)
    initial_lines_calls = fake_repo.lines_call_count
    client.get("/api/dashboard?run=18")
    client.get("/api/dashboard?run=18")
    assert fake_repo.lines_call_count == initial_lines_calls + 2


def test_elrs_paged(client, fake_repo):
    _login(client)
    # Generate 120 fake jobs
    jobs = []
    lines = []
    for i in range(1, 121):
        elr = f"ADI2607{i:03d}"
        jobs.append({"run_id": 18, "elr_no": elr, "abs_no": f"ABS{i:03d}", "processing_status": "DONE", "hold_reason": ""})
        lines.append({"run_id": 18, "elr_no": elr, "line_no": 1, "status": "MATCH", "warning": "", "detail": ""})
    fake_repo.jobs_data[18] = jobs
    fake_repo.lines_data[18] = lines

    resp = client.get("/api/elrs?run=18&page=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 120
    assert len(data["rows"]) == 50
    assert data["page"] == 2


def test_cookie_attributes_and_rotation(client):
    login_resp = client.post("/api/auth/login", json={"username": "engineer1", "password": "ValidPassword123!"})
    assert login_resp.status_code == 200
    sess_header = ""
    csrf_header = ""
    for h, v in login_resp.headers.raw:
        if h.lower() == b"set-cookie":
            val = v.decode("latin1")
            if "mark_session=" in val:
                sess_header = val
            elif "mark_csrf=" in val:
                csrf_header = val

    assert "httponly" in sess_header.lower()
    assert "samesite=strict" in sess_header.lower()
    assert "path=/api" in sess_header.lower()
    assert "max-age=28800" in sess_header.lower()
    assert "domain" not in sess_header.lower()

    assert "httponly" not in csrf_header.lower()
    assert "path=/" in csrf_header.lower()

    # Second login rotates session
    old_cookie = client.cookies.get("mark_session")
    login_resp2 = client.post("/api/auth/login", json={"username": "engineer1", "password": "ValidPassword123!"})
    new_cookie = client.cookies.get("mark_session")
    assert old_cookie != new_cookie

    # Old cookie gets 401
    bad_client = TestClient(app)
    bad_client.cookies.set("mark_session", old_cookie)
    bad_resp = bad_client.get("/api/runs")
    assert bad_resp.status_code == 401

    # Logout sends Max-Age=0
    logout_resp = client.post("/api/auth/logout", headers={"X-CSRF-Token": client.cookies.get("mark_csrf")})
    assert logout_resp.status_code == 200
    for h, v in logout_resp.headers.raw:
        if h.lower() == b"set-cookie":
            assert "max-age=0" in v.decode("latin1").lower()


def test_csrf_from_other_session_rejected(client):
    # Session A
    clientA = TestClient(app)
    _login(clientA)
    tokenA = clientA.cookies.get("mark_csrf")

    # Session B
    clientB = TestClient(app)
    _login(clientB)
    tokenB = clientB.cookies.get("mark_csrf")

    # Use session A's cookies with session B's CSRF header
    resp = clientA.post(
        "/api/reviews",
        json={"run_id": 18, "elr_no": "ADI2607001", "line_no": 1, "reason": "OTHER", "note": "x", "corrected_mark": "y", "is_draft": False},
        headers={"X-CSRF-Token": tokenB},
    )
    assert resp.status_code == 403


def test_no_cors_by_default(client):
    resp = client.options("/api/runs", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in resp.headers

    # With MARK_CORS_ORIGINS
    os.environ["MARK_CORS_ORIGINS"] = "http://ok.example"
    try:
        resp_ok = client.options("/api/runs", headers={"Origin": "http://ok.example", "Access-Control-Request-Method": "GET"})
        assert resp_ok.headers.get("access-control-allow-origin") == "http://ok.example"
        resp_evil = client.options("/api/runs", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
        assert "access-control-allow-origin" not in resp_evil.headers
    finally:
        del os.environ["MARK_CORS_ORIGINS"]


# --- Fix-ups after the Task 1-6 review (2026-11-05) ---

def test_cross_origin_post_rejected(client):
    csrf = _login(client)
    body = {"run_id": 18, "elr_no": "ADI2607001", "line_no": 1, "reason": "OTHER", "note": "x",
            "corrected_mark": "y", "is_draft": True}
    resp = client.post("/api/reviews", json=body,
                       headers={"X-CSRF-Token": csrf, "Origin": "http://evil.example"})
    assert resp.status_code == 403 and resp.json()["detail"] == "Origin not allowed"
    same = client.post("/api/reviews", json=body,
                       headers={"X-CSRF-Token": csrf, "Origin": "http://testserver"})
    assert same.status_code != 403


def test_invalid_bearer_does_not_fall_back_to_cookie(client):
    _login(client)
    resp = client.get("/api/runs", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_secure_cookie_names(monkeypatch):
    from mark_api.deps import get_cookie_name
    monkeypatch.setenv("MARK_COOKIE_SECURE", "true")
    assert get_cookie_name("mark_session") == "__Secure-mark_session"   # Path=/api cannot use __Host-
    assert get_cookie_name("mark_csrf") == "__Host-mark_csrf"


def test_metrics_key_on_route_template(client):
    from mark_api.app import metrics
    _login(client)
    client.get("/api/elrs/ADI2607001", params={"run": 18})
    assert "/api/elrs/{elr}" in metrics.durations
    assert not any(k.startswith("/api/elrs/ADI") for k in metrics.durations)


def test_http_request_logged_with_request_id_and_template(client, capsys):
    _login(client)
    capsys.readouterr()
    client.get("/api/elrs/ADI2607001", params={"run": 18}, headers={"X-Request-ID": "req_fixed_1"})
    events = [json.loads(l) for l in capsys.readouterr().out.splitlines() if l.startswith("{")]
    http = [e for e in events if e["event"] == "http.request"]
    assert http and http[-1]["route"] == "/api/elrs/{elr}" and http[-1]["request_id"] == "req_fixed_1"


def test_failed_login_log_has_no_username(client, capsys):
    client.post("/api/auth/login", json={"username": "someone_secret", "password": "wrong-password-1"})
    out = capsys.readouterr().out
    assert "auth.login_failed" in out and "someone_secret" not in out


def test_review_audit_carries_ip_and_request_id(client, fake_repo):
    csrf = _login(client)
    client.post("/api/reviews",
                json={"run_id": 18, "elr_no": "ADI2607001", "line_no": 1, "reason": "OTHER",
                      "note": "n", "corrected_mark": "VAL", "is_draft": False},
                headers={"X-CSRF-Token": csrf, "X-Real-IP": "10.0.0.7", "X-Request-ID": "req-test-1"})
    row = fake_repo.audit_data[-1]
    assert row["action"] == "review.saved"
    assert row["client_ip"] == "10.0.0.7"          # sent as X-Real-IP header
    assert row["request_id"] == "req-test-1"       # sent as X-Request-ID header


def test_unknown_user_audited_without_name(client, fake_repo, capsys):
    client.post("/api/auth/login", json={"username": "nobody-xyz", "password": "x" * 12},
                headers={"X-Real-IP": "10.0.0.9"})
    row = fake_repo.audit_data[-1]
    assert (row["action"], row["user_id"], row["detail"]["reason"], row["client_ip"]) == \
           ("auth.login_failed", None, "unknown_user", "10.0.0.9")
    assert "nobody-xyz" not in json.dumps(fake_repo.audit_data, default=str) + capsys.readouterr().out


def test_fifth_failure_audits_failed_and_locked(client, fake_repo):
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "engineer1", "password": "WrongPassword!"})
    actions = [r["action"] for r in fake_repo.audit_data]
    assert actions.count("auth.login_failed") == 5 and actions[-1] == "auth.locked"
    assert fake_repo.audit_data[-2]["detail"] == {"reason": "bad_password", "failed_count": 5}


def test_locked_and_inactive_attempts_audited(client, fake_repo):
    u = fake_repo.users["engineer1"]
    u["locked_until"] = datetime.now(timezone.utc) + timedelta(minutes=10)
    client.post("/api/auth/login", json={"username": "engineer1", "password": "ValidPassword123!"})
    assert fake_repo.audit_data[-1]["detail"] == {"reason": "locked"}
    u["locked_until"], u["active"] = None, False
    client.post("/api/auth/login", json={"username": "engineer1", "password": "ValidPassword123!"})
    assert fake_repo.audit_data[-1]["detail"] == {"reason": "inactive"}


def test_expired_session_audited_once(client, fake_repo):
    _login(client)
    for s in fake_repo.sessions.values():
        s["last_seen_at"] -= timedelta(minutes=61)
    assert client.get("/api/runs").status_code == 401
    assert client.get("/api/runs").status_code == 401
    rows = [r for r in fake_repo.audit_data if r["action"] == "auth.session_expired"]
    assert len(rows) == 1 and rows[0]["detail"] == {"why": "idle"}


def test_audit_failure_does_not_break_login(client, fake_repo, monkeypatch):
    monkeypatch.setattr(fake_repo, "audit", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    assert client.post("/api/auth/login", json={"username": "engineer1", "password": "ValidPassword123!"}).status_code == 200


def test_admin_routes_forbidden_for_engineer(client):
    _login(client)
    assert client.get("/api/admin/users").status_code == 403


def test_admin_unlock_clears_lock_and_audits(client, fake_repo):
    fake_repo.users["engineer1"].update(failed_count=5, locked_until=datetime.now(timezone.utc) + timedelta(minutes=15))
    csrf = _login(client, "admin1")
    uid = fake_repo.users["engineer1"]["user_id"]
    assert client.post(f"/api/admin/users/{uid}/unlock").status_code == 403                    # no CSRF header
    r = client.post(f"/api/admin/users/{uid}/unlock", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and fake_repo.users["engineer1"]["locked_until"] is None
    assert fake_repo.audit_data[-1]["detail"] == {"target_user_id": uid}
    assert client.post("/api/admin/users/99999/unlock", headers={"X-CSRF-Token": csrf}).status_code == 404


def test_admin_users_state(client, fake_repo):
    _login(client, "admin1")
    states = {u["username"]: u["state"] for u in client.get("/api/admin/users").json()}
    assert states["engineer1"] == "OK"


def test_admin_activity_range_validation(client):
    _login(client, "admin1")
    assert client.get("/api/admin/activity?from=2026-01-01&to=2026-06-01").status_code == 422   # > 92 days
    assert client.get("/api/admin/activity?from=2026-11-05&to=2026-11-01").status_code == 422   # from > to
    assert client.get("/api/admin/activity?from=bad").status_code == 422
    assert client.get("/api/admin/activity").status_code == 200




def test_elrs_and_detail_handle_null_text_fields(client, fake_repo):
    for l in fake_repo.lines_data[18]:
        l.update(warning=None, detail=None, compare_rules=None)
    for j in fake_repo.jobs_data[18]:
        j.update(hold_reason=None, hold_detail=None, abs_no=None)
    _login(client)
    r = client.get("/api/elrs?run=18&page=1")
    assert r.status_code == 200 and r.json()["total"] >= 1
    assert client.get("/api/elrs?run=18&q=adi").status_code == 200
    assert client.get("/api/elrs/ADI2607001?run=18").status_code == 200


def test_metrics_counts_logins(client, fake_repo):
    from mark_api.metrics import metrics
    raw_tok = "tok_test_metrics_12345"
    digest = hashlib.sha256(raw_tok.encode("utf-8")).hexdigest()
    fake_repo.api_tokens[digest] = {
        "token_id": 2,
        "name": "metrics_token_2",
        "scopes": ["metrics:read"],
        "expires_at": None,
    }
    before = metrics.login_failed
    client.post("/api/auth/login", json={"username": "engineer1", "password": "WrongPassword!"})
    _login(client)
    body = client.get("/api/metrics", headers={"Authorization": f"Bearer {raw_tok}"}).json()
    assert body["login_failed"] == before + 1 and body["login_ok"] >= 1
    assert "active_sessions" in body and "rate_limited" not in body



def test_review_uses_line_key_not_snapshot_abs(client, fake_repo):
    # Real DB: job/snapshot abs is "ABS071169-ENG-2" while line_result.abs_no is "ABS071169";
    # line_review's FK is (run_id, elr_no, abs_no, side, line_no) -> line_result.
    fake_repo.snapshots_data[(18, "ADI2607001")]["abs_file"] = "ABS071290-ENG-2"
    csrf = _login(client)
    body = {"run_id": 18, "elr_no": "ADI2607001", "reason": "OTHER", "corrected_mark": "MARK1"}
    r = client.post("/api/reviews", json=dict(body, line_no=1), headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    saved = fake_repo.reviews_data[-1]
    assert (saved["abs_no"], saved["side"], saved["line_no"]) == ("ABS071290", "TOP", 1)
    n = len(fake_repo.reviews_data)
    r = client.post("/api/reviews", json=dict(body, line_no=99), headers={"X-CSRF-Token": csrf})
    assert r.status_code == 404 and len(fake_repo.reviews_data) == n


def test_review_invalidates_dashboard_after_save(client, monkeypatch):
    from mark_api.routers import workflow
    events = []
    monkeypatch.setattr(workflow, "notify_revision", lambda *args: events.append(args), raising=False)
    csrf = _login(client)
    body = {"run_id": 18, "elr_no": "ADI2607001", "line_no": 1, "reason": "OTHER"}
    assert client.post("/api/reviews", json=body, headers={"X-CSRF-Token": csrf}).status_code == 200
    assert events == [(18, "ADI2607001", None)]


def test_dashboard_without_redis_accepts_multiple_runs(client, fake_repo, monkeypatch):
    monkeypatch.setattr("mark_api.routers.validation.get_redis", lambda: None)
    _login(client)
    for run in range(100, 109):
        assert client.get(f"/api/dashboard?run={run}").status_code == 200


def test_websocket_requires_session(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws/events", headers={"origin": "http://testserver"}):
            pass


def test_websocket_rejects_cross_origin(client):
    from starlette.websockets import WebSocketDisconnect
    _login(client)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws/events", headers={"origin": "http://other.example"}):
            pass


def test_websocket_sends_revision_event_for_authenticated_user(client, fake_repo, monkeypatch):
    from mark_api.routers import ws

    class PubSub:
        async def subscribe(self, channel):
            assert channel == "mark_events"
        async def get_message(self, **kwargs):
            return {"type": "message", "data": '{"run_id": 21}'}
        async def aclose(self):
            pass

    class Redis:
        def pubsub(self):
            return PubSub()

    monkeypatch.setattr(ws, "get_async_redis", lambda: Redis())
    _login(client)
    touches = []
    monkeypatch.setattr(fake_repo, "touch_session", lambda *args: touches.append(1))
    with client.websocket_connect("/api/ws/events", headers={"origin": "http://testserver"}) as socket:
        assert socket.receive_json()["run_id"] == 21
    assert touches == []


def test_websocket_revalidates_without_disconnecting_valid_session(client, monkeypatch):
    import asyncio
    from mark_api.routers import ws

    class PubSub:
        calls = 0
        async def subscribe(self, channel):
            pass
        async def get_message(self, **kwargs):
            await asyncio.sleep(0.01)
            self.calls += 1
            return {"type": "message", "data": '{"run_id": 21}'} if self.calls == 5 else None
        async def aclose(self):
            pass

    class Redis:
        def pubsub(self):
            return PubSub()

    checks = []
    monkeypatch.setattr(ws, "_session_authorized", lambda socket: checks.append(1) or True)
    monkeypatch.setattr(ws, "REVALIDATE_INTERVAL", 0.02)
    monkeypatch.setattr(ws, "get_async_redis", lambda: Redis())
    with client.websocket_connect("/api/ws/events", headers={"origin": "http://testserver"}) as socket:
        assert socket.receive_json()["run_id"] == 21
    assert len(checks) >= 2


def test_websocket_closes_when_session_is_revoked(client, monkeypatch):
    import asyncio
    from mark_api.routers import ws
    from starlette.websockets import WebSocketDisconnect

    class PubSub:
        async def subscribe(self, channel):
            pass
        async def get_message(self, **kwargs):
            await asyncio.sleep(0.01)
        async def aclose(self):
            pass

    class Redis:
        def pubsub(self):
            return PubSub()

    statuses = iter([True, False])
    monkeypatch.setattr(ws, "_session_authorized", lambda socket: next(statuses))
    monkeypatch.setattr(ws, "REVALIDATE_INTERVAL", 0.02)
    monkeypatch.setattr(ws, "get_async_redis", lambda: Redis())
    with client.websocket_connect("/api/ws/events", headers={"origin": "http://testserver"}) as socket:
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()

