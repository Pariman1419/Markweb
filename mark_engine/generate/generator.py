from __future__ import annotations

import re
from dataclasses import replace

from mark_engine.domain.models import (
    DocType,
    DocumentResolution,
    ElrMeta,
    ExpectedLine,
    ExpectedMark,
    ExpectedToken,
    Flag,
    InferenceResult,
    LayoutLine,
    Side,
    SlrFacts,
    SlrInstruction,
)
from mark_engine.encode.adi1039 import apply_adi1039
from mark_engine.encode.ocr_fix import ocr_fix
from mark_engine.encode.remark import remark_graphics
from mark_engine.encode.symbol_adi import encode_symbol_adi
from mark_engine.rules.ruleset import RuleSet
from mark_engine.version import ENGINE_VERSION

_CARET_LOGO_PATTERN = re.compile(r"\^\s*[:=]\s*ADI\s*L", re.IGNORECASE)
_DECL_PATTERN = re.compile(r"([@%^*{<!#?])\s*[:=]")
_ADI_LOGO_PATTERN = re.compile(r"ADI\s*LOGO", re.IGNORECASE)
_LOGO_PATTERN = re.compile(r"LOGO", re.IGNORECASE)


def _remark_declares_logo(remark: str | None, require: str | None) -> bool:
    parts = [s.strip() for s in (remark, require) if s and s.strip()]
    rm = " | ".join(parts)
    if not rm:
        return False
    if _CARET_LOGO_PATTERN.search(rm):
        return True
    decl = set(_DECL_PATTERN.findall(rm))
    if decl.intersection({"^", "%", "*", "{"}):
        return True
    if _ADI_LOGO_PATTERN.search(rm) or _LOGO_PATTERN.search(rm):
        return True
    return False


_E3_DECL_PATTERN = re.compile(r"\be3\s*[:=]", re.IGNORECASE)
_LT_DECL_PATTERN = re.compile(r"<\s*[:=]")
_LOGO_SYMBOLS = frozenset("%{*^")  # ADI logo, full logo, LTC logo, caret (= ADI logo)




def _rule_flags(rules: RuleSet, rule_id: str) -> frozenset[Flag]:
    try:
        _, flags = rules.usable(rule_id)
        return flags
    except KeyError:
        return frozenset()


def generate_expected(
    meta: ElrMeta,
    docs: DocumentResolution,
    slr: SlrFacts,
    inference: InferenceResult,
    rules: RuleSet,
) -> ExpectedMark:
    """Generate expected mark lines with priority ordering and review flags."""
    inf_by_loc: dict[tuple[Side, int], LayoutLine] = {
        (l.side, l.line_no): l for l in inference.lines
    }
    slr_by_loc: dict[tuple[Side, int], SlrInstruction] = {
        (inst.side, inst.line_no): inst for inst in slr.instructions
    }

    all_locs = sorted(
        set(inf_by_loc.keys()) | set(slr_by_loc.keys()),
        key=lambda loc: (0 if loc[0] == Side.TOP else 1, loc[1]),
    )

    remark_declares_logo = _remark_declares_logo(meta.mark_remark, meta.mark_require)
    gfx_mapping = remark_graphics(meta.mark_remark, meta.mark_require)

    parts = [s.strip() for s in (meta.mark_remark, meta.mark_require) if s and s.strip()]
    rm_joined = " | ".join(parts)
    pbfree_code = (
        "e3"
        if _E3_DECL_PATTERN.search(rm_joined) and not _LT_DECL_PATTERN.search(rm_joined)
        else "<"
    )

    revision_mismatch = (
        docs is not None
        and hasattr(docs, "steps")
        and ("REVISION_NAME_MISMATCH" in docs.steps or "PRODUCT_NO_ABS_MISMATCH" in docs.steps)
    )
    has_unresolved_slr = bool(slr.unresolved) if slr is not None else False

    lines: list[ExpectedLine] = []

    for side, line_no in all_locs:
        line_flags: set[Flag] = set()
        applied_rules: set[str] = set()

        if has_unresolved_slr:
            line_flags.add(Flag.SLR_UNRESOLVED)

        if revision_mismatch:
            line_flags.add(Flag.RULE_CONFLICT)

        inf_line = inf_by_loc.get((side, line_no))
        slr_inst = slr_by_loc.get((side, line_no))

        raw_text = inf_line.text if inf_line is not None else ""
        raw_graphics = inf_line.graphics if inf_line is not None else ""

        # Step 1: ABS text from inference LayoutLine
        if inf_line is not None and raw_text:
            fixed_text, ocr_rules = ocr_fix(raw_text)
            applied_rules.update(ocr_rules)
            # MARK_REMARK (P20) beats OCR fix (P50): OCRFIX-5 writes the Pb-free mark as '<',
            # but a remark declaring "e3 = Pb-free" (and no '<') means the code is 'e3'.
            if "R07-OCRFIX-5" in ocr_rules and pbfree_code == "e3":
                fixed_text = re.sub(r"<(?=\s*$)", "e3", fixed_text)

            encoded_text, unmapped_tokens = encode_symbol_adi(fixed_text)
            if unmapped_tokens:
                line_flags.add(Flag.UNMAPPED_TOKEN)
            if encoded_text != fixed_text:
                applied_rules.add("R07-SYMBOL-ADI")

            adi_text, adi_tokens = apply_adi1039(encoded_text, DocType.ABS)
            for tok in adi_tokens:
                applied_rules.add(tok.rule_id)

            text_part = adi_text
            text_tokens: list[ExpectedToken] = list(adi_tokens)
            for r_id in ocr_rules:
                text_tokens.append(ExpectedToken(text="", rule_id=r_id, source="OCR_FIX"))
        else:
            text_part = ""
            text_tokens = []

        # Step 2: Graphics prefix
        mapped_graphics = "".join(gfx_mapping.get(c, c) for c in raw_graphics)
        graphic_tokens: list[ExpectedToken] = []

        for c in mapped_graphics:
            if _CARET_LOGO_PATTERN.search(rm_joined):
                g_rule = "R07-REMARK-CARET"
            elif c == "@":
                g_rule = "R07-REMARK-PIN"
            elif c in ("%", "*", "{", "^"):
                g_rule = "R07-REMARK-LOGO"
            else:
                g_rule = "R07-REMARK-LOGO"
            applied_rules.add(g_rule)
            graphic_tokens.append(ExpectedToken(text=c, rule_id=g_rule, source="REMARK"))

        if "@" in raw_graphics and "@" not in gfx_mapping.get("@", "@"):
            line_flags.add(Flag.GRAPHIC_REMARK_CONFLICT)

        # Step 3: SLR Override
        if slr_inst is not None:
            if slr_inst.value is None:
                line_flags.add(Flag.SLR_AMBIGUOUS)
            else:
                slr_text, slr_tokens = apply_adi1039(slr_inst.value, DocType.SLR)
                text_part = slr_text
                text_tokens = list(slr_tokens)
                line_flags.add(Flag.SLR_OVERRIDE)
                applied_rules.add("R04-SLR-LINE")
                for tok in slr_tokens:
                    applied_rules.add(tok.rule_id)

        # Step 4: Combine text and graphics prefix
        if mapped_graphics and text_part:
            full_text = f"{mapped_graphics} {text_part}"
        elif mapped_graphics:
            full_text = mapped_graphics
        elif text_part:
            full_text = text_part
        else:
            full_text = ""

        combined_tokens = tuple(graphic_tokens + text_tokens)

        # Merge flags from usable rules
        for r_id in applied_rules:
            line_flags.update(_rule_flags(rules, r_id))

        lines.append(
            ExpectedLine(
                side=side,
                line_no=line_no,
                text=full_text,
                tokens=combined_tokens,
                flags=frozenset(line_flags),
            )
        )

    # MARK_REMARK declares a logo for the part (not per side). Conflict only when no expected
    # line carries any logo symbol — from YOLO graphics or from the drawing text
    # (e.g. {LTC-PARTIAL-LOGO} -> '*'). Checking per side with only '%'/'{' flagged every
    # BOTTOM line and every LTC/caret logo (R1: 303 lines, 259 already equal to Oracle).
    if remark_declares_logo and not any(
        ch in _LOGO_SYMBOLS for line in lines for ch in line.text
    ):
        lines = [
            replace(line, flags=line.flags | {Flag.GRAPHIC_REMARK_CONFLICT}) for line in lines
        ]

    return ExpectedMark(
        elr_no=meta.elr_no,
        lines=tuple(lines),
        rule_version=rules.version,
        engine_version=ENGINE_VERSION,
    )
