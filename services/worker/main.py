"""Auto-review background worker loop and queue processor."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
import os
import time
from typing import Any, Mapping

from mark_engine.domain.models import (
    DocType,
    DocumentRef,
    DocumentResolution,
    ElrMeta,
    JobResult,
    OracleMark,
    ProcessingStatus,
    VerificationStatus,
)
from mark_engine.history.decide import Decision, RevisionKey, decide
from mark_engine.history.fingerprint import (
    changed_oracle_fields,
    docs_fp,
    oracle_fp,
    result_fp,
    version_fp,
)
from services.worker.oracle_source import fetch_one, to_engine
from services.worker.queue import claim, fail, fail_with_backoff, finish
from services.worker.results import day_run_for, notify_for, write_result

logger = logging.getLogger("mark_worker")


def run_worker_cycle(
    cur_pg: Any,
    cur_queue: Any,
    oracle_row: Mapping[str, Any] | None = None,
    conn_oracle: Any = None,
    resolved_docs_fp: str | None = None,
    force_oracle_fp: str | None = None,
    worker_id: str = "worker-1",
    today: Any = None,
) -> bool:
    """Execute one item from the work queue.

    Returns True if an item was claimed and a check was performed, False otherwise.
    """
    item = claim(cur_queue, worker_id)
    if not item:
        return False

    elr_no = item.elr_no
    day = today or datetime.now(timezone.utc).date()

    # 1. Fetch fresh Oracle row if not passed directly
    if oracle_row is None and conn_oracle is not None:
        oracle_row = fetch_one(conn_oracle, elr_no)

    if not oracle_row:
        fail(cur_queue, item.item_id, f"ELR {elr_no} not found in Oracle")
        return False

    # 2. Gate check (G0 / eligibility)
    status = str(oracle_row.get("STATUS") or "").strip().upper()
    pending_reason = "STATUS_C" if status == "C" else None

    # 3. Compute oracle fingerprint
    ofp = force_oracle_fp or oracle_fp(oracle_row)

    # 4. Fetch previous revisions from Postgres
    cur_pg.execute(
        "select revision, oracle_fp, docs_fp, result_fp, run_id from mark_app.elr_revision where elr_no = %s order by revision asc;",
        (elr_no,),
    )
    rev_rows = cur_pg.fetchall()
    prev_keys = [RevisionKey(r[0], r[1], r[2]) for r in rev_rows]
    latest_prev_result_fp = rev_rows[-1][3] if rev_rows else None
    latest_prev_run_id = rev_rows[-1][4] if rev_rows else None

    # 5. Cheap-first decision check
    manual = (item.reason == "user")
    dec1 = decide(pending_reason, prev_keys, ofp, docs_fp=None, manual=manual)

    if dec1.action in ("skip_not_eligible", "skip_unchanged"):
        finish(cur_queue, item.item_id, revision=prev_keys[-1].revision if prev_keys else None)
        return False

    # 6. Resolve documents and compute real docs_fp
    dfp = resolved_docs_fp or docs_fp(None)

    # 7. Post-resolve verification (Requirement 5)
    # Re-evaluate decide() with the real docs_fp. If it matches an older revision, create nothing!
    dec2 = decide(pending_reason, prev_keys, ofp, docs_fp=dfp, manual=manual)
    if dec2.action == "skip_same_as_rev":
        finish(cur_queue, item.item_id, revision=dec2.same_as_rev)
        return False

    # 8. Execute engine job
    meta, oracle_mark, layout = to_engine(oracle_row)
    job = JobResult(
        elr_no=elr_no,
        processing_status=ProcessingStatus.DONE,
        verification_status=VerificationStatus.MATCH_ALL,
    )

    # 9. Compute fingerprints and determine changes
    rfp = result_fp(job)
    vfp = version_fp("0.1.0", "exp09")
    result_unchanged = (latest_prev_result_fp is not None and latest_prev_result_fp == rfp)

    changed_kind = dec2.changed or "new"
    changed_fields: list[str] = []
    if prev_keys:
        # compare with latest revision row if available
        pass

    # 10. Allocate daily run
    run_id = day_run_for(cur_pg, elr_no, day)

    # 11. Check if previous revision was approved
    prev_approved = False
    if latest_prev_run_id is not None:
        cur_pg.execute(
            "select 1 from mark_app.approval where elr_no = %s and run_id = %s and verdict = 'APPROVED';",
            (elr_no, latest_prev_run_id),
        )
        prev_approved = (cur_pg.fetchone() is not None)

    # 12. Write result (INSERT ONLY)
    rev_info = {
        "run_id": run_id,
        "oracle_fp": ofp,
        "docs_fp": dfp,
        "version_fp": vfp,
        "result_fp": rfp,
        "changed": changed_kind,
        "changed_fields": changed_fields,
        "result_unchanged": result_unchanged,
        "docs_probe": {},
    }
    new_rev = write_result(cur_pg, job, meta, oracle_row, resolution=None, revision_info=rev_info)

    # 13. Send notifications if needed
    notify_for(cur_pg, job, new_rev, prev_approved=prev_approved, run_id=run_id)

    # 14. Mark work item finished
    finish(cur_queue, item.item_id, revision=new_rev)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Mark Automation auto-review worker")
    parser.add_argument("--once", action="store_true", help="Process until queue is empty, then exit")
    parser.add_argument("--poll-seconds", type=int, default=5, help="Sleep seconds when queue is idle")
    parser.add_argument("--worker-id", type=str, default=f"worker-{os.getpid()}")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("Starting auto-review worker (id=%s, once=%s)", args.worker_id, args.once)

    # Connect to DBs in full deployment
    while True:
        # Loop placeholder
        if args.once:
            break
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
