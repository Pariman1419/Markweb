import pytest
from scripts.load_r1_to_pg import MONTH, line_row, job_row, validate_blind_commit, provenance_note


def test_line_row_preserves_system_and_review_status():
    row = {'elr_no': 'ADI2611001', 'side': 'TOP', 'line_no': '1',
           'expected_mark': 'ABC', 'oracle_mark': 'ABD', 'status': 'DIFF',
           'final_status': 'DB_WRONG', 'warning': 'CHECK', 'hold_reason': '',
           'detail': '', 'compare_rules': '', 'flags': '', 'layout_source': 'auto'}
    result = line_row(42, row, 'ABS000001', '')
    assert result[0] == 42
    assert result[5] == '11_NOV'
    assert result[8] == 'DB_WRONG'
    assert result[11:14] == ('DIFF', 'DB_WRONG', None)
    assert result[14] == 'CHECK'
    assert MONTH['07'] == '7_JUL'


def test_job_row_preserves_layout_error_without_comparison_lines():
    row = {'elr_no': 'ADI2611001', 'processing_status': 'FAILED', 'hold_reason': 'LAYOUT_ERROR'}
    assert job_row(42, row)[:4] == (42, 'ADI2611001', 'FAILED', 'LAYOUT_ERROR')


def test_unfrozen_blind_result_cannot_be_committed(tmp_path):
    with pytest.raises(ValueError, match='official frozen'):
        validate_blind_commit(tmp_path, {'freeze': {'freeze_id': 'UNFROZEN'}})


def test_blind_provenance_describes_allowed_oracle_layout():
    note = provenance_note({'independence': 1.0, 'independence_denom': 2, 'total_jobs': 3,
                            'needs_review_lines': 0, 'hold_count': 1}, None, 'holdout', True)
    assert 'MARK_ID_LAYOUT' in note and 'TOP/BACK_MARK' in note
    assert 'Not Oracle-conditioned' not in note
