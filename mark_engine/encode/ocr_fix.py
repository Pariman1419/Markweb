from __future__ import annotations

import re
from typing import Callable

_ReplType = str | Callable[[re.Match[str]], str]


def _repl_u_suffix(m: re.Match[str]) -> str:
    # Drafting suffix U\d after XXX or (LOT) NUMBER: drop the suffix only. Returning "" for
    # NUMBERU1 erased "LOT NUMBER" so "LAST 2 DIGIT LOT NUMBERU1" never became XX.
    return m.group(1) or m.group(2)


def _repl_origin_eng(m: re.Match[str]) -> str:
    # Handles THAI(?:LAND)?ENG\d -> THAILAND or (COUNTRY OF )ORIGINENG\d -> (COUNTRY OF )ORIGIN
    # ORIGINENG\d -> keep the field text, drop the suffix ("COUNTRY OF ORIGIN" is then
    # encoded by ADI1039 COO). Returning "" here erased the whole COO line.
    val = m.group(0)
    if "THAI" in val.upper():
        return "THAILAND"
    return re.sub(r"ENG\d$", "", val, flags=re.IGNORECASE)


def _repl_serial(m: re.Match[str]) -> str:
    return "X" * int(m.group(1))


OCR_RULES: tuple[tuple[str, re.Pattern[str], _ReplType], ...] = (
    ("R07-OCRFIX-1", re.compile(r"\{SPACEE?\}", re.IGNORECASE), " "),
    ("R07-OCRFIX-2", re.compile(r"\{LTC-PARTIA[L1I]-LO[G6]OE?\}", re.IGNORECASE), "*"),
    ("R07-OCRFIX-3", re.compile(r"\{ADI-PARTIA[L1I]-LO[G6]OE?\}", re.IGNORECASE), "%"),
    ("R07-OCRFIX-4", re.compile(r"\{([YWX]+)E\}", re.IGNORECASE), r"\1"),
    ("R07-OCRFIX-5", re.compile(r"\{v?e3\^?E?\}?(?=\s*$)", re.IGNORECASE), "<"),
    ("R07-OCRFIX-6", re.compile(r"\b(?:(X+)|((?:LOT\s*)?NUMBER))U\d\b", re.IGNORECASE), _repl_u_suffix),
    ("R07-OCRFIX-7", re.compile(r"\b(?:(?:COUNTRY OF )?ORIGIN|THAI(?:LAND)?)ENG\d\b", re.IGNORECASE), _repl_origin_eng),
    ("R07-OCRFIX-8", re.compile(r"\b(\d+) DIGIT SERIAL NUMBER\b", re.IGNORECASE), _repl_serial),
)


def ocr_fix(text: str) -> tuple[str, tuple[str, ...]]:
    """Apply R07-OCRFIX-1..8 rules in order to text.

    Returns the fixed text and a tuple of applied rule IDs.
    """
    applied: list[str] = []
    current = text
    for rule_id, pattern, repl in OCR_RULES:
        if pattern.search(current):
            current = pattern.sub(repl, current)
            applied.append(rule_id)
    return current, tuple(applied)
