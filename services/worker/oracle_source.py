"""Oracle ACTIVEL source adapter for the auto-review worker."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from mark_engine.adapters.oracle_client import select
from mark_engine.adapters.oracle_snapshot import (
    BASE_ELR_QUERY,
    rows_to_meta,
)
from mark_engine.domain.models import ElrMeta, OracleMark, Side
from mark_engine.generate.mark_layout import MarkLayout, parse_layout


def _clean_str(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def fetch_window(conn: Any, from_ts: datetime, to_ts: datetime) -> list[dict[str, Any]]:
    """Fetch ELR rows with LAST_TRAN in [from_ts, to_ts) window using read-only select."""
    query = f"{BASE_ELR_QUERY} AND e.LAST_TRAN >= :from_ts AND e.LAST_TRAN < :to_ts"
    binds = {"from_ts": from_ts, "to_ts": to_ts}
    return select(conn, query, binds)


def fetch_one(conn: Any, elr_no: str) -> dict[str, Any] | None:
    """Fetch latest revision row for a single ELR."""
    query = f"{BASE_ELR_QUERY} AND e.ELR_NO = :elr_no"
    binds = {"elr_no": elr_no}
    rows = select(conn, query, binds)
    if not rows:
        return None
    meta_list = rows_to_meta(rows)
    return meta_list[0] if meta_list else None


def fetch_pending_step(conn: Any, review_step: str) -> list[dict[str, Any]]:
    """Fetch every ADI ELR at review_step with STATUS other than 'C'."""
    query = f"{BASE_ELR_QUERY} AND e.CURRENT_STEP = :review_step AND e.STATUS != 'C'"
    binds = {"review_step": review_step}
    return select(conn, query, binds)


def to_engine(
    row: Mapping[str, Any],
    layout_rows: list[dict[str, Any]] | None = None,
) -> tuple[ElrMeta, OracleMark, MarkLayout | None]:
    """Convert an Oracle row to engine models (ElrMeta, OracleMark, MarkLayout | None)."""
    upper_row = {k.upper(): v for k, v in row.items()}
    raw_elr_no = upper_row.get("ELR_NO")
    elr_no = str(raw_elr_no).strip() if raw_elr_no is not None else ""

    top_mark_id = None
    if upper_row.get("TOP_MARK_ID") is not None:
        try:
            top_mark_id = int(upper_row["TOP_MARK_ID"])
        except (ValueError, TypeError):
            top_mark_id = None

    meta = ElrMeta(
        elr_no=elr_no,
        import_date=_clean_str(upper_row.get("IMPORT_DATE")),
        status=_clean_str(upper_row.get("STATUS")),
        current_step=_clean_str(upper_row.get("CURRENT_STEP")),
        cust_bom_no=_clean_str(upper_row.get("CUST_BOM_NO")),
        cust_bom_revision=_clean_str(upper_row.get("CUST_BOM_REVISION")),
        cust_req_no=_clean_str(upper_row.get("CUST_REQ_NO")),
        cust_assy_lot=_clean_str(upper_row.get("CUST_ASSY_LOT")),
        product_no=_clean_str(upper_row.get("PRODUCT_NO")),
        package_code=_clean_str(upper_row.get("PACKAGE_CODE")),
        mark_remark=_clean_str(upper_row.get("MARK_REMARK")),
        mark_require=_clean_str(upper_row.get("MARK_REQUIRE")),
        top_type_code=_clean_str(upper_row.get("TOP_TYPE_CODE")),
        top_layout_code=_clean_str(upper_row.get("TOP_LAYOUT_CODE")),
        top_mark_id=top_mark_id,
    )

    lines: list[tuple[Side, int, str]] = []
    raw_lines: list[tuple[Side, int, str]] = []

    for i in range(1, 6):
        val = upper_row.get(f"TOP_MARK{i}")
        if val is not None:
            raw_lines.append((Side.TOP, i, str(val)))
            cleaned = str(val).strip()
            if cleaned:
                lines.append((Side.TOP, i, cleaned))

    for i in range(1, 6):
        val = upper_row.get(f"BACK_MARK{i}")
        if val is not None:
            raw_lines.append((Side.BOTTOM, i, str(val)))
            cleaned = str(val).strip()
            if cleaned:
                lines.append((Side.BOTTOM, i, cleaned))

    mark = OracleMark(
        elr_no=elr_no,
        lines=tuple(lines),
        raw_lines=tuple(raw_lines),
    )

    layout: MarkLayout | None = None
    if top_mark_id is not None and layout_rows:
        try:
            layout = parse_layout(top_mark_id, layout_rows)
        except Exception:
            layout = None

    return meta, mark, layout
