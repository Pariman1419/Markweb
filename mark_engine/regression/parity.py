from __future__ import annotations

import re
from typing import Any

MATCH_STATUSES = frozenset({"MATCH", "MATCH_SLR", "MATCH_SHIFT", "MATCH_LOT"})
MISMATCH_STATUSES = frozenset({"DIFF", "DB_WRONG"})
NON_MEASURABLE_STATUSES = frozenset({"NOT_MEASURABLE"})
NON_ELIGIBLE_STATUSES = frozenset({"NOT_ELIGIBLE"})


_ABS_NO_RE = re.compile(r"ABS\d{6}", re.IGNORECASE)


def _abs_number(val: Any) -> str:
    """Normalise an ABS identifier to ABS + 6 digits (R1 uses file stems like ABS066973-ENG-1)."""
    s = _clean_str(val)
    m = _ABS_NO_RE.search(s)
    return m.group(0).upper() if m else s.upper()


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def classify(
    r1_row: dict,
    r0_row: dict | None,
    r0legacy_row: dict | None = None,
) -> str:
    """Classifies parity difference between R1 row and R0 row(s).

    Reason codes:
      - SAME: r1 status equals r0 status (or both match/comparable) and expected/final text equals
      - ORACLE_INFLUENCE_REMOVED: R0 cause in (SLR_OVERRIDE, GRAPHIC_ONLY_LINE, NO_BRAND_LINE, LINE_SHIFT)
        where R0 conditioned text on Oracle, or R0 status MATCH_SLR
      - GRAPHIC_NOW_COUNTED: R0 cause GRAPHIC_SYMBOL
      - LOT_NOW_VERIFIED: R0 status MATCH_LOT where R1 verified lot or flagged diff
      - RESOLVER_CHANGED: ELR measurable status differs, or different ABS selected
      - GATE_SPEC_V2: R0 was measurable via CUST_REQ_NO relaxation in run 3, but R1 is SLR_NOT_FOUND
      - REVIEW_FLAG: R1 line status is NEEDS_REVIEW
      - OCR_SOURCE_CHANGED: R0 line text came from ocr_reocr.csv (kept == 'Y'); flag r0_reocr
      - RESOLVER_CHANGED also when R1 rejected other revisions of the same ABS (abs_other_revisions)
      - BUG: anything else
    """
    if r0_row is None and r0legacy_row is not None:
        r0_row = r0legacy_row

    if r0_row is None:
        return "RESOLVER_CHANGED"

    r1_status = _clean_str(r1_row.get("status"))
    r0_status = _clean_str(r0_row.get("status"))

    r1_exp = _clean_str(r1_row.get("expected_mark"))
    r0_final = _clean_str(r0_row.get("final_mark"))

    r0_cause = _clean_str(r0_row.get("cause"))
    r1_hold = _clean_str(r1_row.get("hold_reason"))
    r1_detail = _clean_str(r1_row.get("detail"))

    elr_no = _clean_str(r1_row.get("elr_no"))
    side = _clean_str(r1_row.get("side"))
    line_no = str(r1_row.get("line_no", "")).strip()

    # 1. REVIEW_FLAG: R1 line status is NEEDS_REVIEW
    if r1_status == "NEEDS_REVIEW":
        return "REVIEW_FLAG"

    # 2. GATE_SPEC_V2: R0 was measurable via CUST_REQ_NO relaxation in run 3, but R1 is SLR_NOT_FOUND
    if (r1_hold == "SLR_NOT_FOUND" or r1_detail == "SLR_NOT_FOUND") and r0_status not in (
        "NOT_MEASURABLE",
        "NOT_ELIGIBLE",
    ):
        return "GATE_SPEC_V2"

    # 3. RESOLVER_CHANGED: different ABS selected
    r1_abs = _abs_number(r1_row.get("abs_no"))
    r0_abs = _abs_number(r0_row.get("abs_no"))
    if r1_abs and r0_abs and r1_abs != r0_abs:
        return "RESOLVER_CHANGED"

    # 4. RESOLVER_CHANGED: ELR measurable status differs
    r1_is_measurable = r1_status not in ("NOT_MEASURABLE", "NOT_ELIGIBLE")
    r0_is_measurable = r0_status not in ("NOT_MEASURABLE", "NOT_ELIGIBLE")
    if r1_is_measurable != r0_is_measurable:
        return "RESOLVER_CHANGED"

    # 5. OCR_SOURCE_CHANGED: R0 text for this line came from ocr_reocr.csv (kept == 'Y',
    #    selected with human GT, R04-REOCR-*); R1 uses the raw cached OCR. Flag set by the runner.
    if _clean_str(r1_row.get("r0_reocr")).upper() == "Y":
        return "OCR_SOURCE_CHANGED"

    # 6. SAME: r1 status equals r0 status (or both match/comparable) and expected/final text equals
    statuses_match = (
        (r1_status == r0_status)
        or (r1_status in MATCH_STATUSES and r0_status in MATCH_STATUSES)
        or (r1_status in MISMATCH_STATUSES and r0_status in MISMATCH_STATUSES)
        or (r1_status in NON_ELIGIBLE_STATUSES and r0_status in NON_ELIGIBLE_STATUSES)
        or (r1_status in NON_MEASURABLE_STATUSES and r0_status in NON_MEASURABLE_STATUSES)
    )
    is_non_compared_same = (
        r1_status == r0_status
        and r1_status in ("NOT_ELIGIBLE", "NOT_MEASURABLE", "NOT_MARKED", "NOT_COMPARABLE")
    )
    if statuses_match and (r1_exp == r0_final or is_non_compared_same):
        return "SAME"

    # 6b. RESOLVER_CHANGED: folder holds other revisions of the same ABS; R1 chose by Oracle
    #     CUST_BOM_REVISION (D-08) while R0 picked the ABS that best matched Oracle (R03-ONE-ABS,
    #     rejected D-06). R0 abs_no carries no revision, so this comes from the R1 resolution.
    if _clean_str(r1_row.get("abs_other_revisions")):
        return "RESOLVER_CHANGED"

    # 7. LOT_NOW_VERIFIED: R0 status MATCH_LOT where R1 verified lot or flagged diff
    if r0_status == "MATCH_LOT":
        return "LOT_NOW_VERIFIED"

    # 8. ORACLE_INFLUENCE_REMOVED: R0 cause in (SLR_OVERRIDE, GRAPHIC_ONLY_LINE, NO_BRAND_LINE, LINE_SHIFT)
    #    or R0 status MATCH_SLR
    if (
        # DB_LINE_EMPTY: R0 matched only because the Oracle line was empty (needs db_mark == '')
        r0_cause in ("SLR_OVERRIDE", "GRAPHIC_ONLY_LINE", "NO_BRAND_LINE", "LINE_SHIFT", "DB_LINE_EMPTY")
        or r0_status == "MATCH_SLR"
    ):
        return "ORACLE_INFLUENCE_REMOVED"

    # 9. GRAPHIC_NOW_COUNTED: R0 cause GRAPHIC_SYMBOL
    if r0_cause == "GRAPHIC_SYMBOL":
        return "GRAPHIC_NOW_COUNTED"

    # 10. Fallback BUG
    return "BUG"
