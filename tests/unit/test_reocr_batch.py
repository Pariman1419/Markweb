from services.inference.reocr_batch import legend_candidates
from mark_engine.abs.reocr import legend_candidates as abs_legend_candidates, trim_logo


def test_legend_candidate_keeps_original_value_and_crop():
    items = [[0, 10, 100, 30, 'LINE 2: ABC', .9], [0, 40, 30, 60, 'other', .8]]
    rows = legend_candidates('image.png', items)
    assert len(rows) == 1
    assert rows[0]['key'] == 'image|TOP|2'
    assert rows[0]['old'] == 'ABC'
    assert rows[0]['box'] == (65, 8, 106, 32)

    abs_rows = abs_legend_candidates('image.png', items)
    assert abs_rows == rows
