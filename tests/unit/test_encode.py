import pytest

from mark_engine.domain.models import DocType, ExpectedToken
from mark_engine.encode.adi1039 import apply_adi1039
from mark_engine.encode.ocr_fix import ocr_fix
from mark_engine.encode.remark import is_skip_mark, remark_graphics
from mark_engine.encode.symbol_adi import encode_symbol_adi


def test_ocrfix_examples():
    text1, rules1 = ocr_fix("{SPACEE}")
    assert text1 == " "
    assert "R07-OCRFIX-1" in rules1

    text2, rules2 = ocr_fix("{YYWWE}")
    assert text2 == "YYWW"
    assert "R07-OCRFIX-4" in rules2

    text3, rules3 = ocr_fix("5 DIGIT SERIAL NUMBER")
    assert text3 == "XXXXX"
    assert "R07-OCRFIX-8" in rules3


def test_symbol_adi_logo():
    assert encode_symbol_adi("{LOGO}")[0] == "*"
    assert encode_symbol_adi("{•}")[0] == "@"
    assert encode_symbol_adi("{<}")[0] == "!"
    assert encode_symbol_adi("{ve3^}")[0] == "<"
    assert encode_symbol_adi("{FACTORYCODE}")[0] == "B"


def test_unmapped_token_reported():
    text, unmapped = encode_symbol_adi("{CCCCC}")
    assert text == "{CCCCC}"
    assert "{CCCCC}" in unmapped


def test_adi1039_lot_slice():
    text, tokens = apply_adi1039("{Lot-5}", DocType.ABS)
    assert text == "XXXXX"
    assert len(tokens) == 1
    tok = tokens[0]
    assert tok.text == "XXXXX"
    assert tok.lot_slice == "last-5"
    assert tok.rule_id == "R07-ADI1039-LOT"
    assert tok.source == "ADI1039"


def test_adi1039_rejects_trs():
    with pytest.raises(ValueError):
        apply_adi1039("TEST", DocType.TRS)
    with pytest.raises(ValueError):
        apply_adi1039("TEST", DocType.OTHER)


def test_adi1039_coo_and_lot_full():
    text, tokens = apply_adi1039("ASSEMBLY LOT NUMBER", DocType.ABS)
    assert text == "XXXXXXXXX"
    assert any(t.rule_id == "R07-ADI1039-LOT" and t.text == "XXXXXXXXX" for t in tokens)

    text_coo, tokens_coo = apply_adi1039("COUNTRY OF ORIGIN", DocType.SLR)
    assert text_coo == "THAILAND"
    assert any(t.rule_id == "R07-ADI1039-COO" and t.text == "THAILAND" for t in tokens_coo)

    text_sp, _ = apply_adi1039("A_B␣C{SPACE}D", DocType.ABS)
    assert text_sp == "A B C D"


def test_remark_caret():
    mapping = remark_graphics("^ = ADI logo", None)
    assert mapping == {"@": "", "%": "^", "{": "^"}


def test_remark_none():
    mapping = remark_graphics(None, None)
    assert mapping == {"@": "@", "%": "%", "{": "{"}


def test_skip_mark():
    assert is_skip_mark("Skip Mark", None) is True
    assert is_skip_mark(None, "skip mark") is True
    assert is_skip_mark("skipmark", None) is True
    assert is_skip_mark(None, None) is False
    assert is_skip_mark("Standard mark", None) is False


@pytest.mark.parametrize(
    "text, expected, lot_slice",
    [
        # ADI1039 Table 2 preview text "n Digit Lot Number" = {Lot-n}; R1 triage ADI2601001 TOP 3
        ("3 DIGIT LOT NUMBERYWW", "XXXYWW", "last-3"),
        ("7 DIGIT LOT NUMBER", "XXXXXXX", "last-7"),
        ("9 Digit Lot Number", "XXXXXXXXX", "last-9"),
        ("LAST 2 DIGIT LOT NUMBER", "XX", "last-2"),
    ],
)
def test_adi1039_plain_text_digit_lot_number(text, expected, lot_slice):
    out, tokens = apply_adi1039(text, DocType.ABS)
    assert out == expected
    assert any(t.rule_id == "R07-ADI1039-LOT" and t.lot_slice == lot_slice for t in tokens)


def test_ocrfix7_origin_eng_suffix_keeps_coo_then_adi1039_thailand():
    """Drafting suffix ORIGINENG4 is noise; the field itself is COUNTRY OF ORIGIN (ADI2605079 TOP 5)."""
    fixed, rules = ocr_fix("COUNTRY OF ORIGINENG4")
    assert fixed == "COUNTRY OF ORIGIN"
    assert "R07-OCRFIX-7" in rules
    out, _ = apply_adi1039(fixed, DocType.ABS)
    assert out == "THAILAND"
    assert ocr_fix("THAILANDENG2")[0] == "THAILAND"


def test_adi1039_digit_lot_number_glued_to_date_code():
    """OCR glues the date code in front: 'YW6 DIGIT LOT NUMBER' (ADI2601045 TOP 3)."""
    assert apply_adi1039("YW6 DIGIT LOT NUMBER", DocType.ABS)[0] == "YWXXXXXX"


def test_lot_number_u_suffix_keeps_field():
    """R07-OCRFIX-6 drops the drafting suffix U1, not the field (ADI2604002 B2, old review 'ตีความผิดปะ')."""
    from mark_engine.encode.ocr_fix import ocr_fix
    from mark_engine.encode.adi1039 import apply_adi1039
    from mark_engine.domain.models import DocType
    fixed, _ = ocr_fix("LAST 2 DIGIT LOT NUMBERU1")
    assert fixed == "LAST 2 DIGIT LOT NUMBER"
    assert apply_adi1039(fixed, DocType.ABS)[0] == "XX"
    assert ocr_fix("XXXU2")[0] == "XXX"
