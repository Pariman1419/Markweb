"""Postgres queue management for the auto-review worker using SKIP LOCKED."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

RETRY_DELAYS: tuple[int, ...] = (1, 5, 15)  # in minutes


@dataclass(frozen=True, slots=True)
class WorkItem:
    item_id: int
    scan_id: int | None
    elr_no: str
    state: str
    reason: str
    attempts: int
    next_attempt_at: datetime
    revision: int | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def enqueue(cur: Any, scan_id: int | None, elr_no: str, reason: str) -> bool:
    """Insert a work item into the queue.

    If an active item ('queued', 'running', 'retry') already exists for this ELR,
    the insert is skipped due to partial unique index, returning False.
    """
    sql = """
    insert into mark_app.work_item (scan_id, elr_no, reason, state)
    values (%s, %s, %s, 'queued')
    on conflict (elr_no) where state in ('queued', 'running', 'retry') do nothing
    returning item_id;
    """
    cur.execute(sql, (scan_id, elr_no, reason))
    row = cur.fetchone()
    return row is not None


def claim(cur: Any, worker_id: str) -> WorkItem | None:
    """Claim the next ready work item using FOR UPDATE SKIP LOCKED.

    Also resets any items stuck in 'running' state for more than 15 minutes back to 'retry'.
    """
    # 1. Reset stuck items
    reset_sql = """
    update mark_app.work_item
    set state = 'retry',
        updated_at = now()
    where state = 'running'
      and updated_at < now() - interval '15 minutes';
    """
    cur.execute(reset_sql)

    # 2. Select next ready item
    select_sql = """
    select item_id, scan_id, elr_no, state, reason, attempts, next_attempt_at, revision, error, created_at, updated_at
    from mark_app.work_item
    where state in ('queued', 'retry')
      and next_attempt_at <= now()
    order by created_at asc
    for update skip locked
    limit 1;
    """
    cur.execute(select_sql)
    row = cur.fetchone()
    if not row:
        return None

    item_id, scan_id, elr_no, state, reason, attempts, next_attempt_at, revision, error, created_at, updated_at = row

    # 3. Mark running and increment attempts
    update_sql = """
    update mark_app.work_item
    set state = 'running',
        attempts = attempts + 1,
        updated_at = now()
    where item_id = %s;
    """
    cur.execute(update_sql, (item_id,))

    return WorkItem(
        item_id=item_id,
        scan_id=scan_id,
        elr_no=elr_no,
        state="running",
        reason=reason,
        attempts=attempts + 1,
        next_attempt_at=next_attempt_at,
        revision=revision,
        error=error,
        created_at=created_at,
        updated_at=updated_at,
    )


def finish(cur: Any, item_id: int, revision: int | None = None) -> None:
    """Mark a work item as done with the generated revision number."""
    sql = """
    update mark_app.work_item
    set state = 'done',
        revision = %s,
        updated_at = now()
    where item_id = %s;
    """
    cur.execute(sql, (revision, item_id))


def fail(cur: Any, item_id: int, error: str, retry_in: timedelta | None = None) -> None:
    """Mark a work item as retry (if retry_in provided) or failed."""
    if retry_in is not None:
        seconds = int(retry_in.total_seconds())
        sql = """
        update mark_app.work_item
        set state = 'retry',
            error = %s,
            next_attempt_at = now() + %s * interval '1 second',
            updated_at = now()
        where item_id = %s;
        """
        cur.execute(sql, (error, seconds, item_id))
    else:
        sql = """
        update mark_app.work_item
        set state = 'failed',
            error = %s,
            updated_at = now()
        where item_id = %s;
        """
        cur.execute(sql, (error, item_id))


def fail_with_backoff(cur: Any, item_id: int, attempts: int, error: str) -> str:
    """Fail a work item with exponential backoff (1m, 5m, 15m), or transition to 'failed' after 3 attempts."""
    if attempts <= len(RETRY_DELAYS):
        delay_minutes = RETRY_DELAYS[attempts - 1]
        fail(cur, item_id, error, retry_in=timedelta(minutes=delay_minutes))
        return "retry"
    else:
        fail(cur, item_id, error, retry_in=None)
        return "failed"
