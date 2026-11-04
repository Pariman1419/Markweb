"""Produce separate confirmed and pending review lists for Marking / Mark Eng."""
import argparse
import csv
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def marking_team_rows(lines):
    confirmed, pending = [], []
    for line in lines:
        final = line.get('final_status') or line.get('status', '')
        status = line.get('status', '')
        detail = line.get('review_detail', '')
        if final == 'DB_WRONG':
            destination, issue = confirmed, 'DB_WRONG'
        elif status in ('DIFF', 'NEEDS_REVIEW') or detail.startswith(('REVISION_MISMATCH', 'PRODUCT_NO_ABS_MISMATCH')):
            destination, issue = pending, status or 'REVIEW'
        else:
            continue
        destination.append({'elr_no': line.get('elr_no', ''), 'side': line.get('side', ''),
                            'line_no': line.get('line_no', ''), 'oracle_mark': line.get('oracle_mark', ''),
                            'expected_mark': line.get('expected_mark', ''), 'issue': issue,
                            'detail': detail or line.get('detail', '')})
    return confirmed, pending


def rule_approval_rows():
    document = (ROOT / 'docs/implementation/07-open-decisions.md').read_text(encoding='utf-8')
    decisions = {}
    stages = {22: 'compare', 23: 'gate', 24: 'resolver', 25: 'review',
              26: 'review', 27: 'inference', 28: 'resolver', 29: 'generate'}
    for line in document.splitlines():
        match = re.match(r'^\|\s*(D-2[2-9])\s*\|\s*(.*?)\s*\|\s*$', line)
        if match:
            number = int(match.group(1)[2:])
            text = match.group(2)
            example = re.search(r'ADI\d{7}', text)
            decisions[match.group(1)] = {'decision': match.group(1), 'title': text,
                                         'rule_stage': stages[number], 'example_elr': example.group() if example else '',
                                         'effect_lines_run14': '', 'approval': ''}
    expected = {f'D-{number}' for number in range(22, 30)}
    if set(decisions) != expected:
        raise ValueError(f'Decisions missing: {sorted(expected - decisions.keys())}')
    return [decisions[key] for key in sorted(decisions)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lines', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    with args.lines.open(encoding='utf-8-sig', newline='') as file:
        confirmed, pending = marking_team_rows(csv.DictReader(file))
    args.out.mkdir(parents=True, exist_ok=True)
    line_fields = ['elr_no', 'side', 'line_no', 'oracle_mark', 'expected_mark', 'issue', 'detail']
    for name, fields, rows in [('marking_confirmed.csv', line_fields, confirmed),
                               ('marking_pending.csv', line_fields, pending),
                               ('rule_approval.csv', ['decision', 'title', 'rule_stage', 'example_elr',
                                                      'effect_lines_run14', 'approval'], rule_approval_rows())]:
        with (args.out / name).open('w', encoding='utf-8-sig', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    print('confirmed:', len(confirmed), 'pending:', len(pending))


if __name__ == '__main__':
    main()
