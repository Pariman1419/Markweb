"""Compare inference service output against frozen run-19 cache.

Validates that:
- Page items match det_rec.json (box count, box within 1 px, text equal, score within 0.01)
- Symbols match detections.json (class multiset, box within 1 px, conf within 0.01)
- Re-OCR results match reocr.csv (key and text equal)

Outputs summary.json and diffs.csv (image_sha256, kind, field).
NO raw OCR text is output in diffs.csv or summary.json to comply with privacy rules.
"""
from collections import Counter
import csv
import io
import json
import os
import sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mark_engine.abs.layout import layout_lines
from mark_engine.abs.reocr import legend_candidates, trim_logo
from mark_engine.adapters.inference_service import InferenceClient, InferenceUnavailable

REOCR_MIN_SCORE = 0.85


def compare_single_image(
    client: InferenceClient,
    image_name: str,
    image_bytes: bytes,
    cached_page: list | None,
    cached_symbols: list | None,
    cached_reocr_rows: list[dict] | None,
    service_cache: dict | None = None,
) -> list[tuple[str, str, str]]:
    """Compare inference service output for a single image with cache.

    Returns list of (image_sha256, kind, field) tuples representing diffs.
    """
    stem = Path(image_name).stem
    diffs = []

    if service_cache is not None and image_name in service_cache:
        service_page, service_symbols, service_reocr_map = service_cache[image_name]
    else:
        # 1. Page OCR
        try:
            service_page = client.page(image_name, image_bytes)
        except Exception:
            service_page = []

        # 2. Symbol detection
        try:
            service_symbols = client.symbols(image_name, image_bytes)
        except Exception:
            service_symbols = []

        # 3. Re-OCR
        service_reocr_map = {}
        if service_page:
            with Image.open(io.BytesIO(image_bytes)) as source:
                image = source.convert("RGB")

            candidates = legend_candidates(image_name, service_page)
            for side, number, text, _, box in layout_lines(service_page):
                key = f"{stem}|{side.value}|{number}"
                if box and not any(row["key"] == key for row in candidates):
                    cropped = trim_logo(image.crop(tuple(int(x) for x in box)))
                    if cropped:
                        candidates.append({"key": key, "old": text.strip(), "image": cropped, "method": "trim_logo"})

            if candidates:
                crops = []
                for candidate in candidates:
                    crop = candidate.get("image") or image.crop(candidate["box"])
                    buf = io.BytesIO()
                    crop.convert("RGB").save(buf, "PNG")
                    crops.append(buf.getvalue())
                try:
                    rec_results = client.rec(crops)
                    for candidate, (new_text, score) in zip(candidates, rec_results):
                        new = (new_text or "").strip()
                        service_reocr_map[candidate["key"]] = new
                except Exception:
                    pass

        if service_cache is not None:
            service_cache[image_name] = (service_page, service_symbols, service_reocr_map)

    # 1. Page OCR comparison
    if not service_page and cached_page:
        diffs.append((stem, "page", "service_error"))
    elif cached_page is not None and service_page:
        if len(service_page) != len(cached_page):
            diffs.append((stem, "page", "box_count"))
        else:
            # Sort both by y0, x0 for stable comparison
            s_sorted = sorted(service_page, key=lambda x: (round(x[1], 1), round(x[0], 1)))
            c_sorted = sorted(cached_page, key=lambda x: (round(x[1], 1), round(x[0], 1)))
            for s_item, c_item in zip(s_sorted, c_sorted):
                # Box check: within 1 px
                box_match = all(abs(s - c) <= 1.0 for s, c in zip(s_item[:4], c_item[:4]))
                if not box_match:
                    diffs.append((stem, "page", "box"))
                    break
                # Text check: exact match
                if str(s_item[4]) != str(c_item[4]):
                    diffs.append((stem, "page", "text"))
                    break
                # Score check: within 0.01
                if abs(float(s_item[5]) - float(c_item[5])) > 0.01:
                    diffs.append((stem, "page", "score"))
                    break

    # 2. Symbol detection comparison
    if service_symbols is None or (not service_symbols and cached_symbols):
        diffs.append((stem, "symbol", "service_error"))
    elif cached_symbols is not None and service_symbols is not None:
        s_classes = Counter(sym[0] for sym in service_symbols)
        c_classes = Counter(sym[0] for sym in cached_symbols)
        if s_classes != c_classes:
            diffs.append((stem, "symbol", "class_multiset"))
        elif len(service_symbols) != len(cached_symbols):
            diffs.append((stem, "symbol", "count"))
        else:
            s_sorted = sorted(service_symbols, key=lambda x: (x[0], round(x[3], 1), round(x[2], 1)))
            c_sorted = sorted(cached_symbols, key=lambda x: (x[0], round(x[3], 1), round(x[2], 1)))
            for s_sym, c_sym in zip(s_sorted, c_sorted):
                # Box within 1 px
                box_match = all(abs(s - c) <= 1.0 for s, c in zip(s_sym[2:6], c_sym[2:6]))
                if not box_match:
                    diffs.append((stem, "symbol", "box"))
                    break
                # Conf within 0.01
                if abs(float(s_sym[1]) - float(c_sym[1])) > 0.01:
                    diffs.append((stem, "symbol", "conf"))
                    break

    # 3. Re-OCR comparison
    cached_reocr_map = {row["key"]: row["new"].strip() for row in (cached_reocr_rows or []) if row.get("key", "").startswith(stem)}
    for k, c_new in cached_reocr_map.items():
        if k not in service_reocr_map:
            diffs.append((stem, "reocr", "missing_key"))
        elif service_reocr_map[k] != c_new:
            diffs.append((stem, "reocr", "text"))

    for k in service_reocr_map:
        if k not in cached_reocr_map:
            diffs.append((stem, "reocr", "unexpected_key"))

    return diffs


def run_comparison(
    cache_dir: Path,
    client: InferenceClient,
    out_dir: Path,
    limit: int | None = None,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    health = client.health()
    device = health.get("ocr_device", "unknown")
    service_version = health.get("model", {}).get("service_version", "0.1.0")

    index_csv = cache_dir / "images_index.csv"
    with open(index_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        index_rows = list(reader)

    if limit:
        index_rows = index_rows[:limit]

    det_rec_path = cache_dir / "det_rec.json"
    det_rec = json.loads(det_rec_path.read_text(encoding="utf-8")) if det_rec_path.exists() else {}

    detections_path = cache_dir / "detections.json"
    detections = json.loads(detections_path.read_text(encoding="utf-8")) if detections_path.exists() else {}

    reocr_path = cache_dir / "reocr.csv"
    reocr_rows = []
    if reocr_path.exists():
        with open(reocr_path, newline="", encoding="utf-8") as f:
            reocr_rows = list(csv.DictReader(f))

    all_diffs = []
    passed_images = 0
    service_cache = {}

    for idx, row in enumerate(index_rows, start=1):
        image_name = row["image"]
        stem = Path(image_name).stem
        image_file = cache_dir / "images" / image_name
        if not image_file.exists():
            continue
        image_bytes = image_file.read_bytes()

        cached_page = det_rec.get(image_name)
        cached_syms = detections.get(stem)

        diffs = compare_single_image(
            client=client,
            image_name=image_name,
            image_bytes=image_bytes,
            cached_page=cached_page,
            cached_symbols=cached_syms,
            cached_reocr_rows=reocr_rows,
            service_cache=service_cache,
        )

        if not diffs:
            passed_images += 1
        else:
            all_diffs.extend(diffs)

        if idx % 20 == 0 or idx == len(index_rows):
            print(f"Compared {idx}/{len(index_rows)} images (passed: {passed_images}, diffs: {len(all_diffs)})", flush=True)

    page_diffs = sum(1 for d in all_diffs if d[1] == "page")
    symbol_diffs = sum(1 for d in all_diffs if d[1] == "symbol")
    reocr_diffs = sum(1 for d in all_diffs if d[1] == "reocr")

    summary = {
        "images_total": len(index_rows),
        "images_passed": passed_images,
        "page_diffs": page_diffs,
        "symbol_diffs": symbol_diffs,
        "reocr_diffs": reocr_diffs,
        "total_diff_records": len(all_diffs),
        "device": device,
        "service_version": service_version,
    }

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    diffs_csv = out_dir / "diffs.csv"
    with open(diffs_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["image_sha256", "kind", "field"])
        for d in all_diffs:
            writer.writerow(list(d))

    return summary


def main():
    import argparse
    from mark_engine.adapters.env import load_env

    load_env()

    parser = argparse.ArgumentParser(description="Compare inference service output against cache")
    parser.add_argument("--cache", default="artifacts/blind-2026h2/cache", help="Path to cache directory")
    parser.add_argument("--addr", default=os.getenv("MARK_INFERENCE_ADDR", "10.151.28.9:50051"), help="Inference server address")
    parser.add_argument("--api-key", default=os.getenv("MARK_INFERENCE_API_KEY", ""), help="API key")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of images")

    args = parser.parse_args()

    client = InferenceClient(args.addr, api_key=args.api_key)
    summary = run_comparison(
        cache_dir=Path(args.cache),
        client=client,
        out_dir=Path(args.out),
        limit=args.limit,
    )
    print("Comparison complete:")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
