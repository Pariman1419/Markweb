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
            {"status": "DIFF", "expected_mark": "@% SAD", "elr_no": "ADI2604053", "side": "TOP", "line_no": 1},
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
