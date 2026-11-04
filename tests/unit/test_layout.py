from pathlib import Path

import pytest

from mark_engine.abs.layout import layout_lines
from mark_engine.abs.symbols_to_lines import assign_graphics
from mark_engine.adapters.snapshot import load_inference
from mark_engine.domain.models import LayoutLine, Side


def test_label_rows():
    items = [
        (10.0, 20.0, 30.0, 35.0, "L1", 0.99),
        (50.0, 20.0, 100.0, 35.0, "AD7799", 0.98),
        (10.0, 50.0, 30.0, 65.0, "L2", 0.99),
        (50.0, 50.0, 100.0, 65.0, "#2615", 0.97),
    ]
    lines = layout_lines(items)
    assert len(lines) == 2
    assert lines[0][0] == Side.TOP
    assert lines[0][1] == 1
    assert lines[0][2] == "AD7799"
    assert lines[1][0] == Side.TOP
    assert lines[1][1] == 2
    assert lines[1][2] == "#2615"


def test_second_l1_is_bottom():
    items = [
        (10.0, 20.0, 30.0, 35.0, "L1", 0.99),
        (50.0, 20.0, 100.0, 35.0, "TOP1", 0.98),
        (10.0, 50.0, 30.0, 65.0, "L2", 0.99),
        (50.0, 50.0, 100.0, 65.0, "TOP2", 0.97),
        (10.0, 80.0, 30.0, 95.0, "L1", 0.99),
        (50.0, 80.0, 100.0, 95.0, "BOT1", 0.96),
    ]
    lines = layout_lines(items)
    assert len(lines) == 3
    assert (lines[0][0], lines[0][1], lines[0][2]) == (Side.TOP, 1, "TOP1")
    assert (lines[1][0], lines[1][1], lines[1][2]) == (Side.TOP, 2, "TOP2")
    assert (lines[2][0], lines[2][1], lines[2][2]) == (Side.BOTTOM, 1, "BOT1")


def test_legend_mode():
    items = [
        (10.0, 20.0, 150.0, 35.0, "LINE 1: ABC", 0.99),
        (10.0, 50.0, 150.0, 65.0, "LINE 2: DEF", 0.98),
    ]
    lines = layout_lines(items)
    assert len(lines) == 2
    assert (lines[0][0], lines[0][1], lines[0][2]) == (Side.TOP, 1, "ABC")
    assert (lines[1][0], lines[1][1], lines[1][2]) == (Side.TOP, 2, "DEF")


def test_pin_dot_above_first_row_goes_to_line1():
    lines = [
        (Side.TOP, 1, "LINE1_TEXT", 0.99, (50.0, 100.0, 150.0, 120.0)),
        (Side.TOP, 2, "LINE2_TEXT", 0.98, (50.0, 140.0, 150.0, 160.0)),
    ]
    detections = [
        ("pin1_dot", 0.95, 30.0, 60.0, 45.0, 75.0),
    ]
    gfx = assign_graphics(lines, detections)
    assert gfx.get((Side.TOP, 1)) == "@"


def test_graphic_below_last_row_ignored():
    lines = [
        (Side.TOP, 1, "LINE1_TEXT", 0.99, (50.0, 100.0, 150.0, 120.0)),
        (Side.TOP, 2, "LINE2_TEXT", 0.98, (50.0, 140.0, 150.0, 160.0)),
    ]
    detections = [
        ("pin1_dot", 0.95, 50.0, 250.0, 70.0, 270.0),
    ]
    gfx = assign_graphics(lines, detections)
    assert (Side.TOP, 1) not in gfx
    assert (Side.TOP, 2) not in gfx
    assert gfx == {}


def test_load_inference_none_when_missing(tmp_path: Path):
    res = load_inference(tmp_path, "ADI9999999", "ABS999999")
    assert res.elr_no == "ADI9999999"
    assert res.lines == ()
    assert res.layout_source == "none"
