import json
import csv
import pytest
from scripts.run_blind import preflight, independence_check
from mark_engine.domain.models import ExpectedMark, JobResult, ProcessingStatus


def test_preflight_refuses_missing_nas_month(tmp_path):
    with pytest.raises(FileNotFoundError, match='9_SEP'):
        preflight(tmp_path, ['9_SEP'], tmp_path / 'cache')


def test_preflight_refuses_incomplete_cache(tmp_path):
    (tmp_path / '9_SEP').mkdir()
    cache = tmp_path / 'cache'
    cache.mkdir()
    with pytest.raises(FileNotFoundError, match='images_index.csv'):
        preflight(tmp_path, ['9_SEP'], cache)


def test_preflight_refuses_unverified_model_manifest(tmp_path):
    (tmp_path / '9_SEP').mkdir()
    cache = tmp_path / 'cache'
    (cache / 'images').mkdir(parents=True)
    (cache / 'images' / 'image.png').write_bytes(b'png')
    with (cache / 'images_index.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=['elr', 'image'])
        writer.writeheader()
        writer.writerow({'elr': 'ADI2609001', 'image': 'image.png'})
    (cache / 'det_rec.json').write_text(json.dumps({'image.png': []}))
    (cache / 'detections.json').write_text(json.dumps({'image': []}))
    (cache / 'reocr.csv').write_text('key,old,new,score,method\n')
    (cache / 'models.json').write_text('{}')
    with pytest.raises(ValueError, match='model provenance'):
        preflight(tmp_path, ['9_SEP'], cache)


def test_independence_detects_asymmetric_missing_expected():
    original = JobResult('A', ProcessingStatus.FAILED)
    blank = JobResult('A', ProcessingStatus.DONE, expected=ExpectedMark('A', (), 'r', 'e'))
    with pytest.raises(RuntimeError, match='Independence'):
        independence_check([(original, blank)])
