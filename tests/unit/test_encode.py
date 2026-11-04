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
