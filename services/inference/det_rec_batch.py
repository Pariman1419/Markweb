"""Batch detection/recognition; run inside the EXP09 OCR container on the AI host."""
import argparse
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK', 'True')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('images', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--recognizer', default='/models/exp09')
    args = parser.parse_args()
    from paddleocr import TextDetection, TextRecognition
    from PIL import Image

    detector = TextDetection(model_name='PP-OCRv5_server_det', device='cpu', enable_mkldnn=False)
    recognizer = TextRecognition(model_name='PP-OCRv5_server_rec', model_dir=args.recognizer, device='cpu')
    output = {}
    for path in sorted(args.images.glob('*.png')):
        with Image.open(path) as source:
            image = source.convert('RGB')
        width, height = image.size
        boxes = []
        for result in detector.predict(input=str(path), batch_size=1):
            for polygon in result['dt_polys']:
                xs = [float(point[0]) for point in polygon]
                ys = [float(point[1]) for point in polygon]
                pad = 0.15 * (max(ys) - min(ys))
                boxes.append([max(0, min(xs)-pad), max(0, min(ys)-pad), min(width, max(xs)+pad), min(height, max(ys)+pad)])
        items = []
        for box in boxes:
            name = None
            try:
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp:
                    name = temp.name
                image.crop(tuple(round(value) for value in box)).save(name)
                result = next(iter(recognizer.predict(input=name, batch_size=1)))
                items.append([round(value, 1) for value in box] + [result['rec_text'], round(float(result['rec_score']), 4)])
            finally:
                if name:
                    Path(name).unlink(missing_ok=True)
        output[path.name] = items
        print(path.name, len(items), flush=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
