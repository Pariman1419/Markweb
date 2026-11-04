"""Conversion helpers for a read-only ACTIVEL snapshot."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def rows_to_meta(rows: list[dict]) -> list[dict]:
    latest = {}
    for row in rows:
        elr = row.get('ELR_NO')
        if not elr:
            continue
        revision = str(row.get('ELR_REV') or '').strip()
        previous = latest.get(elr)
        # ACTIVEL revisions are zero-padded strings. A duplicate revision with
        # different contents is not safe to resolve by fetch order.
        if previous is None or revision > str(previous.get('ELR_REV') or '').strip():
            latest[elr] = row
        elif revision == str(previous.get('ELR_REV') or '').strip() and row != previous:
            raise ValueError(f'ELR {elr}: duplicate revision {revision} has differing rows')
    return [{k: _json_value(v) for k, v in row.items()} for _, row in sorted(latest.items())]


def layout_json(rows: list[dict]) -> dict[str, list[list]]:
    output: dict[str, list[list]] = {}
    for row in rows:
        key = str(int(row['MARK_ID']))
        output.setdefault(key, []).append([int(row['MARK_ROW']), int(row['MARK_COLUMN']), row.get('MARK_DATA')])
    for cells in output.values():
        cells.sort(key=lambda cell: (cell[0], cell[1]))
    return output
