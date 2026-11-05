"""Reconstruct run-17 layout errors for a local-only comparison page.

The frozen engine and input files are verified; this tool writes only to the
chosen artifact directory and never changes the stored DB run.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import csv
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from zipfile import ZipFile

from mark_engine.adapters.env import load_env
from mark_engine.adapters.inference_cache import load_cached_inference, validate_cached_document
from mark_engine.adapters.snapshot import load_elr_snapshot
from mark_engine.documents.locate import build_folder_index
from mark_engine.domain.models import Side
from mark_engine.generate.mark_layout import LayoutError, fill_line_with_conflicts, parse_layout
from mark_engine.rules.ruleset import RuleSet
import mark_engine.pipeline as pipeline

MONTHS = ['7_JUL', '8_AUG', '9_SEP', '10_OCT', '11_NOV']


def safe_json(value):
    return json.dumps(value, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


def make_line(layout, number, line, oracle_raw):
    generated = line.text or '' if line else ''
    if line:
        prefix = ''.join(t.text for t in line.tokens if t.source == 'REMARK')
        if prefix and generated.startswith(prefix + ' '):
            generated = prefix + generated[len(prefix) + 1:]
    cells = [layout.cells.get((number, col)) for col in range(1, 19)]
    try:
        rendered, conflicts = fill_line_with_conflicts(layout, number, generated)
        status, error = 'ok', ''
    except LayoutError as exc:
        rendered, conflicts, status, error = None, (), 'error', str(exc)
    return {'number': number, 'raw_generated': line.text or '' if line else '',
            'generated': generated, 'layout': cells, 'oracle': (oracle_raw or '')[3:21].ljust(18),
            'rendered': rendered, 'conflicts': conflicts, 'status': status, 'error': error}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_engine(repo, archive):
    with ZipFile(archive) as z:
        frozen = {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()
                  if n.startswith('mark_engine/') and n.endswith(('.py', '.json', '.csv'))
                  and not Path(n).name.startswith('FREEZE-')}
    current = {p.relative_to(repo).as_posix(): sha(p) for p in (repo / 'mark_engine').rglob('*')
               if p.is_file() and p.suffix in ('.py', '.json', '.csv')
               and '__pycache__' not in p.parts and not p.name.startswith('FREEZE-')}
    if current != frozen:
        raise RuntimeError('Current engine differs from archived run-17 engine; use the archived engine')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=Path('artifacts/blind-2026h2'))
    parser.add_argument('--out', type=Path, default=Path('artifacts/blind-2026h2/overflow-review'))
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    verify_engine(repo, repo / 'artifacts/release-run17/engine.zip')
    run, cache, source = args.data / 'run', args.data / 'cache', args.data / 'oracle'
    metrics = json.loads((run / 'metrics.json').read_text(encoding='utf-8'))
    for name, expected in metrics['input_sha256'].items():
        if sha(Path(name)) != expected:
            raise RuntimeError(f'run-17 input hash differs: {name}')
    if sha(run / 'jobs.csv') != metrics['output_sha256']['jobs.csv']:
        raise RuntimeError('run-17 jobs.csv differs from the frozen result')
    with (run / 'jobs.csv').open(encoding='utf-8', newline='') as f:
        jobs = [r for r in csv.DictReader(f) if r['processing_status'] == 'FAILED' and 'overflow' in r['hold_reason']]
    snapshot = load_elr_snapshot(source / 'elr_meta.json')
    raw_layouts = json.loads((source / 'mark_layout.json').read_text(encoding='utf-8'))
    layouts = {int(k): parse_layout(int(k), [dict(zip(('MARK_ROW', 'MARK_COLUMN', 'MARK_DATA'), cell)) for cell in v])
               for k, v in raw_layouts.items()}
    with (cache / 'images_index.csv').open(encoding='utf-8', newline='') as f:
        image_index = {r['elr']: r for r in csv.DictReader(f)}
    load_env()
    root = Path(os.environ['NAS_ROOT']) / 'ELR Online 2026'
    folder_index = build_folder_index(root, MONTHS)
    rules = RuleSet.load()
    loader = partial(load_cached_inference, cache)
    validate = partial(validate_cached_document, cache)
    context = threading.local()
    original_generate = pipeline.generate_expected

    def capture(*args, **kwargs):
        result = original_generate(*args, **kwargs)
        context.expected = result
        return result

    pipeline.generate_expected = capture

    def replay(prior):
        elr = prior['elr_no']
        context.expected = None
        meta, oracle = snapshot[elr]
        record = {'elr': elr, 'mark_id': meta.top_mark_id, 'recorded_error': prior['hold_reason'],
                  'abs': prior['abs_no'], 'image': image_index.get(elr, {}).get('image', ''), 'lines': [],
                  'verified': False, 'replay_error': ''}
        try:
            job = pipeline.process_elr(meta, oracle, root, MONTHS, args.out / 'work', rules, loader,
                                       layouts=layouts, folder_index=folder_index, inference_validator=validate)
            expected = context.expected
            if expected is None or job.hold_reason != prior['hold_reason']:
                raise RuntimeError(f'Unable to reproduce recorded outcome (now: {job.hold_reason or job.processing_status})')
            record['lines'] = [make_line(layouts[meta.top_mark_id], n, expected.line(Side.TOP, n), oracle.get_raw(Side.TOP, n))
                               for n in range(1, 6)]
            record['verified'] = True
        except Exception as exc:
            record['replay_error'] = f'{type(exc).__name__}: {exc}'
        return record

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(replay, jobs))
    finally:
        pipeline.generate_expected = original_generate
    args.out.mkdir(parents=True, exist_ok=True)
    template = (repo / 'services/engine/overflow_review.html').read_text(encoding='utf-8')
    html = template.replace('/*OVERFLOW_DATA*/[]', safe_json(results)).replace('/*RUN_HASH*/""', json.dumps(metrics['output_sha256']['jobs.csv']))
    (args.out / 'index.html').write_text(html, encoding='utf-8')
    print('Recorded overflows:', len(results), 'reproduced:', sum(x['verified'] for x in results),
          'unavailable:', sum(not x['verified'] for x in results), flush=True)


if __name__ == '__main__':
    main()
