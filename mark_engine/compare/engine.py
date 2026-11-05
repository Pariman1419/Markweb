from __future__ import annotations

import re
from typing import Sequence

from mark_engine.compare.lot import match_lot
from mark_engine.compare.shift import match_shift
from mark_engine.domain.models import (
    ElrMeta,
    ExpectedLine,
    ExpectedMark,
    Flag,
    LineComparison,
    LineStatus,
    OracleMark,
    Side,
    SlrFacts,
)
from mark_engine.rules.ruleset import RuleSet


def nospace(s: str | None) -> str:
    """Remove all whitespace characters from string."""
    if s is None:
        return ""
    return re.sub(r"\s+", "", s)


_COO_FULL = "THAILAND"
_COO_LAYOUT_SHORT = "THAI"  # most common ACTL short form, used when THAILAND does not fit
_COO_MIN_ABBR = 2  # Mark Eng 2026-11-04 (09 Q1): TH, THA, THAI, THAIL... all read as THAILAND


def _coo_abbreviation(exp_text: str, ora_text: str) -> str | None:
    """Oracle's short form when it equals expected with THAILAND shortened to a prefix of >= 2 chars."""
    exp_ns = nospace(exp_text).upper()
    ora_ns = nospace(ora_text).upper()
    # Expected carries THAILAND, or THAI when the layout had no room for it (pipeline).
    written = _COO_FULL if _COO_FULL in exp_ns else _COO_LAYOUT_SHORT if _COO_LAYOUT_SHORT in exp_ns else None
    if written is None:
        return None
    for k in range(_COO_MIN_ABBR, len(_COO_FULL) + 1):
        if _COO_FULL[:k] != written and exp_ns.replace(written, _COO_FULL[:k]) == ora_ns:
            return _COO_FULL[:k]
    return None


def _serial_digits_match(exp_text: str | None, ora_text: str) -> bool:
    if not exp_text or not ora_text:
        return False
    if not re.search(r"X+", exp_text):
        return False
    return bool(re.search(r"\d+", ora_text))


def compare(
    expected: ExpectedMark,
    oracle: OracleMark,
    slr: SlrFacts | None = None,
    meta: ElrMeta | None = None,
    rules: RuleSet | None = None,
) -> tuple[LineComparison, ...]:
    """Compare ExpectedMark and OracleMark line by line following decision hierarchy.

    Decision hierarchy per (side, line_no) over lines 1..5:
    (Skip if both expected line text is empty/None and oracle text is empty/None)
    1. Review Flags Gate: If expected line has flags other than SLR_OVERRIDE -> NEEDS_REVIEW
    2. Empty Oracle: If oracle text is "" -> DB_EMPTY
    3. Exact Match: If nospace(expected) == nospace(oracle) -> MATCH_SLR or MATCH
    3b. COO abbreviation: Oracle has THAILAND shortened to TH..THAILAN -> MATCH with warning
        (compare_rules R07-ADI1039-COO, detail COO_ABBREVIATED)
    4. Verified Lot Match: match_lot -> MATCH_LOT
    5. Line Shift: side-level match_shift -> MATCH_SHIFT
    6. Oracle Value in SLR -> NEEDS_REVIEW (ORACLE_VALUE_IN_SLR)
    7. Serial Not Verifiable (OCRFIX-8) -> NEEDS_REVIEW (SERIAL_NOT_VERIFIABLE)
    8. Else -> DIFF (or detail DB_LOT_IS_PACKAGE if R07-DB-PACKAGE)
    """
    comparisons: list[LineComparison] = []

    scheduled_lots = slr.scheduled_lots if slr is not None else ()
    import_date = meta.import_date if meta is not None else None
    slr_text = slr.text if slr is not None else ""

    # Evaluate side-level shift for each side
    shift_matched: dict[Side, bool] = {
        side: match_shift(expected, oracle, side) for side in (Side.TOP, Side.BOTTOM)
    }

    for side in (Side.TOP, Side.BOTTOM):
        is_side_shifted = shift_matched[side]

        for line_no in range(1, 6):
            exp_line = expected.line(side, line_no)
            exp_text = exp_line.text if exp_line is not None else None
            ora_text = oracle.get(side, line_no)

            # Skip if both expected line text is empty/None and oracle text is empty/None
            if (exp_text is None or exp_text == "") and (ora_text is None or ora_text == ""):
                continue

            # 1. Review Flags Gate:
            # If expected line has any flag other than SLR_OVERRIDE
            if exp_line is not None:
                review_flags = [f for f in exp_line.flags if f != Flag.SLR_OVERRIDE]
                if review_flags:
                    detail = ", ".join(sorted(f.value for f in review_flags))
                    comparisons.append(
                        LineComparison(
                            side=side,
                            line_no=line_no,
                            expected=exp_text,
                            oracle=ora_text,
                            status=LineStatus.NEEDS_REVIEW,
                            compare_rules=(),
                            detail=detail,
                        )
                    )
                    continue

            # 2. Empty Oracle
            if ora_text == "":
                comparisons.append(
                    LineComparison(
                        side=side,
                        line_no=line_no,
                        expected=exp_text,
                        oracle=ora_text,
                        status=LineStatus.DB_EMPTY,
                        compare_rules=(),
                        detail="oracle empty",
                    )
                )
                continue

            # 3. Exact Match (ignoring spaces, graphics included)
            if exp_text is not None and nospace(exp_text) == nospace(ora_text):
                if exp_line is not None and Flag.SLR_OVERRIDE in exp_line.flags:
                    comparisons.append(
                        LineComparison(
                            side=side,
                            line_no=line_no,
                            expected=exp_text,
                            oracle=ora_text,
                            status=LineStatus.MATCH_SLR,
                            compare_rules=("R04-SLR-LINE",),
                            detail="",
                        )
                    )
                else:
                    comparisons.append(
                        LineComparison(
                            side=side,
                            line_no=line_no,
                            expected=exp_text,
                            oracle=ora_text,
                            status=LineStatus.MATCH,
                            compare_rules=("EXACT",),
                            detail="",
                        )
                    )
                continue

            # 3a. Letters equal but case differs ("Bajau TC" vs Oracle "BAJAU TC"). The laser marks
            # what Oracle holds; 31 of 36 such lines Jan-Nov 2026 had an all-uppercase Oracle. Counted
            # as a match, shown as a warning (overflow review 2026-11-05: "Warning เตือนเรื่องขนาด").
            if exp_text is not None and nospace(exp_text).upper() == nospace(ora_text).upper():
                slr = exp_line is not None and Flag.SLR_OVERRIDE in exp_line.flags
                comparisons.append(
                    LineComparison(
                        side=side,
                        line_no=line_no,
                        expected=exp_text,
                        oracle=ora_text,
                        status=LineStatus.MATCH_SLR if slr else LineStatus.MATCH,
                        compare_rules=("R04-SLR-LINE",) if slr else ("CASE_INSENSITIVE",),
                        detail="CASE_DIFF",
                        warning=f"CASE_DIFF: expected {exp_text.strip()}, Oracle {ora_text.strip()}",
                    )
                )
                continue

            # 3b. COO abbreviation (R07-ADI1039-COO, ADI1039 5.5.3: full name only "when space
            # allows"). Expected always carries THAILAND; Oracle may hold the short form.
            coo_abbr = _coo_abbreviation(exp_text, ora_text) if exp_text is not None else None
            if coo_abbr is not None:
                # MATCH, but Mark Eng wants the user to see that Oracle differs (09 Q1)
                comparisons.append(
                    LineComparison(
                        side=side,
                        line_no=line_no,
                        expected=exp_text,
                        oracle=ora_text,
                        status=LineStatus.MATCH,
                        compare_rules=("R07-ADI1039-COO",),
                        detail="COO_ABBREVIATED",
                        warning=f"COO_ABBREVIATED: Oracle {coo_abbr}, expected {_COO_FULL}",
                    )
                )
                continue

            # 4. Verified Lot Match
            if exp_line is not None and match_lot(exp_line, ora_text, scheduled_lots, import_date):
                comparisons.append(
                    LineComparison(
                        side=side,
                        line_no=line_no,
                        expected=exp_text,
                        oracle=ora_text,
                        status=LineStatus.MATCH_LOT,
                        compare_rules=("R07-PLACEHOLDER", "R04-SLR-LOT"),
                        detail="",
                    )
                )
                continue

            # 5. Line Shift (side-level)
            if is_side_shifted:
                comparisons.append(
                    LineComparison(
                        side=side,
                        line_no=line_no,
                        expected=exp_text,
                        oracle=ora_text,
                        status=LineStatus.MATCH_SHIFT,
                        compare_rules=("R06-SHIFT",),
                        detail="",
                    )
                )
                continue

            # 6. Oracle Value in SLR
            ora_ns = nospace(ora_text)
            if (
                len(ora_ns) >= 6
                and any(c.isalpha() for c in ora_ns)
                and any(c.isdigit() for c in ora_ns)
                and slr_text
                and bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(ora_ns)}(?![A-Za-z0-9])", slr_text))
            ):
                comparisons.append(
                    LineComparison(
                        side=side,
                        line_no=line_no,
                        expected=exp_text,
                        oracle=ora_text,
                        status=LineStatus.NEEDS_REVIEW,
                        compare_rules=("ORACLE_VALUE_IN_SLR",),
                        detail="ORACLE_VALUE_IN_SLR",
                    )
                )
                continue

            # 7. Serial Not Verifiable
            if (
                exp_line is not None
                and any(t.rule_id == "R07-OCRFIX-8" for t in exp_line.tokens)
                and _serial_digits_match(exp_text, ora_text)
            ):
                comparisons.append(
                    LineComparison(
                        side=side,
                        line_no=line_no,
                        expected=exp_text,
                        oracle=ora_text,
                        status=LineStatus.NEEDS_REVIEW,
                        compare_rules=("R07-OCRFIX-8",),
                        detail="SERIAL_NOT_VERIFIABLE",
                    )
                )
                continue

            # 8. Else DIFF
            if (
                exp_text is not None
                and re.search(r"X+", exp_text)
                and re.search(r"T?SSOP", ora_text, re.IGNORECASE)
            ):
                comparisons.append(
                    LineComparison(
                        side=side,
                        line_no=line_no,
                        expected=exp_text,
                        oracle=ora_text,
                        status=LineStatus.DIFF,
                        compare_rules=("R07-DB-PACKAGE",),
                        detail="DB_LOT_IS_PACKAGE",
                    )
                )
            else:
                comparisons.append(
                    LineComparison(
                        side=side,
                        line_no=line_no,
                        expected=exp_text,
                        oracle=ora_text,
                        status=LineStatus.DIFF,
                        compare_rules=(),
                        detail="",
                    )
                )

    return tuple(comparisons)
