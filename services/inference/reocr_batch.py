"""Re-read legend values and optional dark-logo crops through the OCR service."""
import argparse
import csv
import io
import json
from pathlib import Path
import re

LEGEND = re.compile(r'^\s*(?:L|LINE)\s*([1-9])\s*:\s*(\S.*)$', re.I)


def legend_candidates(name, items):
    rows = []
    for x0, y0, x1, y1, text, _ in items:
        match = LEGEND.match(text)
        if match:
            cut = x0 + (x1 - x0) * (text.index(':') + 1) / len(text)
            rows.append({'key': f'{Path(name).stem}|TOP|{match.group(1)}',
                         'old': match.group(2).strip(),
                         'box': (int(cut) + 2, int(y0) - 2, int(x1) + 6, int(y1) + 2),
                         'method': 'legend_value'})
    return rows


def trim_logo(image):
    import numpy as np
    darkness = (np.asarray(image.convert('L')) < 100).mean(axis=0)
    width, height = image.size
    xs = np.where(darkness > 0.5)[0]
    if not len(xs) or xs[0] > 0.25 * width:
        return None
    x = int(xs[0])
    while x < width and not (darkness[x:x + 4] < 0.02).all():
        x += 1
    if x - xs[0] < 0.5 * height or x > 0.6 * width or darkness[xs[0]:x].max() < 0.9:
        return None
    return image.crop((min(width - 1, x + max(3, height // 8)), 0, width, height))


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
