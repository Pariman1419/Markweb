from pathlib import Path
import hashlib

from mark_engine.abs.auto_inference import build_auto_inference
from mark_engine.adapters.snapshot import _load_csv_cached, _load_json_cached, _load_reocr
from mark_engine.domain.models import InferenceResult


def validate_cached_document(cache_dir: Path, elr_no: str, pdf: Path, resolved_sha256: str) -> None:
    rows = [row for row in _load_csv_cached(str(cache_dir / 'images_index.csv'))
            if row.get('elr', '').upper() == elr_no.upper() and row.get('abs_file', '').upper() == pdf.stem.upper()]
    if len(rows) != 1 or not rows[0].get('source_sha256'):
        raise ValueError(f'{elr_no}: missing or duplicate source ABS fingerprint')
    expected = rows[0]['source_sha256']
    actual = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if expected != resolved_sha256 or expected != actual:
        raise ValueError(f'{elr_no}: ABS content changed since image extraction')


def load_cached_inference(cache_dir: Path, elr_no: str, abs_stem: str) -> InferenceResult:
    required = [cache_dir / name for name in ('images_index.csv', 'det_rec.json', 'detections.json', 'reocr.csv')]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f'Inference cache missing: {path}')
    matching = [row for row in _load_csv_cached(str(required[0]))
                if row.get('elr', '').upper() == elr_no.upper()
                and row.get('abs_file', '').upper() == abs_stem.upper()]
    if len(matching) > 1:
        raise ValueError(f'{elr_no}: duplicate inference index entries')
    if not matching:
        raise ValueError(f'{elr_no}: no inference index for resolved ABS {abs_stem}')
    name = matching[0]['image']
    stem = Path(name).stem
    det_rec = _load_json_cached(str(required[1]))
    detections = _load_json_cached(str(required[2]))
    if name not in det_rec or stem not in detections:
        raise ValueError(f'{elr_no}: incomplete inference cache for {name}')
    return build_auto_inference(elr_no, stem, det_rec[name], detections[stem], _load_reocr(str(required[3])))
