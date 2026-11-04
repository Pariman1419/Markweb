from __future__ import annotations

import re
from typing import Sequence

from mark_engine.domain.models import ExpectedLine, ExpectedToken


def extract_lot_slice(lot: str, lot_slice: str) -> str | None:
    """Extract a specified slice from a scheduled lot string."""
    clean = lot.replace(".", "").replace(" ", "")
    if lot_slice == "1-9":
        return clean[:9] if len(clean) >= 9 else None
    if lot_slice == "3-7":
        return clean[2:7] if len(clean) >= 7 else None
    if lot_slice == "first-half":
        return clean[:4] if len(clean) >= 4 else None
    if lot_slice == "last-half":
        return clean[-5:] if len(clean) >= 5 else None
    if lot_slice.startswith("last-"):
        try:
            n = int(lot_slice.split("-")[1])
            return clean[-n:] if len(clean) >= n else None
        except ValueError:
            return None
    return None


def _candidate_slices_for_length(k: int) -> list[str]:
    """Return default candidate lot slices for an X-run of length k."""
    candidates = [f"last-{k}"]
    if k == 5:
        candidates.extend(["3-7", "last-half"])
    elif k == 4:
        candidates.append("first-half")
    elif k == 9:
        candidates.append("1-9")
    return candidates


def match_lot(
    expected_line: ExpectedLine | None,
    oracle_text: str,
    scheduled_lots: Sequence[str],
    import_date: str | None = None,
) -> bool:
    """Check whether oracle_text matches expected_line via verified placeholders.

    1. Expected line must contain placeholders (e.g. X-runs or YYWW).
    2. Non-placeholder characters must match literally (ignoring spaces).
    3. Every X-run group must correspond to digits matching a lot slice in scheduled_lots.
    4. Every YYWW group must be 4 digits with WW in 01..53 and YY within +-1 of import year.
    """
    if expected_line is None or not expected_line.text or not oracle_text:
        return False

    exp = "".join(expected_line.text.split())
    ora = "".join(oracle_text.split())

    if len(exp) != len(ora):
        return False

    placeholders: list[tuple[int, int, str]] = []

    for m in re.finditer(r"YYWW", exp):
        placeholders.append((m.start(), m.end(), "YYWW"))
    for m in re.finditer(r"(?<!Y)YWW", exp):
        if not any(p[0] <= m.start() < p[1] for p in placeholders):
            placeholders.append((m.start(), m.end(), "YWW"))
    for m in re.finditer(r"X+", exp):
        placeholders.append((m.start(), m.end(), "X"))

    if not placeholders:
        return False

    placeholders.sort(key=lambda p: p[0])

    # Check non-placeholder characters match literally
    is_ph = [False] * len(exp)
    for start, end, _ in placeholders:
        for i in range(start, end):
            is_ph[i] = True

    for i in range(len(exp)):
        if not is_ph[i]:
            if exp[i] != ora[i]:
                return False

    base_yy: int | None = None
    if import_date:
        ym = re.search(r"\b(20\d\d|\d{4})\b", import_date)
        if ym:
            base_yy = int(ym.group(1)) % 100

    lot_tokens: list[ExpectedToken] = [
        t for t in expected_line.tokens if t.lot_slice is not None
    ]
    lot_tok_idx = 0

    for start, end, kind in placeholders:
        ora_segment = ora[start:end]

        if kind == "YYWW":
            if not ora_segment.isdigit() or len(ora_segment) != 4:
                return False
            yy = int(ora_segment[:2])
            ww = int(ora_segment[2:])
            if not (1 <= ww <= 53):
                return False
            if base_yy is not None:
                allowed_yy = {(base_yy - 1) % 100, base_yy, (base_yy + 1) % 100}
                if yy not in allowed_yy:
                    return False

        elif kind == "YWW":
            if not ora_segment.isdigit() or len(ora_segment) != 3:
                return False
            y = int(ora_segment[0])
            ww = int(ora_segment[1:])
            if not (1 <= ww <= 53):
                return False
            if base_yy is not None:
                base_y = base_yy % 10
                allowed_y = {(base_y - 1) % 10, base_y, (base_y + 1) % 10}
                if y not in allowed_y:
                    return False

        elif kind == "X":
            if not ora_segment.isdigit():
                return False
            if not scheduled_lots:
                return False

            k = end - start
            slices_to_check: list[str] = []
            if lot_tok_idx < len(lot_tokens):
                tok_slice = lot_tokens[lot_tok_idx].lot_slice
                if tok_slice:
                    slices_to_check.append(tok_slice)
                lot_tok_idx += 1
            else:
                slices_to_check = _candidate_slices_for_length(k)

            matched = False
            for s_slice in slices_to_check:
                for lot in scheduled_lots:
                    extracted = extract_lot_slice(lot, s_slice)
                    if extracted is not None and extracted == ora_segment:
                        matched = True
                        break
                if matched:
                    break

            if not matched:
                return False

    return True
