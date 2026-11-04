import json
import os
import subprocess
from pathlib import Path
from typing import Any

from mark_engine.domain.models import ElrMeta, OracleMark, Side


def _clean_str(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def load_elr_snapshot(path: Path) -> dict[str, tuple[ElrMeta, OracleMark]]:
    """Loads ELR snapshot rows from a JSON file into (ElrMeta, OracleMark) tuples.
    
    Returns a dict mapping ELR number (str) to (ElrMeta, OracleMark).
    """
    with open(path, "r", encoding="utf-8") as f:
        rows: list[dict[str, Any]] = json.load(f)

    result: dict[str, tuple[ElrMeta, OracleMark]] = {}

    for row in rows:
        # Standardize keys to uppercase for robust lookup
        upper_row = {k.upper(): v for k, v in row.items()}

        raw_elr_no = upper_row.get("ELR_NO")
        if raw_elr_no is None:
            continue
        elr_no = str(raw_elr_no).strip()

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
        )

        lines: list[tuple[Side, int, str]] = []
        for i in range(1, 6):
            val = upper_row.get(f"TOP_MARK{i}")
            if val is not None:
                cleaned = str(val).strip()
                if cleaned:
                    lines.append((Side.TOP, i, cleaned))

        for i in range(1, 6):
            val = upper_row.get(f"BACK_MARK{i}")
            if val is not None:
                cleaned = str(val).strip()
                if cleaned:
                    lines.append((Side.BOTTOM, i, cleaned))

        oracle_mark = OracleMark(elr_no=elr_no, lines=tuple(lines))
        result[elr_no] = (meta, oracle_mark)

    return result


def r0_root() -> Path:
    """Returns the R0 root path from MARK_R0_ROOT or default D:/CIM Project/mark."""
    env = os.environ.get("MARK_R0_ROOT")
    if env:
        return Path(env)
    return Path("D:/CIM Project/mark")


def verify_r0_root(root: Path) -> None:
    """Verifies that R0 root exists and has no uncommitted changes on experiments."""
    if not root.is_dir():
        raise RuntimeError(f"R0 root directory does not exist: {root}")

    cmd = ["git", "-C", str(root), "diff", "--quiet", "regression-r0-2026-11-04", "--", "experiments"]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"R0 root {root} has git diff against regression-r0-2026-11-04 on experiments (exit code {proc.returncode})"
        )
