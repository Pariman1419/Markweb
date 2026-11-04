import pytest
from mark_engine.regression.parity import classify


@pytest.mark.parametrize(
    "r1_row, r0_row, r0legacy_row, expected_reason",
    [
        # SAME: same status, same text
        (
            {"status": "MATCH", "expected_mark": "ADW", "elr_no": "ADI2601001", "side": "TOP", "line_no": 1},
            {"status": "MATCH", "final_mark": "ADW", "cause": "OK"},
            None,
            "SAME",
        ),
        # SAME: both non-eligible
        (
            {"status": "NOT_ELIGIBLE", "expected_mark": "", "elr_no": "ADI2601002", "side": "TOP", "line_no": 1},
            {"status": "NOT_ELIGIBLE", "final_mark": "", "cause": "TYPE_CODE_NOT_E"},
            None,
            "SAME",
        ),
        # REVIEW_FLAG: R1 is NEEDS_REVIEW
        (
            {"status": "NEEDS_REVIEW", "expected_mark": "ADW", "elr_no": "ADI2601003", "side": "TOP", "line_no": 1},
            {"status": "MATCH", "final_mark": "ADW", "cause": "OK"},
            None,
            "REVIEW_FLAG",
        ),
        # GATE_SPEC_V2: R1 is HOLD: SLR_NOT_FOUND, but R0 was measurable
        (
            {
                "status": "NOT_MEASURABLE",
                "hold_reason": "SLR_NOT_FOUND",
                "detail": "SLR_NOT_FOUND",
                "expected_mark": "",
                "elr_no": "ADI2601004",
                "side": "TOP",
                "line_no": 1,
            },
            {"status": "MATCH", "final_mark": "ADW", "cause": "OK"},
            None,
            "GATE_SPEC_V2",
        ),
        # RESOLVER_CHANGED: R0 is None (ELR not in R0)
        (
            {"status": "MATCH", "expected_mark": "ADW", "elr_no": "ADI2604099", "side": "TOP", "line_no": 1},
            None,
            None,
            "RESOLVER_CHANGED",
        ),
        # RESOLVER_CHANGED: different ABS selected
        (
            {
                "status": "MATCH",
                "expected_mark": "ADW",
                "abs_no": "ABS069999",
                "elr_no": "ADI2601005",
                "side": "TOP",
                "line_no": 1,
            },
            {"status": "MATCH", "final_mark": "ADW", "abs_no": "ABS068888", "cause": "OK"},
            None,
            "RESOLVER_CHANGED",
        ),
        # RESOLVER_CHANGED: ELR measurable status differs (R1 HOLD, R0 MATCH)
        (
            {
                "status": "NOT_MEASURABLE",
                "hold_reason": "ABS_NOT_FOUND",
                "expected_mark": "",
                "elr_no": "ADI2601006",
                "side": "TOP",
                "line_no": 1,
            },
            {"status": "MATCH", "final_mark": "ADW", "cause": "OK"},
            None,
            "RESOLVER_CHANGED",
        ),
        # OCR_SOURCE_CHANGED: Jan-Apr row from ocr_reocr.csv
        (
            {"status": "DIFF", "expected_mark": "@% SAD", "elr_no": "ADI2604053", "side": "TOP", "line_no": 1, "r0_reocr": "Y"},
            {"status": "MATCH", "final_mark": "@% ADW", "cause": "GRAPHIC_SYMBOL", "month": "4_APR"},
            None,
            "OCR_SOURCE_CHANGED",
        ),
        # LOT_NOW_VERIFIED: R0 status MATCH_LOT
        (
            {"status": "DIFF", "expected_mark": "0433", "elr_no": "ADI2601027", "side": "BOTTOM", "line_no": 2},
            {"status": "MATCH_LOT", "final_mark": "0433", "cause": "PLACEHOLDER_vs_LITERAL"},
            None,
            "LOT_NOW_VERIFIED",
        ),
        # ORACLE_INFLUENCE_REMOVED: R0 cause SLR_OVERRIDE
        (
            {"status": "DIFF", "expected_mark": "ABC", "elr_no": "ADI2601007", "side": "TOP", "line_no": 1},
            {"status": "MATCH_SLR", "final_mark": "XYZ", "cause": "SLR_OVERRIDE"},
            None,
            "ORACLE_INFLUENCE_REMOVED",
        ),
        # ORACLE_INFLUENCE_REMOVED: R0 cause GRAPHIC_ONLY_LINE
        (
            {"status": "DIFF", "expected_mark": "%", "elr_no": "ADI2601008", "side": "TOP", "line_no": 1},
            {"status": "MATCH", "final_mark": "@%", "cause": "GRAPHIC_ONLY_LINE"},
            None,
            "ORACLE_INFLUENCE_REMOVED",
        ),
        # ORACLE_INFLUENCE_REMOVED: R0 cause LINE_SHIFT
        (
            {"status": "DIFF", "expected_mark": "LINE1", "elr_no": "ADI2601009", "side": "TOP", "line_no": 1},
            {"status": "MATCH_SHIFT", "final_mark": "LINE1", "cause": "LINE_SHIFT"},
            None,
            "ORACLE_INFLUENCE_REMOVED",
        ),
        # GRAPHIC_NOW_COUNTED: R0 cause GRAPHIC_SYMBOL (where not SAME)
        (
            {"status": "DIFF", "expected_mark": "@% ADW", "elr_no": "ADI2601010", "side": "TOP", "line_no": 1},
            {"status": "MATCH", "final_mark": "@%  ADW", "cause": "GRAPHIC_SYMBOL"},
            None,
            "GRAPHIC_NOW_COUNTED",
        ),
        # BUG: unexplainable divergence
        (
            {"status": "DIFF", "expected_mark": "FOO", "elr_no": "ADI2601011", "side": "TOP", "line_no": 1},
            {"status": "MATCH", "final_mark": "BAR", "cause": "OK"},
            None,
            "BUG",
        ),
    ],
)
def test_parity_classify_codes(r1_row, r0_row, r0legacy_row, expected_reason):
    assert classify(r1_row, r0_row, r0legacy_row) == expected_reason


def test_parity_abs_no_normalised():
    """R1 abs_no is a file stem (ABS066973-ENG-1); R0 is ABS066973 -> same ABS, not RESOLVER_CHANGED."""
    r1 = {"status": "MATCH", "expected_mark": "ADW", "abs_no": "ABS066973-ENG-1",
          "elr_no": "ADI2601023", "side": "TOP", "line_no": 1}
    r0 = {"status": "MATCH", "final_mark": "ADW", "abs_no": "ABS066973", "cause": "OK"}
    assert classify(r1, r0, None) == "SAME"


def test_parity_r0_db_line_empty_is_oracle_influence():
    """R0 cause DB_LINE_EMPTY matched only because Oracle was empty (R0 rule needs db_mark == '')."""
    r1 = {"status": "DB_EMPTY", "expected_mark": "@ EB{1-DC}", "elr_no": "ADI2602124", "side": "TOP", "line_no": 1}
    r0 = {"status": "MATCH", "final_mark": "@ MYW", "cause": "DB_LINE_EMPTY"}
    assert classify(r1, r0, None) == "ORACLE_INFLUENCE_REMOVED"


def test_parity_ocr_source_only_when_r0_reocr_flagged():
    """Same divergence without the R0 re-OCR flag is a BUG (no hard-coded ELR list)."""
    r1 = {"status": "DIFF", "expected_mark": "LHYBN", "elr_no": "ADI2605013", "side": "TOP", "line_no": 2}
    r0 = {"status": "MATCH", "final_mark": "LHYB", "cause": "OK"}
    assert classify(r1, r0, None) == "BUG"
    assert classify({**r1, "r0_reocr": "Y"}, r0, None) == "OCR_SOURCE_CHANGED"


def test_parity_other_abs_revision_rejected_is_resolver_changed():
    """Folder has ABS068387B and C; Oracle BOM rev B -> R1 uses B; R0 picked by Oracle (R03-ONE-ABS)."""
    r1 = {"status": "DIFF", "expected_mark": "FS7201", "abs_no": "ABS068387B", "elr_no": "ADI2606077",
          "side": "TOP", "line_no": 2, "abs_other_revisions": "ABS068387C"}
    r0 = {"status": "MATCH", "final_mark": "S7201BCP", "abs_no": "ABS068387", "cause": "OK"}
    assert classify(r1, r0, None) == "RESOLVER_CHANGED"
    r1_same = {**r1, "status": "MATCH", "expected_mark": "S7201BCP"}
    assert classify(r1_same, r0, None) == "SAME"
