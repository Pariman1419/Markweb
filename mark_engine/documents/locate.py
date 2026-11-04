import re
from pathlib import Path
from typing import Iterable

RANGE_PATTERN = re.compile(r"^ADI(\d{4})(\d{3})-(\d{1,3})$")


def build_folder_index(root: Path, months: Iterable[str]) -> dict[str, tuple[Path, ...]]:
    """Snapshot month directory entries once for a batch; fail on missing months."""
    result = {}
    for month in months:
        directory = root / month
        if not directory.is_dir():
            raise FileNotFoundError(f'NAS month unavailable: {directory}')
        result[month] = tuple(sorted((p for p in directory.iterdir() if p.is_dir()), key=lambda p: p.name))
    return result


def find_elr_folders(root: Path, elr_no: str, months: Iterable[str], *,
                     index: dict[str, tuple[Path, ...]] | None = None) -> list[tuple[Path, str]]:
    """Scan <root>/<month> for directories matching the given ELR number.

    Returns a list of tuples (folder_path, kind) where kind is one of:
      - 'exact': folder name matches elr_no exactly
      - 'range': folder name is a range like ADI2603011-14 containing elr_no
      - 'annotated': folder name starts with elr_no followed by whitespace
    """
    results: list[tuple[Path, str]] = []

    for month in months:
        month_dir = root / month
        if index is not None:
            if month not in index:
                raise ValueError(f'month absent from folder index: {month}')
            subdirs = index[month]
        else:
            if not month_dir.is_dir():
                continue
            subdirs = sorted([p for p in month_dir.iterdir() if p.is_dir()], key=lambda p: p.name)
        for folder in subdirs:
            name = folder.name

            # 1. Exact match
            if name == elr_no:
                results.append((folder, "exact"))
                continue

            # 2. Annotated match: starts with elr_no followed by whitespace
            if name.startswith(elr_no) and len(name) > len(elr_no) and name[len(elr_no)].isspace():
                results.append((folder, "annotated"))
                continue

            # 3. Range match: ^ADI(\d{4})(\d{3})-(\d{1,3})$
            m = RANGE_PATTERN.match(name)
            if m:
                year_month = m.group(1)   # e.g. "2603"
                start_str = m.group(2)    # e.g. "011"
                end_str = m.group(3)      # e.g. "14"

                n = len(end_str)
                prefix = f"ADI{year_month}"
                lo = int(start_str[-n:])
                hi = int(end_str)
                if lo <= hi:
                    base_prefix = f"{prefix}{start_str[:-n]}"
                    matched_elrs = {f"{base_prefix}{str(i).zfill(n)}" for i in range(lo, hi + 1)}
                    if elr_no in matched_elrs:
                        results.append((folder, "range"))
                        continue

    return results
