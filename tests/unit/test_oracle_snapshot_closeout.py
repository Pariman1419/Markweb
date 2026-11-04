from datetime import datetime
from decimal import Decimal
import pytest

from mark_engine.adapters.oracle_snapshot import rows_to_meta, layout_json


def test_snapshot_latest_revision_and_json_values():
    rows = [
        {'ELR_NO': 'ADI2607001', 'ELR_REV': '00', 'TOP_MARK_ID': Decimal('20168')},
        {'ELR_NO': 'ADI2607001', 'ELR_REV': '02', 'TOP_MARK_ID': Decimal('20168'),
         'IMPORT_DATE': datetime(2026, 7, 1)},
    ]
    result = rows_to_meta(rows)
    assert len(result) == 1 and result[0]['ELR_REV'] == '02'
    assert result[0]['TOP_MARK_ID'] == 20168
    assert result[0]['IMPORT_DATE'] == '2026-07-01T00:00:00'


def test_layout_json_groups_and_keeps_blank_cells():
    rows = [{'MARK_ID': 2, 'MARK_ROW': 1, 'MARK_COLUMN': 1, 'MARK_DATA': ' '},
            {'MARK_ID': 2, 'MARK_ROW': 1, 'MARK_COLUMN': 2, 'MARK_DATA': '*'}]
    assert layout_json(rows) == {'2': [[1, 1, ' '], [1, 2, '*']]}


def test_snapshot_rejects_different_rows_for_same_revision():
    with pytest.raises(ValueError, match='duplicate revision'):
        rows_to_meta([{'ELR_NO': 'ADI2607001', 'ELR_REV': '00', 'STATUS': 'R'},
                      {'ELR_NO': 'ADI2607001', 'ELR_REV': '00', 'STATUS': 'C'}])
