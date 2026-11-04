import json

from mark_engine.adapters.snapshot import load_elr_snapshot


def test_snapshot_reads_top_mark_id(tmp_path):
    path = tmp_path / 'elr.json'
    path.write_text(json.dumps([{'ELR_NO': 'ADI2601085', 'TOP_MARK_ID': 20168}]), encoding='utf-8')
    meta, _ = load_elr_snapshot(path)['ADI2601085']
    assert meta.top_mark_id == 20168


def test_snapshot_retains_untrimmed_oracle_positions(tmp_path):
    path = tmp_path / 'elr.json'
    path.write_text(json.dumps([{'ELR_NO': 'ADI2601085', 'TOP_MARK1': '   *  YYWW           '}]), encoding='utf-8')
    _, oracle = load_elr_snapshot(path)['ADI2601085']
    from mark_engine.domain.models import Side
    assert oracle.get(Side.TOP, 1) == '*  YYWW'
    assert oracle.get_raw(Side.TOP, 1) == '   *  YYWW           '
