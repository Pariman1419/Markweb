"""Conversion helpers for a read-only ACTIVEL snapshot."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any

ELR_FIELDS = (
    'ELR_NO ELR_REV IMPORT_FILE1 CUST_REQ_NO CUST_BOM_NO CUST_BOM_REVISION '
    'CUST_ASSY_LOT PRODUCT_NO PACKAGE_CODE CURRENT_STEP STATUS LAST_TRAN MARK_APPROVE '
    'MARK_NAME IMPORT_DATE TOP_MARK_ID BACK_MARK_ID TOP_MARK1 TOP_MARK2 TOP_MARK3 '
    'TOP_MARK4 TOP_MARK5 BACK_MARK1 BACK_MARK2 BACK_MARK3 BACK_MARK4 BACK_MARK5 '
    'MARK_REMARK MARK_REQUIRE TM_LASER BM_LASER'
).split()

BASE_ELR_QUERY = (
    'SELECT ' + ', '.join('e.' + field for field in ELR_FIELDS) +
    ', t.TYPE_CODE TOP_TYPE_CODE, t.LAYOUT_CODE TOP_LAYOUT_CODE,'
    ' t.OPERATION_CODE TOP_OPERATION, t.REMARK TOP_TEMPLATE_REMARK,'
    ' t.MARK_FILE_REVISION TOP_MARK_FILE_REV, b.TYPE_CODE BACK_TYPE_CODE,'
    ' b.LAYOUT_CODE BACK_LAYOUT_CODE, b.REMARK BACK_TEMPLATE_REMARK'
    ' FROM ACTLDBA.ELR e LEFT JOIN ACTLDBA.MARK_ID t ON e.TOP_MARK_ID = t.MARK_ID'
    ' LEFT JOIN ACTLDBA.MARK_ID b ON e.BACK_MARK_ID = b.MARK_ID'
    " WHERE e.CUST_CODE = 'ADI'"
)


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
