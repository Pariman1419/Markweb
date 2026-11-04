"""Export the R1 review state to CSV: every line of the run, its True / Warning / Error class,
the cause, and the verdicts/notes people entered on the review page.

Usage:
    python scripts/export_review_csv.py --verdicts <dir with verdicts/*.json> --out reviews/<name>.csv

<dir> is an ArtifactData `list` dump of the review page's `verdicts` collection (one JSON per line id).
Lines the system did not compare get class NOT_COMPARED and their status as the cause.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_review_page import COMPARED, NOT_COMPARED_LABEL, R1, classify, rd  # noqa: E402

FIELDS = ["id", "class", "cause", "elr_no", "side", "line_no", "layout_source", "expected_mark", "oracle_mark",
          "system_status", "final_status", "flags", "warning", "review_detail", "hold_reason", "hold_detail",
          "page_verdict", "page_note", "page_at"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdicts", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    verd = {}
    for f in Path(a.verdicts).glob("verdicts/*.json"):
        verd[f.stem] = json.loads(f.read_text(encoding="utf-8"))

    rows, counts = [], {}
    for r in rd(R1 / "lines.csv"):
        lid = f"{r['elr_no']}_{r['side'][0]}{r['line_no']}"
        if r["status"] in COMPARED:
            cls, cause = classify(r)
        else:
            cls, cause = "NOT_COMPARED", NOT_COMPARED_LABEL.get(r["status"], r["status"])
        counts[cls] = counts.get(cls, 0) + 1
        v = verd.get(lid, {})
        rows.append({
            "id": lid, "class": cls, "cause": cause, "elr_no": r["elr_no"], "side": r["side"],
            "line_no": r["line_no"], "layout_source": r["layout_source"], "expected_mark": r["expected_mark"],
            "oracle_mark": r["oracle_mark"], "system_status": r["status"],
            "final_status": r.get("final_status") or r["status"], "flags": r["flags"], "warning": r.get("warning", ""),
            "review_detail": r.get("review_detail", ""), "hold_reason": r.get("hold_reason", ""),
            "hold_detail": r.get("hold_detail", ""), "page_verdict": v.get("verdict", ""),
            "page_note": v.get("note", ""), "page_at": v.get("at", ""),
        })
    missing = sorted(set(verd) - {r["id"] for r in rows})
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:  # BOM: opens correctly in Excel (Thai notes)
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "rows ->", out, counts, "| page verdicts", len(verd), "| verdicts without a line", missing)


if __name__ == "__main__":
    main()
