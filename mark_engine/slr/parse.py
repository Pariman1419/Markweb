import re
from mark_engine.domain.models import Side, SlrFacts, SlrInstruction


def parse_slr(text: str) -> SlrFacts:
    """Parse SLR text for special instructions, line markings, and scheduled lots."""
    norm_text = text.replace("‐", "-")

    sec_match = re.search(
        r"SPECIAL INSTRUCTIONS\s*([\s\S]*?)(?:\nANALOG\s+DEVICES|\nASSEMBLY LOT|\Z)",
        norm_text,
        re.IGNORECASE,
    )
    section_text = sec_match.group(1).strip() if sec_match else norm_text

    instructions: list[SlrInstruction] = []

    # Pattern matching line instructions e.g.:
    # "Line 1: ...", "Line Mark 2 - Q1", "TOP Line 1 ...", "BOTTOM Line 1 ..."
    line_pattern = re.compile(
        r"(?:(TOP|BOTTOM)\s+)?Line\s+(?:Mark\s+)?(\d+)[:\s\-]+([^\n\r]+)",
        re.IGNORECASE,
    )
    for m in line_pattern.finditer(section_text):
        side_str = m.group(1)
        side = Side.BOTTOM if side_str and side_str.upper() == "BOTTOM" else Side.TOP
        line_no = int(m.group(2))
        val = m.group(3).strip()
        instructions.append(
            SlrInstruction(
                side=side,
                line_no=line_no,
                value=val,
                quote=m.group(0),
            )
        )

    scheduled_lots: list[str] = []
    lot_sec = re.search(
        r"Scheduled Lot ID\s*([\s\S]*?)(?:\n[A-Z]{3,}|\Z)", norm_text, re.IGNORECASE
    )
    if lot_sec:
        for lot_m in re.finditer(r"\b(\d{6,8})\.\d+", lot_sec.group(1)):
            scheduled_lots.append(lot_m.group(1))

    return SlrFacts(
        text=norm_text,
        instructions=tuple(instructions),
        scheduled_lots=tuple(scheduled_lots),
    )
