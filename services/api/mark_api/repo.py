"""PostgreSQL repository layer with connection pooling, slow query logging and metrics."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
import time
from typing import Any

import psycopg2
from psycopg2.extras import DictCursor, Json, RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

from mark_api.logging import log_event
from mark_engine.adapters.env import load_env


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
                raise

    def runs(self) -> list[dict[str, Any]]:
        return self._execute("select run_id, period, created_at, note from mark_logic.run order by run_id desc", fetch_all=True)

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

    def token_by_hash(self, token_hash: str) -> dict[str, Any] | None:
        q = """
        select token_id, name, token_hash, scopes, created_by, expires_at
        from mark_app.api_token
        where token_hash = %s
        """
        return self._execute(q, (token_hash,), fetch_one=True)
