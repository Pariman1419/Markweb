import csv
import json
from pathlib import Path
import pytest

from scripts.load_app_snapshot import build_snapshot_rows


@pytest.fixture
def snapshot_fixtures(tmp_path):
    oracle_dir = tmp_path / "oracle"
    cache_dir = tmp_path / "cache"
    run_dir = tmp_path / "run"
    run_hold_dir = tmp_path / "run_hold"

    oracle_dir.mkdir()
    cache_dir.mkdir()
    (cache_dir / "images").mkdir()
    run_dir.mkdir()
    run_hold_dir.mkdir()

    # oracle
    meta = [
        {
            "ELR_NO": "ADI2607001",
            "TOP_MARK_ID": 25077.0,
            "TOP_LAYOUT_CODE": "ZE",
            "TOP_MARK1": "@% PKG#",
            "TOP_MARK2": "41200",
            "TOP_MARK3": "DUMMY",
            "TOP_MARK4": "40 LFCSP",
            "TOP_MARK5": None,
            "MARK_REMARK": "@ = Pin one dot",
            "MARK_REQUIRE": None,
            "TOP_TEMPLATE_REMARK": None,
        }
    ]
    (oracle_dir / "elr_meta.json").write_text(json.dumps(meta), encoding="utf-8")

    layout = {
        "25077": [
            [1, 1, "@"],
            [1, 2, "%"],
        ]
    }
    (oracle_dir / "mark_layout.json").write_text(json.dumps(layout), encoding="utf-8")

    # cache
    (cache_dir / "images" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    with open(cache_dir / "images_index.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["elr", "abs_file", "image", "method", "page", "sha256", "source_sha256"])
        w.writerow(["ADI2607001", "ABS071290-ENG-1", "a.png", "raster", "1", "hash_a", "src_hash_a"])

    # run
    with open(run_dir / "jobs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["elr_no", "abs_no", "processing_status"])
        w.writerow(["ADI2607001", "ABS071290-ENG-1", "DONE"])

    with open(run_dir / "lines.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["elr_no", "side", "line_no", "compare_rules", "flags", "detail"])
        w.writerow(["ADI2607001", "TOP", "1", "EXACT", "", ""])
        w.writerow(["ADI2607001", "TOP", "2", "EXACT", "", ""])

    # run_hold
    with open(run_hold_dir / "jobs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["elr_no", "abs_no", "processing_status"])
        w.writerow(["ADI2607002", "", "HOLD"])

    with open(run_hold_dir / "lines.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["elr_no", "side", "line_no", "compare_rules", "flags", "detail"])

    # empty cache for hold only
    cache_hold_dir = tmp_path / "cache_hold"
    cache_hold_dir.mkdir()
    with open(cache_hold_dir / "images_index.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["elr", "abs_file", "image", "method", "page", "sha256", "source_sha256"])

    oracle_hold_dir = tmp_path / "oracle_hold"
    oracle_hold_dir.mkdir()
    meta_hold = [
        {
            "ELR_NO": "ADI2607002",
            "TOP_MARK_ID": None,
            "TOP_LAYOUT_CODE": None,
            "TOP_MARK1": None,
            "TOP_MARK2": None,
            "TOP_MARK3": None,
            "TOP_MARK4": None,
            "TOP_MARK5": None,
            "MARK_REMARK": None,
            "MARK_REQUIRE": None,
            "TOP_TEMPLATE_REMARK": None,
        }
    ]
    (oracle_hold_dir / "elr_meta.json").write_text(json.dumps(meta_hold), encoding="utf-8")
    (oracle_hold_dir / "mark_layout.json").write_text(json.dumps({}), encoding="utf-8")

    return {
        "oracle": oracle_dir,
        "cache": cache_dir,
        "run": run_dir,
        "run_hold": run_hold_dir,
        "cache_hold": cache_hold_dir,
        "oracle_hold": oracle_hold_dir,
    }


def test_snapshot_row_has_five_oracle_rows_and_layout_grid(snapshot_fixtures):
    f = snapshot_fixtures
    row = build_snapshot_rows(18, f["oracle"], f["cache"], f["run"])[0]
    assert len(row["oracle_top_raw"]) == 5 and row["oracle_top_raw"][4] == ""
    assert len(row["layout_cells"]) == 5 and len(row["layout_cells"][0]) == 18
    assert row["layout_cells"][0][0] == "@" and row["layout_cells"][0][5] is None  # unlisted = free


def test_mark_id_float_and_line_extra(snapshot_fixtures):
    f = snapshot_fixtures
    row = build_snapshot_rows(18, f["oracle"], f["cache"], f["run"])[0]  # fixture TOP_MARK_ID = 25077.0
    assert row["top_mark_id"] == 25077 and row["line_extra"]["1"]["compare_rules"] == "EXACT"


def test_hold_elr_without_image_has_null_image_path(snapshot_fixtures):
    f = snapshot_fixtures
    assert build_snapshot_rows(18, f["oracle_hold"], f["cache_hold"], f["run_hold"])[0]["image_path"] is None
