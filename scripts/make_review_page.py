"""Build the R1 review page (per-topic line lists, like R0 diff_review.html).

Usage:
    python scripts/make_review_page.py --template <page.html> --out <page_out.html> [--images]

The template contains the marker /*ROWS*/[] which is replaced by the row JSON.
--images adds the ABS line crop (file:/// path + bbox from R0 annotation) for a LOCAL page only:
the drawings are customer documents and must not be published (D-14/D-20).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

R0 = Path("D:/CIM Project/mark")
R0_OUT = R0 / "experiments/abs_vs_db/out"
R1 = Path("artifacts/regression-r1")

# Topics come from the run itself (D-25 alerts in review_detail, old verdicts in final_status)
TOPIC_ORDER = ("RC2", "RC3", "OLD")


def rd(p: Path) -> list[dict]:
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


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
    a = ap.parse_args()

    meta = {v["ELR_NO"]: v for v in json.load(open(R0_OUT / "elr_meta_2026.json", encoding="utf-8"))}
    jobs = {r["elr_no"]: r for r in rd(R1 / "jobs.csv")}
    old = {}
    for f in ("diff_review_2026-11-04.csv", "diff_review_2026-11-04b.csv"):
        for r in rd(R0 / "experiments/abs_vs_db/review" / f):
            old[r["id"]] = r
    imgs = image_index() if a.images else {}

    rows = []
    for r in rd(R1 / "lines.csv"):
        lid = f"{r['elr_no']}_{r['side'][0]}{r['line_no']}"
        rd_ = r.get("review_detail", "")
        if "PRODUCT_NO_ABS_MISMATCH" in rd_ and r["status"] == "NEEDS_REVIEW":
            topic = "RC3"
        elif "REVISION_MISMATCH" in rd_ and r["status"] == "NEEDS_REVIEW":
            topic = "RC2"
        elif r.get("final_status", r["status"]) != r["status"]:
            topic = "OLD"
        else:
            continue
        m = meta.get(r["elr_no"], {})
        o = old.get(lid, {})
        row = {
            "id": lid, "topic": topic, "elr": r["elr_no"], "side": r["side"], "line": int(r["line_no"]),
            "src": r["layout_source"], "abs": jobs[r["elr_no"]]["abs_no"],
            "orev": m.get("CUST_BOM_REVISION") or "", "bom": m.get("CUST_BOM_NO") or "", "pn": m.get("PRODUCT_NO") or "",
            "exp": r["expected_mark"], "ora": r["oracle_mark"], "status": r["status"],
            "flags": r["flags"], "detail": r["detail"],
            "remark": " | ".join(x for x in (m.get("MARK_REMARK"), m.get("MARK_REQUIRE")) if x),
            "alert": rd_, "final": r.get("final_status", r["status"]),
            "ov": o.get("verdict", ""), "on": o.get("note", ""), "ofinal": o.get("final", ""),
        }
        if a.images and (r["elr_no"], r["side"], r["line_no"]) in imgs:
            row["img"], row["bb"] = imgs[(r["elr_no"], r["side"], r["line_no"])]
        rows.append(row)

    tpl = Path(a.template).read_text(encoding="utf-8")
    assert "/*ROWS*/[]" in tpl
    html = tpl.replace("/*ROWS*/[]", json.dumps(rows, ensure_ascii=False))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(html, encoding="utf-8")
    print(len(rows), "rows ->", a.out, {t: sum(x["topic"] == t for x in rows) for t in TOPIC_ORDER})


if __name__ == "__main__":
    main()
