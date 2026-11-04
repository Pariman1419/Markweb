from __future__ import annotations

from collections import Counter
from typing import Sequence

from mark_engine.domain.models import ExpectedMark, OracleMark, Side

GRAPHIC_CHARS = frozenset("@%*<^!#{?}")


def extract_graphics(s: str | None) -> list[str]:
    if not s:
        return []
    return [c for c in s if c in GRAPHIC_CHARS]


def extract_text_only(s: str | None) -> str:
    if not s:
        return ""
    return "".join(c for c in s if c not in GRAPHIC_CHARS and not c.isspace())


def match_shift(expected: ExpectedMark, oracle: OracleMark, side: Side) -> bool:
    """Evaluate side-level shift (R06-SHIFT).

    Conditions:
    1. Oracle line 1 on that side is graphics-only (no letters/digits).
    2. Every expected text line n equals oracle text line n+1.
    3. Side graphic multisets between expected and oracle are equal.
    """
    ora_l1 = oracle.get(side, 1)
    if not ora_l1 or not ora_l1.strip():
        return False

    # 1. Oracle line 1 on that side is graphics-only (no letters/digits)
    if any(c.isalnum() for c in ora_l1):
        return False
    if not any(c in GRAPHIC_CHARS for c in ora_l1):
        return False

    # 2. Every expected text line n equals oracle text line n+1
    has_text = False
    for n in range(1, 5):
        exp_line = expected.line(side, n)
        exp_txt = extract_text_only(exp_line.text if exp_line and exp_line.text else "")
        ora_next_txt = extract_text_only(oracle.get(side, n + 1))
        if exp_txt != ora_next_txt:
            return False
        if exp_txt:
            has_text = True

    # Line 5 of expected cannot shift to line 6 in oracle
    exp_l5 = expected.line(side, 5)
    if exp_l5 and exp_l5.text and extract_text_only(exp_l5.text):
        return False

    if not has_text:
        return False

    # 3. Side graphic multisets between expected and oracle are equal
    exp_gfx_list: list[str] = []
    for n in range(1, 6):
        line = expected.line(side, n)
        if line and line.text:
            exp_gfx_list.extend(extract_graphics(line.text))

    ora_gfx_list: list[str] = []
    for n in range(1, 6):
        ora_line_text = oracle.get(side, n)
        if ora_line_text:
            ora_gfx_list.extend(extract_graphics(ora_line_text))

    if Counter(exp_gfx_list) != Counter(ora_gfx_list):
        return False

    return True
