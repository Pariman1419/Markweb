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

RC_GROUPS = {
    "RC1": "ADI2601052 ADI2601053 ADI2601054 ADI2601103 ADI2602033 ADI2602098 ADI2602100 ADI2602142 ADI2602161 ADI2603081 ADI2606066",
    "RC2": "ADI2603024 ADI2603025 ADI2603026 ADI2603027 ADI2603028 ADI2603029 ADI2603030 ADI2603072 ADI2603073 ADI2603074 ADI2603075 ADI2603076",
    "RC3": "ADI2602126 ADI2606076",
}
OLD_TOPIC = {
    # (verdict or note keyword) -> topic, from diff_review_2026-11-04*.csv cross-check
    "DBW": {"ADI2605086_T3", "ADI2605087_T3", "ADI2605088_T3", "ADI2602044_T2", "ADI2602050_T2"},
    "LEG": {"ADI2605013_T2", "ADI2606019_T2", "ADI2605047_T3", "ADI2605047_T4", "ADI2605047_T5",
            "ADI2605048_T3", "ADI2605048_T4", "ADI2605048_T5"},
    "OCR": {"ADI2602089_T5", "ADI2604053_T1", "ADI2605076_T1"},
}


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

    rc_of = {e: g for g, s in RC_GROUPS.items() for e in s.split()}
    rows = []
    for r in rd(R1 / "lines.csv"):
        lid = f"{r['elr_no']}_{r['side'][0]}{r['line_no']}"
        topic = None
        if r["elr_no"] in rc_of and "RULE_CONFLICT" in r["flags"]:
            topic = rc_of[r["elr_no"]]
        else:
            topic = next((t for t, ids in OLD_TOPIC.items() if lid in ids), None)
        if topic is None:
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
    print(len(rows), "rows ->", a.out, {t: sum(x["topic"] == t for x in rows) for t in ("RC1", "RC2", "RC3", "DBW", "LEG", "OCR")})


if __name__ == "__main__":
    main()
