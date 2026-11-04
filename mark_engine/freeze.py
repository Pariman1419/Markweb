"""Detect changes to code and shipped rule data after a blind-test freeze."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    paths = []
    for directory in ('mark_engine', 'services/inference', 'scripts'):
        base = root / directory
        if base.is_dir():
            paths.extend(p for p in base.rglob('*') if p.is_file()
                         and p.suffix in {'.py', '.json', '.csv'}
                         and not p.name.startswith('FREEZE-') and '__pycache__' not in p.parts)
    registry = root / 'models' / 'REGISTRY.json'
    if registry.is_file():
        paths.append(registry)
    for path in sorted(paths, key=lambda p: p.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, 'big'))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, 'big'))
        digest.update(content)
    return digest.hexdigest()


def write_freeze(root: Path, path: Path, rule_version: str) -> dict:
    from mark_engine.version import ENGINE_VERSION
    git = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    record = {'freeze_id': 'FREEZE-R1', 'created_at': datetime.now(timezone.utc).isoformat(),
              'rule_version': rule_version, 'engine_version': ENGINE_VERSION,
              'git_commit': git.stdout.strip() if git.returncode == 0 else None,
              'code_sha256': tree_hash(root)}
    path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record


def check_freeze(root: Path, path: Path) -> dict:
    record = json.loads(path.read_text(encoding='utf-8'))
    if record.get('code_sha256') != tree_hash(root):
        raise RuntimeError('engine or inference code changed since freeze')
    return record
