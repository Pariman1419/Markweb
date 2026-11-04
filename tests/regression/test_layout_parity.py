import csv
import json
import os
from pathlib import Path

import pytest

from mark_engine.abs.layout import layout_lines
from mark_engine.adapters.snapshot import r0_root


@pytest.mark.regression
def test_layout_matches_legacy_h1_lines():
    root = r0_root()
    h1_lines_path = root / "experiments" / "abs_vs_db" / "out" / "h1_lines.csv"
    det_path = root / "experiments" / "abs_vs_db" / "out" / "h1_det_rec.json"
    reocr_path = root / "experiments" / "abs_vs_db" / "out" / "ocr_reocr.csv"

    if not h1_lines_path.is_file() or not det_path.is_file():
        pytest.skip(f"Legacy H1 files not found at {root}")

    reocr_keys = set()
    if reocr_path.is_file():
        with open(reocr_path, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r["kept"] == "Y" and r["method"] == "legend_value":
                    reocr_keys.add(r["key"])

    expected = {}
    with open(h1_lines_path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            expected[(r["image"], r["side"], int(r["line"]))] = r["ocr_text"]

    with open(det_path, encoding="utf-8") as f:
        det = json.load(f)

    checked = 0
    for img_name, items in det.items():
        stem = Path(img_name).stem
        lines = layout_lines(items)
        for side, line_no, text, _score, _bbox in lines:
            key = f"{stem}|{side.value}|{line_no}"
            if key in reocr_keys:
                continue
            assert (stem, side.value, line_no) in expected, f"Missing key {key} in expected"
            assert text == expected[(stem, side.value, line_no)], f"Text mismatch on {key}"
            checked += 1

    assert checked > 0, "No lines were verified against h1_lines.csv"
