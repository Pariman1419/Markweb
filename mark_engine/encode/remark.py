from __future__ import annotations

import re

_SKIP_MARK_PATTERN = re.compile(r"skip\s*mark", re.IGNORECASE)
_CARET_LOGO_PATTERN = re.compile(r"\^\s*[:=]\s*ADI\s*L", re.IGNORECASE)
_DECL_PATTERN = re.compile(r"([@%^*{<!#?])\s*[:=]")
_ADI_LOGO_PATTERN = re.compile(r"ADI\s*LOGO", re.IGNORECASE)
_LOGO_PATTERN = re.compile(r"LOGO", re.IGNORECASE)


def remark_graphics(remark: str | None, require: str | None) -> dict[str, str]:
    """Map YOLO graphic symbols (@, %, {) to DB codes following MARK_REMARK/MARK_REQUIRE legend.

    Empty/None remark returns default mapping {'@': '@', '%': '%', '{': '{'}.
    Caret logo ('^ = ADI logo') returns {'@': '', '%': '^', '{': '^'}.
    """
    parts = [s.strip() for s in (remark, require) if s and s.strip()]
    rm = " | ".join(parts)
    if not rm:
        return {"@": "@", "%": "%", "{": "{"}

    if _CARET_LOGO_PATTERN.search(rm):
        return {"@": "", "%": "^", "{": "^"}

    decl = set(_DECL_PATTERN.findall(rm))
    pin = "@" if ("@" in decl or not decl) else ""

    if not decl or "%" in decl or _ADI_LOGO_PATTERN.search(rm):
        logo = "%"
    elif "*" in decl:
        logo = "*"
    elif "{" in decl:
        logo = "{"
    else:
        logo = "%" if _LOGO_PATTERN.search(rm) else ""

    return {
        "@": pin,
        "%": logo,
        "{": "{" if ("{" in decl or not decl) else logo,
    }


def is_skip_mark(remark: str | None, require: str | None) -> bool:
    """Check whether MARK_REMARK or MARK_REQUIRE specifies skip mark."""
    for s in (remark, require):
        if s and _SKIP_MARK_PATTERN.search(s):
            return True
    return False
