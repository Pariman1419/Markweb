from mark_engine.domain.models import (
    DocumentResolution,
    ElrMeta,
    Flag,
    InferenceResult,
    LayoutLine,
    Side,
    SlrFacts,
    SlrInstruction,
)
from mark_engine.generate.generator import generate_expected
from mark_engine.rules.ruleset import RuleSet


def _rules() -> RuleSet:
    return RuleSet.load()


def test_abs_only_line():
    meta = ElrMeta(elr_no="ADI2601001")
    docs = DocumentResolution(elr_no="ADI2601001", decision="RESOLVED")
    slr = SlrFacts(text="")
    inference = InferenceResult(
        elr_no="ADI2601001",
        lines=(LayoutLine(side=Side.TOP, line_no=1, text="{LOGO} ADW", graphics=""),),
    )
    expected = generate_expected(meta, docs, slr, inference, _rules())

    line = expected.line(Side.TOP, 1)
    assert line is not None
    assert line.text == "* ADW"


def test_graphics_prefixed():
    meta = ElrMeta(elr_no="ADI2601002")
    docs = DocumentResolution(elr_no="ADI2601002", decision="RESOLVED")
    slr = SlrFacts(text="")
    inference = InferenceResult(
        elr_no="ADI2601002",
        lines=(LayoutLine(side=Side.TOP, line_no=1, text="ADW", graphics="@%"),),
    )
    expected = generate_expected(meta, docs, slr, inference, _rules())

    line = expected.line(Side.TOP, 1)
    assert line is not None
    assert line.text == "@% ADW"


def test_caret_remark_no_pin():
    meta = ElrMeta(elr_no="ADI2601003", mark_remark="^ = ADI logo")
    docs = DocumentResolution(elr_no="ADI2601003", decision="RESOLVED")
    slr = SlrFacts(text="")
    inference = InferenceResult(
        elr_no="ADI2601003",
        lines=(LayoutLine(side=Side.TOP, line_no=1, text="ADW", graphics="@%"),),
    )
    expected = generate_expected(meta, docs, slr, inference, _rules())

    line = expected.line(Side.TOP, 1)
    assert line is not None
    assert line.text is not None and line.text.startswith("^")
    assert Flag.GRAPHIC_REMARK_CONFLICT in line.flags


def test_slr_overrides_text():
    meta = ElrMeta(elr_no="ADI2601004")
    docs = DocumentResolution(elr_no="ADI2601004", decision="RESOLVED")
    slr = SlrFacts(
        text="Line 2: Q1",
        instructions=(
            SlrInstruction(side=Side.TOP, line_no=2, value="Q1"),
        ),
    )
    inference = InferenceResult(
        elr_no="ADI2601004",
        lines=(
            LayoutLine(side=Side.TOP, line_no=1, text="LINE1", graphics=""),
            LayoutLine(side=Side.TOP, line_no=2, text="OLD_LINE2", graphics=""),
        ),
    )
    expected = generate_expected(meta, docs, slr, inference, _rules())

    line2 = expected.line(Side.TOP, 2)
    assert line2 is not None
    assert line2.text == "Q1"
    assert Flag.SLR_OVERRIDE in line2.flags


def test_slr_tokens_render_placeholders():
    meta = ElrMeta(elr_no="ADI2601005")
    docs = DocumentResolution(elr_no="ADI2601005", decision="RESOLVED")
    slr = SlrFacts(
        text="Line 1: {Lot-4}",
        instructions=(
            SlrInstruction(side=Side.TOP, line_no=1, value="{Lot-4}"),
        ),
    )
    inference = InferenceResult(
        elr_no="ADI2601005",
        lines=(LayoutLine(side=Side.TOP, line_no=1, text="ORIGINAL", graphics=""),),
    )
    expected = generate_expected(meta, docs, slr, inference, _rules())

    line = expected.line(Side.TOP, 1)
    assert line is not None
    assert line.text == "XXXX"
    matching = [t for t in line.tokens if t.text == "XXXX" and t.lot_slice == "last-4"]
    assert len(matching) == 1


def test_unresolved_sentence_flags_all_lines():
    meta = ElrMeta(elr_no="ADI2601006")
    docs = DocumentResolution(elr_no="ADI2601006", decision="RESOLVED")
    slr = SlrFacts(
        text="Please brand per attachment.",
        unresolved=("check attachment",),
    )
    inference = InferenceResult(
        elr_no="ADI2601006",
        lines=(
            LayoutLine(side=Side.TOP, line_no=1, text="AAA", graphics=""),
            LayoutLine(side=Side.TOP, line_no=2, text="BBB", graphics=""),
        ),
    )
    expected = generate_expected(meta, docs, slr, inference, _rules())

    assert len(expected.lines) == 2
    for line in expected.lines:
        assert Flag.SLR_UNRESOLVED in line.flags


def test_slr_only_line_created():
    meta = ElrMeta(elr_no="ADI2601007")
    docs = DocumentResolution(elr_no="ADI2601007", decision="RESOLVED")
    slr = SlrFacts(
        text="Line 2: NEWLINE",
        instructions=(
            SlrInstruction(side=Side.TOP, line_no=2, value="NEWLINE"),
        ),
    )
    inference = InferenceResult(
        elr_no="ADI2601007",
        lines=(
            LayoutLine(side=Side.TOP, line_no=1, text="LINE1", graphics=""),
        ),
    )
    expected = generate_expected(meta, docs, slr, inference, _rules())

    line2 = expected.line(Side.TOP, 2)
    assert line2 is not None
    assert line2.text == "NEWLINE"
    assert Flag.SLR_OVERRIDE in line2.flags


def test_slr_ambiguous_keeps_text_and_flags():
    meta = ElrMeta(elr_no="ADI2601008")
    docs = DocumentResolution(elr_no="ADI2601008", decision="RESOLVED")
    slr = SlrFacts(
        text="Line 1 ambiguous",
        instructions=(
            SlrInstruction(side=Side.TOP, line_no=1, value=None),
        ),
    )
    inference = InferenceResult(
        elr_no="ADI2601008",
        lines=(
            LayoutLine(side=Side.TOP, line_no=1, text="EXISTING", graphics=""),
        ),
    )
    expected = generate_expected(meta, docs, slr, inference, _rules())

    line1 = expected.line(Side.TOP, 1)
    assert line1 is not None
    assert line1.text == "EXISTING"
    assert Flag.SLR_AMBIGUOUS in line1.flags
    assert Flag.SLR_OVERRIDE not in line1.flags


def test_unmapped_token_flag():
    meta = ElrMeta(elr_no="ADI2601009")
    docs = DocumentResolution(elr_no="ADI2601009", decision="RESOLVED")
    slr = SlrFacts(text="")
    inference = InferenceResult(
        elr_no="ADI2601009",
        lines=(
            LayoutLine(side=Side.TOP, line_no=1, text="{UNKNOWN_XYZ} ADW", graphics=""),
        ),
    )
    expected = generate_expected(meta, docs, slr, inference, _rules())

    line1 = expected.line(Side.TOP, 1)
    assert line1 is not None
    assert Flag.UNMAPPED_TOKEN in line1.flags


def test_remark_declares_logo_yolo_missing():
    meta = ElrMeta(elr_no="ADI2601010", mark_remark="% = ADI logo")
    docs = DocumentResolution(elr_no="ADI2601010", decision="RESOLVED")
    slr = SlrFacts(text="")
    # YOLO only saw pin dot '@', no logo '%' or '{'
    inference = InferenceResult(
        elr_no="ADI2601010",
        lines=(
            LayoutLine(side=Side.TOP, line_no=1, text="ADW", graphics="@"),
        ),
    )
    expected = generate_expected(meta, docs, slr, inference, _rules())

    line1 = expected.line(Side.TOP, 1)
    assert line1 is not None
    assert Flag.GRAPHIC_REMARK_CONFLICT in line1.flags


def test_revision_name_mismatch_flag():
    meta = ElrMeta(elr_no="ADI2601011")
    docs = DocumentResolution(
        elr_no="ADI2601011",
        decision="RESOLVED",
        steps=("REVISION_NAME_MISMATCH",),
    )
    slr = SlrFacts(text="")
    inference = InferenceResult(
        elr_no="ADI2601011",
        lines=(
            LayoutLine(side=Side.TOP, line_no=1, text="ADW", graphics=""),
        ),
    )
    expected = generate_expected(meta, docs, slr, inference, _rules())

    line1 = expected.line(Side.TOP, 1)
    assert line1 is not None
    assert Flag.RULE_CONFLICT in line1.flags


def test_expected_versions_and_line_ordering():
    meta = ElrMeta(elr_no="ADI2601012")
    docs = DocumentResolution(elr_no="ADI2601012", decision="RESOLVED")
    slr = SlrFacts(
        text="",
        instructions=(
            SlrInstruction(side=Side.BOTTOM, line_no=1, value="BOT1"),
        ),
    )
    inference = InferenceResult(
        elr_no="ADI2601012",
        lines=(
            LayoutLine(side=Side.TOP, line_no=2, text="TOP2", graphics=""),
            LayoutLine(side=Side.TOP, line_no=1, text="TOP1", graphics=""),
        ),
    )
    rules = _rules()
    expected = generate_expected(meta, docs, slr, inference, rules)

    assert expected.rule_version == rules.version
    assert expected.engine_version == "0.1.0"
    assert len(expected.lines) == 3
    # Check sorting: TOP 1, TOP 2, BOTTOM 1
    assert expected.lines[0].side == Side.TOP and expected.lines[0].line_no == 1
    assert expected.lines[1].side == Side.TOP and expected.lines[1].line_no == 2
    assert expected.lines[2].side == Side.BOTTOM and expected.lines[2].line_no == 1



def _gen(remark: str, lines: tuple) -> "ExpectedMark":
    meta = ElrMeta(elr_no="ADI2601099", mark_remark=remark)
    docs = DocumentResolution(elr_no="ADI2601099", decision="RESOLVED")
    return generate_expected(meta, docs, SlrFacts(text=""), InferenceResult(elr_no="ADI2601099", lines=lines), _rules())


def test_logo_in_ocr_text_is_not_conflict():
    """'* = LTC LOGO': the logo comes from the drawing text ({LTC-PARTIAL-LOGO} -> *), not YOLO (ADI2601010)."""
    exp = _gen("* = LTC LOGO , YWW = DATE CODE", (
        LayoutLine(side=Side.TOP, line_no=1, text="LTC", graphics=""),
        LayoutLine(side=Side.TOP, line_no=2, text="{LTC-PARTIAL-LOGO} YWW", graphics=""),
    ))
    assert all(Flag.GRAPHIC_REMARK_CONFLICT not in l.flags for l in exp.lines)


def test_logo_on_top_does_not_flag_bottom_lines():
    """MARK_REMARK declares symbols for the part, not per side; bottom mark normally has no logo."""
    exp = _gen("@ = PIN ONE DOT, % = ADI LOGO", (
        LayoutLine(side=Side.TOP, line_no=1, text="ADW", graphics="@%"),
        LayoutLine(side=Side.BOTTOM, line_no=1, text="XXXXXXXXX", graphics=""),
    ))
    assert all(Flag.GRAPHIC_REMARK_CONFLICT not in l.flags for l in exp.lines)


def test_caret_logo_from_yolo_counts_as_logo():
    exp = _gen("^ = ADI LOGO", (LayoutLine(side=Side.TOP, line_no=1, text="ADW", graphics="%"),))
    assert Flag.GRAPHIC_REMARK_CONFLICT not in exp.line(Side.TOP, 1).flags


def test_logo_declared_but_absent_everywhere_flags_all_lines():
    exp = _gen("% = ADI LOGO", (
        LayoutLine(side=Side.TOP, line_no=1, text="ADW", graphics="@"),
        LayoutLine(side=Side.BOTTOM, line_no=1, text="XXXXXXXXX", graphics=""),
    ))
    assert all(Flag.GRAPHIC_REMARK_CONFLICT in l.flags for l in exp.lines)


def test_pbfree_code_follows_remark_e3():
    """MARK_REMARK 'e3 = Pb-free identification' (ADI2603063): Oracle code is 'e3', not '<' (OCRFIX-5 default)."""
    exp = _gen("YWXX = AUTO GENERATE BY SYSTEM | * = LTC Logo, e3 = Pb- free identification",
               (LayoutLine(side=Side.TOP, line_no=3, text="{e3}", graphics=""),))
    assert exp.line(Side.TOP, 3).text == "e3"


def test_pbfree_code_default_lt_when_remark_declares_lt():
    exp = _gen("YYWW = AUTO GENERATE BY SYSTEM | * = LTC LOGO , < = PB-FREE IDENTIFIED(e3)",
               (LayoutLine(side=Side.TOP, line_no=3, text="{e3}", graphics=""),))
    assert exp.line(Side.TOP, 3).text == "<"
