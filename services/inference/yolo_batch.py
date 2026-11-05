"""Batch symbol detection; thin CLI wrapper over SymbolEngine."""
import argparse
import json
from pathlib import Path

from services.inference.engines import SymbolEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('weights', type=Path)
    parser.add_argument('images', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--device', default='0')
    args = parser.parse_args()

    engine = SymbolEngine(device=args.device, weights=str(args.weights))
    output = {}
    for path in sorted(args.images.glob('*.png')):
        output[path.stem] = engine.symbols(path.read_bytes())
    args.output.write_text(json.dumps(output), encoding='utf-8')


if __name__ == '__main__':
    main()
