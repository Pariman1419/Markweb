"""Results writer for auto-review daily runs and Postgres repository operations."""

from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date
import json
from pathlib import Path
import re
import shutil
from typing import Any, Mapping

from mark_engine.domain.models import DocumentResolution, JobResult, LineStatus, ProcessingStatus

MONTH = {
    "01": "1_JAN", "02": "2_FEB", "03": "3_MAR", "04": "4_APR", "05": "5_MAY", "06": "6_JUN",
    "07": "7_JUL", "08": "8_AUG", "09": "9_SEP", "10": "10_OCT", "11": "11_NOV", "12": "12_DEC",
}


def dashboard_result(job: JobResult) -> str:
    """Use the same result precedence as the ELR listing."""
    if job.processing_status == ProcessingStatus.HOLD:
        return "HOLD"
    if job.processing_status == ProcessingStatus.FAILED:
        return "ERROR"
    statuses = [(str(line.status), bool(line.warning)) for line in job.comparisons]
    if any(status in ("DIFF", "DB_EMPTY", "NOT_MARKED") for status, _ in statuses):
        return "ERROR"
    if any(status in ("MATCH_SHIFT", "NEEDS_REVIEW") or
           (status in ("MATCH", "MATCH_SLR", "MATCH_LOT") and warning)
           for status, warning in statuses):
        return "WARNING"
    if statuses and all(status in ("MATCH", "MATCH_SLR", "MATCH_LOT") for status, _ in statuses):
        return "TRUE"
    return "UNMEASURED"


def _abs_number(s: str) -> str:
    m = re.search(r"ABS\d{6}", s or "", re.IGNORECASE)
    return m.group(0).upper() if m else ""


def line_row(run_id: int, r: dict[str, Any], abs_no: str, parity: str) -> tuple:
    cause = r.get("hold_reason") or r.get("detail") or r.get("compare_rules") or None
    detail = "; ".join(f"{k}={v}" for k, v in [
        ("rules", r.get("compare_rules", "")), ("flags", r.get("flags", "")),
        ("detail", r.get("detail", "")), ("warning", r.get("warning", "")),
        ("hold_detail", r.get("hold_detail", "")), ("review_detail", r.get("review_detail", "")),
        ("review_verdict", r.get("review_verdict", "")),
        ("system_status", r["status"] if r.get("final_status") and r["final_status"] != r["status"] else ""),
        ("layout_source", r.get("layout_source", "")), ("parity_vs_r0", parity),
    ] if v)
    final = r.get("final_status") or r["status"]
    month_val = MONTH.get(r["elr_no"][5:7]) if len(r["elr_no"]) >= 7 else None
    return (
        run_id, r["elr_no"], _abs_number(abs_no), r["side"], int(r["line_no"]),
        month_val, r.get("expected_mark") or None,
        r.get("oracle_mark") or None, final, cause, detail,
        r["status"], final, r.get("review_detail") or None, r.get("warning") or None,
        r.get("hold_detail") or None, r.get("layout_source") or None
    )


def job_row(run_id: int, row: dict[str, Any]) -> tuple:
    return (
        run_id, row["elr_no"], row["processing_status"], row.get("hold_reason") or None,
        row.get("hold_detail") or None, row.get("review_detail") or None,
        row.get("verification_status") or None, row.get("approval_status") or None,
        row.get("layout_source") or None, row.get("abs_no") or None
    )


def build_snapshot_rows(run_id: int, oracle_dir: Path, cache_dir: Path, run_dir: Path) -> list[dict[str, Any]]:
    import pymupdf
    from mark_engine.domain.models import Side
    from mark_engine.slr.parse import parse_slr

    oracle_dir = Path(oracle_dir)
    cache_dir = Path(cache_dir)
    run_dir = Path(run_dir)

    # 1. Load elr_meta
    meta_path = oracle_dir / "elr_meta.json"
    raw_meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else []
    meta_by_elr = {r["ELR_NO"]: r for r in raw_meta}

    # 2. Load mark_layout
    layout_path = oracle_dir / "mark_layout.json"
    raw_layouts = json.loads(layout_path.read_text(encoding="utf-8")) if layout_path.is_file() else {}

    # 3. Load cache images_index
    img_index_path = cache_dir / "images_index.csv"
    img_by_elr: dict[str, dict[str, str]] = {}
    if img_index_path.is_file():
        with open(img_index_path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                img_by_elr[row["elr"]] = row

    # 4. Load jobs.csv to get ordered list of ELRs
    jobs_path = run_dir / "jobs.csv"
    jobs: list[dict[str, str]] = []
    if jobs_path.is_file():
        with open(jobs_path, encoding="utf-8") as f:
            jobs = list(csv.DictReader(f))
    else:
        jobs = [{"elr_no": elr} for elr in meta_by_elr]

    # 5. Load lines.csv for line_extra (TOP side only)
    lines_path = run_dir / "lines.csv"
    lines_by_elr: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    if lines_path.is_file():
        with open(lines_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("side") == "TOP":
                    l_no = str(row["line_no"])
                    lines_by_elr[row["elr_no"]][l_no] = {
                        "compare_rules": row.get("compare_rules", ""),
                        "flags": row.get("flags", ""),
                        "detail": row.get("detail", ""),
                    }

    rows: list[dict[str, Any]] = []

    for job in jobs:
        elr_no = job["elr_no"]
        meta = meta_by_elr.get(elr_no, {})

        # top_mark_id
        top_mark_id_val = meta.get("TOP_MARK_ID")
        top_mark_id = int(float(top_mark_id_val)) if top_mark_id_val is not None else None

        # layout_code
        layout_code = meta.get("TOP_LAYOUT_CODE") or None

        # line_extra
        line_extra = lines_by_elr.get(elr_no, {})

        # oracle_top_raw: 5 strings
        oracle_top_raw = [meta.get(f"TOP_MARK{i}") or "" for i in range(1, 6)]

        # layout_cells: 5x18
        layout_cells = None
        if top_mark_id is not None:
            layout_data = raw_layouts.get(str(top_mark_id)) or raw_layouts.get(top_mark_id)
            if layout_data is not None:
                grid: list[list[str | None]] = [[None for _ in range(18)] for _ in range(5)]
                for r_item in layout_data:
                    # r_item: [row, col, char]
                    r, c, ch = r_item[0], r_item[1], r_item[2]
                    if 1 <= r <= 5 and 1 <= c <= 18:
                        grid[r - 1][c - 1] = ch
                layout_cells = grid

        # image info
        img_info = img_by_elr.get(elr_no)
        abs_file = img_info["abs_file"] if img_info and "abs_file" in img_info else (job.get("abs_no") or None)
        abs_sha256 = img_info.get("sha256") if img_info else None
        image_path = None
        if img_info and img_info.get("image") and img_info.get("sha256"):
            image_path = f"abs/{run_id}/{img_info['sha256']}.png"

        # SLR PDFs
        work_elr = run_dir / "work" / elr_no
        slr_files: list[str] = []
        slr_instructions: list[dict[str, Any]] = []
        if work_elr.is_dir():
            slr_paths = sorted(work_elr.glob("**/SLR*.pdf"))
            slr_files = [p.name for p in slr_paths]
            texts: list[str] = []
            for p in slr_paths:
                try:
                    with pymupdf.open(p) as doc:
                        t = "\n".join(page.get_text() for page in doc)
                        if t.strip():
                            texts.append(t)
                except Exception:
                    pass
            if texts:
                facts = parse_slr("\n".join(texts))
                slr_instructions = [
                    {"line": inst.line_no, "value": inst.value, "quote": inst.quote}
                    for inst in facts.instructions
                    if inst.side == Side.TOP
                ]

        rows.append(
            {
                "run_id": run_id,
                "elr_no": elr_no,
                "top_mark_id": top_mark_id,
                "layout_code": layout_code,
                "line_extra": line_extra,
                "mark_remark": meta.get("MARK_REMARK") or None,
                "mark_require": meta.get("MARK_REQUIRE") or None,
                "top_template_remark": meta.get("TOP_TEMPLATE_REMARK") or None,
                "oracle_top_raw": oracle_top_raw,
                "layout_cells": layout_cells,
                "abs_file": abs_file,
                "abs_sha256": abs_sha256,
                "image_path": image_path,
                "slr_files": slr_files,
                "slr_instructions": slr_instructions,
            }
        )

    return rows


def copy_images(run_id: int, rows: list[dict[str, Any]], cache_dir: Path, files_root: Path) -> int:
    images_dir = Path(cache_dir) / "images"
    target_dir = Path(files_root) / "abs" / str(run_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    img_index_path = Path(cache_dir) / "images_index.csv"
    img_by_elr: dict[str, dict[str, str]] = {}
    if img_index_path.is_file():
        with open(img_index_path, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                img_by_elr[r["elr"]] = r

    copied = 0
    for row in rows:
        elr_no = row["elr_no"]
        info = img_by_elr.get(elr_no)
        if not info:
            continue
        src_name = info.get("image")
        sha = info.get("sha256")
        if not src_name or not sha:
            continue
        src = images_dir / src_name
        dest = target_dir / f"{sha}.png"
        if src.is_file():
            if not dest.exists():
                shutil.copy2(src, dest)
            copied += 1
    return copied


def day_run_for(
    cur: Any,
    elr_no: str,
    day: date,
    git_commit: str = "",
    engine_version: str = "0.1.0",
    model_version: str = "exp09",
) -> int:
    """Find or create an auto daily run for the given day that has NO job_result for this ELR.

    Reuses period auto-YYYY-MM-DD until this ELR repeats on the same day, then creates
    auto-YYYY-MM-DD.2, .3, etc.
    """
    base_period = f"auto-{day.isoformat()}"
    suffix = 1

    while True:
        period = base_period if suffix == 1 else f"{base_period}.{suffix}"
        cur.execute("select run_id from mark_logic.run where period = %s", (period,))
        row = cur.fetchone()

        if row is None:
            # Create new run (INSERT ONLY into mark_logic)
            cur.execute(
                """
                insert into mark_logic.run (period, git_commit, ocr_model, symbol_model, note)
                values (%s, %s, %s, %s, 'auto-review')
                returning run_id;
                """,
                (period, git_commit, engine_version, model_version),
            )
            created_row = cur.fetchone()
            if created_row[0] <= 19:
                raise ValueError("Refusing to create a protected run ID (1-19)")
            return created_row[0]

        run_id = row[0]
        if run_id <= 19:
            suffix += 1
            continue
        # Check if this ELR has already been recorded in this run
        cur.execute(
            "select 1 from mark_logic.job_result where run_id = %s and elr_no = %s",
            (run_id, elr_no),
        )
        if cur.fetchone() is None:
            # No row for this ELR in this run, safe to reuse
            return run_id

        # ELR already recorded in this run; advance to next suffix run
        suffix += 1


def write_result(
    cur: Any,
    job: JobResult,
    meta: Any,
    oracle_row: Mapping[str, Any],
    resolution: DocumentResolution | None,
    revision_info: dict[str, Any],
    files_root: Path | None = None,
    schema_logic: str = "mark_logic",
    schema_app: str = "mark_app",
    image_path: str | None = None,
) -> int:
    """Write job results, line results, elr_snapshot, and elr_revision in an INSERT-ONLY manner.

    Returns the newly created revision number.
    """
    run_id = revision_info["run_id"]
    if schema_logic == "mark_logic" and int(run_id) <= 19:
        raise ValueError("Refusing to write to protected run IDs 1-19")
    elr_no = job.elr_no

    # 1. Determine next revision number for this ELR
    cur.execute(f"select coalesce(max(revision), 0) from {schema_app}.elr_revision where elr_no = %s", (elr_no,))
    max_rev = cur.fetchone()[0]
    new_revision = max_rev + 1

    # 2. Insert job_result
    abs_no = ""
    if resolution and resolution.abs and resolution.abs.number:
        abs_no = resolution.abs.number

    jdict = {
        "elr_no": elr_no,
        "processing_status": job.processing_status.value,
        "hold_reason": job.hold_reason,
        "hold_detail": getattr(job, "hold_detail", None),
        "review_detail": getattr(job, "review_detail", None),
        "verification_status": job.verification_status.value if job.verification_status else None,
        "approval_status": job.approval_status.value if job.approval_status else None,
        "layout_source": job.layout_source,
        "abs_no": abs_no,
    }
    jrow = job_row(run_id, jdict)
    cur.execute(
        f"""
        insert into {schema_logic}.job_result (
            run_id, elr_no, processing_status, hold_reason, hold_detail,
            review_detail, verification_status, approval_status, layout_source, abs_no
        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        jrow,
    )

    # 3. Insert line_result rows
    for comp in job.comparisons:
        ldict = {
            "elr_no": elr_no,
            "side": comp.side.value,
            "line_no": comp.line_no,
            "status": comp.status.value,
            "expected_mark": comp.expected or "",
            "oracle_mark": comp.oracle or "",
            "compare_rules": getattr(comp, "compare_rules", ""),
            "detail": getattr(comp, "detail", ""),
            "warning": getattr(comp, "warning", ""),
        }
        lrow = line_row(run_id, ldict, abs_no=abs_no, parity="NONE")
        cur.execute(
            f"""
            insert into {schema_logic}.line_result (
                run_id, elr_no, abs_no, side, line_no, month,
                final_mark, db_mark, status, cause, cause_detail,
                system_status, final_status, review_detail, warning, hold_detail, layout_source
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            lrow,
        )

    # 4. Insert elr_snapshot
    oracle_top_raw = [
        oracle_row.get(f"TOP_MARK{i}") for i in range(1, 6) if oracle_row.get(f"TOP_MARK{i}") is not None
    ]
    line_extra = {"oracle_row": dict(oracle_row)}
    cur.execute(
        f"""
        insert into {schema_app}.elr_snapshot (
            run_id, elr_no, top_mark_id, line_extra, oracle_top_raw, abs_file, abs_sha256, image_path
        ) values (%s, %s, %s, %s, %s, %s, %s, %s);
        """,
        (
            run_id,
            elr_no,
            getattr(meta, "top_mark_id", None),
            json.dumps(line_extra),
            json.dumps(oracle_top_raw),
            resolution.abs.path if resolution and resolution.abs else None,
            resolution.abs.sha256 if resolution and resolution.abs else None,
            image_path,
        ),
    )

    # 5. Insert elr_revision
    docs_probe_val = json.dumps(revision_info.get("docs_probe", {}))
    cur.execute(
        f"""
        insert into {schema_app}.elr_revision (
            elr_no, revision, oracle_fp, docs_fp, version_fp, result_fp,
            changed, changed_fields, result_unchanged, docs_probe, run_id
        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """,
        (
            elr_no,
            new_revision,
            revision_info["oracle_fp"],
            revision_info["docs_fp"],
            revision_info["version_fp"],
            revision_info["result_fp"],
            revision_info["changed"],
            revision_info.get("changed_fields") or [],
            revision_info.get("result_unchanged", False),
            docs_probe_val,
            run_id,
        ),
    )

    return new_revision


def notify_for(
    cur: Any,
    job: JobResult,
    revision: int,
    prev_approved: bool = False,
    run_id: int = 0,
) -> list[str]:
    """Generate and insert user notifications and publish PostgreSQL NOTIFY events."""
    notifications: list[tuple[str, str]] = []

    if prev_approved:
        notifications.append((
            "changed_after_approve",
            f"ELR {job.elr_no} changed after approval (rev {revision})",
        ))

    if job.processing_status == ProcessingStatus.HOLD:
        notifications.append((
            "hold",
            f"ELR {job.elr_no} entered HOLD: {job.hold_reason}",
        ))
    elif job.processing_status == ProcessingStatus.FAILED:
        if job.hold_reason == "INFERENCE_FAILED":
            notifications.append((
                "inference_failed",
                f"ELR {job.elr_no} inference failed (rev {revision})",
            ))
        else:
            notifications.append((
                "failed",
                f"ELR {job.elr_no} failed (rev {revision})",
            ))

    notified_kinds: list[str] = []
    for kind, message in notifications:
        cur.execute(
            """
            insert into mark_app.notification (elr_no, run_id, revision, kind, message)
            values (%s, %s, %s, %s, %s)
            on conflict (elr_no, kind, revision) do nothing;
            """,
            (job.elr_no, run_id, revision, kind, message),
        )
        payload = json.dumps({
            "elr_no": job.elr_no,
            "run_id": run_id,
            "revision": revision,
            "kind": kind,
            "message": message,
        })
        safe_payload = payload.replace("'", "''")
        cur.execute(f"NOTIFY mark_events, '{safe_payload}';")
        notified_kinds.append(kind)

    return notified_kinds
