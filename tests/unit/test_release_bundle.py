from zipfile import ZipFile
from scripts.build_release import build_unit


def test_release_bundle_excludes_secrets_and_python_caches(tmp_path):
    (tmp_path / 'services' / 'inference').mkdir(parents=True)
    (tmp_path / 'services' / 'inference' / 'worker.py').write_text('pass')
    (tmp_path / 'services' / 'inference' / '.env').write_text('SECRET=do-not-copy')
    cache = tmp_path / 'services' / 'inference' / '__pycache__'
    cache.mkdir()
    (cache / 'worker.pyc').write_bytes(b'cache')
    out = tmp_path / 'unit.zip'
    build_unit(tmp_path, out, ['services/inference'])
    with ZipFile(out) as z:
        assert z.namelist() == ['services/inference/worker.py']
