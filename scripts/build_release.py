"""Build separate source bundles for the engine, AI worker and DBA."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from mark_engine.freeze import check_freeze

ALLOWED = {'.py', '.json', '.csv', '.html', '.md', '.toml', '.sql'}


def build_unit(root: Path, output: Path, inputs: list[str]) -> None:
    files = set()
    for name in inputs:
        path = root / name
        if not path.exists():
            raise FileNotFoundError(path)
        candidates = path.rglob('*') if path.is_dir() else (path,)
        files.update(p for p in candidates if p.is_file() and p.suffix in ALLOWED
                     and '__pycache__' not in p.parts and not p.name.startswith('.env'))
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(root).as_posix())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--freeze', type=Path, default=Path('mark_engine/rules/data/FREEZE-R1.json'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    freeze = check_freeze(root, args.freeze)
    units = {
        'engine.zip': ['mark_engine', 'scripts', 'services/inference', 'services/engine',
                       'models/REGISTRY.json', 'pyproject.toml'],
        'inference.zip': ['services/inference'],
        'database.zip': ['services/database', 'migrations/0004_line_result_review_columns.sql'],
    }
    hashes = {}
    for name, inputs in units.items():
        output = args.out / name
        build_unit(root, output, inputs)
        hashes[name] = hashlib.sha256(output.read_bytes()).hexdigest()
    (args.out / 'release-manifest.json').write_text(json.dumps({'freeze': freeze, 'units': hashes}, indent=2), encoding='utf-8')
    print('Release units:', ', '.join(units))


if __name__ == '__main__':
    main()
