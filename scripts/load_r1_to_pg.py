"""Insert an R1 (mark_engine) regression result as a NEW run in mark_web.mark_logic.

Never updates existing runs or logic_rule. Without --commit the inserts run and are rolled back.

Usage:
    MARK_PG_PASSWORD=... python scripts/load_r1_to_pg.py artifacts/regression-r1 --note "what changed" [--commit]

See docs/implementation/08-database-tables.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

MONTH = {"01": "1_JAN", "02": "2_FEB", "03": "3_MAR", "04": "4_APR", "05": "5_MAY", "06": "6_JUN", "07": "7_JUL", "08": "8_AUG", "09": "9_SEP", "10": "10_OCT", "11": "11_NOV"}
NEEDS_REVIEW_MEANING = (
    "R1 mark_engine: expected line carries a review flag (SLR_UNRESOLVED, SLR_AMBIGUOUS, UNMAPPED_TOKEN, "
    "GRAPHIC_REMARK_CONFLICT, RULE_CONFLICT) or Oracle digits not verifiable"
)


def _git(*a: str) -> str:
    return subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()


def _abs_number(s: str) -> str:
    m = re.search(r"ABS\d{6}", s or "", re.IGNORECASE)
    return m.group(0).upper() if m else ""


def line_row(run_id: int, r: dict[str, str], abs_no: str, parity: str) -> tuple:
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
    return (run_id, r["elr_no"], _abs_number(abs_no), r["side"], int(r["line_no"]),
            MONTH.get(r["elr_no"][5:7]), r.get("expected_mark") or None,
            r.get("oracle_mark") or None, final, cause, detail,
            r["status"], final, r.get("review_detail") or None, r.get("warning") or None,
            r.get("hold_detail") or None, r.get("layout_source") or None)


def job_row(run_id: int, row: dict[str, str]) -> tuple:
    return (run_id, row['elr_no'], row['processing_status'], row.get('hold_reason') or None,
            row.get('hold_detail') or None, row.get('review_detail') or None,
            row.get('verification_status') or None, row.get('approval_status') or None,
            row.get('layout_source') or None, row.get('abs_no') or None)


def validate_blind_commit(directory: Path, metrics: dict) -> None:
    from scripts.run_blind import file_hash
    freeze = metrics.get('freeze') or {}
    if (freeze.get('freeze_id') != 'FREEZE-R1' or not freeze.get('git_commit') or
            not freeze.get('code_sha256') or metrics.get('independence') != 1.0 or
            not metrics.get('independence_denom')):
        raise ValueError('Blind commit requires an official frozen run with verified independence')
    for name in ('jobs.csv', 'lines.csv'):
        if metrics.get('output_sha256', {}).get(name) != file_hash(directory / name):
            raise ValueError(f'Blind output checksum mismatch: {name}')


def provenance_note(metrics: dict, bugs: int | None, note: str, is_blind: bool) -> str:
    provenance = ('Uses Oracle MARK_ID_LAYOUT; expected independent of TOP/BACK_MARK:' if is_blind
                  else 'Expected independent of Oracle mark values:')
    return (f"R1 mark_engine (RV-2026-11-04-R0). {provenance} "
            f"independence {metrics['independence']:.0%} measured on "
            f"{metrics.get('independence_denom', metrics['total_jobs'])} ELR; "
            f"NEEDS_REVIEW {metrics['needs_review_lines']}; hold {metrics['hold_count']}; "
            f"parity BUG {bugs if bugs is not None else 'not measured'}. {note} "
            "Not comparable 1:1 with runs 1-3.")


def main() -> None:
    from mark_engine.adapters.env import load_env
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("r1_dir")
    ap.add_argument("--note", default="")
    ap.add_argument("--period", default="2026-01..2026-06")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--host", default="10.151.28.2")
    ap.add_argument("--db", default="mark_web")
    ap.add_argument("--user", default="postgres")
    args = ap.parse_args()
    r1 = args.r1_dir

    jobs = {r["elr_no"]: r for r in csv.DictReader(open(f"{r1}/jobs.csv", encoding="utf-8"))}
    parity_path = Path(r1) / "parity.csv"
    par = {(r["elr_no"], r["side"], r["line_no"]): r["reason"]
           for r in csv.DictReader(parity_path.open(encoding="utf-8"))} if parity_path.exists() else {}
    m = json.load(open(f"{r1}/metrics.json", encoding="utf-8"))
    is_blind = 'blind' in args.period.lower() or 'freeze' in m
    if is_blind and args.commit:
        validate_blind_commit(Path(r1), m)
    summary_path = Path(r1) / "parity_summary.json"
    bugs = json.loads(summary_path.read_text(encoding="utf-8")).get("BUG", 0) if summary_path.exists() else None

    rows = []
    for r in csv.DictReader(open(f"{r1}/lines.csv", encoding="utf-8")):
        rows.append(line_row(0, r, jobs[r["elr_no"]]["abs_no"], par.get((r["elr_no"], r["side"], r["line_no"]), ""))[1:])
    keys = [x[:4] for x in rows]
    assert len(keys) == len(set(keys)), "duplicate primary key"

    note = provenance_note(m, bugs, args.note, is_blind)

    conn = psycopg2.connect(host=args.host, port=5432, dbname=args.db, user=args.user,
                            password=os.environ["MARK_PG_PASSWORD"], connect_timeout=8)
    cur = conn.cursor()
    cur.execute("select run_id, count(*) from mark_logic.line_result group by 1 order by 1")
    before = cur.fetchall()
    cur.execute(
        """insert into mark_logic.status_dictionary(status, meaning, counts_as_match, in_denominator, action, ui_color)
           values ('NEEDS_REVIEW', %s, false, true, 'Mark Engineer review in Mark_web', 'review')
           on conflict (status) do nothing""",
        (NEEDS_REVIEW_MEANING,),
    )
    # a rolled-back dry run still consumes a sequence value
    cur.execute(
        """insert into mark_logic.status_dictionary(status, meaning, counts_as_match, in_denominator, action, ui_color)
           values ('HUMAN_FIXED', 'Reviewed: the system read the line wrong (OCR / legend on the drawing); a person supplied the mark', false, true, 'Corrected by reviewer', 'review')
           on conflict (status) do nothing""")
    cur.execute(
        """insert into mark_logic.run(period, git_commit, ocr_model, symbol_model, elr_total, elr_measurable,
             lines_total, lines_measured, lines_match, match_pct, lines_db_wrong, lines_diff, pipeline_right_pct, note)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning run_id""",
        (args.period, (f"mark-web frozen {m['freeze']['git_commit']}" if is_blind and m.get('freeze', {}).get('git_commit') else f"mark-web {_git('rev-parse', '--short', 'HEAD')} ({_git('branch', '--show-current')})"),
         ("Blind batch: PP-OCRv5 det + EXP09 PP-OCRv5_server_rec ep40" if is_blind else "R0 cached inference: PP-OCRv5 det + EXP09 PP-OCRv5_server_rec ep40"),
         ("Blind batch: YOLOv8n symdet_v2" if is_blind else "R0 cached inference: YOLOv8n symdet_v2"),
         m["total_jobs"], m["coverage_elr_num"], len(rows), m["oracle_agreement_denom"], m["oracle_agreement_num"],
         round(100 * m["oracle_agreement"], 2), sum(1 for x in rows if x[7] == "DB_WRONG"), m["DIFF"], None, note),
    )
    run_id = cur.fetchone()[0]
    execute_values(
        cur,
        """insert into mark_logic.job_result(run_id, elr_no, processing_status, hold_reason,
             hold_detail, review_detail, verification_status, approval_status, layout_source, abs_no) values %s""",
        [job_row(run_id, row) for row in jobs.values()], page_size=500,
    )
    execute_values(
        cur,
        """insert into mark_logic.line_result(run_id, elr_no, abs_no, side, line_no, month, final_mark, db_mark,
             status, cause, cause_detail, system_status, final_status, review_detail, warning, hold_detail, layout_source) values %s""",
        [(run_id, *x) for x in rows],
        page_size=500,
    )
    cur.execute("select run_id, count(*) from mark_logic.line_result group by 1 order by 1")
    after = cur.fetchall()
    print("rows", len(rows), "run_id", run_id, "before", before, "after", after)
    assert run_id not in [b[0] for b in before]
    assert [b for b in after if b[0] != run_id] == before, "existing runs changed"
    if args.commit:
        conn.commit()
        print("COMMITTED")
    else:
        conn.rollback()
        print("DRY RUN - rolled back")


if __name__ == "__main__":
    main()
