"""Batch symbol detection on the AI host."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('weights', type=Path)
    parser.add_argument('images', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--device', default='0')
    args = parser.parse_args()
    from ultralytics import YOLO

    model = YOLO(str(args.weights))
    output = {}
    for path in sorted(args.images.glob('*.png')):
        result = model.predict(str(path), imgsz=1024, conf=0.25, device=args.device, verbose=False)[0]
        output[path.stem] = [
            [result.names[int(cls)], round(float(score), 3)] + [round(float(value), 1) for value in box]
            for cls, score, box in zip(result.boxes.cls, result.boxes.conf, result.boxes.xyxy)
        ]
    args.output.write_text(json.dumps(output), encoding='utf-8')


if __name__ == '__main__':
    main()
