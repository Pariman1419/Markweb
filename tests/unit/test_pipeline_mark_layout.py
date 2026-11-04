from dataclasses import replace

from mark_engine.domain.models import InferenceResult, LayoutLine, OracleMark, ProcessingStatus, Side
from mark_engine.generate.mark_layout import parse_layout
from mark_engine.pipeline import process_elr
from tests.unit.test_pipeline import _rules, _setup_elr


def test_pipeline_applies_layout_before_comparison(month_tree, tmp_path):
    _, meta = _setup_elr(month_tree, 'ADI2601008')
    meta = replace(meta, top_mark_id=20168)
    layout = parse_layout(20168, [
        {'MARK_ROW': 1, 'MARK_COLUMN': 1, 'MARK_DATA': '*'},
        {'MARK_ROW': 1, 'MARK_COLUMN': 2, 'MARK_DATA': ' '},
        {'MARK_ROW': 1, 'MARK_COLUMN': 3, 'MARK_DATA': ' '},
    ])
    loader = lambda elr, stem: InferenceResult(elr, (LayoutLine(Side.TOP, 1, 'YYWW', '*'),))
    oracle = OracleMark(meta.elr_no, ((Side.TOP, 1, '*  YYWW'),))
    job = process_elr(meta, oracle, month_tree, ['1_JAN'], tmp_path / 'work', _rules(), loader, layouts={20168: layout})
    assert job.expected.line(Side.TOP, 1).text.startswith('*  YYWW')
    assert any(token.source == 'LAYOUT' and token.text == '*' for token in job.expected.line(Side.TOP, 1).tokens)


def test_pipeline_missing_layout_fails_without_comparison(month_tree, tmp_path):
    _, meta = _setup_elr(month_tree, 'ADI2601009')
    meta = replace(meta, top_mark_id=20168)
    loader = lambda elr, stem: InferenceResult(elr, (LayoutLine(Side.TOP, 1, 'ABC', ''),))
    oracle = OracleMark(meta.elr_no, ((Side.TOP, 1, 'ABC'),))
    job = process_elr(meta, oracle, month_tree, ['1_JAN'], tmp_path / 'work', _rules(), loader, layouts={})
    assert job.processing_status == ProcessingStatus.FAILED
    assert job.expected is None and not job.comparisons
    assert '20168' in job.hold_reason


def test_missing_layout_reported_even_if_ocr_has_no_lines(month_tree, tmp_path):
    _, meta = _setup_elr(month_tree, 'ADI2601012')
    meta = replace(meta, top_mark_id=20168)
    loader = lambda elr, stem: InferenceResult(elr, (), 'none')
    job = process_elr(meta, OracleMark(meta.elr_no), month_tree, ['1_JAN'], tmp_path / 'work', _rules(), loader, layouts={})
    assert job.processing_status == ProcessingStatus.FAILED
    assert 'layout missing' in job.hold_reason


def test_pipeline_reports_fixed_symbol_conflict(month_tree, tmp_path):
    _, meta = _setup_elr(month_tree, 'ADI2601010')
    meta = replace(meta, top_mark_id=20168)
    layout = parse_layout(20168, [{'MARK_ROW': 1, 'MARK_COLUMN': 1, 'MARK_DATA': '*'}])
    loader = lambda elr, stem: InferenceResult(elr, (LayoutLine(Side.TOP, 1, 'ABC', '@'),))
    oracle = OracleMark(meta.elr_no, ((Side.TOP, 1, '*ABC'),))
    job = process_elr(meta, oracle, month_tree, ['1_JAN'], tmp_path / 'work', _rules(), loader, layouts={20168: layout})
    assert job.expected.line(Side.TOP, 1).text.startswith('*ABC')
    assert 'LAYOUT_FIXED_CONFLICT' in job.comparisons[0].warning


def test_position_difference_is_warning_without_changing_match(month_tree, tmp_path):
    _, meta = _setup_elr(month_tree, 'ADI2601011')
    meta = replace(meta, top_mark_id=20168)
    layout = parse_layout(20168, [
        {'MARK_ROW': 1, 'MARK_COLUMN': 1, 'MARK_DATA': '*'},
        {'MARK_ROW': 1, 'MARK_COLUMN': 2, 'MARK_DATA': ' '},
    ])
    loader = lambda elr, stem: InferenceResult(elr, (LayoutLine(Side.TOP, 1, 'ABC', '*'),))
    oracle = OracleMark(meta.elr_no, ((Side.TOP, 1, '*ABC'),), ((Side.TOP, 1, '   *ABC              '),))
    job = process_elr(meta, oracle, month_tree, ['1_JAN'], tmp_path / 'work', _rules(), loader, layouts={20168: layout})
    assert job.comparisons[0].status.value == 'MATCH'
    assert 'LAYOUT_POSITION' in job.comparisons[0].warning


def test_position_mask_treats_placeholder_digits_as_same_position():
    from mark_engine.pipeline import position_differs
    assert not position_differs('*  YYWW'.ljust(18), '   *  2610'.ljust(21))
    assert position_differs('*  YYWW'.ljust(18), '   * 2610'.ljust(21))


def test_shift_match_warns_about_row_shift(month_tree, tmp_path):
    _, meta = _setup_elr(month_tree, 'ADI2601013')
    meta = replace(meta, top_mark_id=20168)
    layout = parse_layout(20168, [{'MARK_ROW': 1, 'MARK_COLUMN': 1, 'MARK_DATA': '*'}])
    loader = lambda elr, stem: InferenceResult(elr, (LayoutLine(Side.TOP, 1, 'ABC', '*'),))
    oracle = OracleMark(meta.elr_no, ((Side.TOP, 1, '*'), (Side.TOP, 2, 'ABC')))
    job = process_elr(meta, oracle, month_tree, ['1_JAN'], tmp_path / 'work', _rules(), loader, layouts={20168: layout})
    shifted = [row for row in job.comparisons if row.status.value == 'MATCH_SHIFT']
    assert shifted and all('LAYOUT_LINE_SHIFT' in row.warning for row in shifted)
