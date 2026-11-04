import pytest
from mark_engine.freeze import tree_hash, write_freeze, check_freeze


def test_freeze_refuses_changed_engine_or_inference(tmp_path):
    root = tmp_path / 'repo'
    (root / 'mark_engine').mkdir(parents=True)
    (root / 'services' / 'inference').mkdir(parents=True)
    (root / 'mark_engine' / 'x.py').write_text('a=1\n')
    (root / 'services' / 'inference' / 'worker.py').write_text('b=1\n')
    manifest = root / 'freeze.json'
    write_freeze(root, manifest, 'R1')
    check_freeze(root, manifest)
    (root / 'services' / 'inference' / 'worker.py').write_text('b=2\n')
    with pytest.raises(RuntimeError, match='changed'):
        check_freeze(root, manifest)


def test_hash_changes_with_filename_even_if_content_equal(tmp_path):
    folder = tmp_path / 'mark_engine'
    folder.mkdir()
    (folder / 'a.py').write_text('x')
    before = tree_hash(tmp_path)
    (folder / 'a.py').rename(folder / 'b.py')
    assert tree_hash(tmp_path) != before
