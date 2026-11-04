"""Apply human review verdicts on top of the system comparison.

The system status (MATCH / DIFF / NEEDS_REVIEW ...) is never changed: it stays the measure of
what the engine produced on its own (independence and parity use it). `final_status` is the
result after a person reviewed the line:

- DB_WRONG     the reviewed answer equals the system's expected mark but not Oracle
               -> Oracle is wrong, notify the Marking team
- HUMAN_FIXED  the reviewed answer equals Oracle but not the system (OCR misread, legend on the
               drawing) -> a person supplied the mark; not counted as a system match
- MATCH        the reviewed answer equals both (review cleared a flag)
- otherwise    the verdict is stale (values changed since the review) -> system status kept

Sources: R0 review exports `experiments/abs_vs_db/review/diff_review_*.csv` (verdict, note,
final = value the reviewer approved). Notes without a verdict count only when they say the
answer is on the drawing ("มีบอกในภาพ").
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

ORACLE_WRONG = frozenset({"DB wrong", "SLR / ECN change"})
SYSTEM_WRONG = frozenset({"OCR wrong"})
LEGEND_NOTE = "มีบอกในภาพ"
COMPARED = frozenset({"MATCH", "MATCH_SLR", "MATCH_SHIFT", "MATCH_LOT", "DIFF", "NEEDS_REVIEW"})


@dataclass(frozen=True)
class Verdict:
    line_id: str  # ELR_<side letter><line>, e.g. ADI2605086_T3
    verdict: str
    note: str
    answer: str | None  # value the reviewer approved; None = Oracle is the answer


def _ns(s: str | None) -> str:
    return "".join((s or "").split())


def load_verdicts(review_dir: Path) -> dict[str, Verdict]:
    out: dict[str, Verdict] = {}
    for f in sorted(review_dir.glob("diff_review_*.csv")):  # later files override earlier ones
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            v, note = (r.get("verdict") or "").strip(), (r.get("note") or "").strip()
            if v in ORACLE_WRONG:
                out[r["id"]] = Verdict(r["id"], v, note, answer=r.get("final") or "")
            elif v in SYSTEM_WRONG or (not v and LEGEND_NOTE in note):
                out[r["id"]] = Verdict(r["id"], v, note, answer=None)
    return out


def final_status(row: dict, v: Verdict | None) -> str:
    status = row["status"]
    # only lines the system actually compared (a held / ineligible ELR has no expected to judge)
    if v is None or status not in COMPARED:
        return status
    exp, ora = _ns(row["expected_mark"]), _ns(row["oracle_mark"])
    answer = ora if v.answer is None else _ns(v.answer)
    if answer == ora:
        return "MATCH" if exp == ora else "HUMAN_FIXED"
    if answer == exp:
        return "DB_WRONG"
    return status
