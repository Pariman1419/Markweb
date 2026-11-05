from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import pytest

API_DIR = Path(__file__).resolve().parents[2] / "services" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from mark_api.grouping import classify_line, classify_job, summarize
from mark_api.workflow import approve_blockers
from mark_api.auth import (
    hash_password,
    verify_password,
    login_state,
    new_token,
    session_valid,
    csrf_ok,
    can,
)
from mark_api.logging import log_event
from mark_api.files import safe_file


def test_classify_line():
    assert classify_line("MATCH", "") == "TRUE"
    assert classify_line("MATCH", "CASE_DIFF: …") == "WARNING"
    assert classify_line("NEEDS_REVIEW", "") == "WARNING"
    assert classify_line("DIFF", "") == "ERROR"
    assert classify_line("NOT_ELIGIBLE", "") == "NONE"


def test_summarize_counts_failed_job_as_error_and_hold_by_elr():
    s = summarize(
        [{"elr_no": "ADI2607001", "line_no": 1, "status": "MATCH", "warning": "", "detail": ""}],
        [
            {"elr_no": "ADI2607001", "processing_status": "DONE", "hold_reason": ""},
            {"elr_no": "ADI2607002", "processing_status": "HOLD", "hold_reason": "BOM_NOT_FOUND: x"},
        ],
    )
    assert s["cards"]["TRUE"]["count"] == 1 and s["cards"]["HOLD"]["count"] == 1
    assert s["hold_causes"] == [{"cause": "BOM_NOT_FOUND", "count": 1}]
    assert s["monthly"][0]["month"] == "2026-07"


def test_approve_blocked_until_error_line_has_reason_and_value():
    lines = [{"line_no": 2, "status": "DIFF", "warning": ""}]
    assert approve_blockers(lines, {}) == [2]
    assert approve_blockers(lines, {2: {"reason": "DB_WRONG", "corrected_mark": "X", "is_draft": True}}) == [2]
    assert approve_blockers(lines, {2: {"reason": "DB_WRONG", "corrected_mark": "X", "is_draft": False}}) == []


def test_lock_after_five_failures():
    now = datetime(2026, 11, 5, tzinfo=timezone.utc)
    assert login_state({"active": True, "locked_until": now + timedelta(minutes=15)}, now) == "LOCKED"


def test_session_idle_and_absolute_expiry():
    now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
    assert session_valid({"expires_at": now + timedelta(hours=1), "last_seen_at": now - timedelta(minutes=59)}, now)
    assert not session_valid({"expires_at": now + timedelta(hours=1), "last_seen_at": now - timedelta(minutes=61)}, now)
    assert not session_valid({"expires_at": now - timedelta(seconds=1), "last_seen_at": now}, now)


def test_csrf_and_roles():
    assert csrf_ok("a", "a") and not csrf_ok("a", None) and not csrf_ok(None, None)
    assert can("engineer", "approve") and not can("engineer", "metrics")
    assert can("admin", "metrics") and not can("admin", "approve")


def test_log_event_drops_sensitive_fields(capsys):
    log_event("auth.login_failed", user_id=None, password="x", token="y", elr_no="ADI2607001")
    line = json.loads(capsys.readouterr().out)
    assert line["event"] == "auth.login_failed" and line["elr_no"] == "ADI2607001"
    assert "password" not in line and "token" not in line


def test_safe_file_rejects_traversal(tmp_path):
    (tmp_path / "abs").mkdir()
    (tmp_path / "abs" / "a.png").write_bytes(b"x")
    assert safe_file(tmp_path, "abs/a.png") is not None
    assert safe_file(tmp_path, "../secret") is None and safe_file(tmp_path, "C:/Windows/win.ini") is None
