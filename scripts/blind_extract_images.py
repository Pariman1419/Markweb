"""Resolve documents and extract blind ABS images; input documents remain read-only."""
import argparse
import csv
import hashlib
import os
from pathlib import Path

from mark_engine.abs.brand_page import extract_brand_image
from mark_engine.adapters.env import load_env
from mark_engine.adapters.snapshot import load_elr_snapshot
from mark_engine.documents.resolve import resolve_documents
from mark_engine.documents.locate import build_folder_index


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--nas-root', type=Path)
    parser.add_argument('--months', nargs='+', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    load_env()
    root = args.nas_root or Path(os.environ['NAS_ROOT']) / 'ELR Online 2026'
    missing = [str(root / month) for month in args.months if not (root / month).is_dir()]
    if missing:
        raise SystemExit('NAS month unavailable: ' + ', '.join(missing))
    images = args.out / 'images'
    folder_index = build_folder_index(root, args.months)
    images.mkdir(parents=True, exist_ok=True)
    rows, skipped = [], []
    for elr_no, (meta, _) in sorted(load_elr_snapshot(args.snapshot).items()):
        try:
            resolution = resolve_documents(meta, root, args.months, args.out / 'work', folder_index=folder_index)
            if resolution.decision != 'RESOLVED' or resolution.abs is None:
                skipped.append({'elr': elr_no, 'reason': resolution.hold_reason or 'NO_ABS'})
                continue
            data, method, page = extract_brand_image(Path(resolution.abs.path))
            if hashlib.sha256(Path(resolution.abs.path).read_bytes()).hexdigest() != resolution.abs.sha256:
                raise ValueError('ABS changed during image extraction')
            digest = hashlib.sha256(data).hexdigest()
            name = digest + '.png'
            destination = images / name
            if not destination.exists():
                destination.write_bytes(data)
            elif hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f'Image hash mismatch: {destination}')
            rows.append({'elr': elr_no, 'abs_file': Path(resolution.abs.path).stem,
                         'image': name, 'method': method, 'page': page, 'sha256': digest,
                         'source_sha256': resolution.abs.sha256})
        except Exception as exc:
            skipped.append({'elr': elr_no, 'reason': f'EXTRACT_ERROR: {type(exc).__name__}: {exc}'})
        if (len(rows) + len(skipped)) % 25 == 0:
            print('processed', len(rows) + len(skipped), flush=True)
    for filename, fields, values in [('images_index.csv', ['elr', 'abs_file', 'image', 'method', 'page', 'sha256', 'source_sha256'], rows),
                                     ('extract_skipped.csv', ['elr', 'reason'], skipped)]:
        with (args.out / filename).open('w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(values)
    print('extracted:', len(rows), 'skipped:', len(skipped))


if __name__ == '__main__':
    main()
