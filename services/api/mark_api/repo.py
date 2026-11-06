"""PostgreSQL repository layer with connection pooling, slow query logging and metrics."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import os
import time
from typing import Any

import psycopg2
from psycopg2.extras import DictCursor, Json, RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from mark_api.logging import log_event
from mark_engine.adapters.env import load_env

logger = logging.getLogger("mark_api.repo")


class ScanLockConflict(Exception):
    """Raised when an advisory lock for scan cannot be acquired."""
    pass


class Repo:
    def __init__(self, host: str | None = None, db: str | None = None,
                 user: str | None = None, password: str | None = None):
        load_env()
        self.host = host or os.getenv("MARK_PG_HOST", "10.151.28.2")
        self.db = db or os.getenv("MARK_PG_DB", "mark_web")
        self.user = user or os.getenv("MARK_PG_USER", "mark_app")
        self.password = password or os.getenv("MARK_PG_PASSWORD", "")
        self.pool = ThreadedConnectionPool(
            1, 10,
            host=self.host,
            port=5432,
            dbname=self.db,
            user=self.user,
            password=self.password,
            connect_timeout=8,
            options="-c statement_timeout=5000"
        )

    @contextmanager
    def _conn(self):
        conn = self.pool.getconn()
        try:
            yield conn
        finally:
            self.pool.putconn(conn)

    def _execute(self, query: str, params: Any = None, fetch_one: bool = False, fetch_all: bool = False, commit: bool = False):
        t0 = time.perf_counter()
        with self._conn() as conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, params)
                    res = None
                    if fetch_one:
                        res = cur.fetchone()
                    elif fetch_all:
                        res = cur.fetchall()
                    if commit:
                        conn.commit()
                    duration_ms = (time.perf_counter() - t0) * 1000.0
                    if duration_ms > 500.0:
                        log_event("db.slow_query", duration_ms=round(duration_ms, 2), sql=query[:200])
                    return res
            except Exception as e:
                conn.rollback()
                log_event("db.error", error=str(e), sql=query[:200])
                try:
                    from mark_api.metrics import metrics
                    metrics.inc("db_error")
                except Exception:
                    pass
                raise

    def runs(self) -> list[dict[str, Any]]:
        return self._execute("select run_id, period, run_at as created_at, note from mark_logic.run order by run_id desc", fetch_all=True)

    def lines(self, run_id: int) -> list[dict[str, Any]]:
        q = """
        select l.run_id, l.elr_no, l.abs_no, l.side, l.line_no,
               l.final_mark as expected, l.db_mark as oracle,
               l.final_status as status, l.warning, l.review_detail,
               l.cause_detail as detail, s.line_extra
        from mark_logic.line_result l
        left join mark_app.elr_snapshot s on (l.run_id = s.run_id and l.elr_no = s.elr_no)
        where l.run_id = %s and l.side = 'TOP'
        order by l.elr_no, l.line_no
        """
        rows = self._execute(q, (run_id,), fetch_all=True)
        for r in rows:
            extra = r.pop("line_extra", None) or {}
            line_extra = extra.get(str(r["line_no"]), {})
            r["compare_rules"] = line_extra.get("compare_rules", "")
            r["flags"] = line_extra.get("flags", "")
            if not r["detail"] and line_extra.get("detail"):
                r["detail"] = line_extra.get("detail")
        return rows

    def jobs(self, run_id: int) -> list[dict[str, Any]]:
        q = """
        select run_id, elr_no, processing_status, hold_reason, hold_detail,
               review_detail, verification_status, approval_status, layout_source, abs_no
        from mark_logic.job_result
        where run_id = %s
        order by elr_no
        """
        return self._execute(q, (run_id,), fetch_all=True)

    def job(self, run_id: int, elr: str) -> dict[str, Any] | None:
        q = """
        select run_id, elr_no, processing_status, hold_reason, hold_detail,
               review_detail, verification_status, approval_status, layout_source, abs_no
        from mark_logic.job_result
        where run_id = %s and elr_no = %s
        """
        return self._execute(q, (run_id, elr), fetch_one=True)

    def lines_for_elr(self, run_id: int, elr: str) -> list[dict[str, Any]]:
        q = """
        select l.run_id, l.elr_no, l.abs_no, l.side, l.line_no,
               l.final_mark as expected, l.db_mark as oracle,
               l.final_status as status, l.warning, l.review_detail,
               l.cause_detail as detail, s.line_extra
        from mark_logic.line_result l
        left join mark_app.elr_snapshot s on (l.run_id = s.run_id and l.elr_no = s.elr_no)
        where l.run_id = %s and l.elr_no = %s and l.side = 'TOP'
        order by l.line_no
        """
        rows = self._execute(q, (run_id, elr), fetch_all=True)
        for r in rows:
            extra = r.pop("line_extra", None) or {}
            line_extra = extra.get(str(r["line_no"]), {})
            r["compare_rules"] = line_extra.get("compare_rules", "")
            r["flags"] = line_extra.get("flags", "")
            if not r["detail"] and line_extra.get("detail"):
                r["detail"] = line_extra.get("detail")
        return rows

    def snapshot(self, run_id: int, elr: str) -> dict[str, Any] | None:
        q = """
        select run_id, elr_no, top_mark_id, layout_code, line_extra,
               mark_remark, mark_require, top_template_remark, oracle_top_raw,
               layout_cells, abs_file, abs_sha256, image_path, slr_files,
               slr_instructions, import_date
        from mark_app.elr_snapshot
        where run_id = %s and elr_no = %s
        """
        return self._execute(q, (run_id, elr), fetch_one=True)

    def latest_reviews(self, run_id: int, elr: str) -> dict[int, dict[str, Any]]:
        q = """
        select distinct on (line_no) review_id, run_id, elr_no, abs_no, side,
               line_no, reason, note, corrected_mark, reviewer_id, is_draft, created_at
        from mark_app.line_review
        where run_id = %s and elr_no = %s and side = 'TOP'
        order by line_no, created_at desc
        """
        rows = self._execute(q, (run_id, elr), fetch_all=True)
        return {r["line_no"]: r for r in rows}

    def add_review(self, run_id: int, elr_no: str, abs_no: str, side: str, line_no: int,
                   reason: str, note: str, corrected_mark: str, reviewer_id: int, is_draft: bool) -> int:
        q = """
        insert into mark_app.line_review (
            run_id, elr_no, abs_no, side, line_no, reason, note, corrected_mark, reviewer_id, is_draft
        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning review_id
        """
        res = self._execute(q, (run_id, elr_no, abs_no, side, line_no, reason, note, corrected_mark, reviewer_id, is_draft),
                            fetch_one=True, commit=True)
        return res["review_id"]

    def add_approval(self, run_id: int, elr_no: str, decision: str, user_id: int) -> int:
        q = """
        insert into mark_app.approval (run_id, elr_no, decision, user_id)
        values (%s, %s, %s, %s)
        returning approval_id
        """
        res = self._execute(q, (run_id, elr_no, decision, user_id), fetch_one=True, commit=True)
        return res["approval_id"]

    def latest_approval(self, run_id: int, elr: str) -> dict[str, Any] | None:
        q = """
        select approval_id, run_id, elr_no, decision, user_id, created_at
        from mark_app.approval
        where run_id = %s and elr_no = %s
        order by created_at desc
        limit 1
        """
        return self._execute(q, (run_id, elr), fetch_one=True)

    def audit(self, user_id: int | None, action: str, run_id: int | None = None,
              elr_no: str | None = None, line_no: int | None = None, detail: Any = None,
              *, client_ip: str | None = None, request_id: str | None = None) -> int:
        q = """
        insert into mark_app.audit_log (user_id, action, run_id, elr_no, line_no, detail, client_ip, request_id)
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        returning audit_id
        """
        res = self._execute(q, (user_id, action, run_id, elr_no, line_no,
                                Json(detail) if detail is not None else None,
                                client_ip, request_id),
                            fetch_one=True, commit=True)
        return res["audit_id"]

    def user_by_name(self, username: str) -> dict[str, Any] | None:
        q = """
        select user_id, username, display_name, role, password_hash, active, failed_count, locked_until, created_at
        from mark_app.app_user
        where lower(username) = %s
        """
        return self._execute(q, (username.strip().lower(),), fetch_one=True)

    def user_by_id(self, user_id: int) -> dict[str, Any] | None:
        q = """
        select user_id, username, display_name, role, password_hash, active, failed_count, locked_until, created_at
        from mark_app.app_user
        where user_id = %s
        """
        return self._execute(q, (user_id,), fetch_one=True)

    def record_login(self, user_id: int, ok: bool) -> None:
        if ok:
            q = "update mark_app.app_user set failed_count = 0, locked_until = null where user_id = %s"
            self._execute(q, (user_id,), commit=True)
        else:
            q = """
            update mark_app.app_user
            set failed_count = failed_count + 1,
                locked_until = case when failed_count + 1 >= 5 then now() + interval '15 minutes' else null end
            where user_id = %s
            """
            self._execute(q, (user_id,), commit=True)

    def create_session(self, token_hash: str, user_id: int, csrf_hash: str, expires_at: datetime) -> None:
        q = """
        insert into mark_app.user_session (token_hash, user_id, csrf_hash, expires_at)
        values (%s, %s, %s, %s)
        """
        self._execute(q, (token_hash, user_id, csrf_hash, expires_at), commit=True)

    def session_user(self, token_hash: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        q = """
        select s.token_hash, s.user_id, s.csrf_hash, s.expires_at, s.last_seen_at,
               u.username, u.display_name, u.role, u.password_hash, u.active, u.failed_count, u.locked_until
        from mark_app.user_session s
        join mark_app.app_user u on s.user_id = u.user_id
        where s.token_hash = %s
        """
        row = self._execute(q, (token_hash,), fetch_one=True)
        if not row:
            return None
        sess = {
            "token_hash": row["token_hash"],
            "user_id": row["user_id"],
            "csrf_hash": row["csrf_hash"],
            "expires_at": row["expires_at"],
            "last_seen_at": row["last_seen_at"],
        }
        u = {
            "user_id": row["user_id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
            "password_hash": row["password_hash"],
            "active": row["active"],
            "failed_count": row["failed_count"],
            "locked_until": row["locked_until"],
        }
        return sess, u

    def touch_session(self, token_hash: str) -> None:
        q = """
        update mark_app.user_session
        set last_seen_at = now()
        where token_hash = %s and last_seen_at < now() - interval '1 minute'
        """
        self._execute(q, (token_hash,), commit=True)

    def delete_session(self, token_hash: str) -> None:
        self._execute("delete from mark_app.user_session where token_hash = %s", (token_hash,), commit=True)

    def delete_user_sessions(self, user_id: int) -> None:
        self._execute("delete from mark_app.user_session where user_id = %s", (user_id,), commit=True)

    def active_sessions(self) -> int:
        q = "select count(*) as cnt from mark_app.user_session where expires_at > now()"
        row = self._execute(q, fetch_one=True)
        return int(row["cnt"]) if row and "cnt" in row else 0

    def token_by_hash(self, token_hash: str) -> dict[str, Any] | None:
        q = """
        select token_id, name, token_hash, scopes, created_by, expires_at
        from mark_app.api_token
        where token_hash = %s
        """
        return self._execute(q, (token_hash,), fetch_one=True)

    def admin_users(self) -> list[dict[str, Any]]:
        q = """
        select
            u.user_id,
            u.username,
            u.display_name,
            u.role,
            u.active,
            u.failed_count,
            u.locked_until,
            a.last_login_at
        from mark_app.app_user u
        left join (
            select user_id, max(created_at) as last_login_at
            from mark_app.audit_log
            where action = 'auth.login_ok'
            group by user_id
        ) a on a.user_id = u.user_id
        order by u.user_id
        """
        rows = self._execute(q, fetch_all=True)
        return rows if isinstance(rows, list) else []

    def unlock_user(self, user_id: int) -> bool:
        q = """
        update mark_app.app_user
        set failed_count = 0, locked_until = null
        where user_id = %s
        returning user_id
        """
        res = self._execute(q, (user_id,), fetch_one=True, commit=True)
        return res is not None

    def activity(self, date_from: Any, date_to: Any, run_id: int) -> dict[str, Any]:
        q_user = """
        select
            (a.created_at at time zone 'Asia/Bangkok')::date::text as day,
            u.user_id,
            u.display_name,
            count(*) filter (where a.action = 'review.saved')::int as reviews,
            count(*) filter (where a.action = 'approval.saved')::int as approvals
        from mark_app.audit_log a
        join mark_app.app_user u on u.user_id = a.user_id
        where a.action in ('review.saved', 'approval.saved')
          and (a.created_at at time zone 'Asia/Bangkok')::date >= %s
          and (a.created_at at time zone 'Asia/Bangkok')::date <= %s
        group by 1, 2, 3
        order by day asc, u.user_id asc
        """
        per_user_day = self._execute(q_user, (date_from, date_to), fetch_all=True)
        if not isinstance(per_user_day, list):
            per_user_day = []

        q_progress = """
        with latest_app as (
            select distinct on (elr_no) elr_no, decision
            from mark_app.approval
            where run_id = %s
            order by elr_no, created_at desc
        ),
        totals as (
            select count(*)::int as total
            from mark_logic.job_result
            where run_id = %s
        )
        select
            %s::int as run_id,
            coalesce(t.total, 0)::int as total_elrs,
            coalesce(count(*) filter (where l.decision = 'APPROVED'), 0)::int as approved,
            coalesce(count(*) filter (where l.decision = 'REJECTED'), 0)::int as rejected,
            (coalesce(t.total, 0) - coalesce(count(l.decision), 0))::int as undecided
        from totals t
        left join latest_app l on true
        group by t.total
        """
        prog_res = self._execute(q_progress, (run_id, run_id, run_id), fetch_one=True)
        if not prog_res:
            prog_res = {"run_id": run_id, "total_elrs": 0, "approved": 0, "rejected": 0, "undecided": 0}

        q_auth = """
        select
            (created_at at time zone 'Asia/Bangkok')::date::text as day,
            count(*) filter (where action = 'auth.login_ok')::int as login_ok,
            count(*) filter (where action = 'auth.login_failed')::int as login_failed,
            count(*) filter (where action = 'auth.locked')::int as locked,
            count(*) filter (where action = 'auth.session_expired')::int as session_expired
        from mark_app.audit_log
        where action in ('auth.login_ok', 'auth.login_failed', 'auth.locked', 'auth.session_expired')
          and (created_at at time zone 'Asia/Bangkok')::date >= %s
          and (created_at at time zone 'Asia/Bangkok')::date <= %s
        group by 1
        order by day asc
        """
        auth_per_day = self._execute(q_auth, (date_from, date_to), fetch_all=True)
        if not isinstance(auth_per_day, list):
            auth_per_day = []

        return {
            "per_user_day": per_user_day,
            "run_progress": prog_res,
            "auth_per_day": auth_per_day,
        }

    def audit_events(self, date_from: Any, date_to: Any, user_id: int | None, action: str | None, page: int) -> list[dict[str, Any]]:
        offset = max(0, (page - 1) * 50)
        q = """
        select
            a.created_at,
            a.action,
            a.user_id,
            u.display_name,
            host(a.client_ip) as client_ip,
            a.request_id,
            a.detail
        from mark_app.audit_log a
        left join mark_app.app_user u on u.user_id = a.user_id
        where (a.created_at at time zone 'Asia/Bangkok')::date >= %s
          and (a.created_at at time zone 'Asia/Bangkok')::date <= %s
          and (%s::bigint is null or a.user_id = %s::bigint)
          and (%s::text is null or a.action = %s::text)
        order by a.created_at desc
        limit 50 offset %s
        """
        rows = self._execute(q, (date_from, date_to, user_id, user_id, action, action, offset), fetch_all=True)
        return rows if isinstance(rows, list) else []

    @contextmanager
    def hold_scan_lock(self):
        """Borrow one connection from the pool, acquire session advisory lock, yield conn, unlock on SAME conn, return to pool."""
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("select pg_try_advisory_lock(hashtext('mark_scan_lock')) as locked;")
                row = cur.fetchone()
                locked = bool(row and (row[0] if isinstance(row, (tuple, list)) else row.get("locked")))
            if not locked:
                raise ScanLockConflict("A scan is already running")
            yield conn
        finally:
            try:
                with conn.cursor() as cur:
                    cur.execute("select pg_advisory_unlock(hashtext('mark_scan_lock'));")
                conn.commit()
            except Exception as exc:
                logger.warning("Error releasing scan advisory lock: %s", exc)
            self.pool.putconn(conn)

    def try_scan_lock(self) -> bool:
        row = self._execute("select pg_try_advisory_lock(hashtext('mark_scan_lock')) as locked", fetch_one=True)
        return bool(row and row.get("locked"))

    def release_scan_lock(self) -> None:
        self._execute("select pg_advisory_unlock(hashtext('mark_scan_lock'))", commit=True)

    def last_successful_scan(self, source: str | None = None) -> dict[str, Any] | None:
        """Fetch the most recent successful scan with finished_at not null and error null.

        Requirement (4): queries source in ('airflow', 'initial').
        """
        if source:
            q = """
            select * from mark_app.scan
            where source = %s and finished_at is not null and error is null
            order by started_at desc limit 1;
            """
            return self._execute(q, (source,), fetch_one=True)
        else:
            q = """
            select * from mark_app.scan
            where source in ('airflow', 'initial') and finished_at is not null and error is null
            order by started_at desc limit 1;
            """
            return self._execute(q, fetch_one=True)

    def create_scan(self, source: str, requested_by: str | None, from_ts: datetime | None,
                    to_ts: datetime | None) -> int:
        """Requirement (2): Create single scan row at start with finished_at=null and error=null."""
        row = self._execute(
            """
            insert into mark_app.scan (source, requested_by, from_ts, to_ts, started_at, finished_at, error, counts)
            values (%s, %s, %s, %s, now(), null, null, null)
            returning scan_id;
            """,
            (source, requested_by, from_ts, to_ts),
            fetch_one=True,
            commit=True,
        )
        return row["scan_id"] if isinstance(row, dict) else row[0]

    def finish_scan(self, scan_id: int, counts: dict[str, Any]) -> None:
        """Requirement (2): On completion, update finished_at and counts."""
        self._execute(
            """
            update mark_app.scan
            set finished_at = now(),
                counts = %s
            where scan_id = %s;
            """,
            (json.dumps(counts), scan_id),
            commit=True,
        )

    def fail_scan(self, scan_id: int, error: str, counts: dict[str, Any] | None = None) -> None:
        """Requirement (2): On error, update finished_at and error."""
        counts_json = json.dumps(counts) if counts is not None else None
        self._execute(
            """
            update mark_app.scan
            set finished_at = now(),
                error = %s,
                counts = coalesce(%s, counts)
            where scan_id = %s;
            """,
            (error, counts_json, scan_id),
            commit=True,
        )

    def record_scan(self, source: str, requested_by: str | None, from_ts: datetime | None,
                    to_ts: datetime | None, counts: dict[str, Any], error: str | None = None) -> int:
        # Backward compatibility helper
        scan_id = self.create_scan(source, requested_by, from_ts, to_ts)
        if error:
            self.fail_scan(scan_id, error, counts=counts)
        else:
            self.finish_scan(scan_id, counts)
        return scan_id

    def enqueue_work_item(self, scan_id: int | None, elr_no: str, reason: str) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into mark_app.work_item (scan_id, elr_no, state, reason)
                    values (%s, %s, 'queued', %s)
                    on conflict (elr_no) where state in ('queued', 'running', 'retry') do nothing
                    returning item_id;
                    """,
                    (scan_id, elr_no, reason),
                )
                row = cur.fetchone()
                conn.commit()
                return row is not None

    def get_elr_history(self, elr_no: str) -> dict[str, Any]:
        with self._conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    select r.revision, r.run_id, r.created_at, r.changed, r.result_unchanged,
                           j.processing_status, j.verification_status, j.approval_status, j.hold_reason
                    from mark_app.elr_revision r
                    left join mark_logic.job_result j on j.run_id = r.run_id and j.elr_no = r.elr_no
                    where r.elr_no = %s
                    order by r.revision asc;
                    """,
                    (elr_no,),
                )
                rev_rows = cur.fetchall()

                cur.execute(
                    "select 1 from mark_app.work_item where elr_no = %s and state in ('queued', 'running', 'retry') limit 1;",
                    (elr_no,),
                )
                queued = cur.fetchone() is not None

                if not rev_rows:
                    return {"in_system": False, "latest": None, "revisions": [], "queued": queued}

                latest = rev_rows[-1]
                return {
                    "in_system": True,
                    "latest": {
                        "run_id": latest["run_id"],
                        "revision": latest["revision"],
                        "status": latest.get("processing_status") or "DONE",
                        "created_at": latest.get("created_at"),
                    },
                    "revisions": rev_rows,
                    "queued": queued,
                }

    def add_notification(self, elr_no: str, kind: str, message: str = "", run_id: int | None = None, revision: int | None = None) -> None:
        if not message:
            message = f"ELR {elr_no}: {kind}"
        with self._conn() as conn:
            with conn.cursor() as cur:
                # Defense-in-depth: skip if unread notification for (elr_no, kind, coalesce(revision, 0)) exists
                try:
                    cur.execute(
                        """
                        select 1 from mark_app.notification
                        where elr_no = %s
                          and kind = %s
                          and coalesce(revision, 0) = coalesce(%s, 0)
                          and read_at is null
                        limit 1;
                        """,
                        (elr_no, kind, revision),
                    )
                    if cur.fetchone():
                        return
                except Exception:
                    logger.exception("Failed checking existing unread notification for %s (%s)", elr_no, kind)
                    conn.rollback()

                try:
                    cur.execute(
                        """
                        insert into mark_app.notification (elr_no, run_id, revision, kind, message)
                        values (%s, %s, %s, %s, %s)
                        on conflict (elr_no, kind, coalesce(revision, 0)) where read_at is null do nothing;
                        """,
                        (elr_no, run_id, revision, kind, message),
                    )
                    conn.commit()
                except Exception:
                    logger.exception("Failed inserting notification with unread partial unique index for %s (%s)", elr_no, kind)
                    conn.rollback()
                    try:
                        cur.execute(
                            """
                            insert into mark_app.notification (elr_no, run_id, revision, kind, message)
                            values (%s, %s, %s, %s, %s)
                            on conflict (elr_no, kind, revision) do nothing;
                            """,
                            (elr_no, run_id, revision, kind, message),
                        )
                        conn.commit()
                    except Exception:
                        logger.exception("Failed fallback notification insert for %s (%s)", elr_no, kind)
                        conn.rollback()

    notify = add_notification

    def list_notifications(self, user_id: int, unread_only: bool = True) -> list[dict[str, Any]]:
        if unread_only:
            q = "select * from mark_app.notification where read_at is null order by created_at desc limit 100;"
            return self._execute(q, fetch_all=True) or []
        else:
            q = "select * from mark_app.notification order by created_at desc limit 100;"
            return self._execute(q, fetch_all=True) or []

    def mark_notification_read(self, notif_id: int, username: str) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update mark_app.notification set read_by = %s, read_at = now() where notification_id = %s returning notification_id;",
                    (username, notif_id),
                )
                row = cur.fetchone()
                conn.commit()
                return row is not None

    def get_previous_revisions(self, elr_no: str) -> list[Any]:
        from mark_engine.history.decide import RevisionKey
        rows = self._execute(
            "select revision, oracle_fp, docs_fp from mark_app.elr_revision where elr_no = %s order by revision asc;",
            (elr_no,),
            fetch_all=True,
        )
        if not rows:
            return []
        return [RevisionKey(r["revision"], r["oracle_fp"], r["docs_fp"]) for r in rows]

    def requeue_unapproved_step6(self) -> int:
        query = """
        select distinct on (r.elr_no) r.elr_no, j.processing_status, j.approval_status
        from mark_app.elr_revision r
        join mark_logic.job_result j on j.run_id = r.run_id and j.elr_no = r.elr_no
        order by r.elr_no, r.revision desc;
        """
        rows = self._execute(query, fetch_all=True)
        if not rows:
            return 0
        count = 0
        for r in rows:
            if r["processing_status"] == "HOLD" or r.get("approval_status") != "APPROVED":
                if self.enqueue_work_item(None, r["elr_no"], "retry_docs"):
                    count += 1
        return count

