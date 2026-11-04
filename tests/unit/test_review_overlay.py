from mark_engine.regression.review_overlay import Verdict, final_status


def _row(exp, ora, status="DIFF"):
    return {"expected_mark": exp, "oracle_mark": ora, "status": status}


def test_db_wrong_when_system_equals_reviewed_answer():
    v = Verdict("ADI2605086_T3", "DB wrong", "ตัวพิมเล็ก x", answer="#YYWW9x9")
    assert final_status(_row("#YYWW9x9", "#YYWW9X9"), v) == "DB_WRONG"


def test_slr_ecn_change_is_db_wrong():
    v = Verdict("ADI2602050_T2", "SLR / ECN change", "SLR ระบุไว้", answer="ADBMS6834")
    assert final_status(_row("ADBMS6834", "ADW90040", "NEEDS_REVIEW"), v) == "DB_WRONG"


def test_ocr_wrong_is_human_fixed():
    v = Verdict("ADI2604053_T1", "OCR wrong", "อ่าน OCR ผิด", answer=None)
    assert final_status(_row("@% SAD", "@%  ADW"), v) == "HUMAN_FIXED"


def test_legend_note_with_system_right_clears_review():
    v = Verdict("ADI2605047_T3", "", "มีบอกในภาพ", answer=None)
    assert final_status(_row("FET10", "FET10", "NEEDS_REVIEW"), v) == "MATCH"
    assert final_status(_row("UJHN", "UJH", "NEEDS_REVIEW"), v) == "HUMAN_FIXED"


def test_stale_verdict_keeps_system_status():
    """Reviewed answer no longer equals R1 expected or Oracle -> do not apply."""
    v = Verdict("X_T1", "DB wrong", "", answer="ABC")
    assert final_status(_row("XYZ", "QQQ"), v) == "DIFF"


def test_no_verdict_keeps_status():
    assert final_status(_row("A", "B"), None) == "DIFF"


def test_held_line_is_not_overridden():
    v = Verdict("ADI2603041_B1", "OCR wrong", "", answer=None)
    assert final_status(_row("", "#YWW", "NOT_MEASURABLE"), v) == "NOT_MEASURABLE"
