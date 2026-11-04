"""Insert R1 (mark_engine) as a new run in mark_logic. Never touches runs 1-3 or logic_rule."""
import csv, json, os, re, sys
import psycopg2
R1 = sys.argv[1]; COMMIT = "--commit" in sys.argv
MONTH = {"01":"1_JAN","02":"2_FEB","03":"3_MAR","04":"4_APR","05":"5_MAY","06":"6_JUN"}
jobs = {r["elr_no"]: r for r in csv.DictReader(open(f"{R1}/jobs.csv", encoding="utf-8"))}
par = {(r["elr_no"], r["side"], r["line_no"]): r["reason"] for r in csv.DictReader(open(f"{R1}/parity.csv", encoding="utf-8"))}
m = json.load(open(f"{R1}/metrics.json", encoding="utf-8"))
def absno(s):
    x = re.search(r"ABS\d{6}", s or "", re.I); return x.group(0).upper() if x else ""
rows = []
for r in csv.DictReader(open(f"{R1}/lines.csv", encoding="utf-8")):
    j = jobs[r["elr_no"]]
    cause = r["hold_reason"] or r["detail"] or r["compare_rules"] or None
    cd = "; ".join(f"{k}={v}" for k, v in [("rules", r["compare_rules"]), ("flags", r["flags"]), ("detail", r["detail"]),
          ("layout_source", r["layout_source"]), ("parity_vs_r0", par.get((r["elr_no"], r["side"], r["line_no"]), ""))] if v)
    rows.append((r["elr_no"], absno(j["abs_no"]), r["side"], int(r["line_no"]), MONTH.get(r["elr_no"][5:7]),
                 r["expected_mark"] or None, r["oracle_mark"] or None, r["status"], cause, cd))
keys = [(x[0], x[1], x[2], x[3]) for x in rows]
assert len(keys) == len(set(keys)), "duplicate PK"
st = {}
for x in rows: st[x[7]] = st.get(x[7], 0) + 1
print("rows", len(rows), st)
c = psycopg2.connect(host="10.151.28.2", port=5432, dbname="mark_web", user="postgres",
                     password=os.environ["MARK_PG_PASSWORD"], connect_timeout=8)
cur = c.cursor()
cur.execute("select run_id, count(*) from mark_logic.line_result group by 1 order by 1"); before = cur.fetchall()
cur.execute("""insert into mark_logic.status_dictionary(status, meaning, counts_as_match, in_denominator, action, ui_color)
  values ('NEEDS_REVIEW','R1 mark_engine: expected line carries a review flag (SLR_UNRESOLVED, SLR_AMBIGUOUS, UNMAPPED_TOKEN, GRAPHIC_REMARK_CONFLICT, RULE_CONFLICT) or Oracle digits not verifiable',
          false, true, 'Mark Engineer review in Mark_web', 'review') on conflict (status) do nothing""")
cur.execute("select setval('mark_logic.run_run_id_seq', (select max(run_id) from mark_logic.run))")
cur.execute("""insert into mark_logic.run(period, git_commit, ocr_model, symbol_model, elr_total, elr_measurable, lines_total,
  lines_measured, lines_match, match_pct, lines_db_wrong, lines_diff, pipeline_right_pct, note)
  values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning run_id""",
  ("2026-01..2026-06", "mark-web cb9b74e (phase1/r1-fixes)",
   "R0 cached inference: PP-OCRv5 det + EXP09 PP-OCRv5_server_rec ep40", "R0 cached inference: YOLOv8n symdet_v2",
   m["total_jobs"], m["coverage_elr_num"], len(rows), m["oracle_agreement_denom"], m["oracle_agreement_num"],
   round(100 * m["oracle_agreement"], 2), 0, m["DIFF"], None,
   f"R1 mark_engine independent generate (RV-2026-11-04-R0 + R1 triage fixes, docs 01 s7). Not Oracle-conditioned: "
   f"independence {m['independence']:.0%} measured on {m['total_jobs']} ELR; NEEDS_REVIEW {m['needs_review_lines']}; "
   f"hold {m['hold_count']}; parity BUG 0 (D-03 met); supersedes run 4 (9dce03e). Not comparable 1:1 with runs 1-3."))
run_id = cur.fetchone()[0]
from psycopg2.extras import execute_values
execute_values(cur, """insert into mark_logic.line_result(run_id, elr_no, abs_no, side, line_no, month, final_mark, db_mark, status, cause, cause_detail) values %s""", [(run_id,) + x for x in rows], page_size=500)
cur.execute("select run_id, count(*) from mark_logic.line_result group by 1 order by 1"); after = cur.fetchall()
print("run_id", run_id, "before", before, "after", after)
assert [b for b in after if b[0] != run_id] == before and run_id not in [b[0] for b in before]
if COMMIT: c.commit(); print("COMMITTED")
else: c.rollback(); print("DRY RUN - rolled back")
