import csv
from mark_engine.domain.models import JobResult, ProcessingStatus
from mark_engine.regression.artifacts import write_jobs_csv, write_lines_csv


def test_failed_job_is_recorded_and_has_no_false_lines(tmp_path):
    job = JobResult('ADI2607001', ProcessingStatus.FAILED, hold_reason='LAYOUT_ERROR')
    write_jobs_csv(tmp_path / 'jobs.csv', [job])
    write_lines_csv(tmp_path / 'lines.csv', [job])
    with (tmp_path / 'jobs.csv').open(encoding='utf-8', newline='') as f:
        row = next(csv.DictReader(f))
    assert row['processing_status'] == 'FAILED'
    assert row['hold_reason'] == 'LAYOUT_ERROR'
    with (tmp_path / 'lines.csv').open(encoding='utf-8', newline='') as f:
        assert list(csv.DictReader(f)) == []
