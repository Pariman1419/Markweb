import re
from mark_engine.domain.models import Side, SlrFacts, SlrInstruction

SLR_STOP = re.compile(
    r"^(?:BUILD|ADDITIONAL|MUST|PLEASE|FOR|DIE\d*|WAFER|TRACKING|BEF|PRODUCT|TN#|SHIPPING|AUTO|USE|THIS|"
    r"NOTES?|INTENT|SHIP|DO|TOP|BOTTOM|LINE|AND|WITH|SAME|QUAL|CUSTOMER)\b",
    re.IGNORECASE,
)

LINE_HEADER_RE = re.compile(
    r"\b(TOP|BOTTOM)\b|\bline\s*(?:mark\s*)?(\d+)\b(?:\s+of\s+the\s+\w+)?\s*(?:-|:|to\b|as follows:?)?\s*",
    re.IGNORECASE,
)

# Coverage detector: a sentence is "about the mark" only when it names the mark itself.
# Bare "lot" / "attachment" / "top" are NOT enough: in Jan-Jun SLRs they appear almost only in
# wafer / fab-lot / logistics notes ("SPECIAL LOT REQUEST" header, "Fab Lot ID", "IB Lot"), which
# flagged 191 ELRs as SLR_UNRESOLVED although 86 % of those lines already matched Oracle.
MARKING_KEYWORDS_RE = re.compile(
    r"\b(?:"
    r"brand\w*|mark(?:ing|ings|s|ed)?|logo|symbol|laser|date\s*code"
    r"|line\s*\d+|(?:first|second|third|fourth|fifth)\s+line"
    r"|(?:top|bottom)\s*side"
    r"|attach\w*\s+for\s+(?:further\s+|more\s+)?instructions?"
    r")\b",
    re.IGNORECASE,
)


# Cross-lot notes that tie the date VALUE to other SLRs ("Same date code with: SLR230991, SLR230988").
# They do not change the mark format (the date stays a placeholder), so they are not an unread
# instruction. Before this, the words "date code" flagged every line SLR_UNRESOLVED and blocked the
# lot check (ADI2601023 BOTTOM 2 {Lot-4} = 0523).
SAME_DATE_CODE_NOTE_RE = re.compile(r"^\s*same\s+date\s*code\s+(?:as|with)\b[\s:]*(?:SLR\d{6}[\s,;&]*(?:and\s+)?)+\.?\s*$", re.I)


_NL = ""  # private-use char; str.split() does not treat it as whitespace


_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
_BRAND_WORD = r"(?:marking|brand(?:\s+content)?)"
# "Second line of brand content / marking: 'GL3G'" (Glacier / multi-project wafer SLRs).
ORDINAL_LINE_RE = re.compile(
    rf"\b(first|second|third|fourth|fifth)\s+line\s+of\s+(?:the\s+)?{_BRAND_WORD}(?:\s*/\s*{_BRAND_WORD})?\s*:\s*",
    re.IGNORECASE,
)
# Sentences that only point to the line instructions in the same SLR. Unresolved only when the
# SLR gives no line instruction at all (24755: "*Ignore Brand on ABS. Brand as indicated below.").
POINTER_SENTENCE_RE = re.compile(
    r"^\*?\s*(?:ignore\s+(?:the\s+)?brand(?:ing)?\s+on\s+(?:the\s+)?abs"
    r"|brand(?:ing)?\s+as\s+indicated\s+below"
    r"|use\s+the\s+attached\s+abs\s+and\s+markings?\s+below)\.?$",
    re.IGNORECASE,
)


def _ordinal_value(text: str) -> str:
    """Quoted value when quoted ('GL3G', "LSNv00"), else the leading mark tokens."""
    quoted = re.match(r"""\s*['"‘’“”]([^'"‘’“”]+)['"‘’“”]""", text)
    if quoted:
        return quoted.group(1).strip()
    toks: list[str] = []
    for word in text.split():
        if SLR_STOP.match(word) or re.match(r"^[a-z]", word):
            break
        toks.append(word.rstrip(".,;"))
        if word.endswith((".", ";")):
            break
    return " ".join(t for t in toks if t)


def _without_breaks(sentence: str) -> str:
    return re.sub(r"\s+", " ", sentence.replace(_NL, " ")).strip()


def parse_slr(text: str) -> SlrFacts:
    """Parse SLR text for special instructions, line markings, scheduled lots, qual lot, and coverage."""
    norm_text = re.sub(r"[\u2010-\u2015\u2212]", "-", text)

    # 1. Scheduled lots (ASSEMBLY LOTS / Scheduled Lot ID)
    scheduled_lots: list[str] = []
    lot_idx = norm_text.upper().find("SCHEDULED LOT ID")
    if lot_idx != -1:
        remainder = norm_text[lot_idx + len("SCHEDULED LOT ID"):]
        for line in remainder.splitlines():
            line = line.strip()
            m = re.match(r"^(\d{6,8})\.\d+$", line)
            if m:
                lot = m.group(1)
                if lot not in scheduled_lots:
                    scheduled_lots.append(lot)

    # 2. Qual lot check (consistency check only, never an instruction)
    qual_match = re.search(r"\bQual\s+lot\s+(\d+)\s+of\s+(\d+)\b", norm_text, re.IGNORECASE)
    qual_lot = (int(qual_match.group(1)), int(qual_match.group(2))) if qual_match else None

    # 3. Extract SPECIAL INSTRUCTIONS section (R04-SLR-SECTION)
    sec_match = re.search(
        r"SPECIAL INSTRUCTIONS\s*\r?\n(.*?)(?:\r?\nANALOG\s*\r?\nDEVICES|\r?\nASSEMBLY LOT[S]?\b|\Z)",
        norm_text,
        re.DOTALL | re.IGNORECASE,
    )
    if sec_match:
        section_raw = sec_match.group(1)
    else:
        # If no explicit SPECIAL INSTRUCTIONS header:
        # Exclude Scheduled Lot ID / ASSEMBLY LOT section if present
        lot_header_match = re.search(
            r"\b(?:SCHEDULED LOT ID|ASSEMBLY LOT[S]?)\b", norm_text, re.IGNORECASE
        )
        if lot_header_match:
            section_raw = norm_text[:lot_header_match.start()]
        else:
            section_raw = norm_text

    # Multiple whitespace -> single space; text-line breaks survive as a marker word so a line
    # value stops at the end of its PDF text line ("line 5 - TNOE\nBalance of the wafer ...").
    section_norm = re.sub(r"\s*\n\s*", f" {_NL} ", section_raw.strip())
    section_norm = re.sub(r"\s+", " ", section_norm).strip()

    # 4. Split section into sentences ((?<=[.;])\s+)
    sentences = [s.strip() for s in re.split(r"(?<=[.;])\s+", section_norm) if s.strip()]

    raw_instructions: dict[tuple[Side, int], list[tuple[str, str]]] = {}
    unresolved: list[str] = []
    pointer_sentences: list[str] = []
    current_side = Side.TOP

    for sentence in sentences:
        broken = sentence
        sentence = _without_breaks(sentence)
        if not sentence:
            continue
        produced_instruction = False
        for om in ORDINAL_LINE_RE.finditer(broken):
            value = _ordinal_value(broken[om.end():].split(_NL)[0])
            if value:
                quote = f"{om.group(0).strip()} {value}"
                raw_instructions.setdefault((current_side, _ORDINALS[om.group(1).lower()]), []).append((value, quote))
                produced_instruction = True
        matches = list(LINE_HEADER_RE.finditer(broken))
        i = 0
        while i < len(matches):
            m = matches[i]
            if m.group(1):
                current_side = Side.BOTTOM if m.group(1).upper() == "BOTTOM" else Side.TOP
                i += 1
                continue

            line_no = int(m.group(2))
            rest = broken[m.end():]
            while rest.lstrip().startswith(_NL):
                rest = rest.lstrip()[1:]

            # If rest immediately starts with another line instruction or 'as follows'
            if re.match(r"^\s*(?:as follows:?|line\s*\d)", rest, re.IGNORECASE) or not rest.strip():
                i += 1
                continue

            toks: list[str] = []
            for word in rest.split():
                if word == _NL:
                    if toks:
                        break
                    continue
                if SLR_STOP.match(word) or re.match(r"^[a-z]", word):
                    break
                cleaned = word.rstrip(".,;")
                if not cleaned:
                    break
                toks.append(cleaned)
                if word.endswith((".", ";")):
                    break

            if toks:
                val = " ".join(toks)
                quote = f"{m.group(0).strip()} {val}".strip()
                raw_instructions.setdefault((current_side, line_no), []).append((val, quote))
                produced_instruction = True

            i += 1

        if not produced_instruction:
            if SAME_DATE_CODE_NOTE_RE.match(sentence):
                continue
            if POINTER_SENTENCE_RE.match(sentence):
                pointer_sentences.append(sentence)
                continue
            if MARKING_KEYWORDS_RE.search(sentence):
                # Sentence is marking-related; check if it is only a qual-lot announcement
                without_qual = re.sub(
                    r"qual\s+lot\s+\d+\s+of\s+\d+", "", sentence, flags=re.IGNORECASE
                )
                if MARKING_KEYWORDS_RE.search(without_qual):
                    if sentence not in unresolved:
                        unresolved.append(sentence)

    if not raw_instructions:
        unresolved.extend(s for s in pointer_sentences if s not in unresolved)

    instructions: list[SlrInstruction] = []
    for (side, line_no), val_quotes in raw_instructions.items():
        unique_vals: list[str] = []
        quotes: list[str] = []
        for val, quote in val_quotes:
            if val not in unique_vals:
                unique_vals.append(val)
            quotes.append(quote)

        if len(unique_vals) == 1:
            instructions.append(
                SlrInstruction(
                    side=side,
                    line_no=line_no,
                    value=unique_vals[0],
                    quote=" ; ".join(quotes),
                    alternatives=(),
                )
            )
        else:
            instructions.append(
                SlrInstruction(
                    side=side,
                    line_no=line_no,
                    value=None,
                    quote=" ; ".join(quotes),
                    alternatives=tuple(unique_vals),
                )
            )

    return SlrFacts(
        text=norm_text,
        instructions=tuple(instructions),
        scheduled_lots=tuple(scheduled_lots),
        qual_lot=qual_lot,
        unresolved=tuple(unresolved),
    )
