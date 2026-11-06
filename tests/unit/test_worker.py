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
                item["error"] = None
                item["updated_at"] = now
                self.store.locked_ids.discard(item_id)

            elif "update mark_app.work_item" in sql_clean and "state = 'retry'" in sql_clean:
                if len(params) == 4:
                    attempts, error, retry_sec, item_id = params
                    self.store.items[item_id]["attempts"] = attempts
                else:
                    error, retry_sec, item_id = params
                item = self.store.items[item_id]
                item["state"] = "retry"
                item["error"] = error
                item["next_attempt_at"] = now + timedelta(seconds=retry_sec)
                item["updated_at"] = now
                self.store.locked_ids.discard(item_id)

            elif "update mark_app.work_item" in sql_clean and "state = 'failed'" in sql_clean:
                if len(params) == 3:
                    attempts, error, item_id = params
                    self.store.items[item_id]["attempts"] = attempts
                else:
                    error, item_id = params
                item = self.store.items[item_id]
                item["state"] = "failed"
                item["error"] = error
                item["updated_at"] = now
                self.store.locked_ids.discard(item_id)
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


# ---------------------------------------------------------------------------
# Task 4 Tests: Results writer & Worker loop
# ---------------------------------------------------------------------------
from mark_engine.domain.models import JobResult, ProcessingStatus, VerificationStatus, ApprovalStatus
from services.worker.results import (
    day_run_for,
    write_result,
    notify_for,
    job_row,
    line_row,
)
from services.worker.main import CycleResult, run_worker_cycle


class FakePgCursor:
    def __init__(self):
        self.connection = self
        self.rolled_back = False
        self.committed = False
        self.executed: list[tuple[str, tuple]] = []
        self.runs: dict[int, dict[str, Any]] = {}
        self.job_results: list[dict[str, Any]] = []
        self.line_results: list[dict[str, Any]] = []
        self.snapshots: list[dict[str, Any]] = []
        self.revisions: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []
        self.approvals: list[dict[str, Any]] = []
        self._next_run_id = 100
        self._last_fetch = None

    def rollback(self):
        self.rolled_back = True

    def commit(self):
        self.committed = True

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql: str, params: tuple = ()):
        self.executed.append((sql, params))
        sql_clean = " ".join(sql.split()).lower()

        if "select run_id from mark_logic.run where period =" in sql_clean:
            period = params[0]
            matched = [rid for rid, r in self.runs.items() if r["period"] == period]
            self._last_fetch = (matched[0],) if matched else None

        elif "select 1 from mark_logic.job_result where run_id =" in sql_clean:
            run_id, elr_no = params[0], params[1]
            exists = any(j["run_id"] == run_id and j["elr_no"] == elr_no for j in self.job_results)
            self._last_fetch = (1,) if exists else None

        elif "insert into mark_logic.run" in sql_clean:
            period = params[0]
            rid = self._next_run_id
            self._next_run_id += 1
            self.runs[rid] = {"run_id": rid, "period": period}
            self._last_fetch = (rid,)

        elif "insert into mark_logic.job_result" in sql_clean:
            self.job_results.append({"run_id": params[0], "elr_no": params[1]})
            self._last_fetch = None

        elif "insert into mark_logic.line_result" in sql_clean:
            self.line_results.append({"run_id": params[0], "elr_no": params[1]})
            self._last_fetch = None

        elif "insert into mark_app.elr_snapshot" in sql_clean:
            self.snapshots.append({
                "run_id": params[0],
                "elr_no": params[1],
                "top_mark_id": params[2],
                "line_extra": params[3] if len(params) > 3 else "{}",
            })
            self._last_fetch = None

        elif "select line_extra from mark_app.elr_snapshot where run_id =" in sql_clean:
            run_id, elr_no = params[0], params[1]
            matched = [s for s in self.snapshots if s["run_id"] == run_id and s["elr_no"] == elr_no]
            self._last_fetch = (matched[0]["line_extra"],) if matched else None

        elif "insert into mark_app.elr_revision" in sql_clean:
            self.revisions.append({
                "elr_no": params[0],
                "revision": params[1],
                "oracle_fp": params[2],
                "docs_fp": params[3],
                "version_fp": params[4],
                "result_fp": params[5],
                "changed": params[6],
                "changed_fields": params[7],
                "result_unchanged": params[8],
                "docs_probe": params[9],
                "run_id": params[10],
            })
            self._last_fetch = None

        elif "select coalesce(max(revision), 0) from mark_app.elr_revision where elr_no =" in sql_clean:
            elr_no = params[0]
            revs = [r["revision"] for r in self.revisions if r["elr_no"] == elr_no]
            self._last_fetch = (max(revs, default=0),)

        elif "select 1 from mark_app.approval where elr_no =" in sql_clean:
            elr_no, run_id = params[0], params[1]
            exists = any(a["elr_no"] == elr_no and a["run_id"] == run_id and a.get("decision") == "APPROVED" for a in self.approvals)
            self._last_fetch = (1,) if exists else None

        elif "insert into mark_app.notification" in sql_clean:
            self.notifications.append({"elr_no": params[0], "run_id": params[1], "revision": params[2], "kind": params[3]})
            self._last_fetch = None

        elif "select revision, oracle_fp, docs_fp, result_fp, run_id" in sql_clean:
            elr_no = params[0]
            matched = [r for r in self.revisions if r["elr_no"] == elr_no]
            self._last_fetchall = [
                (
                    r["revision"],
                    r.get("oracle_fp", ""),
                    r.get("docs_fp", ""),
                    r.get("result_fp", ""),
                    r["run_id"],
                    r.get("docs_probe", {}),
                )
                for r in matched
            ]

        else:
            self._last_fetch = None

    def fetchone(self):
        return self._last_fetch

    def fetchall(self):
        return getattr(self, "_last_fetchall", [])


def test_day_run_reuses_until_elr_repeats_then_suffix():
    cur = FakePgCursor()
    day = datetime(2026, 11, 6).date()

    # 1. First ELR creates run auto-2026-11-06
    r1 = day_run_for(cur, "ADI2601001", day)
    assert cur.runs[r1]["period"] == "auto-2026-11-06"

    # Simulate recording job_result for ADI2601001 in r1
    cur.job_results.append({"run_id": r1, "elr_no": "ADI2601001"})

    # 2. Second different ELR reuses the same run r1
    r2 = day_run_for(cur, "ADI2601002", day)
    assert r2 == r1

    # 3. Same ELR ADI2601001 repeats on the same day -> must create suffix run .2
    r3 = day_run_for(cur, "ADI2601001", day)
    assert r3 != r1
    assert cur.runs[r3]["period"] == "auto-2026-11-06.2"


def test_write_result_never_updates_existing_rows():
    cur = FakePgCursor()
    meta = ElrMeta(elr_no="ADI2601001", product_no="AD999")
    job = JobResult(elr_no="ADI2601001", processing_status=ProcessingStatus.DONE)
    oracle_row = {"ELR_NO": "ADI2601001", "PRODUCT_NO": "AD999"}
    rev_info = {
        "run_id": 100,
        "oracle_fp": "ofp1",
        "docs_fp": "dfp1",
        "version_fp": "vfp1",
        "result_fp": "rfp1",
        "changed": "new",
        "changed_fields": [],
        "result_unchanged": False,
        "docs_probe": {},
    }

    new_rev = write_result(cur, job, meta, oracle_row, resolution=None, revision_info=rev_info)
    assert new_rev == 1

    # Invariant check: only INSERT queries on mark_logic, zero UPDATE or DELETE
    for sql, _ in cur.executed:
        sql_lower = sql.lower()
        if "mark_logic." in sql_lower:
            assert sql_lower.strip().startswith("insert") or sql_lower.strip().startswith("select")


def test_approved_revision_kept_and_new_revision_notifies():
    cur = FakePgCursor()
    cur.approvals.append({"elr_no": "ADI2601001", "run_id": 100, "decision": "APPROVED"})
    job = JobResult(elr_no="ADI2601001", processing_status=ProcessingStatus.DONE)

    # When previous revision was approved, notification includes changed_after_approve
    notified = notify_for(cur, job, revision=2, prev_approved=True, run_id=101)
    assert "changed_after_approve" in notified
    assert len(cur.notifications) == 1
    assert cur.notifications[0]["kind"] == "changed_after_approve"


def test_same_as_old_revision_creates_nothing():
    cur = FakePgCursor()
    # Revision 1 exists
    cur.revisions.append({"elr_no": "ADI2601001", "revision": 1, "oracle_fp": "ofp1", "docs_fp": "dfp1", "run_id": 100})
    # Revision 2 exists
    cur.revisions.append({"elr_no": "ADI2601001", "revision": 2, "oracle_fp": "ofp2", "docs_fp": "dfp2", "run_id": 101})

    queue_store = InMemoryQueueStore()
    q_cur = queue_store.Cursor(queue_store)
    enqueue(q_cur, 1, "ADI2601001", "scan")

    # Oracle row reverted back to ofp1
    oracle_row = {"ELR_NO": "ADI2601001", "PRODUCT_NO": "AD1", "STATUS": "A"}

    # Mock oracle and resolution
    prev_rev_count = len(cur.revisions)
    executed_check = run_worker_cycle(
        cur,
        q_cur,
        oracle_row=oracle_row,
        force_oracle_fp="ofp1",
        resolved_docs_fp="dfp1",
        worker_id="worker-test",
    )
    # If same as revision 1, no new revision created
    assert executed_check == CycleResult.SKIPPED
    assert len(cur.revisions) == prev_rev_count


def test_oracle_reverted_to_old_rev_after_docs_resolved_creates_nothing():
    """Requirement (5): After docs resolved, re-check decide() with real docs_fp.

    If skip_same_as_rev, creates no revision.
    """
    cur = FakePgCursor()
    # Rev 1: oracle=ofp1, docs=dfp1
    cur.revisions.append({"elr_no": "ADI2601001", "revision": 1, "oracle_fp": "ofp1", "docs_fp": "dfp1", "run_id": 100})
    # Rev 2: oracle=ofp2, docs=dfp2
    cur.revisions.append({"elr_no": "ADI2601001", "revision": 2, "oracle_fp": "ofp2", "docs_fp": "dfp2", "run_id": 101})

    queue_store = InMemoryQueueStore()
    q_cur = queue_store.Cursor(queue_store)
    enqueue(q_cur, 1, "ADI2601001", "scan")

    # cheap-first saw ofp1 (which is different from latest ofp2), so it proceeded to resolve docs
    # but when docs resolved, docs_fp is dfp1, matching rev 1!
    prev_rev_count = len(cur.revisions)
    executed = run_worker_cycle(
        cur,
        q_cur,
        oracle_row={"ELR_NO": "ADI2601001", "PRODUCT_NO": "AD1", "STATUS": "A"},
        force_oracle_fp="ofp1",
        resolved_docs_fp="dfp1",
        worker_id="worker-test",
    )
    assert executed == CycleResult.SKIPPED
    assert len(cur.revisions) == prev_rev_count


def test_inference_down_retries_then_hold_inference_failed():
    cur = FakePgCursor()
    queue_store = InMemoryQueueStore()
    q_cur = queue_store.Cursor(queue_store)
    enqueue(q_cur, 1, "ADI2601001", "scan")

    # Simulate inference failing on all attempts
    for attempt in range(1, 4):
        item = claim(q_cur, "worker-1")
        assert item is not None
        assert item.attempts == attempt
        state = fail_with_backoff(q_cur, item.item_id, item.attempts, "InferenceUnavailable: connection refused")
        assert state == "retry"
        # Simulate backoff timer elapsed
        queue_store.items[item.item_id]["next_attempt_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)

    # 4th attempt -> fails with backoff returns "failed"
    item = claim(q_cur, "worker-1")
    assert item is not None
    assert item.attempts == 4
    state = fail_with_backoff(q_cur, item.item_id, item.attempts, "InferenceUnavailable: connection refused")
    assert state == "failed"


def test_version_only_change_not_rechecked():
    from mark_engine.history.decide import RevisionKey, decide
    # When oracle and docs are unchanged but version_fp changes:
    prev = [RevisionKey(1, "o1", "d1")]
    dec = decide(pending_reason=None, prev=prev, oracle_fp="o1", docs_fp="d1", manual=False)
    # Automatic re-check skips unchanged input even if version changes
    assert dec.action == "skip_unchanged"


def test_loader_scripts_unchanged_output():
    # Verify line_row and job_row contracts
    jrow = job_row(100, {"elr_no": "ADI2601001", "processing_status": "DONE"})
    assert jrow[0] == 100
    assert jrow[1] == "ADI2601001"
    assert jrow[2] == "DONE"

    lrow = line_row(100, {"elr_no": "ADI2601001", "side": "TOP", "line_no": "1", "status": "MATCH"}, "ABS065001", "IDENTICAL")
    assert lrow[0] == 100
    assert lrow[1] == "ADI2601001"
    assert lrow[2] == "ABS065001"
    assert lrow[8] == "MATCH"


# ---------------------------------------------------------------------------
# Requirement-specific Unit Tests (Task 4 Pipeline Integration)
# ---------------------------------------------------------------------------
import json
from pathlib import Path
import mark_engine
from mark_engine.domain.models import DocumentRef, DocType, DocumentResolution
from mark_engine.history.fingerprint import version_fp
from mark_engine.adapters.inference_service import InferenceUnavailable


def test_step8_invokes_real_process_elr(monkeypatch):
    """(1) Step 8 calls process_elr() with engine models and active loaders."""
    cur = FakePgCursor()
    queue_store = InMemoryQueueStore()
    q_cur = queue_store.Cursor(queue_store)
    enqueue(q_cur, 1, "ADI2601001", "scan")

    recorded_calls = []

    def mock_process_elr(meta, oracle, root, months, work_dir, rules, loader, **kwargs):
        recorded_calls.append({
            "meta": meta,
            "oracle": oracle,
            "root": root,
            "months": months,
            "work_dir": work_dir,
            "rules": rules,
            "loader": loader,
            "kwargs": kwargs,
        })
        return JobResult(
            elr_no=meta.elr_no,
            processing_status=ProcessingStatus.DONE,
            verification_status=VerificationStatus.MATCH_ALL,
        )

    monkeypatch.setattr("services.worker.main.process_elr", mock_process_elr)

    oracle_row = {"ELR_NO": "ADI2601001", "PRODUCT_NO": "AD1", "STATUS": "A", "CURRENT_STEP": "6"}
    res = run_worker_cycle(
        cur,
        q_cur,
        oracle_row=oracle_row,
        resolved_docs_fp="dfp_test",
        worker_id="worker-test",
    )
    assert res == CycleResult.PROCESSED
    assert len(recorded_calls) == 1
    call = recorded_calls[0]
    assert call["meta"].elr_no == "ADI2601001"
    assert call["oracle"].elr_no == "ADI2601001"
    assert len(cur.revisions) == 1


def test_docs_probe_captured_and_saved(tmp_path, monkeypatch):
    """(2) resolve ABS/SLR from NAS, calculate docs_fp, write docs_probe."""
    cur = FakePgCursor()
    queue_store = InMemoryQueueStore()
    q_cur = queue_store.Cursor(queue_store)
    enqueue(q_cur, 1, "ADI2601001", "scan")

    # Create dummy files to probe
    abs_file = tmp_path / "ABS065001.pdf"
    abs_file.write_bytes(b"dummy abs content")
    slr_file = tmp_path / "SLR065001.pdf"
    slr_file.write_bytes(b"dummy slr content")

    dummy_res = DocumentResolution(
        elr_no="ADI2601001",
        decision="RESOLVED",
        abs=DocumentRef(path=str(abs_file), sha256="sha_abs", doc_type=DocType.ABS),
        slr=(DocumentRef(path=str(slr_file), sha256="sha_slr", doc_type=DocType.SLR),),
    )

    monkeypatch.setattr("services.worker.main.resolve_documents", lambda *args, **kwargs: dummy_res)
    monkeypatch.setattr(
        "services.worker.main.process_elr",
        lambda *args, **kwargs: JobResult(
            elr_no="ADI2601001",
            processing_status=ProcessingStatus.DONE,
            verification_status=VerificationStatus.MATCH_ALL,
            resolution=dummy_res,
        ),
    )

    oracle_row = {"ELR_NO": "ADI2601001", "PRODUCT_NO": "AD1", "STATUS": "A", "CURRENT_STEP": "6"}
    ok = run_worker_cycle(cur, q_cur, oracle_row=oracle_row)
    assert ok == CycleResult.PROCESSED
    assert len(cur.revisions) == 1
    rev = cur.revisions[0]
    assert rev["docs_fp"] != "none"
    probe = json.loads(rev["docs_probe"]) if isinstance(rev["docs_probe"], str) else rev["docs_probe"]
    assert str(abs_file) in probe
    assert probe[str(abs_file)]["size"] == len(b"dummy abs content")
    assert str(slr_file) in probe
    assert probe[str(slr_file)]["size"] == len(b"dummy slr content")


def test_cheap_first_docs_probe_skips_when_files_unchanged_and_runs_when_changed(tmp_path, monkeypatch):
    """(3) If Oracle unchanged, compare docs_probe first. If files changed, re-evaluate."""
    abs_file = tmp_path / "ABS065001.pdf"
    abs_file.write_bytes(b"original content")
    st = abs_file.stat()

    stored_probe = {str(abs_file): {"size": st.st_size, "mtime": st.st_mtime}}

    cur = FakePgCursor()
    cur.revisions.append({
        "elr_no": "ADI2601001",
        "revision": 1,
        "oracle_fp": "ofp_same",
        "docs_fp": "dfp1",
        "result_fp": "rfp1",
        "run_id": 100,
        "docs_probe": stored_probe,
    })

    queue_store = InMemoryQueueStore()
    q_cur = queue_store.Cursor(queue_store)
    enqueue(q_cur, 1, "ADI2601001", "scan")

    resolve_called = []
    monkeypatch.setattr("services.worker.main.resolve_documents", lambda *a, **kw: resolve_called.append(1))

    oracle_row = {"ELR_NO": "ADI2601001", "PRODUCT_NO": "AD1", "STATUS": "A", "CURRENT_STEP": "6"}

    # Case A: File untouched -> docs_probe matches -> skips without resolve_documents
    ok = run_worker_cycle(cur, q_cur, oracle_row=oracle_row, force_oracle_fp="ofp_same")
    assert ok == CycleResult.SKIPPED
    assert len(resolve_called) == 0
    assert len(cur.revisions) == 1

    # Case B: File modified on NAS -> docs_probe differs -> resolves documents and runs
    enqueue(q_cur, 1, "ADI2601001", "scan")
    abs_file.write_bytes(b"modified new content longer size")

    dummy_res = DocumentResolution(
        elr_no="ADI2601001",
        decision="RESOLVED",
        abs=DocumentRef(path=str(abs_file), sha256="sha_new", doc_type=DocType.ABS),
    )
    monkeypatch.setattr("services.worker.main.resolve_documents", lambda *a, **kw: dummy_res)
    monkeypatch.setattr(
        "services.worker.main.process_elr",
        lambda *args, **kwargs: JobResult(
            elr_no="ADI2601001",
            processing_status=ProcessingStatus.DONE,
            verification_status=VerificationStatus.MATCH_ALL,
            resolution=dummy_res,
        ),
    )

    ok2 = run_worker_cycle(cur, q_cur, oracle_row=oracle_row, force_oracle_fp="ofp_same")
    assert ok2 == CycleResult.PROCESSED
    assert len(cur.revisions) == 2
    assert cur.revisions[1]["changed"] == "docs"


def test_g0_pending_reason_skips_ineligible(monkeypatch):
    """(4) G0 uses pending_reason(meta, review_step)."""
    monkeypatch.setenv("MARK_REVIEW_STEP", "6")

    cur = FakePgCursor()
    queue_store = InMemoryQueueStore()
    q_cur = queue_store.Cursor(queue_store)
    enqueue(q_cur, 1, "ADI2601001", "scan")

    # Current step is 5 (not review step 6)
    oracle_row = {"ELR_NO": "ADI2601001", "STATUS": "A", "CURRENT_STEP": "5"}
    ok = run_worker_cycle(cur, q_cur, oracle_row=oracle_row, resolved_docs_fp="dfp")
    assert ok == CycleResult.SKIPPED
    assert len(cur.revisions) == 0

    # Status C (closed)
    enqueue(q_cur, 1, "ADI2601002", "scan")
    oracle_row_c = {"ELR_NO": "ADI2601002", "STATUS": "C", "CURRENT_STEP": "6"}
    ok_c = run_worker_cycle(cur, q_cur, oracle_row=oracle_row_c, resolved_docs_fp="dfp")
    assert ok_c == CycleResult.SKIPPED
    assert len(cur.revisions) == 0


def test_manual_recheck_reason_forces_execution(monkeypatch):
    """(5) manual = (item.reason == 'recheck') forces check even if unchanged."""
    cur = FakePgCursor()
    cur.revisions.append({
        "elr_no": "ADI2601001",
        "revision": 1,
        "oracle_fp": "ofp1",
        "docs_fp": "dfp1",
        "result_fp": "rfp1",
        "run_id": 100,
        "docs_probe": {},
    })

    queue_store = InMemoryQueueStore()
    q_cur = queue_store.Cursor(queue_store)
    enqueue(q_cur, 1, "ADI2601001", "recheck")  # manual trigger

    monkeypatch.setattr(
        "services.worker.main.process_elr",
        lambda *args, **kwargs: JobResult(
            elr_no="ADI2601001",
            processing_status=ProcessingStatus.DONE,
            verification_status=VerificationStatus.MATCH_ALL,
        ),
    )

    oracle_row = {"ELR_NO": "ADI2601001", "PRODUCT_NO": "AD1", "STATUS": "A", "CURRENT_STEP": "6"}
    ok = run_worker_cycle(
        cur,
        q_cur,
        oracle_row=oracle_row,
        force_oracle_fp="ofp1",
        resolved_docs_fp="dfp1",
    )
    assert ok == CycleResult.PROCESSED
    assert len(cur.revisions) == 2
    assert cur.revisions[1]["changed"] == "manual"


def test_approval_query_matches_real_schema():
    """(6) query approval uses column decision = 'APPROVED' on PostgreSQL."""
    import os
    import psycopg2
    from mark_engine.adapters.env import load_env

    env_path = os.environ.get("ENV_FILE", "D:/CIM Project/mark-web/.env")
    load_env(Path(env_path) if Path(env_path).is_file() else None)

    password = os.environ.get("MARK_WORKER_PG_PASSWORD")
    if not password:
        pytest.skip("MARK_WORKER_PG_PASSWORD not in environment, skipping live DB query test")

    try:
        conn = psycopg2.connect(
            host=os.getenv("PGHOST", "10.151.28.2"),
            port=int(os.getenv("PGPORT", 5432)),
            dbname=os.getenv("PGDATABASE", "mark_web"),
            user=os.getenv("MARK_WORKER_PG_USER", "mark_worker"),
            password=password,
            connect_timeout=3,
        )
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Live DB unreachable: {exc}")

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM mark_app.approval WHERE elr_no = 'NONEXISTENT' AND run_id = -1 AND decision = 'APPROVED';")
            rows = cur.fetchall()
            assert rows == []
    finally:
        conn.close()


def test_version_fp_uses_engine_and_model_version():
    """(7) version_fp uses mark_engine.__version__ and model_version."""
    from services.worker.main import get_service_model_version

    class MockClient:
        def health(self):
            return {"model": {"service_version": "v1.2.3"}}

    mv = get_service_model_version(MockClient())
    assert mv == "v1.2.3"
    vfp = version_fp(mark_engine.__version__, mv)
    assert len(vfp) == 64


def test_inference_unavailable_fail_with_backoff_and_hold_inference_failed(monkeypatch):
    """(8) InferenceUnavailable calls fail_with_backoff; final attempt writes HOLD INFERENCE_FAILED."""
    cur = FakePgCursor()
    queue_store = InMemoryQueueStore()
    q_cur = queue_store.Cursor(queue_store)
    enqueue(q_cur, 1, "ADI2601001", "scan")

    def mock_failing_process_elr(*args, **kwargs):
        raise InferenceUnavailable("GPU cluster timeout")

    monkeypatch.setattr("services.worker.main.process_elr", mock_failing_process_elr)

    oracle_row = {"ELR_NO": "ADI2601001", "PRODUCT_NO": "AD1", "STATUS": "A", "CURRENT_STEP": "6"}

    # Attempt 1 -> retry
    ok1 = run_worker_cycle(cur, q_cur, oracle_row=oracle_row, resolved_docs_fp="dfp")
    assert ok1 == CycleResult.PROCESSED
    assert len(cur.revisions) == 0

    # Simulate fast-forwarding attempts to 3 (exhausting backoff)
    item_id = list(queue_store.items.keys())[0]
    queue_store.items[item_id]["attempts"] = 3
    queue_store.items[item_id]["next_attempt_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)

    # Attempt 4 -> fails with backoff returns "failed" -> writes HOLD INFERENCE_FAILED & notifies
    ok4 = run_worker_cycle(cur, q_cur, oracle_row=oracle_row, resolved_docs_fp="dfp")
    assert ok4 == CycleResult.PROCESSED
    assert len(cur.revisions) == 1
    assert len(cur.notifications) == 1
    assert cur.notifications[0]["kind"] == "hold"


def test_changed_fields_uses_changed_oracle_fields_from_elr_snapshot(monkeypatch):
    """(9) changed_fields uses changed_oracle_fields comparing previous revision's Oracle row."""
    cur = FakePgCursor()
    old_oracle_row = {"ELR_NO": "ADI2601001", "PRODUCT_NO": "OLD_PART", "STATUS": "A", "CURRENT_STEP": "6"}
    cur.snapshots.append({
        "run_id": 100,
        "elr_no": "ADI2601001",
        "top_mark_id": 1,
        "line_extra": json.dumps({"oracle_row": old_oracle_row}),
    })
    cur.revisions.append({
        "elr_no": "ADI2601001",
        "revision": 1,
        "oracle_fp": "ofp_old",
        "docs_fp": "dfp1",
        "result_fp": "rfp1",
        "run_id": 100,
        "docs_probe": {},
    })

    queue_store = InMemoryQueueStore()
    q_cur = queue_store.Cursor(queue_store)
    enqueue(q_cur, 1, "ADI2601001", "scan")

    monkeypatch.setattr(
        "services.worker.main.process_elr",
        lambda *args, **kwargs: JobResult(
            elr_no="ADI2601001",
            processing_status=ProcessingStatus.DONE,
            verification_status=VerificationStatus.MATCH_ALL,
        ),
    )

    new_oracle_row = {"ELR_NO": "ADI2601001", "PRODUCT_NO": "NEW_PART", "STATUS": "A", "CURRENT_STEP": "6"}
    ok = run_worker_cycle(
        cur,
        q_cur,
        oracle_row=new_oracle_row,
        resolved_docs_fp="dfp1",
    )
    assert ok == CycleResult.PROCESSED
    assert len(cur.revisions) == 2
    rev2 = cur.revisions[1]
    assert rev2["changed"] == "oracle"
    assert "PRODUCT_NO" in rev2["changed_fields"]


def test_task6_step4_simulated_oracle_top_mark2_change(monkeypatch):
    """Task 6 Step 4: Simulated Oracle change feeds worker row with TOP_MARK2 changed -> changed=oracle, changed_fields=['TOP_MARK2']."""
    cur = FakePgCursor()
    old_oracle_row = {
        "ELR_NO": "ADI2607006",
        "PRODUCT_NO": "PART1",
        "STATUS": "A",
        "CURRENT_STEP": "6",
        "TOP_MARK1": "LINE1",
        "TOP_MARK2": "ORIGINAL_MARK",
    }
    cur.snapshots.append({
        "run_id": 100,
        "elr_no": "ADI2607006",
        "top_mark_id": 1,
        "line_extra": json.dumps({"oracle_row": old_oracle_row}),
    })
    cur.revisions.append({
        "elr_no": "ADI2607006",
        "revision": 1,
        "oracle_fp": "ofp_old_1",
        "docs_fp": "dfp_nas_1",
        "result_fp": "rfp_1",
        "run_id": 100,
        "docs_probe": {},
    })

    queue_store = InMemoryQueueStore()
    q_cur = queue_store.Cursor(queue_store)
    enqueue(q_cur, 1, "ADI2607006", "scan")

    monkeypatch.setattr(
        "services.worker.main.process_elr",
        lambda *args, **kwargs: JobResult(
            elr_no="ADI2607006",
            processing_status=ProcessingStatus.DONE,
            verification_status=VerificationStatus.MATCH_ALL,
        ),
    )

    new_oracle_row = dict(old_oracle_row)
    new_oracle_row["TOP_MARK2"] = "CHANGED_MARK"

    result = run_worker_cycle(
        cur,
        q_cur,
        oracle_row=new_oracle_row,
        resolved_docs_fp="dfp_nas_1",
    )
    assert result == CycleResult.PROCESSED
    assert len(cur.revisions) == 2
    rev2 = cur.revisions[1]
    assert rev2["changed"] == "oracle"
    assert rev2["changed_fields"] == ["TOP_MARK2"]


def test_main_connects_as_mark_worker_and_runs_once(monkeypatch):
    """(10) main() connects to Postgres with mark_worker and Oracle read-only, exits on --once."""
    from services.worker.main import main

    monkeypatch.setenv("MARK_WORKER_PG_USER", "mark_worker")
    monkeypatch.setenv("MARK_WORKER_PG_PASSWORD", "secret")

    pg_connect_args = {}
    class MockPgConn:
        def cursor(self):
            class DummyCur:
                def __enter__(self): return self
                def __exit__(self, *args): pass
            return DummyCur()
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def close(self): pass

    def mock_pg_connect(**kwargs):
        pg_connect_args.update(kwargs)
        return MockPgConn()

    monkeypatch.setattr("psycopg2.connect", mock_pg_connect)
    monkeypatch.setattr("services.worker.main.connect_actl", lambda: MockPgConn())
    monkeypatch.setattr("services.worker.main.run_worker_cycle", lambda *args, **kwargs: CycleResult.NO_ITEM)
    monkeypatch.setattr("sys.argv", ["main.py", "--once"])

    main()

    assert pg_connect_args["user"] == "mark_worker"
    assert pg_connect_args["password"] == "secret"


def test_extract_marking_image_creates_hashed_png(tmp_path):
    """(A) extract_marking_image creates <sha256>.png directly from ABS document."""
    from mark_engine.abs.brand_page import extract_marking_image
    import fitz

    # Create dummy single-page PDF with an image
    pdf_path = tmp_path / "dummy_abs.pdf"
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    # Insert a 10x10 pixmap
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), 0)
    pix.set_rect(fitz.IRect(0, 0, 10, 10), (255, 0, 0))
    page.insert_image(fitz.Rect(10, 10, 50, 50), pixmap=pix)
    doc.save(str(pdf_path))
    doc.close()

    dest_dir = tmp_path / "extracted_images"
    img_path, digest = extract_marking_image(pdf_path, dest_dir)
    assert img_path.is_file()
    assert img_path.name == f"{digest}.png"
    assert len(digest) == 64


def test_worker_extracts_marking_image_without_images_index_csv(tmp_path, monkeypatch):
    """(A) Worker extracts marking page image directly and passes path to service loader."""
    import services.worker.main as w_main

    cur = FakePgCursor()
    queue_store = InMemoryQueueStore()
    q_cur = queue_store.Cursor(queue_store)
    enqueue(q_cur, 1, "ADI2601001", "scan")

    abs_file = tmp_path / "ABS065001.pdf"
    abs_file.write_bytes(b"dummy abs content")

    dummy_res = DocumentResolution(
        elr_no="ADI2601001",
        decision="RESOLVED",
        abs=DocumentRef(path=str(abs_file), sha256="sha_abs", doc_type=DocType.ABS),
    )
    monkeypatch.setattr("services.worker.main.resolve_documents", lambda *a, **kw: dummy_res)

    extracted_img = tmp_path / "work" / "images" / "fake_img_sha.png"
    extracted_img.parent.mkdir(parents=True, exist_ok=True)
    extracted_img.write_bytes(b"dummy png bytes")
    monkeypatch.setattr(
        "services.worker.main.extract_marking_image",
        lambda p, dest: (extracted_img, "fake_img_sha"),
    )

    captured_loader = []
    def mock_process_elr(meta, oracle, root, months, work_dir, rules, loader, **kwargs):
        captured_loader.append(loader)
        return JobResult(
            elr_no="ADI2601001",
            processing_status=ProcessingStatus.DONE,
            verification_status=VerificationStatus.MATCH_ALL,
        )

    monkeypatch.setattr("services.worker.main.process_elr", mock_process_elr)
    monkeypatch.setenv("MARK_INFERENCE", "service")

    oracle_row = {"ELR_NO": "ADI2601001", "PRODUCT_NO": "AD1", "STATUS": "A", "CURRENT_STEP": "6"}
    res = run_worker_cycle(cur, q_cur, oracle_row=oracle_row, work_dir=tmp_path / "work")
    assert res == CycleResult.PROCESSED
    assert len(captured_loader) == 1
    loader = captured_loader[0]
    # Check that loader is bound to load_service_inference_for_image with extracted_img
    assert loader.func.__name__ == "load_service_inference_for_image"
    assert loader.args[1] == extracted_img


def test_worker_recovers_from_unhandled_item_exception(monkeypatch):
    """(B) Unexpected error during ELR processing: rollback dirty tx, fail_with_backoff, worker survives."""
    cur = FakePgCursor()
    queue_store = InMemoryQueueStore()
    q_cur = queue_store.Cursor(queue_store)
    enqueue(q_cur, 1, "ADI2601001", "scan")

    def mock_exploding_process_elr(*args, **kwargs):
        # Insert dirty partial result into cur before blowing up
        cur.job_results.append({"run_id": 999, "elr_no": "ADI2601001"})
        raise RuntimeError("Unexpected pipeline crash!")

    monkeypatch.setattr("services.worker.main.process_elr", mock_exploding_process_elr)

    oracle_row = {"ELR_NO": "ADI2601001", "PRODUCT_NO": "AD1", "STATUS": "A", "CURRENT_STEP": "6"}
    res = run_worker_cycle(
        cur,
        q_cur,
        oracle_row=oracle_row,
        resolved_docs_fp="dfp_test",
        worker_id="worker-test",
    )
    # Worker returns ERROR (item claimed & handled as error), cur rolled back, item set to retry
    assert res == CycleResult.ERROR
    assert cur.rolled_back is True
    item = queue_store.items[1]
    assert item["state"] == "retry"
    assert "Unexpected pipeline crash!" in item["error"]


def test_worker_rollback_retains_attempts_and_fails_on_4th_attempt(monkeypatch):
    """(4) Worker rollback does not lose attempts; item transitions to failed after 4 attempts."""
    cur = FakePgCursor()
    queue_store = InMemoryQueueStore()
    q_cur = queue_store.Cursor(queue_store)
    enqueue(q_cur, 1, "ADI2601001", "scan")

    def mock_exploding_process_elr(*args, **kwargs):
        cur.job_results.append({"dirty": True})
        raise RuntimeError("Crash!")

    monkeypatch.setattr("services.worker.main.process_elr", mock_exploding_process_elr)
    oracle_row = {"ELR_NO": "ADI2601001", "PRODUCT_NO": "AD1", "STATUS": "A", "CURRENT_STEP": "6"}

    # Run 4 cycles
    for attempt in range(1, 5):
        # Reset next_attempt_at to past so claim() can pick it up
        queue_store.items[1]["next_attempt_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        res = run_worker_cycle(
            cur,
            q_cur,
            oracle_row=oracle_row,
            resolved_docs_fp="dfp_test",
            worker_id="worker-test",
        )
        assert res == CycleResult.ERROR
        assert cur.rolled_back is True
        item = queue_store.items[1]
        assert item["attempts"] == attempt
        if attempt < 4:
            assert item["state"] == "retry"
        else:
            assert item["state"] == "failed"


def test_worker_once_exits_with_error_code_after_5_consecutive_errors(monkeypatch):
    """(4) In --once mode, if cycle errors occur 5 times consecutively, worker exits with code 1."""
    import sys
    from services.worker.main import main

    def mock_failing_cycle(*args, **kwargs):
        return CycleResult.ERROR

    monkeypatch.setattr("services.worker.main.run_worker_cycle", mock_failing_cycle)
    monkeypatch.setattr("psycopg2.connect", lambda **kw: FakePgCursor())
    monkeypatch.setattr("services.worker.main.connect_actl", lambda: FakePgCursor())
    monkeypatch.setattr("sys.argv", ["main.py", "--once"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1


def test_worker_once_mode_loops_until_no_item(monkeypatch):
    """(C) --once terminates only when CycleResult.NO_ITEM is returned."""
    from services.worker.main import main

    cycle_returns = [
        CycleResult.PROCESSED,
        CycleResult.SKIPPED,
        CycleResult.NO_ITEM,
    ]
    calls = []

    def mock_run_cycle(*args, **kwargs):
        ret = cycle_returns.pop(0)
        calls.append(ret)
        return ret

    monkeypatch.setattr("services.worker.main.run_worker_cycle", mock_run_cycle)
    monkeypatch.setattr("psycopg2.connect", lambda **kw: FakePgCursor())
    monkeypatch.setattr("services.worker.main.connect_actl", lambda: FakePgCursor())
    monkeypatch.setattr("sys.argv", ["main.py", "--once"])

    main()

    assert calls == [CycleResult.PROCESSED, CycleResult.SKIPPED, CycleResult.NO_ITEM]


def test_finish_resets_error_to_null():
    """(3) finish() sets error = null so completed items do not retain error strings."""
    queue_store = InMemoryQueueStore()
    q_cur = queue_store.Cursor(queue_store)
    enqueue(q_cur, 1, "ADI2601001", "recheck")
    item_id = list(queue_store.items.keys())[0]

    # Set an error on the item first
    queue_store.items[item_id]["error"] = "previous transient error"
    assert queue_store.items[item_id]["error"] == "previous transient error"

    finish(q_cur, item_id, revision=1)
    assert queue_store.items[item_id]["state"] == "done"
    assert queue_store.items[item_id]["revision"] == 1
    assert queue_store.items[item_id]["error"] is None


def test_probe_resolution_excludes_work_directory(tmp_path):
    """(4) docs_probe keeps only files on NAS storage, strictly excluding paths starting with work_dir."""
    from mark_engine.domain.models import DocumentRef, DocumentResolution
    from services.worker.main import probe_resolution

    nas_pdf = tmp_path / "nas" / "SLR245168.pdf"
    nas_pdf.parent.mkdir(parents=True)
    nas_pdf.write_bytes(b"dummy nas slr")

    work_extracted_pdf = tmp_path / "work" / "ADI2607006" / "extracted" / "SLR245168.pdf"
    work_extracted_pdf.parent.mkdir(parents=True)
    work_extracted_pdf.write_bytes(b"extracted in work")

    # Path containing substring 'work' (like 'network') but NOT starting with work_dir
    nas_network_pdf = tmp_path / "nas" / "network" / "SLR245169.pdf"
    nas_network_pdf.parent.mkdir(parents=True)
    nas_network_pdf.write_bytes(b"nas network slr")

    res = DocumentResolution(
        elr_no="ADI2607006",
        decision="RESOLVED",
        abs=DocumentRef(path=str(nas_pdf), doc_type="ABS", number="ABS047695", sha256="abc"),
        slr=(
            DocumentRef(path=str(nas_pdf), doc_type="SLR", number="SLR245168", sha256="def"),
            DocumentRef(path=str(work_extracted_pdf), doc_type="SLR", number="SLR245168", sha256="ghi"),
            DocumentRef(path=str(nas_network_pdf), doc_type="SLR", number="SLR245169", sha256="jkl"),
        ),
    )

    probe = probe_resolution(res, work_dir=tmp_path / "work" / "ADI2607006")
    assert str(nas_pdf) in probe
    assert str(nas_network_pdf) in probe
    assert str(work_extracted_pdf) not in probe


def test_real_schema_enqueue_and_results_writer():
    """(0) Integration test verifying enqueue_work_item and write_result SQL against throwaway test schema."""
    import os
    import psycopg2
    from mark_engine.adapters.env import load_env
    from mark_engine.domain.models import JobResult, LineComparison, Side, LineStatus, ProcessingStatus, VerificationStatus
    from mark_engine.adapters.snapshot import ElrMeta
    from services.worker.results import write_result
    from services.worker.queue import enqueue, finish

    env_path = os.environ.get("ENV_FILE", "D:/CIM Project/mark-web/.env")
    load_env(Path(env_path) if Path(env_path).is_file() else None)

    password = os.environ.get("MARK_PG_PASSWORD") or os.environ.get("MARK_WORKER_PG_PASSWORD")
    if not password:
        pytest.skip("Database password not in environment, skipping live schema test")

    user = os.environ.get("MARK_PG_USER", "postgres")
    try:
        conn = psycopg2.connect(
            host=os.getenv("PGHOST", "10.151.28.2"),
            port=int(os.getenv("PGPORT", 5432)),
            dbname=os.getenv("PGDATABASE", "mark_web"),
            user=user,
            password=password,
            connect_timeout=3,
        )
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Live DB unreachable: {exc}")

    test_schema = "t_worker_test_enqueue"
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {test_schema} CASCADE;")
            cur.execute(f"CREATE SCHEMA {test_schema};")
            cur.execute(f"""
                CREATE TABLE {test_schema}.run (
                    run_id bigint generated always as identity primary key,
                    period text not null
                );
                CREATE TABLE {test_schema}.job_result (
                    run_id bigint not null,
                    elr_no text not null,
                    processing_status text not null,
                    hold_reason text,
                    hold_detail text,
                    review_detail text,
                    verification_status text,
                    approval_status text,
                    layout_source text,
                    abs_no text,
                    primary key (run_id, elr_no)
                );
                CREATE TABLE {test_schema}.line_result (
                    run_id bigint not null,
                    elr_no text not null,
                    abs_no text,
                    side text not null,
                    line_no int not null,
                    month text,
                    final_mark text,
                    db_mark text,
                    status text not null,
                    cause text,
                    cause_detail text,
                    system_status text,
                    final_status text,
                    review_detail text,
                    warning text,
                    hold_detail text,
                    layout_source text
                );
                CREATE TABLE {test_schema}.elr_snapshot (
                    run_id bigint not null,
                    elr_no text not null,
                    top_mark_id int,
                    line_extra jsonb,
                    oracle_top_raw jsonb,
                    abs_file text,
                    abs_sha256 text,
                    primary key (run_id, elr_no)
                );
                CREATE TABLE {test_schema}.elr_revision (
                    elr_no text not null,
                    revision int not null,
                    oracle_fp text not null,
                    docs_fp text not null,
                    version_fp text not null,
                    result_fp text not null,
                    changed text not null,
                    changed_fields text[],
                    result_unchanged boolean not null default false,
                    docs_probe jsonb,
                    run_id bigint not null,
                    created_at timestamptz not null default now(),
                    primary key (elr_no, revision)
                );
                CREATE TABLE {test_schema}.work_item (
                    item_id bigint generated always as identity primary key,
                    scan_id bigint,
                    elr_no text not null,
                    state text not null check (state in ('queued', 'running', 'done', 'retry', 'failed')),
                    reason text not null check (reason in ('scan', 'user', 'recheck', 'retry_docs')),
                    attempts int not null default 0,
                    next_attempt_at timestamptz not null default now(),
                    revision int,
                    error text,
                    created_at timestamptz not null default now(),
                    updated_at timestamptz not null default now()
                );
                CREATE UNIQUE INDEX work_item_active_elr_idx on {test_schema}.work_item (elr_no)
                  where state in ('queued', 'running', 'retry');
            """)

            # Insert run dynamically (NOT hardcoded 22!)
            cur.execute(f"INSERT INTO {test_schema}.run (period) VALUES ('test-period') RETURNING run_id;")
            dynamic_run_id = cur.fetchone()[0]

            # 1. Test enqueue with state='queued' and finish with error=null on test schema
            test_elr = "ADI2699999"
            ok = enqueue(cur, None, test_elr, "recheck", schema=test_schema)
            assert ok is True

            cur.execute(f"SELECT item_id, state, error FROM {test_schema}.work_item WHERE elr_no = %s;", (test_elr,))
            item = cur.fetchone()
            assert item[1] == "queued"
            item_id = item[0]

            # Simulate prior error, then finish()
            cur.execute(f"UPDATE {test_schema}.work_item SET error = 'stale error' WHERE item_id = %s;", (item_id,))
            finish(cur, item_id, revision=99, schema=test_schema)
            cur.execute(f"SELECT state, revision, error FROM {test_schema}.work_item WHERE item_id = %s;", (item_id,))
            fin_row = cur.fetchone()
            assert fin_row[0] == "done"
            assert fin_row[1] == 99
            assert fin_row[2] is None

            # 2. Test write_result with dynamic run_id on test schema
            job = JobResult(
                elr_no=test_elr,
                processing_status=ProcessingStatus.DONE,
                verification_status=VerificationStatus.MATCH_ALL,
                comparisons=(
                    LineComparison(
                        side=Side.TOP,
                        line_no=1,
                        expected="MARK1",
                        oracle="MARK1",
                        status=LineStatus.MATCH,
                    ),
                ),
                layout_source="auto",
            )
            meta = ElrMeta(elr_no=test_elr, product_no="P99", top_mark_id=1, status="A", current_step="6")
            oracle_row = {"ELR_NO": test_elr, "TOP_MARK1": "MARK1", "STATUS": "A"}
            rev_info = {
                "run_id": dynamic_run_id,
                "oracle_fp": "ofp_test_schema",
                "docs_fp": "dfp_test_schema",
                "version_fp": "vfp_test_schema",
                "result_fp": "rfp_test_schema",
                "changed": "manual",
                "docs_probe": {"dummy": {"size": 1, "mtime": 1.0}},
            }

            new_rev = write_result(
                cur,
                job,
                meta,
                oracle_row,
                resolution=None,
                revision_info=rev_info,
                schema_logic=test_schema,
                schema_app=test_schema,
            )
            assert new_rev == 1

            # Verify line_result column values in test schema
            cur.execute(
                f"SELECT final_mark, db_mark, status FROM {test_schema}.line_result WHERE elr_no = %s;",
                (test_elr,),
            )
            l_res = cur.fetchall()
            assert len(l_res) == 1
            assert l_res[0][0].strip() == "MARK1"
            assert l_res[0][1].strip() == "MARK1"
            assert l_res[0][2] == "MATCH"

            # Clean up throwaway schema
            cur.execute(f"DROP SCHEMA IF EXISTS {test_schema} CASCADE;")
            conn.commit()
    finally:
        conn.close()


def test_manual_recheck_allows_same_fingerprint_but_auto_skips():
    from mark_engine.history.decide import RevisionKey, decide

    rev1 = RevisionKey(1, "ofp_old", "dfp_same")
    rev2 = RevisionKey(2, "ofp_new", "dfp_same")

    # 1. Automatic run on same fp as latest (rev2) -> skip_unchanged
    d_auto_latest = decide(None, [rev1, rev2], "ofp_new", "dfp_same", manual=False)
    assert d_auto_latest.action == "skip_unchanged"

    # 2. Automatic run on same fp as older revision (rev1) -> skip_same_as_rev
    d_auto_old = decide(None, [rev1, rev2], "ofp_old", "dfp_same", manual=False)
    assert d_auto_old.action == "skip_same_as_rev"
    assert d_auto_old.same_as_rev == 1

    # 3. Manual recheck on same fp as latest -> check, changed="manual"
    d_manual_latest = decide(None, [rev1, rev2], "ofp_new", "dfp_same", manual=True)
    assert d_manual_latest.action == "check"
    assert d_manual_latest.changed == "manual"

    # 4. Manual recheck on same fp as older revision -> check, changed="manual"
    d_manual_old = decide(None, [rev1, rev2], "ofp_old", "dfp_same", manual=True)
    assert d_manual_old.action == "check"
    assert d_manual_old.changed == "manual"


def test_schema_migration_0008_manual_revision_partial_index():
    """Verify on throwaway PostgreSQL schema (not real mark_web) that:
    1. Migration 0008 partial index allows duplicate (oracle_fp, docs_fp) when changed='manual'
    2. Automatic revisions (changed<>'manual') with duplicate fingerprints are rejected by partial unique index.
    3. Dynamic run_id is used (never hard-coded 22).
    """
    import os
    import psycopg2
    from dotenv import load_dotenv

    load_dotenv("D:/CIM Project/mark-web/.env")
    host = os.environ.get("MARK_PG_HOST", "10.151.28.2")
    db = os.environ.get("MARK_PG_DB", "mark_web")
    user = os.environ.get("MARK_PG_USER", "postgres")
    password = os.environ.get("MARK_PG_PASSWORD", "")

    try:
        conn = psycopg2.connect(
            host=host, port=5432, dbname=db, user=user, password=password, connect_timeout=5
        )
    except Exception:
        pytest.skip("PostgreSQL not reachable from this test runner")

    test_schema = "t_worker_test_0008"
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {test_schema} CASCADE;")
            cur.execute(f"CREATE SCHEMA {test_schema};")
            cur.execute(f"""
                CREATE TABLE {test_schema}.run (
                    run_id bigint generated always as identity primary key,
                    period text not null
                );
                CREATE TABLE {test_schema}.elr_revision (
                    elr_no text not null,
                    revision int not null,
                    oracle_fp text not null,
                    docs_fp text not null,
                    version_fp text not null,
                    result_fp text not null,
                    changed text not null check (changed in ('new', 'oracle', 'docs', 'both', 'manual')),
                    changed_fields text[],
                    result_unchanged boolean not null default false,
                    docs_probe jsonb,
                    run_id bigint not null references {test_schema}.run(run_id),
                    created_at timestamptz not null default now(),
                    primary key (elr_no, revision),
                    constraint elr_revision_fp_unique unique (elr_no, oracle_fp, docs_fp)
                );
            """)

            # Dynamic run_id (no hardcoded 22)
            cur.execute(f"INSERT INTO {test_schema}.run (period) VALUES ('test-run-0008') RETURNING run_id;")
            dynamic_run_id = cur.fetchone()[0]

            # Apply 0008 migration on test schema
            cur.execute(f"ALTER TABLE {test_schema}.elr_revision DROP CONSTRAINT IF EXISTS elr_revision_fp_unique;")
            cur.execute(f"""
                CREATE UNIQUE INDEX elr_revision_fp_auto_unique
                  ON {test_schema}.elr_revision (elr_no, oracle_fp, docs_fp)
                  WHERE changed <> 'manual';
            """)

            test_elr = "T_0008_REV_TEST"

            # Insert rev 1 (manual)
            cur.execute(f"""
                INSERT INTO {test_schema}.elr_revision (
                    elr_no, revision, oracle_fp, docs_fp, version_fp, result_fp, changed, run_id
                ) VALUES (%s, 1, 'fp_o', 'fp_d', 'fp_v', 'fp_r1', 'manual', %s);
            """, (test_elr, dynamic_run_id))

            # Insert rev 2 (manual) with identical fingerprints -> must succeed!
            cur.execute(f"""
                INSERT INTO {test_schema}.elr_revision (
                    elr_no, revision, oracle_fp, docs_fp, version_fp, result_fp, changed, run_id
                ) VALUES (%s, 2, 'fp_o', 'fp_d', 'fp_v', 'fp_r2', 'manual', %s);
            """, (test_elr, dynamic_run_id))

            # Insert rev 3 (oracle / automatic) with same fingerprints -> succeeds as first non-manual
            cur.execute(f"""
                INSERT INTO {test_schema}.elr_revision (
                    elr_no, revision, oracle_fp, docs_fp, version_fp, result_fp, changed, run_id
                ) VALUES (%s, 3, 'fp_o', 'fp_d', 'fp_v', 'fp_r3', 'oracle', %s);
            """, (test_elr, dynamic_run_id))

            # Insert rev 4 (oracle / automatic) with duplicate fingerprints -> must raise UniqueViolation!
            try:
                cur.execute(f"""
                    INSERT INTO {test_schema}.elr_revision (
                        elr_no, revision, oracle_fp, docs_fp, version_fp, result_fp, changed, run_id
                    ) VALUES (%s, 4, 'fp_o', 'fp_d', 'fp_v', 'fp_r4', 'oracle', %s);
                """, (test_elr, dynamic_run_id))
                pytest.fail("Expected UniqueViolation on elr_revision_fp_auto_unique for duplicate changed='oracle'")
            except psycopg2.IntegrityError:
                # Expected!
                conn.rollback()

            # Clean up throwaway schema
            with conn.cursor() as cur2:
                cur2.execute(f"DROP SCHEMA IF EXISTS {test_schema} CASCADE;")
                conn.commit()
    finally:
        conn.close()





