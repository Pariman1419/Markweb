import csv
import json

import pytest
from mark_engine.adapters.inference_cache import load_cached_inference, validate_cached_document


def test_missing_inference_files_are_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_cached_inference(tmp_path, 'ADI2607001', 'ABS000001')


def test_cache_reads_image_and_empty_detections(tmp_path):
    with (tmp_path / 'images_index.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['elr', 'abs_file', 'image'])
        writer.writeheader()
        writer.writerow({'elr': 'ADI2607001', 'abs_file': 'ABS000001', 'image': 'x.png'})
    (tmp_path / 'det_rec.json').write_text(json.dumps({'x.png': []}), encoding='utf-8')
    (tmp_path / 'detections.json').write_text(json.dumps({'x': []}), encoding='utf-8')
    (tmp_path / 'reocr.csv').write_text('key,old,new,score,method\n', encoding='utf-8')
    result = load_cached_inference(tmp_path, 'ADI2607001', 'ABS000001')
    assert result.layout_source == 'auto' and not result.lines


def test_resolved_elr_with_no_image_is_an_error(tmp_path):
    (tmp_path / 'images_index.csv').write_text('elr,abs_file,image\n', encoding='utf-8')
    (tmp_path / 'det_rec.json').write_text('{}', encoding='utf-8')
    (tmp_path / 'detections.json').write_text('{}', encoding='utf-8')
    (tmp_path / 'reocr.csv').write_text('key,old,new,score,method\n', encoding='utf-8')
    with pytest.raises(ValueError, match='no inference index'):
        load_cached_inference(tmp_path, 'ADI2607001', 'ABS000001')


def test_inference_requires_same_abs_content_as_extracted_image(tmp_path):
    import hashlib
    pdf = tmp_path / 'ABS000001.pdf'
    pdf.write_bytes(b'original')
    sha = hashlib.sha256(b'original').hexdigest()
    (tmp_path / 'images_index.csv').write_text(
        f'elr,abs_file,image,source_sha256\nADI2607001,ABS000001,x.png,{sha}\n', encoding='utf-8')
    validate_cached_document(tmp_path, 'ADI2607001', pdf, sha)
    pdf.write_bytes(b'changed')
    with pytest.raises(ValueError, match='ABS content'):
        validate_cached_document(tmp_path, 'ADI2607001', pdf, sha)
    changed = hashlib.sha256(b'changed').hexdigest()
    with pytest.raises(ValueError, match='ABS content'):
        validate_cached_document(tmp_path, 'ADI2607001', pdf, changed)
