from __future__ import annotations

import importlib.resources as pkg_resources
import json
from pathlib import Path
import re

_SYM_DATA: dict[str, str] | None = None
_DATE_LOT_PATTERN = re.compile(r"y+w+|yw|yxxw|y|x+", re.IGNORECASE)
_BRACKETED_TOKEN_PATTERN = re.compile(r"\{([^{}]*)\}")


def get_symbol_map() -> dict[str, str]:
    global _SYM_DATA
    if _SYM_DATA is None:
        try:
            ref = pkg_resources.files("mark_engine.encode").joinpath("data", "symbol_adi_r0.json")
            with ref.open("r", encoding="utf-8") as f:
                _SYM_DATA = json.load(f)
        except Exception:
            path = Path(__file__).resolve().parent / "data" / "symbol_adi_r0.json"
            with path.open("r", encoding="utf-8") as f:
                _SYM_DATA = json.load(f)
    return _SYM_DATA


def encode_symbol_adi(text: str) -> tuple[str, tuple[str, ...]]:
    """Encode bracketed tokens {token} into component symbols per Symbol ADI.

    Preserves date/lot placeholders {YYWW}, {XXXXX} in uppercase.
    Unmapped tokens (including {CCCCC}) remain in text and are returned in unmapped_tokens.
    """
    if not text:
        return "", ()

    sym = get_symbol_map()
    unmapped: list[str] = []

    def _replace_token(m: re.Match[str]) -> str:
        raw_inner = m.group(1)
        k = raw_inner.strip().lower()

        if k in sym:
            return sym[k]

        if _DATE_LOT_PATTERN.fullmatch(k):
            return raw_inner.strip().upper()

        full_token = f"{{{raw_inner}}}"
        unmapped.append(full_token)
        return full_token

    encoded_text = _BRACKETED_TOKEN_PATTERN.sub(_replace_token, text)
    return encoded_text, tuple(unmapped)
