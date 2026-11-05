"""Generate an isolated, local-only review page from a completed run."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile


def isolate_review(source: str, run_hash: str) -> str:
    old_key = 'LKEY="r1-review-v1"'
    old_cloud = 'const c=window.claude;'
    if source.count(old_key) != 1 or source.count(old_cloud) != 1:
        raise ValueError('Review template storage markers changed; cannot safely isolate')
    return source.replace(old_key, f'LKEY="mark-review-{run_hash[:16]}"').replace(old_cloud, 'const c=null;')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--in', dest='input_dir', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256((args.input_dir / 'metrics.json').read_bytes()).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as temporary:
        temp = Path(temporary) / 'review.html'
        subprocess.run([sys.executable, '-m', 'scripts.make_review_page', '--in', str(args.input_dir),
                        '--snapshot', str(args.snapshot), '--title', args.title, '--template',
                        str(repo / 'scripts/review_page_template.html'), '--out', str(temp)], check=True)
        safe = isolate_review(temp.read_text(encoding='utf-8'), digest)
        temp.write_text(safe, encoding='utf-8')
        temp.replace(args.out)
    print('Local-only isolated review:', args.out)


if __name__ == '__main__':
    main()
