"""Unit tests for Scan, Lookup, Oracle-Check, Re-check, and Notifications API."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
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


class FakeScansRepo:
    def __init__(self):
        self.users: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.api_tokens: dict[str, dict[str, Any]] = {}
        self.audit_log: list[dict[str, Any]] = []
        self.scans: list[dict[str, Any]] = []
        self.work_items: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []
        self.notification_reads: set[tuple[int, int]] = set()  # (notif_id, user_id)
        self.revisions: list[dict[str, Any]] = []
        self.locked_scan: bool = False

    def add_user(self, username: str, role: str = "engineer", active: bool = True) -> int:
        uid = len(self.users) + 1
        self.users[username] = {
            "user_id": uid,
            "username": username,
            "display_name": username.title(),
            "role": role,
            "is_active": active,
            "failed_attempts": 0,
            "locked_until": None,
        }
        return uid

    def add_token(self, name: str, scopes: list[str], raw_token: str) -> None:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        self.api_tokens[token_hash] = {
            "name": name,
            "token_hash": token_hash,
            "scopes": scopes,
            "created_by": 1,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=30),
        }

    def token_by_hash(self, token_hash: str) -> dict[str, Any] | None:
        return self.api_tokens.get(token_hash)

    def session_user(self, token_hash: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        sess = self.sessions.get(token_hash)
        if not sess:
            return None
        user = next((u for u in self.users.values() if u["user_id"] == sess["user_id"]), None)
        return (sess, user) if user else None

    def touch_session(self, token_hash: str) -> None:
        if token_hash in self.sessions:
            self.sessions[token_hash]["last_seen_at"] = datetime.now(timezone.utc)

    def delete_session(self, token_hash: str) -> None:
        self.sessions.pop(token_hash, None)

    def audit(self, user_id: int | None, action: str, client_ip: str | None = None,
              request_id: str | None = None, run_id: int | None = None,
              elr_no: str | None = None, line_no: int | None = None,
              detail: dict[str, Any] | None = None) -> None:
        self.audit_log.append({
            "user_id": user_id,
            "action": action,
            "client_ip": client_ip,
            "request_id": request_id,
            "run_id": run_id,
            "elr_no": elr_no,
            "detail": detail,
        })

    def try_scan_lock(self) -> bool:
        if self.locked_scan:
            return False
        self.locked_scan = True
        return True

    def release_scan_lock(self) -> None:
        self.locked_scan = False

    def last_successful_scan(self, source: str = "airflow") -> dict[str, Any] | None:
        matching = [s for s in self.scans if s.get("source") == source and s.get("finished_at")]
        return matching[-1] if matching else None

    def record_scan(self, source: str, requested_by: str | None, from_ts: datetime | None,
                    to_ts: datetime | None, counts: dict[str, Any], error: str | None = None) -> int:
        scan_id = len(self.scans) + 1
        now = datetime.now(timezone.utc)
        self.scans.append({
            "scan_id": scan_id,
            "source": source,
            "requested_by": requested_by,
            "from_ts": from_ts,
            "to_ts": to_ts,
            "counts": counts,
            "started_at": now,
            "finished_at": now if not error else None,
            "error": error,
        })
        return scan_id

    def enqueue_work_item(self, scan_id: int | None, elr_no: str, reason: str) -> bool:
        # Check active items
        for item in self.work_items:
            if item["elr_no"] == elr_no and item["state"] in ("queued", "running", "retry"):
                return False
        item_id = len(self.work_items) + 1
        now = datetime.now(timezone.utc)
        self.work_items.append({
            "item_id": item_id,
            "scan_id": scan_id,
            "elr_no": elr_no,
            "state": "queued",
            "reason": reason,
            "created_at": now,
        })
        return True

    def get_elr_history(self, elr_no: str) -> dict[str, Any]:
        revs = [r for r in self.revisions if r["elr_no"] == elr_no]
        queued = any(w["elr_no"] == elr_no and w["state"] in ("queued", "running", "retry") for w in self.work_items)
        if not revs:
            return {"in_system": False, "latest": None, "revisions": [], "queued": queued}
        sorted_revs = sorted(revs, key=lambda r: r["revision"])
        latest = sorted_revs[-1]
        return {
            "in_system": True,
            "latest": {
                "run_id": latest["run_id"],
                "revision": latest["revision"],
                "status": latest.get("status", "DONE"),
                "created_at": latest.get("created_at"),
            },
            "revisions": sorted_revs,
            "queued": queued,
        }

    def add_notification(self, elr_no: str, kind: str, run_id: int | None = None, revision: int | None = None, message: str = "") -> None:
        notif_id = len(self.notifications) + 1
        self.notifications.append({
            "id": notif_id,
            "elr_no": elr_no,
            "kind": kind,
            "run_id": run_id,
            "revision": revision,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    def list_notifications(self, user_id: int, unread_only: bool = True) -> list[dict[str, Any]]:
        res = []
        for n in self.notifications:
            is_read = (n["id"], user_id) in self.notification_reads
            if unread_only and is_read:
                continue
            res.append({**n, "read": is_read})
        return res

    def mark_notification_read(self, notif_id: int, user_id: int) -> bool:
        exists = any(n["id"] == notif_id for n in self.notifications)
        if not exists:
            return False
        self.notification_reads.add((notif_id, user_id))
        return True


@pytest.fixture
def repo(monkeypatch):
    r = FakeScansRepo()
    app.dependency_overrides[get_repo] = lambda: r
    yield r
    app.dependency_overrides.pop(get_repo, None)


@pytest.fixture
def client(repo):
    return TestClient(app)


def auth_cookies(repo, username="alice", role="engineer"):
    uid = repo.add_user(username, role)
    raw_token = f"tok_{username}"
    raw_csrf = f"csrf_{username}"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    csrf_hash = hashlib.sha256(raw_csrf.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    repo.sessions[token_hash] = {
        "user_id": uid,
        "csrf_hash": csrf_hash,
        "expires_at": now + timedelta(days=1),
        "created_at": now,
        "last_seen_at": now,
    }
    return {"mark_session": raw_token, "mark_csrf": raw_csrf}, {"X-CSRF-Token": raw_csrf}


def test_scan_requires_scan_write_scope(client, repo, monkeypatch):
    """POST /api/scans requires Bearer token with scan:write scope."""
    monkeypatch.setattr("mark_api.routers.scans.connect_actl", lambda: None)
    monkeypatch.setattr("mark_api.routers.scans.fetch_window", lambda *args, **kwargs: [])

    # 1. Invalid / no bearer token -> 401
    resp = client.post("/api/scans", json={"source": "airflow"}, headers={"Authorization": "Bearer invalid_tok"})
    assert resp.status_code == 401

    # 2. Token with metrics:read scope only -> 403
    repo.add_token("metrics_tok", ["metrics:read"], "token_metrics_123")
    resp = client.post(
        "/api/scans",
        json={"source": "airflow"},
        headers={"Authorization": "Bearer token_metrics_123"},
    )
    assert resp.status_code == 403

    # 3. Token with scan:write scope -> proceeds
    repo.add_token("scan_tok", ["scan:write"], "token_scan_123")
    resp = client.post(
        "/api/scans",
        json={"source": "airflow", "from_ts": "2026-11-01T00:00:00Z", "to_ts": "2026-11-02T00:00:00Z"},
        headers={"Authorization": "Bearer token_scan_123"},
    )
    assert resp.status_code in (200, 201)
    assert "counts" in resp.json()


def test_scan_window_from_watermark_minus_5min(client, repo, monkeypatch):
    """Airflow scan window automatically sets from_ts = last_scan.to_ts - 5min."""
    repo.add_token("scan_tok", ["scan:write"], "token_scan_123")
    t0 = datetime(2026, 11, 5, 12, 0, 0, tzinfo=timezone.utc)
    repo.record_scan("airflow", "airflow_job", from_ts=t0 - timedelta(hours=1), to_ts=t0, counts={})

    recorded_window = []

    def mock_fetch_window(conn, from_ts, to_ts):
        recorded_window.append((from_ts, to_ts))
        return []

    monkeypatch.setattr("mark_api.routers.scans.fetch_window", mock_fetch_window)
    monkeypatch.setattr("mark_api.routers.scans.connect_actl", lambda: object())

    resp = client.post(
        "/api/scans",
        json={"source": "airflow"},
        headers={"Authorization": "Bearer token_scan_123"},
    )
    assert resp.status_code in (200, 201)
    assert len(recorded_window) == 1
    from_ts, to_ts = recorded_window[0]
    expected_from = t0 - timedelta(minutes=5)
    assert abs((from_ts - expected_from).total_seconds()) < 1.0


def test_concurrent_scan_returns_409(client, repo):
    """Running a second scan while one is active returns 409 Conflict."""
    repo.add_token("scan_tok", ["scan:write"], "token_scan_123")
    repo.locked_scan = True

    resp = client.post(
        "/api/scans",
        json={"source": "airflow"},
        headers={"Authorization": "Bearer token_scan_123"},
    )
    assert resp.status_code == 409


def test_lookup_not_in_system(client, repo):
    """GET /api/elrs/lookup returns in_system=false when ELR not in DB."""
    cookies, headers = auth_cookies(repo)
    resp = client.get("/api/elrs/lookup?elr=ADI9999999", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()
    assert data["in_system"] is False
    assert data["latest"] is None
    assert data["queued"] is False


def test_oracle_check_not_found_notifies(client, repo, monkeypatch):
    """POST /api/elrs/{elr}/oracle-check not found in Oracle -> notification + 404."""
    cookies, headers = auth_cookies(repo)
    monkeypatch.setattr("mark_api.routers.scans.fetch_one", lambda conn, elr: None)
    monkeypatch.setattr("mark_api.routers.scans.connect_actl", lambda: "mock_oracle_conn")

    resp = client.post("/api/elrs/ADI9999999/oracle-check", cookies=cookies, headers=headers)
    assert resp.status_code == 404
    data = resp.json()
    assert "not_found_in_oracle" in data.get("detail", "")
    assert any(n["kind"] == "not_in_oracle" and n["elr_no"] == "ADI9999999" for n in repo.notifications)


def test_oracle_check_not_eligible_returns_reason(client, repo, monkeypatch):
    """POST /api/elrs/{elr}/oracle-check not eligible (G0) -> 200 {queued:false, reason}."""
    cookies, headers = auth_cookies(repo)
    monkeypatch.setattr("mark_api.routers.scans.connect_actl", lambda: "mock_oracle_conn")
    monkeypatch.setattr(
        "mark_api.routers.scans.fetch_one",
        lambda conn, elr: {"ELR_NO": elr, "STATUS": "C", "CURRENT_STEP": "6"},
    )

    resp = client.post("/api/elrs/ADI2601001/oracle-check", cookies=cookies, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["queued"] is False
    assert data["reason"] == "STATUS_C"
    assert any(n["kind"] == "not_eligible" and n["elr_no"] == "ADI2601001" for n in repo.notifications)


def test_recheck_requires_csrf_and_role(client, repo):
    """POST /api/elrs/{elr}/recheck requires CSRF and role in (engineer, mark_eng_approver, admin)."""
    # 1. Missing CSRF -> 403
    cookies, headers = auth_cookies(repo, role="engineer")
    resp = client.post("/api/elrs/ADI2601001/recheck", cookies=cookies)
    assert resp.status_code == 403

    # 2. Wrong role (e.g. operator) -> 403
    cookies_op, headers_op = auth_cookies(repo, username="bob", role="operator")
    resp = client.post("/api/elrs/ADI2601001/recheck", cookies=cookies_op, headers=headers_op)
    assert resp.status_code == 403

    # 3. Valid role & CSRF -> 200 and queued with reason=recheck
    resp = client.post("/api/elrs/ADI2601001/recheck", cookies=cookies, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"queued": True}
    assert any(w["elr_no"] == "ADI2601001" and w["reason"] == "recheck" for w in repo.work_items)


def test_notifications_read_is_per_user(client, repo):
    """GET /api/notifications and POST /api/notifications/{id}/read is per user."""
    u1_cookies, u1_headers = auth_cookies(repo, username="user1", role="engineer")
    u2_cookies, u2_headers = auth_cookies(repo, username="user2", role="engineer")

    repo.add_notification("ADI2601001", "hold")
    notif_id = repo.notifications[0]["id"]

    # user1 reads notification
    resp = client.post(f"/api/notifications/{notif_id}/read", cookies=u1_cookies, headers=u1_headers)
    assert resp.status_code == 200

    # user1 unread list is now empty
    resp1 = client.get("/api/notifications?unread=1", cookies=u1_cookies)
    assert len(resp1.json()) == 0

    # user2 unread list still sees it
    resp2 = client.get("/api/notifications?unread=1", cookies=u2_cookies)
    assert len(resp2.json()) == 1
    assert resp2.json()[0]["id"] == notif_id
