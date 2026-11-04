from pathlib import Path
import pytest


@pytest.fixture
def month_tree(tmp_path: Path) -> Path:
    """Create a mock NAS root containing month directories."""
    root = tmp_path / "nas"
    for m in ["1_JAN", "2_FEB", "3_MAR", "4_APR", "5_MAY", "6_JUN"]:
        (root / m).mkdir(parents=True, exist_ok=True)
    return root
