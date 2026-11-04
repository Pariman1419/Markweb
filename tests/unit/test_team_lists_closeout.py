from scripts.export_team_lists import marking_team_rows, rule_approval_rows


def test_team_list_separates_confirmed_and_pending():
    rows = [
        {'elr_no': 'A', 'side': 'TOP', 'line_no': '1', 'status': 'DIFF', 'final_status': 'DB_WRONG'},
        {'elr_no': 'B', 'side': 'TOP', 'line_no': '1', 'status': 'DIFF', 'final_status': 'DIFF'},
        {'elr_no': 'C', 'side': 'TOP', 'line_no': '1', 'status': 'MATCH', 'final_status': 'MATCH'},
        {'elr_no': 'D', 'side': 'TOP', 'line_no': '1', 'status': 'DB_EMPTY', 'final_status': 'DB_EMPTY'},
    ]
    confirmed, pending = marking_team_rows(rows)
    assert [row['elr_no'] for row in confirmed] == ['A']
    assert [row['elr_no'] for row in pending] == ['B', 'D']


def test_rule_approval_list_contains_all_decisions():
    rows = rule_approval_rows()
    assert {row['decision'] for row in rows} == {f'D-{n}' for n in range(22, 30)}
    assert all(row['approval'] == '' for row in rows)
