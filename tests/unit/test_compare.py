from __future__ import annotations

import copy
from mark_engine.compare.engine import compare, nospace
from mark_engine.compare.lot import match_lot
from mark_engine.compare.shift import match_shift
from mark_engine.domain.models import (
    ElrMeta,
    ExpectedLine,
    ExpectedMark,
    ExpectedToken,
    Flag,
    LineComparison,
    LineStatus,
    OracleMark,
    Side,
    SlrFacts,
)
from mark_engine.rules.ruleset import RuleSet


def _make_expected(
    lines: tuple[ExpectedLine, ...],
    elr_no: str = "ADI2601001",
) -> ExpectedMark:
    return ExpectedMark(
        elr_no=elr_no,
        lines=lines,
        rule_version="RV-2026-11-04-R0",
        engine_version="0.1.0",
    )


def _make_oracle(
    lines: tuple[tuple[Side, int, str], ...],
    elr_no: str = "ADI2601001",
) -> OracleMark:
    return OracleMark(elr_no=elr_no, lines=lines)


def _make_slr(
    text: str = "",
    scheduled_lots: tuple[str, ...] = (),
) -> SlrFacts:
    return SlrFacts(
        text=text,
        scheduled_lots=scheduled_lots,
    )


def _make_meta(
    import_date: str | None = "2026-03-15",
    elr_no: str = "ADI2601001",
) -> ElrMeta:
    return ElrMeta(elr_no=elr_no, import_date=import_date)


def test_exact_match() -> None:
    expected_line = ExpectedLine(side=Side.TOP, line_no=1, text="ABC DEF")
    expected = _make_expected((expected_line,))
    oracle = _make_oracle(((Side.TOP, 1, "ABC  DEF"),))
    slr = _make_slr()
    meta = _make_meta()

    results = compare(expected, oracle, slr, meta)
    assert len(results) == 1
    comp = results[0]
    assert comp.side == Side.TOP
    assert comp.line_no == 1
    assert comp.status == LineStatus.MATCH
    assert comp.compare_rules == ("EXACT",)
    assert comp.detail == ""


def test_graphics_count() -> None:
    expected_line = ExpectedLine(side=Side.TOP, line_no=1, text="@% ADW")
    expected = _make_expected((expected_line,))
    oracle = _make_oracle(((Side.TOP, 1, "% ADW"),))
    slr = _make_slr()
    meta = _make_meta()

    results = compare(expected, oracle, slr, meta)
    assert len(results) == 1
    comp = results[0]
    assert comp.status == LineStatus.DIFF
    assert comp.compare_rules == ()


def test_match_slr() -> None:
    expected_line = ExpectedLine(
        side=Side.TOP,
        line_no=1,
        text="SLR_VAL",
        flags=frozenset({Flag.SLR_OVERRIDE}),
    )
    expected = _make_expected((expected_line,))
    oracle = _make_oracle(((Side.TOP, 1, "SLR_VAL"),))
    slr = _make_slr()
    meta = _make_meta()

    results = compare(expected, oracle, slr, meta)
    assert len(results) == 1
    comp = results[0]
    assert comp.status == LineStatus.MATCH_SLR
    assert comp.compare_rules == ("R04-SLR-LINE",)


def test_lot_digits_in_slr_match_lot() -> None:
    tok = ExpectedToken(
        text="XXXXX",
        rule_id="R07-ADI1039-LOT",
        source="ADI1039",
        lot_slice="last-5",
    )
    expected_line = ExpectedLine(
        side=Side.TOP,
        line_no=1,
        text="BXXXXX",
        tokens=(tok,),
    )
    expected = _make_expected((expected_line,))
    oracle = _make_oracle(((Side.TOP, 1, "B28558"),))
    slr = _make_slr(scheduled_lots=("7228558",))
    meta = _make_meta(import_date="2026-03-15")

    results = compare(expected, oracle, slr, meta)
    assert len(results) == 1
    comp = results[0]
    assert comp.status == LineStatus.MATCH_LOT
    assert comp.compare_rules == ("R07-PLACEHOLDER", "R04-SLR-LOT")


def test_lot_digits_not_in_slr_needs_review() -> None:
    tok = ExpectedToken(
        text="XXXXX",
        rule_id="R07-ADI1039-LOT",
        source="ADI1039",
        lot_slice="last-5",
    )
    expected_line = ExpectedLine(
        side=Side.TOP,
        line_no=1,
        text="BXXXXX",
        tokens=(tok,),
    )
    expected = _make_expected((expected_line,))
    oracle = _make_oracle(((Side.TOP, 1, "B28558"),))
    slr = _make_slr(scheduled_lots=("9999999",))  # 28558 does NOT match
    meta = _make_meta(import_date="2026-03-15")

    results = compare(expected, oracle, slr, meta)
    assert len(results) == 1
    comp = results[0]
    assert comp.status != LineStatus.MATCH_LOT
    assert comp.status == LineStatus.DIFF


def test_bad_week_not_match_lot() -> None:
    tok = ExpectedToken(
        text="YYWW",
        rule_id="R07-ADI1039",
        source="ADI1039",
    )
    expected_line = ExpectedLine(
        side=Side.TOP,
        line_no=1,
        text="YYWW",
        tokens=(tok,),
    )
    expected = _make_expected((expected_line,))
    oracle = _make_oracle(((Side.TOP, 1, "2660"),))  # week 60 is invalid
    slr = _make_slr()
    meta = _make_meta(import_date="2026-03-15")

    results = compare(expected, oracle, slr, meta)
    assert len(results) == 1
    comp = results[0]
    assert comp.status != LineStatus.MATCH_LOT
    assert comp.status == LineStatus.DIFF


def test_shift_side() -> None:
    # Side TOP: ABS L1 is "@ ADW", L2 is "LINE2"
    # DB MARK1 is "@", MARK2 is "ADW", MARK3 is "LINE2"
    exp_l1 = ExpectedLine(side=Side.TOP, line_no=1, text="@ ADW")
    exp_l2 = ExpectedLine(side=Side.TOP, line_no=2, text="LINE2")
    expected = _make_expected((exp_l1, exp_l2))

    oracle = _make_oracle((
        (Side.TOP, 1, "@"),
        (Side.TOP, 2, "ADW"),
        (Side.TOP, 3, "LINE2"),
    ))
    slr = _make_slr()
    meta = _make_meta()

    results = compare(expected, oracle, slr, meta)
    top_results = [r for r in results if r.side == Side.TOP]
    assert len(top_results) == 3
    for comp in top_results:
        assert comp.status == LineStatus.MATCH_SHIFT
        assert comp.compare_rules == ("R06-SHIFT",)


def test_oracle_value_in_slr_needs_review() -> None:
    expected_line = ExpectedLine(side=Side.TOP, line_no=1, text="EXP_VAL")
    expected = _make_expected((expected_line,))
    oracle = _make_oracle(((Side.TOP, 1, "SPECIAL123"),))
    slr = _make_slr(text="Please ensure SPECIAL123 is engraved on line 1.")
    meta = _make_meta()

    results = compare(expected, oracle, slr, meta)
    assert len(results) == 1
    comp = results[0]
    assert comp.status == LineStatus.NEEDS_REVIEW
    assert comp.detail == "ORACLE_VALUE_IN_SLR"
    assert comp.compare_rules == ("ORACLE_VALUE_IN_SLR",)


def test_flagged_line_needs_review_even_if_equal() -> None:
    expected_line = ExpectedLine(
        side=Side.TOP,
        line_no=1,
        text="MATCHING_TEXT",
        flags=frozenset({Flag.UNMAPPED_TOKEN}),
    )
    expected = _make_expected((expected_line,))
    oracle = _make_oracle(((Side.TOP, 1, "MATCHING_TEXT"),))
    slr = _make_slr()
    meta = _make_meta()

    results = compare(expected, oracle, slr, meta)
    assert len(results) == 1
    comp = results[0]
    assert comp.status == LineStatus.NEEDS_REVIEW
    assert "UNMAPPED_TOKEN" in comp.detail
    assert comp.compare_rules == ()


def test_compare_does_not_mutate_expected() -> None:
    expected_line = ExpectedLine(
        side=Side.TOP,
        line_no=1,
        text="ORIGINAL",
        flags=frozenset({Flag.SLR_OVERRIDE}),
    )
    expected = _make_expected((expected_line,))
    expected_snapshot = copy.deepcopy(expected)
    oracle = _make_oracle(((Side.TOP, 1, "ORIGINAL"),))
    slr = _make_slr()
    meta = _make_meta()

    _ = compare(expected, oracle, slr, meta)
    assert expected == expected_snapshot


def test_db_empty() -> None:
    expected_line = ExpectedLine(side=Side.TOP, line_no=1, text="SOME_TEXT")
    expected = _make_expected((expected_line,))
    oracle = _make_oracle(((Side.TOP, 1, ""),))
    slr = _make_slr()
    meta = _make_meta()

    results = compare(expected, oracle, slr, meta)
    assert len(results) == 1
    comp = results[0]
    assert comp.status == LineStatus.DB_EMPTY
    assert comp.detail == "oracle empty"
    assert comp.compare_rules == ()


def test_db_lot_is_package() -> None:
    tok = ExpectedToken(
        text="XXXXX",
        rule_id="R07-ADI1039-LOT",
        source="ADI1039",
        lot_slice="last-5",
    )
    expected_line = ExpectedLine(
        side=Side.TOP,
        line_no=1,
        text="BXXXXX",
        tokens=(tok,),
    )
    expected = _make_expected((expected_line,))
    oracle = _make_oracle(((Side.TOP, 1, "BTSSOP"),))
    slr = _make_slr(scheduled_lots=("7228558",))
    meta = _make_meta()

    results = compare(expected, oracle, slr, meta)
    assert len(results) == 1
    comp = results[0]
    assert comp.status == LineStatus.DIFF
    assert comp.detail == "DB_LOT_IS_PACKAGE"
    assert comp.compare_rules == ("R07-DB-PACKAGE",)


def test_serial_not_verifiable() -> None:
    tok = ExpectedToken(
        text="XXXX",
        rule_id="R07-OCRFIX-8",
        source="OCR_FIX",
    )
    expected_line = ExpectedLine(
        side=Side.TOP,
        line_no=1,
        text="XXXX",
        tokens=(tok,),
    )
    expected = _make_expected((expected_line,))
    oracle = _make_oracle(((Side.TOP, 1, "1234"),))
    slr = _make_slr()
    meta = _make_meta()

    results = compare(expected, oracle, slr, meta)
    assert len(results) == 1
    comp = results[0]
    assert comp.status == LineStatus.NEEDS_REVIEW
    assert comp.detail == "SERIAL_NOT_VERIFIABLE"
    assert comp.compare_rules == ("R07-OCRFIX-8",)


def test_both_empty_skipped() -> None:
    expected_line = ExpectedLine(side=Side.TOP, line_no=1, text="")
    expected = _make_expected((expected_line,))
    oracle = _make_oracle(((Side.TOP, 1, ""),))
    slr = _make_slr()
    meta = _make_meta()

    results = compare(expected, oracle, slr, meta)
    assert len(results) == 0
