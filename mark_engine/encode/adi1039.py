from __future__ import annotations

import csv
import importlib.resources as pkg_resources
from pathlib import Path
import re

from mark_engine.domain.models import DocType, ExpectedToken

_CSV_TOKENS: list[dict[str, str]] | None = None


def _load_adi1039_csv() -> list[dict[str, str]]:
    global _CSV_TOKENS
    if _CSV_TOKENS is None:
        try:
            ref = pkg_resources.files("mark_engine.encode").joinpath("data", "adi1039_tokens.csv")
            with ref.open("r", encoding="utf-8") as f:
                _CSV_TOKENS = list(csv.DictReader(f))
        except Exception:
            path = Path(__file__).resolve().parent / "data" / "adi1039_tokens.csv"
            with path.open("r", encoding="utf-8") as f:
                _CSV_TOKENS = list(csv.DictReader(f))
    return _CSV_TOKENS


def apply_adi1039(text: str, doc_type: DocType) -> tuple[str, tuple[ExpectedToken, ...]]:
    """Apply ADI1039 abbreviation mappings and standard rules.

    Only applies to ABS and SLR documents. Raises ValueError for TRS and OTHER.
    """
    if doc_type in (DocType.TRS, DocType.OTHER):
        raise ValueError(f"ADI1039 does not apply to {doc_type}")

    if not text:
        return "", ()

    tokens: list[ExpectedToken] = []
    current = text

    # 1. ASSEMBLY LOT NUMBER / {Lot-Full} -> XXXXXXXXX (R07-ADI1039-LOT)
    def _repl_lot_full(m: re.Match[str]) -> str:
        repl = "XXXXXXXXX"
        tokens.append(
            ExpectedToken(
                text=repl,
                rule_id="R07-ADI1039-LOT",
                source="ADI1039",
                lot_slice="1-9",
            )
        )
        return repl

    current = re.sub(
        r"\{Lot-Full\}|\bASSEMBLY\s+LOT\s+NUMBER\b",
        _repl_lot_full,
        current,
        flags=re.IGNORECASE,
    )

    # 2. Specific lot slices from CSV: {Lot-3-7}, {Lot-Full-LastHalf}, {Lot-Full-FirstHalf}, {Lot-Last-2}, {Lot-Last-1}
    def _repl_lot_slice(repl: str, lot_slice: str):
        def _cb(m: re.Match[str]) -> str:
            tokens.append(
                ExpectedToken(
                    text=repl,
                    rule_id="R07-ADI1039-LOT",
                    source="ADI1039",
                    lot_slice=lot_slice,
                )
            )
            return repl
        return _cb

    current = re.sub(r"\{Lot-3-7\}", _repl_lot_slice("XXXXX", "3-7"), current, flags=re.IGNORECASE)
    current = re.sub(r"\{Lot-Full-LastHalf\}", _repl_lot_slice("XXXXX", "last-half"), current, flags=re.IGNORECASE)
    current = re.sub(r"\{Lot-Full-FirstHalf\}", _repl_lot_slice("XXXX", "first-half"), current, flags=re.IGNORECASE)
    current = re.sub(r"\{Lot-Last-2\}", _repl_lot_slice("XX", "last-2"), current, flags=re.IGNORECASE)
    current = re.sub(r"\{Lot-Last-1\}", _repl_lot_slice("X", "last-1"), current, flags=re.IGNORECASE)

    # 3. {Lot-n} -> X*n with lot_slice="last-n"
    def _repl_lot_n(m: re.Match[str]) -> str:
        n = int(m.group(1))
        repl = "X" * n
        tokens.append(
            ExpectedToken(
                text=repl,
                rule_id="R07-ADI1039-LOT",
                source="ADI1039",
                lot_slice=f"last-{n}",
            )
        )
        return repl

    current = re.sub(r"\{Lot-(\d)\}", _repl_lot_n, current, flags=re.IGNORECASE)
    # Same token in its Table 2 preview-text form, as printed in ABS legends:
    # "7 Digit Lot Number", "LAST 2 DIGIT LOT NUMBER". No trailing \b: OCR often glues the
    # next field ("3 DIGIT LOT NUMBERYWW"), and no leading \b: "YW6 DIGIT LOT NUMBER".
    current = re.sub(
        r"(?:\bLAST\s+)?(?<!\d)(\d)\s*DIGIT\s+LOT\s+NUMBER",
        _repl_lot_n,
        current,
        flags=re.IGNORECASE,
    )

    # 4. Date codes and other CSV tokens: {DC-4}, {DC-3}, {DC-2}, {DC-1}, {Pb-Free}, {FACTORYCODE}
    def _repl_token(repl: str, rule_id: str = "R07-ADI1039"):
        def _cb(m: re.Match[str]) -> str:
            tokens.append(
                ExpectedToken(
                    text=repl,
                    rule_id=rule_id,
                    source="ADI1039",
                    lot_slice=None,
                )
            )
            return repl
        return _cb

    current = re.sub(r"\{DC-4\}", _repl_token("YYWW"), current, flags=re.IGNORECASE)
    current = re.sub(r"\{DC-3\}", _repl_token("YWW"), current, flags=re.IGNORECASE)
    current = re.sub(r"\{DC-2\}", _repl_token("YW"), current, flags=re.IGNORECASE)
    current = re.sub(r"\{DC-1\}", _repl_token("Y"), current, flags=re.IGNORECASE)
    current = re.sub(r"\{Pb-Free\}", _repl_token("#"), current, flags=re.IGNORECASE)
    current = re.sub(r"\{FACTORYCODE\}", _repl_token("B"), current, flags=re.IGNORECASE)

    # 5. COUNTRY OF ORIGIN / \bTHAI(L)?\b -> THAILAND (R07-ADI1039-COO)
    def _repl_coo(m: re.Match[str]) -> str:
        repl = "THAILAND"
        tokens.append(
            ExpectedToken(
                text=repl,
                rule_id="R07-ADI1039-COO",
                source="ADI1039",
                lot_slice=None,
            )
        )
        return repl

    current = re.sub(
        r"\bCOUNTRY\s+OF\s+ORIGIN\b|\bTHAI(L)?\b",
        _repl_coo,
        current,
        flags=re.IGNORECASE,
    )

    # 6. _, ␣, {SPACE} -> space (§5.1.6)
    def _repl_space(m: re.Match[str]) -> str:
        tokens.append(
            ExpectedToken(
                text=" ",
                rule_id="R07-ADI1039",
                source="ADI1039",
                lot_slice=None,
            )
        )
        return " "

    current = re.sub(r"[_␣]|\{SPACE\}", _repl_space, current, flags=re.IGNORECASE)

    return current, tuple(tokens)
