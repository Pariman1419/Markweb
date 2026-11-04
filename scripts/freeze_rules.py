"""Freeze the reviewed engine and inference code for an official blind run."""
import argparse
from pathlib import Path
import subprocess

from mark_engine.freeze import write_freeze


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path('mark_engine/rules/data/FREEZE-R1.json'))
    parser.add_argument('--rule-version', default='RV-2026-11-04-R0')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['git', 'status', '--porcelain', '--', 'mark_engine', 'scripts',
                             'services/inference', 'models/REGISTRY.json'], cwd=root,
                            capture_output=True, text=True, check=True)
    if result.stdout.strip():
        raise RuntimeError('Commit or otherwise resolve engine and inference changes before freezing')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    record = write_freeze(root, args.out, args.rule_version)
    print('Created', args.out, 'code SHA-256:', record['code_sha256'])


if __name__ == '__main__':
    main()
