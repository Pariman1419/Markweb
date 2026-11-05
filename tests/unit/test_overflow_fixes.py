"""Fixes from the run-17 overflow review (2026-11-05, 25 reviewed ELRs)."""
from dataclasses import replace

import pytest

from mark_engine.domain.models import DocType, InferenceResult, LayoutLine, LineStatus, OracleMark, ProcessingStatus, Side
from mark_engine.encode.adi1039 import apply_adi1039
from mark_engine.generate.mark_layout import fill_line, parse_layout
from mark_engine.pipeline import process_elr
from mark_engine.slr.parse import parse_slr
from tests.unit.test_pipeline import _rules, _setup_elr


def _row_layout(mark_id, row, spec):
    """spec: one char per column; '_' = free cell, anything else = reserved cell."""
    return parse_layout(mark_id, [{'MARK_ROW': row, 'MARK_COLUMN': col, 'MARK_DATA': ch}
                                  for col, ch in enumerate(spec.ljust(18), 1) if ch != '_'])


@pytest.mark.parametrize(('spec', 'generated', 'expected'), [
    ('@* ____', '@* YYWW', '@* YYWW'),   # MARK_ID 23706
    ('*   ___', '* YWW', '*   YWW'),     # MARK_ID 23274
    ('*  __', '* YW', '*  YW'),          # MARK_ID 24350
    ('@* ____', '@*YYWW', '@* YYWW'),    # unchanged: no space in the generated text
])
def test_reserved_blank_absorbs_generated_space(spec, generated, expected):
    assert fill_line(_row_layout(1, 1, spec), 1, generated).rstrip() == expected


@pytest.mark.parametrize(('text', 'line', 'value'), [
    ('Pls add special marking in line 5  -   TNOE\nBalance of the wafer pls keep in diebank', 5, 'TNOE'),
    ('BRAND CHANGE   LINE 2  TCE-2-W9\nHOLD BALANCE OF THE WAFER FOR FUTURE BUILDS', 2, 'TCE-2-W9'),
    ('Change Top Mark:\nLine 3 ENGBU1Q\nExpedite Build if possible.', 3, 'ENGBU1Q'),
    ('Please change Top mark / Brand\nLine 3: ENGA\n3065 (Pre-Probe Qty)\nActual Qty: TBD', 3, 'ENGA'),
    ('Top Line 5:  COUNTRY_OF_ORIGIN TSF\n*Return Wafer Remnants', 5, 'COUNTRY_OF_ORIGIN TSF'),
    ('Line 3:\nENGA\nBalance of the wafer', 3, 'ENGA'),  # value on the next text line is still read
])
def test_slr_value_stops_at_text_line_break(text, line, value):
    facts = parse_slr(text)
    assert [(i.line_no, i.value) for i in facts.instructions] == [(line, value)]


@pytest.mark.parametrize(('text', 'expected'), [
    ('U1 #DATE_CODE', 'U1 #YYWW'),
    ('ASSEMBLY_LOT_NUMBER', 'XXXXXXXXX'),
    ('COUNTRY_OF_ORIGIN TSF', 'THAILAND TSF'),
    ('8893-48ENG', '8893-48ENG'),
])
def test_slr_underscore_placeholders_are_encoded(text, expected):
    assert apply_adi1039(text, DocType.SLR)[0] == expected


def test_abs_date_code_words_are_not_rewritten():
    assert apply_adi1039('DATE CODE', DocType.ABS)[0] == 'DATE CODE'


def test_line_overflow_is_review_warning_not_job_failure(month_tree, tmp_path):
    _, meta = _setup_elr(month_tree, 'ADI2601015')
    meta = replace(meta, top_mark_id=22799)
    layout = parse_layout(22799, [{'MARK_ROW': 1, 'MARK_COLUMN': c, 'MARK_DATA': '@%'[c - 1] if c <= 2 else ' '}
                                  for c in range(1, 19)])
    loader = lambda elr, stem: InferenceResult(elr, (
        LayoutLine(Side.TOP, 1, 'TEXT THAT HAS NO ROOM', '@%'), LayoutLine(Side.TOP, 2, 'ADM1266ACPZ', '')))
    oracle = OracleMark(meta.elr_no, ((Side.TOP, 1, '@%'), (Side.TOP, 2, 'ADM1266ACPZ')))
    job = process_elr(meta, oracle, month_tree, ['1_JAN'], tmp_path / 'work', _rules(), loader,
                      layouts={22799: layout})
    assert job.processing_status == ProcessingStatus.DONE and job.hold_reason is None
    by_line = {c.line_no: c for c in job.comparisons if c.side == Side.TOP}
    assert by_line[1].status == LineStatus.NEEDS_REVIEW
    assert 'LAYOUT_OVERFLOW' in by_line[1].warning
    assert by_line[2].status != LineStatus.NEEDS_REVIEW and 'LAYOUT_OVERFLOW' not in by_line[2].warning


def test_full_country_name_shortened_only_when_layout_has_no_room(month_tree, tmp_path):
    _, meta = _setup_elr(month_tree, 'ADI2601016')
    meta = replace(meta, top_mark_id=24755)
    layout = _row_layout(24755, 1, '__________        ')
    loader = lambda elr, stem: InferenceResult(elr, (LayoutLine(Side.TOP, 1, 'COUNTRY OF ORIGIN TSF', ''),))
    oracle = OracleMark(meta.elr_no, ((Side.TOP, 1, 'THAI TSF'),))
    job = process_elr(meta, oracle, month_tree, ['1_JAN'], tmp_path / 'work', _rules(), loader,
                      layouts={24755: layout})
    line = job.comparisons[0]
    assert job.expected.line(Side.TOP, 1).text.rstrip() == 'THAI TSF'  # most common ACTL short form
    assert line.status == LineStatus.MATCH and 'LAYOUT_COO_ABBREVIATED' in line.warning


def test_any_oracle_country_prefix_matches_after_layout_shortening(month_tree, tmp_path):
    _, meta = _setup_elr(month_tree, 'ADI2601017')
    meta = replace(meta, top_mark_id=1)
    layout = _row_layout(1, 1, '______            ')
    loader = lambda elr, stem: InferenceResult(elr, (LayoutLine(Side.TOP, 1, 'COUNTRY OF ORIGIN#', ''),))
    oracle = OracleMark(meta.elr_no, ((Side.TOP, 1, 'THAIL#'),))
    job = process_elr(meta, oracle, month_tree, ['1_JAN'], tmp_path / 'work', _rules(), loader, layouts={1: layout})
    assert job.expected.line(Side.TOP, 1).text.rstrip() == 'THAI#'
    assert job.comparisons[0].status == LineStatus.MATCH
    assert job.comparisons[0].detail == 'COO_ABBREVIATED'  # Oracle THAIL still reads as THAILAND


def _job(month_tree, tmp_path, elr, mark_id, layout, lines, oracle_lines):
    _, meta = _setup_elr(month_tree, elr)
    meta = replace(meta, top_mark_id=mark_id)
    loader = lambda e, stem: InferenceResult(e, tuple(LayoutLine(Side.TOP, n, t, g) for n, t, g in lines))
    oracle = OracleMark(meta.elr_no, tuple((Side.TOP, n, t) for n, t in oracle_lines))
    return process_elr(meta, oracle, month_tree, ['1_JAN'], tmp_path / 'work', _rules(), loader, layouts={mark_id: layout})


def test_no_brand_note_is_dropped_and_graphics_remain(month_tree, tmp_path):
    layout = _row_layout(22799, 1, '@%')
    job = _job(month_tree, tmp_path, 'ADI2601018', 22799, layout, [(1, 'NO BRAND ON THIS LINE', '@%')], [(1, '@%')])
    assert job.expected.line(Side.TOP, 1).text.rstrip() == '@%'
    assert job.comparisons[0].status == LineStatus.MATCH


def test_case_only_difference_is_match_with_warning(month_tree, tmp_path):
    layout = _row_layout(25005, 1, '________')
    job = _job(month_tree, tmp_path, 'ADI2601019', 25005, layout, [(1, 'Bajau TC', '')], [(1, 'BAJAU TC')])
    line = job.comparisons[0]
    assert line.status == LineStatus.MATCH and line.detail == 'CASE_DIFF' and 'CASE_DIFF' in line.warning


def test_trailing_literal_after_abs_token_dropped_only_on_overflow(month_tree, tmp_path):
    rows = [{'MARK_ROW': 1, 'MARK_COLUMN': c, 'MARK_DATA': ch} for c, ch in enumerate('!'.ljust(18), 1)]
    rows += [{'MARK_ROW': 2, 'MARK_COLUMN': c, 'MARK_DATA': ch} for c, ch in enumerate('%  __'.ljust(18), 1) if ch != '_']
    layout = parse_layout(22801, rows)
    job = _job(month_tree, tmp_path, 'ADI2601020', 22801, layout,
               [(2, '{ADI-PARTIAL-LOGO}{YW}X', '')], [(1, '!'), (2, '%  YW')])
    line = next(c for c in job.comparisons if c.line_no == 2)
    assert job.expected.line(Side.TOP, 2).text.rstrip() == '%  YW'
    assert 'LAYOUT_TRAILING_LITERAL_DROPPED' in line.warning and line.status == LineStatus.MATCH


def test_pin_only_row_reflows_following_lines(month_tree, tmp_path):
    spec = {1: '@', 2: '%___', 3: '____'}
    rows = [{'MARK_ROW': r, 'MARK_COLUMN': c, 'MARK_DATA': ch}
            for r in range(1, 6) for c, ch in enumerate(spec.get(r, '').ljust(18), 1) if ch != '_']
    layout = parse_layout(25203, rows)
    job = _job(month_tree, tmp_path, 'ADI2601021', 25203, layout,
               [(1, 'XXX', '@%'), (2, 'GL3G', '')], [(1, '@'), (2, '%XXX'), (3, 'GL3G')])
    by_line = {c.line_no: c for c in job.comparisons}
    assert [by_line[n].status for n in (1, 2, 3)] == [LineStatus.MATCH] * 3
    assert all('LAYOUT_REFLOW' in by_line[n].warning for n in (1, 2, 3))


def test_pointer_sentence_resolved_only_with_line_instructions():
    with_lines = parse_slr('*Ignore Brand on ABS. Brand as indicated below.\nTop Line 1:  ADRF')
    assert with_lines.unresolved == () and [(i.line_no, i.value) for i in with_lines.instructions] == [(1, 'ADRF')]
    assert parse_slr('*Ignore Brand on ABS. Brand as indicated below.').unresolved != ()


def test_ordinal_brand_line_quoted_value():
    facts = parse_slr("Physical die ID: WH3\nSecond line of brand content / marking: 'GL3G'\nPlease see attached")
    assert [(i.line_no, i.value) for i in facts.instructions] == [(2, 'GL3G')]
