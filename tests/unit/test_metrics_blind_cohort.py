from mark_engine.domain.models import ElrMeta, JobResult, OracleMark, ProcessingStatus, Side
from mark_engine.regression.metrics import compute


def test_july_auto_job_is_in_auto_denominator():
    job = JobResult('ADI2607001', ProcessingStatus.DONE, layout_source='auto')
    metrics = compute([job])
    assert metrics['by_layout_source']['auto']['coverage_elr_denom'] == 1
    assert metrics['by_layout_source']['human_crop']['coverage_elr_denom'] == 0


def test_blind_job_without_inference_is_not_human_crop():
    job = JobResult('ADI2607002', ProcessingStatus.HOLD, layout_source='none')
    metrics = compute([job])
    assert metrics['by_layout_source']['human_crop']['coverage_elr_denom'] == 0
    assert metrics['by_layout_source']['none']['coverage_elr_denom'] == 1


def test_failed_layout_job_keeps_oracle_lines_in_coverage_denominator():
    elr = 'ADI2607003'
    job = JobResult(elr, ProcessingStatus.FAILED, hold_reason='LAYOUT_ERROR', layout_source='auto')
    snapshot = {elr: (ElrMeta(elr), OracleMark(elr, ((Side.TOP, 1, 'ABC'), (Side.TOP, 2, 'DEF'))))}
    metrics = compute([job], snapshot)
    assert metrics['coverage_line_denom'] == 2
    assert metrics['by_layout_source']['auto']['coverage_line_denom'] == 2
