"""Build RV-2026-11-04-R0.json from logic_rule.csv and migration 0003.

Reads artifacts/regression-r0/mark_logic/logic_rule.csv (44 rows),
parses provenance and approvals from migrations/0003_rule_governance.sql,
and generates mark_engine/rules/data/RV-2026-11-04-R0.json.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import re
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT_DIR / "artifacts" / "regression-r0" / "mark_logic" / "logic_rule.csv"
SQL_PATH = ROOT_DIR / "migrations" / "0003_rule_governance.sql"
OUTPUT_DIR = ROOT_DIR / "mark_engine" / "rules" / "data"
OUTPUT_PATH = OUTPUT_DIR / "RV-2026-11-04-R0.json"


def parse_sql_provenance(sql_text: str) -> dict[str, tuple[str, str | None]]:
    """Extract (provenance_class, oracle_influence) keyed by rule_id."""
    # Matches values list in:
    # join (values
    #   ('R01-ORACLE','SPEC_DERIVED','read only'),
    #   ...
    # ) as p(rule_id, cls, infl) on p.rule_id = r.rule_id;
    m = re.search(r"join\s+\(values\s+(.*?)\s+\)\s+as\s+p\(rule_id,\s*cls,\s*infl\)", sql_text, re.DOTALL)
    if not m:
        raise ValueError("Could not find provenance values block in migration 0003")

    block = m.group(1)
    # Match tuple: ('rule_id', 'cls', null | 'infl')
    tuple_pattern = re.compile(
        r"\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*(null|'[^']*')\s*\)",
        re.IGNORECASE,
    )
    result = {}
    for rule_id, cls, infl in tuple_pattern.findall(block):
        infl_val = None if infl.lower() == "null" else infl.strip("'")
        result[rule_id] = (cls, infl_val)
    return result


def parse_sql_approvals(sql_text: str) -> list[dict[str, Any]]:
    """Extract approvals list from migration 0003."""
    m = re.search(
        r"insert\s+into\s+mark_rules\.rule_approval\s*\([^)]+\)\s*values\s*(.*?);\s*(?:update|grant|commit|\Z)",
        sql_text,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        raise ValueError("Could not find rule_approval values block in migration 0003")

    block = m.group(1)
    tuple_pattern = re.compile(
        r"\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*(null|'[^']*')\s*,\s*'([^']+)'\s*,\s*(null|'[^']*')\s*\)",
        re.IGNORECASE,
    )
    approvals = []
    for _version_id, rule_id, decision, condition, approver, note in tuple_pattern.findall(block):
        cond_val = None if condition.lower() == "null" else condition.strip("'")
        note_val = None if note.lower() == "null" else note.strip("'")
        approvals.append({
            "rule_id": rule_id,
            "decision": decision,
            "condition": cond_val,
            "approver": approver,
            "note": note_val,
        })
    if len(approvals) != 11:
        raise ValueError(f"Expected 11 approvals, found {len(approvals)}")
    return approvals


def build_rule_version(
    csv_path: Path = CSV_PATH,
    sql_path: Path = SQL_PATH,
    output_path: Path = OUTPUT_PATH,
) -> Path:
    sql_text = sql_path.read_text(encoding="utf-8")
    provenance_map = parse_sql_provenance(sql_text)
    approvals = parse_sql_approvals(sql_text)

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rules = []
        for row in reader:
            rule_id = row["rule_id"]
            if rule_id not in provenance_map:
                raise ValueError(f"Missing provenance for rule: {rule_id}")
            cls, infl = provenance_map[rule_id]
            row_dict = dict(row)
            row_dict["provenance_class"] = cls
            row_dict["oracle_influence"] = infl
            rules.append(row_dict)

    if len(rules) != 44:
        raise ValueError(f"Expected 44 rules in logic_rule.csv, found {len(rules)}")

    rules.sort(key=lambda r: r["rule_id"])
    approvals.sort(key=lambda a: a["rule_id"])

    data = {
        "rule_version": "RV-2026-11-04-R0",
        "rules": rules,
        "approvals": approvals,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")

    return output_path


if __name__ == "__main__":
    out = build_rule_version()
    print(f"Generated {out}")
