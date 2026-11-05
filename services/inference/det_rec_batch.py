"""Batch detection/recognition; thin CLI wrapper over OcrEngine."""
import argparse
import json
from pathlib import Path

from services.inference.engines import OcrEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('images', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--recognizer', default='/models/exp09')
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args()

    engine = OcrEngine(device=args.device, recognizer_dir=args.recognizer)
    output = {}
    for path in sorted(args.images.glob('*.png')):
        items = engine.page(path.read_bytes())
        output[path.name] = items
        print(path.name, len(items), flush=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
