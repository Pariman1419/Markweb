"""Build the R1 review page (per-topic line lists, like R0 diff_review.html).

Usage:
    python scripts/make_review_page.py --template <page.html> --out <page_out.html> [--images]

The template contains the marker /*ROWS*/[] which is replaced by the row JSON.
--images adds the ABS line crop (file:/// path + bbox from R0 annotation) for a LOCAL page only:
the drawings are customer documents and must not be published (D-14/D-20).
"""
from __future__ import annotations

import argparse
import sys
import csv
import html
import json
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
R0 = Path("D:/CIM Project/mark")
R0_OUT = R0 / "experiments/abs_vs_db/out"
R1 = Path("artifacts/regression-r1")

# Tabs: every compared line split by how the system expected mark relates to Oracle (user 2026-11-04)
#   TRUE  system logic = DB (space-insensitive; MATCH_LOT/SLR/SHIFT count as true)
#   WARN  close: Oracle abbreviates the country name (same rule as compare engine R07-ADI1039-COO)
#   ERR   not equal; cause = DB_WRONG (reviewed) / review flag / DIFF
TOPIC_ORDER = ("TRUE", "WARN", "ERR")
COMPARED = {"MATCH", "MATCH_SLR", "MATCH_SHIFT", "MATCH_LOT", "DIFF", "NEEDS_REVIEW"}
NOT_COMPARED_LABEL = {"NOT_MEASURABLE": "HOLD (เอกสารไม่ครบ/ไม่ชัด)", "NOT_ELIGIBLE": "นอกขอบเขต",
                      "DB_EMPTY": "Oracle ว่าง", "NOT_COMPARABLE": "เทียบไม่ได้"}
MATCH_LABEL = {"MATCH": "ตรง", "MATCH_LOT": "ตรง (lot)", "MATCH_SLR": "ตรง (SLR)", "MATCH_SHIFT": "ตรง (เลื่อนบรรทัด)"}


def classify(r: dict) -> tuple[str, str]:
    from mark_engine.compare.engine import _coo_abbreviation

    def ns(x):
        return "".join((x or "").split())

    st, fin = r["status"], r.get("final_status") or r["status"]
    if fin in ('DB_WRONG', 'HUMAN_FIXED') or st == 'DIFF':
        return 'ERR', fin if fin in ('DB_WRONG', 'HUMAN_FIXED') else 'รอตรวจ · DIFF'
    if st == 'NEEDS_REVIEW' and ns(r['expected_mark']) != ns(r['oracle_mark']):
        return 'ERR', 'รอตรวจ · ' + (r.get('flags', '').split(';')[0] or 'NEEDS_REVIEW')
    if r.get('warning') and not r['warning'].startswith('COO_ABBREVIATED'):
        return 'WARN', r['warning']
    if r.get("warning") or _coo_abbreviation(r["expected_mark"], r["oracle_mark"]):
        return "WARN", "ชื่อประเทศย่อ (COO)"
    if st.startswith("MATCH") or ns(r["expected_mark"]) == ns(r["oracle_mark"]):
        if st == "NEEDS_REVIEW":
            return "TRUE", "ตรง · รอแก้ config ตามแจ้งเตือน"
        return "TRUE", MATCH_LABEL.get(st, "ตรง")
    if fin == "DB_WRONG":
        return "ERR", "Oracle ผิด (รีวิวยืนยัน)"
    if fin == "HUMAN_FIXED":
        return "ERR", "ระบบอ่านผิด (รีวิวยืนยัน)"
    if st == "NEEDS_REVIEW":
        return "ERR", "ยังไม่รีวิว · " + (r["flags"].split(";")[0] or "NEEDS_REVIEW")
    return "ERR", "ยังไม่รีวิว · DIFF"


def rd(p: Path) -> list[dict]:
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def error_panel(jobs: list[dict]) -> str:
    failed = [job for job in jobs if job.get('processing_status') == 'FAILED']
    if not failed:
        return ''
    rows = ''.join('<li><code>' + html.escape(job.get('elr_no', '')) + '</code> — ' +
                   html.escape(job.get('hold_reason', '')) + '</li>' for job in failed)
    return f'<details class="gut" open><summary>Processing errors: {len(failed)}</summary><ul>{rows}</ul></details>'


def image_index() -> dict[tuple[str, str, str], tuple[str, list[float]]]:
    s2: dict[str, tuple[str, str]] = {}
    for f, base in (("dataset/annotation.csv", "dataset"), ("dataset/eval_4_apr/annotation_v1.1.csv", "dataset/eval_4_apr")):
        for a in rd(R0 / f):
            s2[a["sample_id"]] = (str(R0 / base / a["full_image_path"]), a["crop_bbox"])
    for a in rd(R0_OUT / "h1_lines.csv"):
        s2[f"{a['image']}_{a['side'][0]}L{a['line']}"] = (str(R0 / f"dataset/eval_h1/full_images/{a['image']}.png"), a["crop_bbox"])
    loc = {}
    for f in ("line_compare.csv", "line_compare_h1.csv"):
        for r in rd(R0_OUT / f):
            if r["sample_id"] in s2:
                p, bb = s2[r["sample_id"]]
                nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", bb or "")][:4]
                loc[(r["elr"], r["side"], r["line"])] = ("file:///" + p.replace("\\", "/"), nums)
    return loc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--images", action="store_true")
    ap.add_argument('--in', dest='input_dir', type=Path, default=R1)
    ap.add_argument('--snapshot', type=Path, default=R0_OUT / 'elr_meta_2026.json')
    ap.add_argument('--title', default='R1 Line Review · run 14')
    a = ap.parse_args()

    meta = {v["ELR_NO"]: v for v in json.load(open(a.snapshot, encoding="utf-8"))}
    jobs = {r["elr_no"]: r for r in rd(a.input_dir / "jobs.csv")}
    old = {}
    for f in (("diff_review_2026-11-04.csv", "diff_review_2026-11-04b.csv") if a.input_dir == R1 else ()):
        for r in rd(R0 / "experiments/abs_vs_db/review" / f):
            old[r["id"]] = r
    imgs = image_index() if a.images else {}

    rows = []
    summary: dict = {"cls": {}, "cause": {}, "not_compared": {}}
    for r in rd(a.input_dir / "lines.csv"):
        lid = f"{r['elr_no']}_{r['side'][0]}{r['line_no']}"
        rd_ = r.get("review_detail", "")
        if r["status"] not in COMPARED:
            k = NOT_COMPARED_LABEL.get(r["status"], r["status"])
            summary["not_compared"][k] = summary["not_compared"].get(k, 0) + 1
            continue
        topic, cause = classify(r)
        summary["cls"][topic] = summary["cls"].get(topic, 0) + 1
        ck = f"{topic}|{cause.split(' · ')[0] if topic == 'ERR' else cause}"
        summary["cause"][ck] = summary["cause"].get(ck, 0) + 1
        m = meta.get(r["elr_no"], {})
        o = old.get(lid, {})
        row = {
            "id": lid, "topic": topic, "elr": r["elr_no"], "side": r["side"], "line": int(r["line_no"]),
            "src": r["layout_source"], "abs": jobs[r["elr_no"]]["abs_no"],
            "orev": m.get("CUST_BOM_REVISION") or "", "bom": m.get("CUST_BOM_NO") or "", "pn": m.get("PRODUCT_NO") or "",
            "exp": r["expected_mark"], "ora": r["oracle_mark"], "status": r["status"],
            "flags": r["flags"], "detail": r["detail"],
            "remark": " | ".join(x for x in (m.get("MARK_REMARK"), m.get("MARK_REQUIRE")) if x),
            "alert": rd_, "final": r.get("final_status", r["status"]), "cause": cause,
            "warn": r.get("warning", ""),
            "ov": o.get("verdict", ""), "on": o.get("note", ""), "ofinal": o.get("final", ""),
        }
        if a.images and (r["elr_no"], r["side"], r["line_no"]) in imgs:
            row["img"], row["bb"] = imgs[(r["elr_no"], r["side"], r["line_no"])]
        rows.append(row)

    tpl = Path(a.template).read_text(encoding="utf-8")
    tpl = tpl.replace('<title>R1 Line Review</title>', '<title>' + html.escape(a.title) + '</title>')
    tpl = tpl.replace('<h1>R1 Line Review · run 14</h1>', '<h1>' + html.escape(a.title) + '</h1>')
    tpl = tpl.replace('<main class="gut"', error_panel(list(jobs.values())) + '<main class="gut"')
    assert "/*ROWS*/[]" in tpl
    assert "/*SUM*/{}" in tpl
    rendered = tpl.replace("/*ROWS*/[]", json.dumps(rows, ensure_ascii=False).replace('</', '<\\/')).replace(
        "/*SUM*/{}", json.dumps(summary, ensure_ascii=False).replace('</', '<\\/'))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(rendered, encoding="utf-8")
    print(len(rows), "rows ->", a.out, {t: sum(x["topic"] == t for x in rows) for t in TOPIC_ORDER})


if __name__ == "__main__":
    main()
