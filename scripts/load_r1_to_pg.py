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

import psycopg2
from psycopg2.extras import execute_values

MONTH = {"01": "1_JAN", "02": "2_FEB", "03": "3_MAR", "04": "4_APR", "05": "5_MAY", "06": "6_JUN"}
NEEDS_REVIEW_MEANING = (
    "R1 mark_engine: expected line carries a review flag (SLR_UNRESOLVED, SLR_AMBIGUOUS, UNMAPPED_TOKEN, "
    "GRAPHIC_REMARK_CONFLICT, RULE_CONFLICT) or Oracle digits not verifiable"
)


def _git(*a: str) -> str:
    return subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()


def _abs_number(s: str) -> str:
    m = re.search(r"ABS\d{6}", s or "", re.IGNORECASE)
    return m.group(0).upper() if m else ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("r1_dir")
    ap.add_argument("--note", default="")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--host", default="10.151.28.2")
    ap.add_argument("--db", default="mark_web")
    ap.add_argument("--user", default="postgres")
    args = ap.parse_args()
    r1 = args.r1_dir

    jobs = {r["elr_no"]: r for r in csv.DictReader(open(f"{r1}/jobs.csv", encoding="utf-8"))}
    par = {(r["elr_no"], r["side"], r["line_no"]): r["reason"]
           for r in csv.DictReader(open(f"{r1}/parity.csv", encoding="utf-8"))}
    m = json.load(open(f"{r1}/metrics.json", encoding="utf-8"))
    bugs = json.load(open(f"{r1}/parity_summary.json", encoding="utf-8")).get("BUG", 0)

    rows = []
    for r in csv.DictReader(open(f"{r1}/lines.csv", encoding="utf-8")):
        cause = r["hold_reason"] or r["detail"] or r["compare_rules"] or None
        detail = "; ".join(
            f"{k}={v}" for k, v in [
                ("rules", r["compare_rules"]), ("flags", r["flags"]), ("detail", r["detail"]),
                ("layout_source", r["layout_source"]),
                ("parity_vs_r0", par.get((r["elr_no"], r["side"], r["line_no"]), "")),
            ] if v
        )
        rows.append((r["elr_no"], _abs_number(jobs[r["elr_no"]]["abs_no"]), r["side"], int(r["line_no"]),
                     MONTH.get(r["elr_no"][5:7]), r["expected_mark"] or None, r["oracle_mark"] or None,
                     r["status"], cause, detail))
    keys = [x[:4] for x in rows]
    assert len(keys) == len(set(keys)), "duplicate primary key"

    note = (
        "R1 mark_engine independent generate (RV-2026-11-04-R0 + R1 fixes, docs 01 s7). Not Oracle-conditioned: "
        f"independence {m['independence']:.0%} measured on {m['total_jobs']} ELR; NEEDS_REVIEW {m['needs_review_lines']}; "
        f"hold {m['hold_count']}; parity BUG {bugs} ({'D-03 met' if bugs == 0 else 'D-03 not met'}). "
        f"{args.note} Not comparable 1:1 with runs 1-3."
    )

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
    cur.execute("select setval('mark_logic.run_run_id_seq', (select max(run_id) from mark_logic.run))")
    cur.execute(
        """insert into mark_logic.run(period, git_commit, ocr_model, symbol_model, elr_total, elr_measurable,
             lines_total, lines_measured, lines_match, match_pct, lines_db_wrong, lines_diff, pipeline_right_pct, note)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning run_id""",
        ("2026-01..2026-06", f"mark-web {_git('rev-parse', '--short', 'HEAD')} ({_git('branch', '--show-current')})",
         "R0 cached inference: PP-OCRv5 det + EXP09 PP-OCRv5_server_rec ep40",
         "R0 cached inference: YOLOv8n symdet_v2",
         m["total_jobs"], m["coverage_elr_num"], len(rows), m["oracle_agreement_denom"], m["oracle_agreement_num"],
         round(100 * m["oracle_agreement"], 2), 0, m["DIFF"], None, note),
    )
    run_id = cur.fetchone()[0]
    execute_values(
        cur,
        """insert into mark_logic.line_result(run_id, elr_no, abs_no, side, line_no, month, final_mark, db_mark,
             status, cause, cause_detail) values %s""",
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
