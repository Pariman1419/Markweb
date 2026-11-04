"""Portable CSV exports consumed by review and database loaders."""
import csv
from pathlib import Path
from mark_engine.domain.models import LineStatus
from mark_engine.regression.metrics import COMPARED_STATUSES, MATCH_ALL_STATUSES

LINE_FIELDS = ['elr_no', 'side', 'line_no', 'layout_source', 'expected_mark', 'oracle_mark', 'status',
               'flags', 'compare_rules', 'detail', 'warning', 'processing_status', 'hold_reason',
               'hold_detail', 'review_detail', 'review_verdict', 'review_note', 'final_status']
JOB_FIELDS = ['elr_no', 'processing_status', 'hold_reason', 'hold_detail', 'review_detail',
              'verification_status', 'approval_status', 'layout_source', 'abs_no', 'total_lines',
              'compared_lines', 'match_lines', 'diff_lines', 'needs_review_lines']


def _write(path, fields, rows):
    with path.open('w', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def write_lines_csv(path: Path, jobs) -> int:
    rows = []
    for job in jobs:
        for comparison in job.comparisons:
            line = job.expected.line(comparison.side, comparison.line_no) if job.expected else None
            status = comparison.status.value
            rows.append({'elr_no': job.elr_no, 'side': comparison.side.value, 'line_no': comparison.line_no,
                         'layout_source': job.layout_source, 'expected_mark': comparison.expected or '',
                         'oracle_mark': comparison.oracle, 'status': status,
                         'flags': ';'.join(sorted(flag.value for flag in line.flags)) if line else '',
                         'compare_rules': ';'.join(comparison.compare_rules), 'detail': comparison.detail,
                         'warning': comparison.warning, 'processing_status': job.processing_status.value,
                         'hold_reason': job.hold_reason or '',
                         'hold_detail': job.resolution.hold_detail or '' if job.resolution else '',
                         'review_detail': job.resolution.review_detail or '' if job.resolution else '',
                         'review_verdict': '', 'review_note': '', 'final_status': status})
    return _write(path, LINE_FIELDS, rows)


def write_jobs_csv(path: Path, jobs) -> int:
    rows = []
    for job in jobs:
        comparisons = job.comparisons
        rows.append({'elr_no': job.elr_no, 'processing_status': job.processing_status.value,
                     'hold_reason': job.hold_reason or '',
                     'hold_detail': job.resolution.hold_detail or '' if job.resolution else '',
                     'review_detail': job.resolution.review_detail or '' if job.resolution else '',
                     'verification_status': job.verification_status.value if job.verification_status else '',
                     'approval_status': job.approval_status.value, 'layout_source': job.layout_source,
                     'abs_no': Path(job.resolution.abs.path).stem if job.resolution and job.resolution.abs else '',
                     'total_lines': len(comparisons),
                     'compared_lines': sum(c.status in COMPARED_STATUSES for c in comparisons),
                     'match_lines': sum(c.status in MATCH_ALL_STATUSES for c in comparisons),
                     'diff_lines': sum(c.status == LineStatus.DIFF for c in comparisons),
                     'needs_review_lines': sum(c.status == LineStatus.NEEDS_REVIEW for c in comparisons)})
    return _write(path, JOB_FIELDS, rows)
