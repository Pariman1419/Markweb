import dataclasses
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from mark_engine.adapters.snapshot import load_elr_snapshot, r0_root, verify_r0_root
from mark_engine.domain.models import ElrMeta, OracleMark, Side


FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "elr_meta_sample.json"


def test_elr_meta_has_no_mark_fields():
    field_names = [f.name.lower() for f in dataclasses.fields(ElrMeta)]
    assert not any("mark1" in name for name in field_names)
    assert not any("top_mark" in name for name in field_names)
    assert not any("back_mark" in name for name in field_names)


def test_load_elr_snapshot_returns_dict_with_meta_and_oracle():
    data = load_elr_snapshot(FIXTURE_PATH)
    assert isinstance(data, dict)
    assert len(data) == 3
    assert set(data.keys()) == {"ADI2699001", "ADI2699002", "ADI2699003"}

    meta1, mark1 = data["ADI2699001"]
    assert isinstance(meta1, ElrMeta)
    assert isinstance(mark1, OracleMark)

    assert meta1.elr_no == "ADI2699001"
    assert meta1.cust_bom_no == "ABS068301"
    assert meta1.cust_bom_revision == "ENG-1"
    assert meta1.cust_req_no == "SLR232022"
    assert meta1.cust_assy_lot == "7284173.1"
    assert meta1.product_no == "2433WCCPC-ANKL4Z"
    assert meta1.package_code == "TQC700E700B048K"
    assert meta1.status == "R"
    assert meta1.current_step == "7"
    assert meta1.import_date == "2026-02-24T06:51:47.000Z"
    assert meta1.top_type_code == "E"
    assert meta1.top_layout_code == "ZG"
    assert meta1.mark_remark == "'@ = PIN ONE DOT,% = ADI LOGO , YYWW = Cust date code generate by system"
    assert meta1.mark_require == "XXXXXXXXX = Cust assy generate by system"

    # Oracle lines are stripped
    assert mark1.get(Side.TOP, 1) == "@%"
    assert mark1.get(Side.TOP, 2) == "AD2433W"
    assert mark1.get(Side.TOP, 3) == "CCPZY20"
    assert mark1.get(Side.TOP, 4) == "XXXXXXXXX"
    assert mark1.get(Side.TOP, 5) == "2.0#YYWW"
    assert mark1.get(Side.BOTTOM, 1) == ""


def test_snapshot_empty_strings_become_none_in_meta():
    data = load_elr_snapshot(FIXTURE_PATH)
    meta2, mark2 = data["ADI2699002"]

    # CUST_REQ_NO was "   " -> stripped to empty -> None
    assert meta2.cust_req_no is None
    assert meta2.cust_bom_no == "ABS064938"

    # Bottom marks in row 2
    assert mark2.get(Side.TOP, 1) == "LTGYF"
    assert mark2.get(Side.TOP, 2) == "*"
    assert mark2.get(Side.TOP, 3) == "e3"
    assert mark2.get(Side.TOP, 4) == ""
    assert mark2.get(Side.BOTTOM, 1) == "THAI"
    assert mark2.get(Side.BOTTOM, 2) == "YWXX"
    assert mark2.get(Side.BOTTOM, 3) == ""

    meta3, mark3 = data["ADI2699003"]
    # CUST_BOM_REVISION was "" -> None
    assert meta3.cust_bom_revision is None
    assert len(mark3.lines) == 0


def test_r0_root_reads_env_or_default(monkeypatch):
    monkeypatch.delenv("MARK_R0_ROOT", raising=False)
    assert r0_root() == Path("D:/CIM Project/mark")

    monkeypatch.setenv("MARK_R0_ROOT", "/custom/r0/path")
    assert r0_root() == Path("/custom/r0/path")


def test_verify_r0_root_raises_when_directory_missing(tmp_path):
    missing_dir = tmp_path / "does_not_exist"
    with pytest.raises(RuntimeError, match="does not exist"):
        verify_r0_root(missing_dir)


def test_verify_r0_root_runs_git_diff(tmp_path):
    existing_dir = tmp_path / "fake_repo"
    existing_dir.mkdir()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "-C", str(existing_dir), "diff", "--quiet", "regression-r0-2026-11-04", "--", "experiments"],
            returncode=0,
        )
        verify_r0_root(existing_dir)
        mock_run.assert_called_once_with(
            ["git", "-C", str(existing_dir), "diff", "--quiet", "regression-r0-2026-11-04", "--", "experiments"],
            capture_output=True,
            check=False,
        )


def test_verify_r0_root_raises_on_git_failure(tmp_path):
    existing_dir = tmp_path / "fake_repo"
    existing_dir.mkdir()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git"],
            returncode=1,
            stderr=b"diff detected",
        )
        with pytest.raises(RuntimeError, match="regression-r0-2026-11-04"):
            verify_r0_root(existing_dir)
