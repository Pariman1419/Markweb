from scripts.make_review_page import classify, error_panel


def test_layout_warning_is_not_described_as_country_abbreviation():
    row = {'status': 'MATCH', 'expected_mark': '* ABC', 'oracle_mark': '*ABC',
           'warning': 'LAYOUT_POSITION', 'flags': ''}
    topic, label = classify(row)
    assert topic == 'WARN'
    assert 'LAYOUT_POSITION' in label


def test_error_panel_displays_failed_jobs_with_safe_text():
    panel = error_panel([{'elr_no': 'ADI2607001', 'processing_status': 'FAILED',
                          'hold_reason': 'bad <layout>'}])
    assert 'ADI2607001' in panel and 'bad &lt;layout&gt;' in panel


def test_difference_with_warning_remains_error():
    row = {'status': 'DIFF', 'final_status': 'DIFF', 'expected_mark': '*ABC',
           'oracle_mark': '*XYZ', 'warning': 'LAYOUT_FIXED_CONFLICT', 'flags': ''}
    assert classify(row)[0] == 'ERR'


def test_equal_text_that_needs_review_is_not_shown_as_true():
    row = {'status': 'NEEDS_REVIEW', 'final_status': 'NEEDS_REVIEW',
           'expected_mark': 'ABC', 'oracle_mark': 'ABC', 'warning': '', 'flags': 'RULE_CONFLICT'}
    assert classify(row)[0] == 'ERR'
