import csv
from pathlib import Path

from mark_engine.adapters.snapshot import _load_reocr, _reread


def test_reocr_selection_ignores_gt_and_kept(tmp_path: Path):
    p = tmp_path / "ocr_reocr.csv"
    rows = [
        ["key", "old", "new", "score", "method", "kept", "gt"],
        ["MAY_IMG011_ABS068396-ENG-1|TOP|2", "LHYBN", "LHYB", "0.9998", "legend_value", "Y", ""],
        ["APR_IMG016_TL1", "SAD", "ADW", "0.9984", "trim_logo", "N", "ADW"],   # kept ignored
        ["APR_IMG005_TL1", "ADRF", "ADRF", "0.9995", "trim_logo", "N", "ADRF"],  # same text
        ["X|TOP|1", "AB", "XY", "0.5", "legend_value", "Y", ""],                # low score
    ]
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows)
    r = _load_reocr(str(p))
    assert set(r) == {"MAY_IMG011_ABS068396-ENG-1|TOP|2", "APR_IMG016_TL1"}
    assert _reread(r, "APR_IMG016_TL1", "SAD") == "ADW"
    assert _reread(r, "APR_IMG016_TL1", "OTHER") == "OTHER"  # first read changed -> not applied
