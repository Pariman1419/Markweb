import pytest

from mark_engine.generate.mark_layout import LayoutError, parse_layout, fill_line, fill_line_with_conflicts


def test_layout_reserves_fixed_and_blank_cells():
    layout = parse_layout(20168, [
        {'MARK_ROW': 1, 'MARK_COLUMN': 1, 'MARK_DATA': '*'},
        {'MARK_ROW': 1, 'MARK_COLUMN': 2, 'MARK_DATA': ' '},
        {'MARK_ROW': 4, 'MARK_COLUMN': 8, 'MARK_DATA': '<'},
    ])
    assert layout.cells[(1, 1)] == '*'
    assert layout.cells[(1, 2)] == ' '
    assert (1, 3) not in layout.cells
    assert layout.cells[(4, 8)] == '<'


@pytest.mark.parametrize('rows', [
    [],
    [{'MARK_ROW': 0, 'MARK_COLUMN': 1, 'MARK_DATA': ' '}],
    [{'MARK_ROW': 1, 'MARK_COLUMN': 19, 'MARK_DATA': ' '}],
    [{'MARK_ROW': 1, 'MARK_COLUMN': 1, 'MARK_DATA': 'AB'}],
    [{'MARK_ROW': 1, 'MARK_COLUMN': 1, 'MARK_DATA': '*'},
     {'MARK_ROW': 1, 'MARK_COLUMN': 1, 'MARK_DATA': '*'}],
])
def test_invalid_layout_is_rejected(rows):
    with pytest.raises(LayoutError):
        parse_layout(20168, rows)


def test_layout_20168_places_fixed_and_generated_once():
    rows = []
    free = {1: set(range(4, 8)), 2: set(range(2, 8)), 3: set(range(3, 8)), 4: set(range(3, 8)), 5: set()}
    for row in range(1, 6):
        for col in range(1, 19):
            if col not in free[row]:
                value = '*' if (row, col) == (1, 1) else '<' if (row, col) == (4, 8) else ' '
                rows.append({'MARK_ROW': row, 'MARK_COLUMN': col, 'MARK_DATA': value})
    layout = parse_layout(20168, rows)
    assert fill_line(layout, 1, '*YYWW').rstrip() == '*  YYWW'
    assert fill_line(layout, 1, '@YYWW').rstrip() == '*  YYWW'
    assert fill_line_with_conflicts(layout, 1, '@YYWW')[1] == ((1, '@', '*'),)
    assert fill_line(layout, 2, '1963').rstrip() == ' 1963'
    assert fill_line(layout, 3, 'EFE15').rstrip() == '  EFE15'
    assert fill_line(layout, 4, 'BSSOP<').rstrip() == '  BSSOP<'
    with pytest.raises(LayoutError, match='overflow'):
        fill_line(layout, 3, 'TOOLONG')


def test_extra_fixed_symbols_are_not_silently_discarded():
    layout = parse_layout(1, [{'MARK_ROW': 1, 'MARK_COLUMN': 1, 'MARK_DATA': '*'}])
    with pytest.raises(LayoutError, match='ambiguous'):
        fill_line(layout, 1, '**ABC')


def test_fixed_text_replaces_conflicting_generated_text_in_fully_fixed_row():
    rows = [{'MARK_ROW': 1, 'MARK_COLUMN': col, 'MARK_DATA':
             ('YYWW'[col - 1] if col <= 4 else ' ')} for col in range(1, 19)]
    text, conflicts = fill_line_with_conflicts(parse_layout(2, rows), 1, 'ZYWW')
    assert text.rstrip() == 'YYWW'
    assert conflicts == ((1, 'Z', 'Y'),)


def test_fixed_symbol_in_middle_is_not_duplicated():
    layout = parse_layout(3, [{'MARK_ROW': 1, 'MARK_COLUMN': 3, 'MARK_DATA': '<'}])
    assert fill_line(layout, 1, 'A<BC').rstrip() == 'A <BC'


def test_generated_internal_space_is_preserved():
    layout = parse_layout(3, [{'MARK_ROW': 1, 'MARK_COLUMN': 3, 'MARK_DATA': '<'}])
    assert fill_line(layout, 1, 'A B').rstrip() == 'A <B'


def test_ambiguous_fixed_text_conflict_is_error_not_guessed():
    rows = [{'MARK_ROW': 1, 'MARK_COLUMN': 1, 'MARK_DATA': 'A'}]
    rows += [{'MARK_ROW': 1, 'MARK_COLUMN': col, 'MARK_DATA': ' '} for col in range(3, 19)]
    with pytest.raises(LayoutError, match='ambiguous'):
        fill_line(parse_layout(4, rows), 1, 'BC')
