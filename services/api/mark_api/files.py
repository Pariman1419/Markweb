"""File safety guards."""
from pathlib import Path


def safe_file(root: Path, relative: str) -> Path | None:
    try:
        resolved_root = Path(root).resolve()
        candidate = (resolved_root / relative).resolve()
        # Must be inside root and not root itself
        candidate.relative_to(resolved_root)
        if candidate == resolved_root:
            return None
        if not candidate.is_file():
            return None
        return candidate
    except (ValueError, RuntimeError, OSError):
        return None
