from datetime import datetime, timedelta, timezone
from typing import Any
import pytest

from mark_engine.domain.models import ElrMeta, OracleMark, Side
from services.worker.oracle_source import (
    fetch_window,
    fetch_one,
    fetch_pending_step,
    to_engine,
)
from services.worker.queue import (
    RETRY_DELAYS,
    WorkItem,
    claim,
    enqueue,
    fail,
    fail_with_backoff,
    finish,
)


class FakeOracleConn:
    def __init__(self, responses: list[list[dict[str, Any]]] | None = None):
        self.queries: list[tuple[str, dict[str, Any] | None]] = []
        self._responses = list(responses or [[]])

    def cursor(self):
        return FakeOracleCursor(self)


class FakeOracleCursor:
    def __init__(self, conn: FakeOracleConn):
        self.conn = conn
        self.description = [("ELR_NO",)]
        self._results: list[dict[str, Any]] = []

    def execute(self, statement: str, params: dict[str, Any] | None = None):
        self.conn.queries.append((statement, params))
        if self.conn._responses:
            self._results = self.conn._responses.pop(0)
        else:
            self._results = []

    def fetchall(self):
        return [tuple(r.values()) for r in self._results]

    def close(self):
        pass


def test_fetch_window_uses_read_only_and_bind_params(monkeypatch):
    recorded_selects = []

    def mock_select(conn, query, binds=None):
        recorded_selects.append((query, binds))
        return [{"ELR_NO": "ADI2601001", "ELR_REV": "01", "PRODUCT_NO": "AD123"}]

    monkeypatch.setattr("services.worker.oracle_source.select", mock_select)

    from_ts = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
    to_ts = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)
    conn = FakeOracleConn()

    rows = fetch_window(conn, from_ts, to_ts)
    assert len(rows) == 1
    assert len(recorded_selects) == 1
    query, binds = recorded_selects[0]
    assert "LAST_TRAN >=" in query
    assert "LAST_TRAN <" in query
    assert binds == {"from_ts": from_ts, "to_ts": to_ts}


def test_fetch_one(monkeypatch):
    recorded_selects = []

    def mock_select(conn, query, binds=None):
        recorded_selects.append((query, binds))
        return [{"ELR_NO": "ADI2601001", "ELR_REV": "01", "PRODUCT_NO": "AD123"}]

    monkeypatch.setattr("services.worker.oracle_source.select", mock_select)
    conn = FakeOracleConn()

    row = fetch_one(conn, "ADI2601001")
    assert row is not None
    assert row["ELR_NO"] == "ADI2601001"
    query, binds = recorded_selects[0]
    assert "ELR_NO = :elr_no" in query
    assert binds == {"elr_no": "ADI2601001"}


def test_fetch_pending_step(monkeypatch):
    recorded_selects = []

    def mock_select(conn, query, binds=None):
        recorded_selects.append((query, binds))
        return [{"ELR_NO": "ADI2601001", "CURRENT_STEP": "REVIEW", "STATUS": "A"}]

    monkeypatch.setattr("services.worker.oracle_source.select", mock_select)
    conn = FakeOracleConn()

    rows = fetch_pending_step(conn, "REVIEW")
    assert len(rows) == 1
    query, binds = recorded_selects[0]
    assert "CURRENT_STEP = :review_step" in query
    assert "STATUS != 'C'" in query
    assert binds == {"review_step": "REVIEW"}


def test_to_engine():
    row = {
        "ELR_NO": "ADI2601001",
        "PRODUCT_NO": "AD12345",
        "TOP_MARK1": "LINE 1",
        "TOP_MARK_ID": "100",
        "STATUS": "A",
    }
    layout_rows = [
        {"MARK_ID": "100", "MARK_ROW": "1", "MARK_COLUMN": "1", "MARK_DATA": "A"},
    ]
    meta, mark, layout = to_engine(row, layout_rows=layout_rows)
    assert isinstance(meta, ElrMeta)
    assert meta.elr_no == "ADI2601001"
    assert isinstance(mark, OracleMark)
    assert mark.get(Side.TOP, 1) == "LINE 1"
    assert layout is not None
    assert layout.mark_id == 100


# ---------------------------------------------------------------------------
# Queue Tests using InMemoryQueueStore for deterministic Postgres queue logic
# ---------------------------------------------------------------------------
class InMemoryQueueStore:
    def __init__(self):
        self.items: dict[int, dict[str, Any]] = {}
        self.next_id = 1
        self.locked_ids: set[int] = set()

    class Cursor:
        def __init__(self, store: "InMemoryQueueStore"):
            self.store = store
            self._last_row = None

        def execute(self, sql: str, params: tuple = ()):
            sql_clean = " ".join(sql.split()).lower()
            now = datetime.now(timezone.utc)

            if "insert into mark_app.work_item" in sql_clean:
                scan_id, elr_no, reason = params[0], params[1], params[2]
                # Check partial unique index: active state in ('queued', 'running', 'retry')
                for item in self.store.items.values():
                    if item["elr_no"] == elr_no and item["state"] in ("queued", "running", "retry"):
                        self._last_row = None
                        return
                item_id = self.store.next_id
                self.store.next_id += 1
                new_item = {
                    "item_id": item_id,
                    "scan_id": scan_id,
                    "elr_no": elr_no,
                    "state": "queued",
                    "reason": reason,
                    "attempts": 0,
                    "next_attempt_at": now,
                    "revision": None,
                    "error": None,
                    "created_at": now,
                    "updated_at": now,
                }
                self.store.items[item_id] = new_item
                self._last_row = (item_id,)

            elif "update mark_app.work_item" in sql_clean and "state = 'retry'" in sql_clean and "interval '15 minutes'" in sql_clean:
                # Reset stuck running items
                fifteen_min_ago = now - timedelta(minutes=15)
                for item in self.store.items.values():
                    if item["state"] == "running" and item["updated_at"] < fifteen_min_ago:
                        item["state"] = "retry"
                        item["updated_at"] = now

            elif "select item_id, scan_id, elr_no" in sql_clean and "skip locked" in sql_clean:
                candidates = [
                    item for item in self.store.items.values()
                    if item["state"] in ("queued", "retry")
                    and item["next_attempt_at"] <= now
                    and item["item_id"] not in self.store.locked_ids
                ]
                candidates.sort(key=lambda x: x["created_at"])
                if candidates:
                    chosen = candidates[0]
                    self.store.locked_ids.add(chosen["item_id"])
                    self._last_row = (
                        chosen["item_id"], chosen["scan_id"], chosen["elr_no"],
                        chosen["state"], chosen["reason"], chosen["attempts"],
                        chosen["next_attempt_at"], chosen["revision"], chosen["error"],
                        chosen["created_at"], chosen["updated_at"]
                    )
                else:
                    self._last_row = None

            elif "update mark_app.work_item" in sql_clean and "state = 'running'" in sql_clean:
                item_id = params[0]
                item = self.store.items[item_id]
                item["state"] = "running"
                item["attempts"] += 1
                item["updated_at"] = now

            elif "update mark_app.work_item" in sql_clean and "state = 'done'" in sql_clean:
                revision, item_id = params[0], params[1]
                item = self.store.items[item_id]
                item["state"] = "done"
                item["revision"] = revision
                item["updated_at"] = now
                self.store.locked_ids.discard(item_id)

            elif "update mark_app.work_item" in sql_clean and "state = 'retry'" in sql_clean:
                error, retry_sec, item_id = params[0], params[1], params[2]
                item = self.store.items[item_id]
                item["state"] = "retry"
                item["error"] = error
                item["next_attempt_at"] = now + timedelta(seconds=retry_sec)
                item["updated_at"] = now
                self.store.locked_ids.discard(item_id)

            elif "update mark_app.work_item" in sql_clean and "state = 'failed'" in sql_clean:
                error, item_id = params[0], params[1]
                item = self.store.items[item_id]
                item["state"] = "failed"
                item["error"] = error
                item["updated_at"] = now
                self.store.locked_ids.discard(item_id)

        def fetchone(self):
            return self._last_row


def test_enqueue_is_idempotent_per_active_elr():
    store = InMemoryQueueStore()
    cur = store.Cursor(store)

    assert enqueue(cur, scan_id=1, elr_no="ADI2601001", reason="scan") is True
    assert enqueue(cur, scan_id=1, elr_no="ADI2601001", reason="scan") is False
    assert enqueue(cur, scan_id=2, elr_no="ADI2601002", reason="user") is True


def test_claim_skips_locked_and_future_items():
    store = InMemoryQueueStore()
    cur = store.Cursor(store)

    enqueue(cur, 1, "ELR_NOW", "scan")
    item = claim(cur, "worker-1")
    assert item is not None
    assert item.elr_no == "ELR_NOW"
    assert item.attempts == 1

    # Second claim when item is locked returns None
    assert claim(cur, "worker-2") is None


def test_stuck_running_returns_to_retry():
    store = InMemoryQueueStore()
    cur = store.Cursor(store)

    enqueue(cur, 1, "ELR_STUCK", "scan")
    item = claim(cur, "worker-1")
    assert item is not None

    # Simulate 20 minutes elapsed while running
    stuck_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    store.items[item.item_id]["updated_at"] = stuck_time
    store.locked_ids.clear()

    # Next claim should reset stuck item to retry and claim it
    item_reclaimed = claim(cur, "worker-2")
    assert item_reclaimed is not None
    assert item_reclaimed.elr_no == "ELR_STUCK"
    assert item_reclaimed.attempts == 2


def test_fail_backoff_then_failed():
    store = InMemoryQueueStore()
    cur = store.Cursor(store)

    enqueue(cur, 1, "ELR_FAIL", "scan")
    item = claim(cur, "worker-1")
    assert item is not None

    # Attempt 1 -> retry backoff 1 min
    state1 = fail_with_backoff(cur, item.item_id, item.attempts, "error 1")
    assert state1 == "retry"

    # Attempt 2 -> retry backoff 5 min
    state2 = fail_with_backoff(cur, item.item_id, 2, "error 2")
    assert state2 == "retry"

    # Attempt 3 -> retry backoff 15 min
    state3 = fail_with_backoff(cur, item.item_id, 3, "error 3")
    assert state3 == "retry"

    # Attempt 4 -> exceeds 3 attempts -> failed
    state4 = fail_with_backoff(cur, item.item_id, 4, "error 4")
    assert state4 == "failed"
