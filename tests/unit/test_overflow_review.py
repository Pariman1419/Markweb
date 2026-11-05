from mark_engine.domain.models import ExpectedLine, ExpectedToken, Side
from mark_engine.generate.mark_layout import parse_layout
from services.engine.overflow_review import make_line, safe_json


def test_make_line_reproduces_fixed_cells_and_marks_failure():
    rows = [{'MARK_ROW': 1, 'MARK_COLUMN': c, 'MARK_DATA': '*' if c == 1 else ' '}
            for c in range(1, 19) if c not in (4, 5)]
    layout = parse_layout(1, rows)
    line = ExpectedLine(Side.TOP, 1, '* ABC', (ExpectedToken('*', 'r', 'REMARK'),))
    info = make_line(layout, 1, line, '   *  AB')
    assert info['generated'] == '*ABC'
    assert info['oracle'][:5] == '*  AB'
    assert info['layout'][:4] == ['*', ' ', ' ', None]
    assert info['status'] == 'error' and 'overflow' in info['error']


def test_json_cannot_close_its_script_tag():
    assert '</script>' not in safe_json({'mark': '</script>'})
