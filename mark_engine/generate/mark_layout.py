"""ACTIVEL's reserved cells; unlisted positions are available for generated text."""
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Iterable, Mapping


class LayoutError(ValueError):
    pass


@dataclass(frozen=True)
class MarkLayout:
    mark_id: int
    cells: Mapping[tuple[int, int], str]


def parse_layout(mark_id: int, rows: Iterable[Mapping[str, Any]]) -> MarkLayout:
    cells: dict[tuple[int, int], str] = {}
    for row in rows:
        try:
            position = (int(row['MARK_ROW']), int(row['MARK_COLUMN']))
        except (KeyError, TypeError, ValueError) as exc:
            raise LayoutError(f'MARK_ID {mark_id}: invalid position') from exc
        if not (1 <= position[0] <= 5 and 1 <= position[1] <= 18):
            raise LayoutError(f'MARK_ID {mark_id}: position outside grid: {position}')
        if position in cells:
            raise LayoutError(f'MARK_ID {mark_id}: duplicate position: {position}')
        value = row.get('MARK_DATA')
        value = ' ' if value is None or value == '' else str(value)
        if len(value) != 1:
            raise LayoutError(f'MARK_ID {mark_id}: invalid cell value at {position}')
        cells[position] = value
    if not cells:
        raise LayoutError(f'MARK_ID {mark_id}: layout missing')
    return MarkLayout(mark_id, MappingProxyType(cells))


def fill_line(layout: MarkLayout, row: int, generated: str) -> str:
    return fill_line_with_conflicts(layout, row, generated)[0]


def fill_line_with_conflicts(layout: MarkLayout, row: int, generated: str) -> tuple[str, tuple[tuple[int, str, str], ...]]:
    """Fill free cells in order, consuming a matching or conflicting graphic at fixed cells.

    The caller removes only known synthetic separators; other spaces are data.
    """
    if not 1 <= row <= 5:
        raise LayoutError(f'MARK_ID {layout.mark_id}: invalid row {row}')
    symbols = frozenset('@%^*{<!#?')
    text = generated
    fixed_symbols = [layout.cells[(row, col)] for col in range(1, 19)
                     if layout.cells.get((row, col), ' ') in symbols]
    if any(text.count(symbol) > fixed_symbols.count(symbol) for symbol in fixed_symbols):
        raise LayoutError(f'MARK_ID {layout.mark_id} row {row}: ambiguous repeated fixed symbol')
    has_free = any((row, col) not in layout.cells for col in range(1, 19))

    @lru_cache(maxsize=None)
    def solve(col, pos):
        if col == 19:
            return (0, (), '', ()) if pos == len(text) else None
        cell = layout.cells.get((row, col))
        choices = []

        def add(character, next_pos, score=0, conflict=None):
            rest = solve(col + 1, next_pos)
            if rest is not None:
                points, positions, suffix, conflicts = rest
                consumed = (col,) if next_pos != pos else ()
                choices.append((points + score, consumed + positions, character + suffix,
                                ((col, text[pos], character),) + conflicts if conflict else conflicts))

        if cell is None:
            if pos < len(text):
                add(text[pos], pos + 1)
            add(' ', pos)
        else:
            add(cell, pos)
            if cell == ' ' and pos < len(text) and text[pos] == ' ':
                # The generator's separator space lands on a reserved blank instead of
                # taking a free cell (MARK_ID 23706 '@* ____' + '@* YYWW').
                add(cell, pos + 1, 2)
            elif cell != ' ' and pos < len(text):
                same = text[pos] == cell
                graphic = cell in symbols and text[pos] in symbols
                if same or graphic or not has_free:
                    add(cell, pos + 1, 2 if same else 1, not same)
        if not choices:
            return None
        return min(choices, key=lambda choice: (-choice[0], choice[1]))

    result = solve(1, 0)
    if result is None:
        fixed_text = any(value != ' ' and value not in symbols for (r, _), value in layout.cells.items() if r == row)
        reason = 'ambiguous fixed-text conflict or overflow' if fixed_text and has_free else 'overflow'
        raise LayoutError(f'MARK_ID {layout.mark_id} row {row}: {reason}')
    return result[2], result[3]
