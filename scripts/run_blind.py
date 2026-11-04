"""Run a frozen, cache-backed blind evaluation; never infer on this host."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import csv
import hashlib
import json
import os
from pathlib import Path

from mark_engine.adapters.env import load_env
from mark_engine.adapters.inference_cache import load_cached_inference
from mark_engine.adapters.snapshot import load_elr_snapshot
from mark_engine.documents.locate import build_folder_index
from mark_engine.domain.models import OracleMark, ProcessingStatus
from mark_engine.freeze import check_freeze
from mark_engine.generate.mark_layout import parse_layout
from mark_engine.pipeline import process_elr
from mark_engine.regression.artifacts import write_jobs_csv, write_lines_csv
from mark_engine.regression.metrics import compute
from mark_engine.rules.ruleset import RuleSet


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def independence_check(pairs):
    failures = [a.elr_no for a, b in pairs if a.expected != b.expected]
    checked = [(a, b) for a, b in pairs if a.expected is not None and b.expected is not None]
    if failures or not checked:
        raise RuntimeError(f'Independence check failed or has no evaluable jobs: {len(failures)} mismatches')
    return len(checked), len(pairs) - len(checked)


def preflight(root: Path, months: list[str], cache: Path) -> None:
    for month in months:
        if not (root / month).is_dir():
            raise FileNotFoundError(f'NAS month unavailable: {root / month}')
    for name in ('images_index.csv', 'det_rec.json', 'detections.json', 'reocr.csv', 'models.json'):
        if not (cache / name).is_file():
            raise FileNotFoundError(f'Inference cache missing: {cache / name}')
    with (cache / 'images_index.csv').open(encoding='utf-8-sig', newline='') as file:
        rows = list(csv.DictReader(file))
    ocr = json.loads((cache / 'det_rec.json').read_text(encoding='utf-8'))
    yolo = json.loads((cache / 'detections.json').read_text(encoding='utf-8'))
    for row in rows:
        name = row['image']
        image = cache / 'images' / name
        if Path(name).name != name or not image.is_file() or name not in ocr or Path(name).stem not in yolo:
            raise ValueError(f'Incomplete cache for {row["elr"]}: {name}')
        if row.get('sha256') and file_hash(image) != row['sha256']:
            raise ValueError(f'Image checksum mismatch for {row["elr"]}: {name}')
    if not rows:
        raise ValueError('Inference image index is empty')
    provenance = json.loads((cache / 'models.json').read_text(encoding='utf-8'))
    required = ('ocr_rec_sha256', 'symbol_sha256', 'detector_sha256', 'ocr_image_id', 'output_sha256')
    if not all(provenance.get(key) for key in required):
        raise ValueError('Incomplete model provenance')
    for field in ('ocr_rec_sha256', 'symbol_sha256', 'detector_sha256'):
        digest = provenance[field]
        if len(digest) != 64 or any(char not in '0123456789abcdef' for char in digest):
            raise ValueError(f'Invalid model provenance: {field}')
    registry_path = Path(__file__).resolve().parents[1] / 'models' / 'REGISTRY.json'
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    expected = {model['name']: model for model in registry['models']}
    if (provenance['ocr_rec_sha256'] != expected['ocr-rec-exp09']['weights_sha256'] or
            provenance['symbol_sha256'] != expected['symdet']['weights_sha256']):
        raise ValueError('Model provenance does not match approved registry')
    validation_path = Path(__file__).resolve().parents[1] / 'services/inference/validation.json'
    validation = json.loads(validation_path.read_text(encoding='utf-8'))
    if provenance.get('validation_sha256') != file_hash(validation_path):
        raise ValueError('AI validation manifest hash differs')
    runtime = provenance.get('runtime', {})
    if any(runtime.get(key) != validation[key] for key in ('ocr_image_id', 'ocr_rec_sha256', 'symbol_sha256',
           'detector_sha256', 'detector_config_sha256', 'detector_settings_sha256', 'ultralytics_version', 'torch_version',
           'client_python', 'client_numpy', 'client_pillow', 'client_requests', 'client_paramiko')):
        raise ValueError('AI runtime differs from validation manifest')
    for name in ('det_rec.json', 'detections.json', 'reocr.csv'):
        if provenance['output_sha256'].get(name) != file_hash(cache / name):
            raise ValueError(f'Inference output checksum mismatch: {name}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--oracle', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--months', nargs='+', required=True)
    parser.add_argument('--nas-root', type=Path)
    parser.add_argument('--freeze', type=Path, default=Path('mark_engine/rules/data/FREEZE-R1.json'))
    parser.add_argument('--allow-unfrozen', action='store_true')
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    load_env()
    repo = Path(__file__).resolve().parents[1]
    try:
        freeze = check_freeze(repo, args.freeze)
    except (FileNotFoundError, RuntimeError):
        if not args.allow_unfrozen:
            raise
        freeze = {'freeze_id': 'UNFROZEN'}
    root = args.nas_root or Path(os.environ['NAS_ROOT']) / 'ELR Online 2026'
    preflight(root, args.months, args.cache)
    input_paths = [args.oracle / 'elr_meta.json', args.oracle / 'mark_layout.json',
                   args.cache / 'images_index.csv', args.cache / 'det_rec.json',
                   args.cache / 'detections.json', args.cache / 'reocr.csv', args.cache / 'models.json']
    input_hashes = {str(path): file_hash(path) for path in input_paths}
    models = json.loads((args.cache / 'models.json').read_text(encoding='utf-8'))
    if models.get('images_index_sha256') != file_hash(args.cache / 'images_index.csv'):
        raise ValueError('Inference model manifest does not match image index')
    if freeze['freeze_id'] != 'UNFROZEN' and (models.get('freeze_id') != freeze['freeze_id'] or
                                               models.get('code_sha256') != freeze['code_sha256']):
        raise ValueError('Inference batch was not generated under this freeze')
    snapshot = load_elr_snapshot(args.oracle / 'elr_meta.json')
    if not snapshot:
        raise ValueError('Oracle snapshot is empty')
    data = json.loads((args.oracle / 'mark_layout.json').read_text(encoding='utf-8'))
    layouts = {int(key): parse_layout(int(key), [dict(zip(('MARK_ROW', 'MARK_COLUMN', 'MARK_DATA'), row)) for row in rows])
               for key, rows in data.items()}
    rules = RuleSet.load()
    index = build_folder_index(root, args.months)
    loader = partial(load_cached_inference, args.cache)
    args.out.mkdir(parents=True, exist_ok=True)

    def process(item):
        meta, oracle = item
        kw = dict(layouts=layouts, folder_index=index)
        job = process_elr(meta, oracle, root, args.months, args.out / 'work', rules, loader, **kw)
        blank = process_elr(meta, OracleMark(meta.elr_no), root, args.months, args.out / 'work', rules, loader, **kw)
        return job, blank

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        pairs = list(executor.map(process, snapshot.values()))
    jobs = [a for a, _ in pairs]
    checked, excluded = independence_check(pairs)
    if any(file_hash(path) != input_hashes[str(path)] for path in input_paths):
        raise RuntimeError('Blind input changed during processing')
    if freeze['freeze_id'] != 'UNFROZEN':
        check_freeze(repo, args.freeze)
    metrics = compute(jobs, snapshot)
    metrics.update({'independence': 1.0, 'independence_num': checked,
                    'independence_denom': checked, 'independence_excluded': excluded,
                    'failed_jobs': sum(job.processing_status == ProcessingStatus.FAILED for job in jobs),
                    'errors': dict(Counter(job.hold_reason for job in jobs if job.processing_status == ProcessingStatus.FAILED)),
                    'freeze': freeze, 'models': models,
                    'input_sha256': input_hashes})
    write_jobs_csv(args.out / 'jobs.csv', jobs)
    write_lines_csv(args.out / 'lines.csv', jobs)
    metrics['output_sha256'] = {name: file_hash(args.out / name) for name in ('jobs.csv', 'lines.csv')}
    (args.out / 'metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    print('jobs:', len(jobs), 'independence:', checked, '/', checked, 'excluded:', excluded,
          'failed:', metrics['failed_jobs'], 'freeze:', freeze['freeze_id'])


if __name__ == '__main__':
    main()
