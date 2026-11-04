import json
from pathlib import Path
import pytest

ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "regression-r1"


@pytest.mark.regression
def test_r1_independence_is_one():
    metrics_path = ARTIFACTS_DIR / "metrics.json"
    assert metrics_path.is_file(), f"Metrics file not found: {metrics_path}. Run scripts/run_regression.py first."

    with open(metrics_path, encoding="utf-8") as f:
        metrics = json.load(f)

    assert metrics.get("independence") == 1.0, f"Expected independence 1.0, got {metrics.get('independence')}"


@pytest.mark.regression
def test_r1_no_bug_parity():
    summary_path = ARTIFACTS_DIR / "parity_summary.json"
    assert summary_path.is_file(), f"Parity summary file not found: {summary_path}. Run scripts/run_regression.py first."

    with open(summary_path, encoding="utf-8") as f:
        summary = json.load(f)

    bug_count = summary.get("BUG", 0)
    assert bug_count == 0, f"Found {bug_count} parity rows classified as BUG: see artifacts/regression-r1/parity.csv"
