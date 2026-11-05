from services.worker.results import build_snapshot_rows, copy_images
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
