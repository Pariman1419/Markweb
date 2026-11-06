"""Auto-review background worker loop and queue processor."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from enum import Enum
from functools import partial
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Sequence

import psycopg2

import mark_engine
from mark_engine.abs.brand_page import extract_marking_image
from mark_engine.adapters.env import load_env
from mark_engine.adapters.inference_cache import load_cached_inference
from mark_engine.adapters.inference_service import (
    InferenceClient,
    InferenceUnavailable,
    load_service_inference,
    load_service_inference_for_image,
)
from mark_engine.adapters.oracle_client import connect_actl
from mark_engine.documents.resolve import resolve_documents
from mark_engine.domain.models import (
    ApprovalStatus,
    DocumentResolution,
    JobResult,
    LineComparison,
    LineStatus,
    ProcessingStatus,
    Side,
)
from mark_engine.generate.mark_layout import MarkLayout, parse_layout
from mark_engine.history.decide import Decision, RevisionKey, decide
from mark_engine.history.fingerprint import (
    changed_oracle_fields,
    docs_fp,
    oracle_fp,
    result_fp,
    version_fp,
)
from mark_engine.pipeline import process_elr
from mark_engine.rules.ruleset import RuleSet
from mark_engine.select import pending_reason
from services.worker.oracle_source import fetch_layout, fetch_one, to_engine
from services.worker.queue import claim, fail, fail_with_backoff, finish
from services.worker.results import day_run_for, notify_for, write_result

logger = logging.getLogger("mark_worker")


class CycleResult(str, Enum):
    NO_ITEM = "NO_ITEM"
    PROCESSED = "PROCESSED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


def probe_resolution(resolution: DocumentResolution | None) -> dict[str, dict[str, Any]]:
    """Capture path, size, and mtime for resolved ABS and SLR files."""
    if not resolution:
        return {}
    probe: dict[str, dict[str, Any]] = {}
    paths: list[str] = []
    if resolution.abs and resolution.abs.path:
        paths.append(resolution.abs.path)
    for slr_ref in resolution.slr:
        if slr_ref and slr_ref.path:
            paths.append(slr_ref.path)

    for p_str in sorted(set(paths)):
        p = Path(p_str)
        try:
            st = p.stat()
            probe[p_str] = {
                "size": st.st_size,
                "mtime": st.st_mtime,
            }
        except OSError:
            probe[p_str] = {
                "size": -1,
                "mtime": -1,
            }
    return probe


def docs_probe_matches(stored_probe: dict[str, Any] | None) -> bool:
    """Return True if every file in stored_probe exists on disk with unchanged size and mtime."""
    if not stored_probe:
        return False
    for path_str, expected_stat in stored_probe.items():
        p = Path(path_str)
        try:
            st = p.stat()
            if st.st_size != expected_stat.get("size"):
                return False
            expected_mtime = expected_stat.get("mtime", 0)
            if abs(st.st_mtime - expected_mtime) > 0.1:
                return False
        except OSError:
            return False
    return True


def get_service_model_version(client: InferenceClient | None = None) -> str:
    """Extract model version from InferenceClient health check, or fallback to default."""
    if client is not None:
        try:
            h = client.health()
            if isinstance(h, dict):
                model_info = h.get("model") or {}
                ver = model_info.get("service_version")
                if ver:
                    return str(ver)
        except Exception:
            pass
    return "exp09"


def run_worker_cycle(
    cur_pg: Any,
    cur_queue: Any,
    oracle_row: Mapping[str, Any] | None = None,
    conn_oracle: Any = None,
    client: InferenceClient | None = None,
    inference_loader: Callable[..., Any] | None = None,
    rules: RuleSet | None = None,
    layouts: Mapping[int, MarkLayout] | None = None,
    nas_root: Path | None = None,
    months: Sequence[str] | None = None,
    work_dir: Path | None = None,
    folder_index: dict[str, tuple[Path, ...]] | None = None,
    resolved_docs_fp: str | None = None,
    force_oracle_fp: str | None = None,
    worker_id: str = "worker-1",
    today: Any = None,
    conn_pg: Any = None,
) -> CycleResult:
    """Execute one item from the work queue.

    Returns CycleResult.NO_ITEM if no item claimed,
    CycleResult.SKIPPED if item was claimed but skipped,
    CycleResult.PROCESSED if item was claimed and processed (including errors handled).
    """
    item = claim(cur_queue, worker_id)
    if not item:
        return CycleResult.NO_ITEM

    try:
        elr_no = item.elr_no
        day = today or datetime.now(timezone.utc).date()

        # 1. Fetch fresh Oracle row if not passed directly
        if oracle_row is None and conn_oracle is not None:
            oracle_row = fetch_one(conn_oracle, elr_no)

        if not oracle_row:
            fail(cur_queue, item.item_id, f"ELR {elr_no} not found in Oracle")
            return CycleResult.PROCESSED

        meta, oracle_mark, _ = to_engine(oracle_row)

        # 2. Gate check (G0 / eligibility)
        review_step = os.environ.get("MARK_REVIEW_STEP", "6")
        p_reason = pending_reason(meta, review_step)

        # 3. Compute oracle fingerprint
        ofp = force_oracle_fp or oracle_fp(oracle_row)

        # 4. Fetch previous revisions from Postgres
        cur_pg.execute(
            "select revision, oracle_fp, docs_fp, result_fp, run_id, docs_probe "
            "from mark_app.elr_revision where elr_no = %s order by revision asc;",
            (elr_no,),
        )
        rev_rows = cur_pg.fetchall()
        prev_keys = [RevisionKey(r[0], r[1], r[2]) for r in rev_rows]
        latest_prev_result_fp = rev_rows[-1][3] if rev_rows else None
        latest_prev_run_id = rev_rows[-1][4] if rev_rows else None
        latest_prev_docs_probe = rev_rows[-1][5] if rev_rows else None
        if isinstance(latest_prev_docs_probe, str):
            try:
                latest_prev_docs_probe = json.loads(latest_prev_docs_probe)
            except Exception:
                latest_prev_docs_probe = None

        # 5. Cheap-first decision check
        manual = (item.reason == "recheck")
        dec1 = decide(p_reason, prev_keys, ofp, docs_fp=None, manual=manual)

        if dec1.action == "skip_not_eligible":
            finish(cur_queue, item.item_id, revision=prev_keys[-1].revision if prev_keys else None)
            return CycleResult.SKIPPED

        if dec1.action == "skip_unchanged":
            # Oracle is unchanged; check docs_probe before doing NAS resolution
            if latest_prev_docs_probe and docs_probe_matches(latest_prev_docs_probe):
                finish(cur_queue, item.item_id, revision=prev_keys[-1].revision if prev_keys else None)
                return CycleResult.SKIPPED

        # 6. Resolve documents from NAS and compute real docs_fp
        root = nas_root or (Path(os.environ["NAS_ROOT"]) / "ELR Online 2026" if "NAS_ROOT" in os.environ else Path("."))
        m_list = list(months) if months else [
            "1_JAN", "2_FEB", "3_MAR", "4_APR", "5_MAY", "6_JUN",
            "7_JUL", "8_AUG", "9_SEP", "10_OCT", "11_NOV", "12_DEC"
        ]
        job_work = work_dir or Path(f"work/{elr_no}")

        if resolved_docs_fp is not None:
            dfp = resolved_docs_fp
            resolution: DocumentResolution | None = None
            current_probe: dict[str, Any] = {}
        else:
            try:
                resolution = resolve_documents(meta, root, m_list, job_work, folder_index=folder_index)
            except Exception as exc:
                logger.warning("Document resolution error for %s: %s", elr_no, exc)
                resolution = None
            dfp = docs_fp(resolution)
            current_probe = probe_resolution(resolution)

        # Extract marking image from resolved ABS if available
        marking_image_path: Path | None = None
        if resolution and resolution.abs and resolution.abs.path:
            abs_p = Path(resolution.abs.path)
            if abs_p.is_file():
                try:
                    images_dir = job_work / "images"
                    marking_image_path, _ = extract_marking_image(abs_p, images_dir)
                except Exception as exc:
                    logger.warning("Failed to extract marking image for %s: %s", elr_no, exc)

        # 7. Post-resolve verification (Requirement 5 & Reverted Oracle row check)
        dec2 = decide(p_reason, prev_keys, ofp, docs_fp=dfp, manual=manual)
        if dec2.action == "skip_same_as_rev":
            finish(cur_queue, item.item_id, revision=dec2.same_as_rev)
            return CycleResult.SKIPPED

        if dec2.action == "skip_unchanged":
            finish(cur_queue, item.item_id, revision=prev_keys[-1].revision if prev_keys else None)
            return CycleResult.SKIPPED

        # 8. Setup rules, layouts, and loader
        active_rules = rules or RuleSet.load()
        active_layouts = dict(layouts) if layouts is not None else {}
        if meta.top_mark_id is not None and meta.top_mark_id not in active_layouts and conn_oracle is not None:
            try:
                l_rows = fetch_layout(conn_oracle, meta.top_mark_id)
                if l_rows:
                    active_layouts[meta.top_mark_id] = parse_layout(meta.top_mark_id, l_rows)
            except Exception as exc:
                logger.warning("Failed to fetch layout for MARK_ID %s: %s", meta.top_mark_id, exc)

        if inference_loader is not None:
            active_loader = inference_loader
        else:
            inf_mode = os.environ.get("MARK_INFERENCE", "cache")
            if inf_mode == "service":
                addr = os.getenv("MARK_INFERENCE_ADDR", "10.151.28.9:50051")
                api_key = os.getenv("MARK_INFERENCE_API_KEY", "")
                if client is None:
                    client = InferenceClient(addr=addr, api_key=api_key)
                if marking_image_path is not None:
                    active_loader = partial(load_service_inference_for_image, client, marking_image_path)
                else:
                    cache_dir = Path(os.getenv("MARK_CACHE_DIR", "cache"))
                    active_loader = partial(load_service_inference, client, cache_dir / "images", cache_dir / "images_index.csv")
            else:
                cache_dir = Path(os.getenv("MARK_CACHE_DIR", "cache"))
                active_loader = partial(load_cached_inference, cache_dir)

        # 9. Execute real engine job
        try:
            job = process_elr(
                meta,
                oracle_mark,
                root,
                m_list,
                job_work,
                active_rules,
                active_loader,
                layouts=active_layouts,
                folder_index=folder_index,
                resolution=resolution,
            )
        except InferenceUnavailable as exc:
            backoff_res = fail_with_backoff(cur_queue, item.item_id, item.attempts, str(exc))
            if backoff_res == "retry":
                return CycleResult.PROCESSED

            # Final retry attempt exhausted -> write HOLD INFERENCE_FAILED
            job = JobResult(
                elr_no=elr_no,
                processing_status=ProcessingStatus.HOLD,
                hold_reason="INFERENCE_FAILED",
                verification_status=None,
                approval_status=ApprovalStatus.NOT_REVIEWED,
                resolution=resolution,
                expected=None,
                comparisons=tuple(
                    LineComparison(
                        side=s,
                        line_no=n,
                        expected=None,
                        oracle=text,
                        status=LineStatus.NOT_MEASURABLE,
                        compare_rules=(),
                        detail="INFERENCE_FAILED",
                    )
                    for s, n, text in oracle_mark.lines
                ),
            )

        # 10. Compute fingerprints and determine changes
        rfp = result_fp(job)
        model_ver = get_service_model_version(client)
        vfp = version_fp(mark_engine.__version__, model_ver)
        result_unchanged = (latest_prev_result_fp is not None and latest_prev_result_fp == rfp)

        changed_kind = dec2.changed or "new"
        changed_fields: list[str] = []
        if latest_prev_run_id is not None:
            cur_pg.execute(
                "select line_extra from mark_app.elr_snapshot where run_id = %s and elr_no = %s;",
                (latest_prev_run_id, elr_no),
            )
            row_extra = cur_pg.fetchone()
            if row_extra and row_extra[0]:
                extra_data = row_extra[0] if isinstance(row_extra[0], dict) else json.loads(row_extra[0])
                prev_oracle_row = extra_data.get("oracle_row")
                if prev_oracle_row:
                    changed_fields = changed_oracle_fields(prev_oracle_row, oracle_row)

        # 11. Allocate daily run
        run_id = day_run_for(
            cur_pg,
            elr_no,
            day,
            engine_version=mark_engine.__version__,
            model_version=model_ver,
        )

        # 12. Check if previous revision was approved
        prev_approved = False
        if latest_prev_run_id is not None:
            cur_pg.execute(
                "select 1 from mark_app.approval where elr_no = %s and run_id = %s and decision = 'APPROVED';",
                (elr_no, latest_prev_run_id),
            )
            prev_approved = (cur_pg.fetchone() is not None)

        # 13. Write result (INSERT ONLY)
        rev_info = {
            "run_id": run_id,
            "oracle_fp": ofp,
            "docs_fp": dfp,
            "version_fp": vfp,
            "result_fp": rfp,
            "changed": changed_kind,
            "changed_fields": changed_fields,
            "result_unchanged": result_unchanged,
            "docs_probe": current_probe,
        }
        new_rev = write_result(cur_pg, job, meta, oracle_row, resolution=resolution, revision_info=rev_info)

        # 14. Send notifications if needed
        notify_for(cur_pg, job, new_rev, prev_approved=prev_approved, run_id=run_id)

        # 15. Mark work item finished
        finish(cur_queue, item.item_id, revision=new_rev)
        return CycleResult.PROCESSED

    except Exception as exc:
        logger.exception("Error processing ELR %s (item %s): %s", item.elr_no, item.item_id, exc)
        conn = conn_pg or getattr(cur_pg, "connection", None)
        if conn is not None and hasattr(conn, "rollback"):
            try:
                conn.rollback()
            except Exception:
                pass
        try:
            fail_with_backoff(cur_queue, item.item_id, item.attempts, str(exc))
            if conn is not None and hasattr(conn, "commit"):
                conn.commit()
        except Exception as queue_exc:
            logger.exception("Failed to record error backoff for item %s: %s", item.item_id, queue_exc)
        return CycleResult.ERROR


def main() -> None:
    parser = argparse.ArgumentParser(description="Mark Automation auto-review worker")
    parser.add_argument("--once", action="store_true", help="Process until queue is empty, then exit")
    parser.add_argument("--poll-seconds", type=int, default=5, help="Sleep seconds when queue is idle")
    parser.add_argument("--worker-id", type=str, default=f"worker-{os.getpid()}")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("Starting auto-review worker (id=%s, once=%s)", args.worker_id, args.once)

    load_env()
    conn_pg = psycopg2.connect(
        host=os.environ.get("PGHOST", "10.151.28.2"),
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ.get("PGDATABASE", "mark_web"),
        user=os.environ.get("MARK_WORKER_PG_USER", "mark_worker"),
        password=os.environ.get("MARK_WORKER_PG_PASSWORD", ""),
    )
    conn_oracle = connect_actl()

    consecutive_cycle_errors = 0
    try:
        while True:
            cycle_err = False
            try:
                with conn_pg:
                    with conn_pg.cursor() as cur:
                        res = run_worker_cycle(
                            cur,
                            cur,
                            conn_oracle=conn_oracle,
                            worker_id=args.worker_id,
                            conn_pg=conn_pg,
                        )
            except Exception as loop_exc:
                logger.exception("Worker cycle loop error: %s", loop_exc)
                cycle_err = True
                res = CycleResult.ERROR
                time.sleep(args.poll_seconds)

            if cycle_err or res == CycleResult.ERROR:
                consecutive_cycle_errors += 1
                if args.once and consecutive_cycle_errors >= 5:
                    logger.error("5 consecutive cycle errors encountered in --once mode; exiting with exit code 1")
                    sys.exit(1)
            else:
                consecutive_cycle_errors = 0

            if res == CycleResult.NO_ITEM:
                if args.once:
                    break
                time.sleep(args.poll_seconds)
    finally:
        try:
            conn_pg.close()
        except Exception:
            pass
        try:
            conn_oracle.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
