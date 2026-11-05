"""Re-read legend values and optional dark-logo crops through the OCR service."""
import argparse
import csv
import io
import json
from pathlib import Path

from mark_engine.abs.reocr import legend_candidates, trim_logo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('images', type=Path)
    parser.add_argument('det_rec', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--url', default='http://10.151.28.9:8095')
    parser.add_argument('--trim-logo', action='store_true', help='also process auto-layout line boxes (requires mark_engine)')
    args = parser.parse_args()
    import requests
    from PIL import Image
    if args.trim_logo:
        from mark_engine.abs.layout import layout_lines
    data = json.loads(args.det_rec.read_text(encoding='utf-8'))
    results = []
    for name, items in sorted(data.items()):
        path = args.images / name
        if not path.is_file():
            raise FileNotFoundError(path)
        with Image.open(path) as original:
            image = original.convert('RGB')
        candidates = legend_candidates(name, items)
        if args.trim_logo:
            for side, number, text, _, box in layout_lines(items):
                key = f'{Path(name).stem}|{side.value}|{number}'
                if box and not any(row['key'] == key for row in candidates):
                    cropped = trim_logo(image.crop(tuple(int(x) for x in box)))
                    if cropped:
                        candidates.append({'key': key, 'old': text.strip(), 'image': cropped, 'method': 'trim_logo'})
        for candidate in candidates:
            crop = candidate.get('image') or image.crop(candidate['box'])
            buffer = io.BytesIO()
            crop.convert('RGB').save(buffer, 'PNG')
            response = requests.post(args.url.rstrip('/') + '/ocr', files={'file': ('crop.png', buffer.getvalue(), 'image/png')}, timeout=60)
            response.raise_for_status()
            result = response.json()
            results.append({'key': candidate['key'], 'old': candidate['old'], 'new': result['text'],
                            'score': round(float(result['score']), 4), 'method': candidate['method']})
    with args.output.open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=['key', 'old', 'new', 'score', 'method'])
        writer.writeheader()
        writer.writerows(results)
    print('re-OCR candidates:', len(results))


if __name__ == '__main__':
    main()
