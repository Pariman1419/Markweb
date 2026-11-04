import pytest
from mark_engine.domain.models import Side
from mark_engine.slr.parse import parse_slr


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Line Mark 2 - Q1", [(Side.TOP, 2, "Q1")]),
        (
            "BOTTOM Line 1 {Pb-Free}{DC-3} Line 2 {Lot-4}",
            [
                (Side.BOTTOM, 1, "{Pb-Free}{DC-3}"),
                (Side.BOTTOM, 2, "{Lot-4}"),
            ],
        ),
        ("brand line 1 as follows: Line 1 EB{1-DC}", [(Side.TOP, 1, "EB{1-DC}")]),
        ("change line 2 to 8892W-U2C", [(Side.TOP, 2, "8892W-U2C")]),
        ("Line 3: QDOSVD", [(Side.TOP, 3, "QDOSVD")]),
        ("TOP Line 1 Y Line 2 Q1", [(Side.TOP, 1, "Y"), (Side.TOP, 2, "Q1")]),
        ("Line 3 - ENGG", [(Side.TOP, 3, "ENGG")]),
        ("line 3 to ENGE", [(Side.TOP, 3, "ENGE")]),
    ],
)
def test_slr_line_instruction_forms(text: str, expected: list[tuple[Side, int, str]]) -> None:
    facts = parse_slr(text)
    actual = [(i.side, i.line_no, i.value) for i in facts.instructions]
    assert actual == expected


def test_conflicting_line_values_ambiguous() -> None:
    text = "Line 2 - AAA\nLine 2 - BBB"
    facts = parse_slr(text)
    assert len(facts.instructions) == 1
    instr = facts.instructions[0]
    assert instr.side == Side.TOP
    assert instr.line_no == 2
    assert instr.value is None
    assert instr.alternatives == ("AAA", "BBB")


def test_duplicate_identical_line_values_not_ambiguous() -> None:
    text = "Line 2 - AAA\nLine 2 - AAA"
    facts = parse_slr(text)
    assert len(facts.instructions) == 1
    instr = facts.instructions[0]
    assert instr.side == Side.TOP
    assert instr.line_no == 2
    assert instr.value == "AAA"
    assert instr.alternatives == ()


def test_scheduled_lots() -> None:
    text = "Scheduled Lot ID\n7346019.1\n7346020.2\n"
    facts = parse_slr(text)
    assert facts.scheduled_lots == ("7346019", "7346020")


def test_follow_attachment_unresolved() -> None:
    text = "Please brand per attachment."
    facts = parse_slr(text)
    assert "Please brand per attachment." in facts.unresolved


def test_unicode_hyphen() -> None:
    text = "Line 3 ‐ ENGG"
    facts = parse_slr(text)
    assert len(facts.instructions) == 1
    assert facts.instructions[0].value == "ENGG"


def test_qual_lot_is_not_instruction() -> None:
    text = "Qual lot 1 of 4"
    facts = parse_slr(text)
    assert facts.qual_lot == (1, 4)
    assert len(facts.instructions) == 0
    assert len(facts.unresolved) == 0


def test_special_instructions_section_full_flow() -> None:
    text = """
HEADER INFO
SPECIAL INSTRUCTIONS
Line 1: TOPVAL.
Please brand per attachment.
ANALOG
DEVICES
Scheduled Lot ID
7346019.1
7346020.2
"""
    facts = parse_slr(text)
    assert [(i.side, i.line_no, i.value) for i in facts.instructions] == [(Side.TOP, 1, "TOPVAL")]
    assert "Please brand per attachment." in facts.unresolved
    assert facts.scheduled_lots == ("7346019", "7346020")


# Coverage must flag only sentences about the mark itself. Real Jan-Jun SLR sentences that
# mention "lot" for wafer / fab / logistics reasons are not marking instructions (R1 triage:
# 803 SLR_UNRESOLVED lines, 689 of them already equal to Oracle).
import pytest  # noqa: E402


@pytest.mark.parametrize(
    "sentence",
    [
        "ANALOG DEVICES SPECIAL LOT REQUEST SLR231445 SLR231445 All information in this request is proprietary to ANALOG DEVICES INC.",
        "This is an IB Lot.",
        "Fab Lot ID: P64937.00 Wafer #: 2;",
        "Please use fab lot Q67740.3 Wafer #5 for this build.",
        "LT4356 - Mold compound change control lot",
        "Use Lot#/W# as instructed below.",
        "Data gathering is required (pls see attachment).",
        "The old and new IPD dies have the same die ID (S7_2g TC24.5 (2 lines)), so please use the new die.",
    ],
)
def test_logistics_lot_sentences_not_unresolved(sentence: str) -> None:
    assert parse_slr(sentence).unresolved == ()


@pytest.mark.parametrize(
    "sentence",
    [
        "Same date code with: SLR230991, SLR230992, SLR230993",
        'Second line of brand content / marking: "LS1234v00" BEF Promis notes: 7.1 is costing off.',
        "See attachment for further instructions.",
        "Laser mark lot number on top side.",
    ],
)
def test_marking_sentences_still_unresolved(sentence: str) -> None:
    assert parse_slr(sentence).unresolved != ()
