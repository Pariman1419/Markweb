"""Snapshot loader for mark_app.elr_snapshot."""
import argparse
from collections import defaultdict
import csv
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

import psycopg2
from psycopg2.extras import Json, execute_values
import pymupdf

from mark_engine.adapters.env import load_env
from mark_engine.domain.models import Side
from mark_engine.slr.parse import parse_slr


def build_snapshot_rows(run_id: int, oracle_dir: Path, cache_dir: Path, run_dir: Path) -> list[dict[str, Any]]:
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
        abs_file = img_info["abs_file"] if img_info else (job.get("abs_no") or None)
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


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Load elr_snapshot for a run.")
    parser.add_argument("--run-id", type=int, required=True, help="Run ID in mark_logic.run")
    parser.add_argument("--oracle", required=True, help="Oracle directory containing elr_meta.json and mark_layout.json")
    parser.add_argument("--cache", required=True, help="Inference cache directory containing images_index.csv and images/")
    parser.add_argument("--run", required=True, help="Run directory containing jobs.csv, lines.csv and work/")
    parser.add_argument("--commit", action="store_true", help="Commit changes to DB and copy images")
    parser.add_argument("--host", default=os.getenv("MARK_PG_HOST", "10.151.28.2"))
    parser.add_argument("--db", default=os.getenv("MARK_PG_DB", "mark_web"))
    parser.add_argument("--user", default=os.getenv("MARK_PG_USER", "postgres"))
    parser.add_argument("--files-root", default=os.getenv("MARK_FILES_ROOT", "data/files"))
    args = parser.parse_args()

    rows = build_snapshot_rows(args.run_id, Path(args.oracle), Path(args.cache), Path(args.run))
    print(f"Built {len(rows)} snapshot rows for run_id {args.run_id}.")

    password = os.environ.get("MARK_PG_PASSWORD", "")
    conn = psycopg2.connect(
        host=args.host,
        port=5432,
        dbname=args.db,
        user=args.user,
        password=password,
        connect_timeout=8,
    )

    try:
        cur = conn.cursor()
        values = [
            (
                r["run_id"],
                r["elr_no"],
                r["top_mark_id"],
                r["layout_code"],
                Json(r["line_extra"]),
                r["mark_remark"],
                r["mark_require"],
                r["top_template_remark"],
                Json(r["oracle_top_raw"]),
                Json(r["layout_cells"]) if r["layout_cells"] is not None else None,
                r["abs_file"],
                r["abs_sha256"],
                r["image_path"],
                r["slr_files"],
                Json(r["slr_instructions"]),
            )
            for r in rows
        ]

        query = """
        insert into mark_app.elr_snapshot (
            run_id, elr_no, top_mark_id, layout_code, line_extra,
            mark_remark, mark_require, top_template_remark, oracle_top_raw,
            layout_cells, abs_file, abs_sha256, image_path, slr_files, slr_instructions
        ) values %s
        on conflict (run_id, elr_no) do update set
            top_mark_id = excluded.top_mark_id,
            layout_code = excluded.layout_code,
            line_extra = excluded.line_extra,
            mark_remark = excluded.mark_remark,
            mark_require = excluded.mark_require,
            top_template_remark = excluded.top_template_remark,
            oracle_top_raw = excluded.oracle_top_raw,
            layout_cells = excluded.layout_cells,
            abs_file = excluded.abs_file,
            abs_sha256 = excluded.abs_sha256,
            image_path = excluded.image_path,
            slr_files = excluded.slr_files,
            slr_instructions = excluded.slr_instructions,
            import_date = now()
        """
        execute_values(cur, query, values)

        if args.commit:
            conn.commit()
            copied = copy_images(args.run_id, rows, Path(args.cache), Path(args.files_root))
            print(f"COMMITTED {len(rows)} snapshot rows to mark_app.elr_snapshot. Copied {copied} ABS images.")
        else:
            conn.rollback()
            print(f"DRY RUN - rolled back ({len(rows)} rows).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
