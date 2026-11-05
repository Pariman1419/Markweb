"""Compare two regression runs and report ELR and line-level state changes."""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


def job_state(row: dict) -> str:
    """Compute state string for a job row: processing_status:(hold_reason|verification_status)."""
    p_status = (row.get("processing_status") or "").strip()
    if p_status in ("HOLD", "FAILED"):
        detail = (row.get("hold_reason") or "").strip()
    else:
        detail = (row.get("verification_status") or "").strip()
    return f"{p_status}:{detail}"


def diff_jobs(base: list[dict], new: list[dict]) -> dict[tuple[str, str], list[str]]:
    """Map (old_state, new_state) -> sorted list of changed elr_no."""
    base_map = {r["elr_no"]: job_state(r) for r in base}
    new_map = {r["elr_no"]: job_state(r) for r in new}

    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    all_elrs = sorted(set(base_map.keys()) | set(new_map.keys()))
    for elr in all_elrs:
        b_st = base_map.get(elr, "MISSING")
        n_st = new_map.get(elr, "MISSING")
        if b_st != n_st:
            groups[(b_st, n_st)].append(elr)

    for k in groups:
        groups[k].sort()
    return dict(groups)


def _load_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def diff_runs(base_dir: Path, new_dir: Path) -> None:
    base_jobs = _load_csv(base_dir / "jobs.csv")
    new_jobs = _load_csv(new_dir / "jobs.csv")

    groups = diff_jobs(base_jobs, new_jobs)

    print("=" * 60)
    print(f"RUN DIFF REPORT: {base_dir.name} -> {new_dir.name}")
    print("=" * 60)

    print("\n--- JOB-LEVEL CHANGES ---")
    if not groups:
        print("No job state changes.")
    else:
        for (b_st, n_st), elrs in sorted(groups.items(), key=lambda x: -len(x[1])):
            print(f"{b_st} -> {n_st}: {len(elrs)}")
            print(f"  ELRs ({len(elrs)}): {', '.join(elrs)}")

    # Line-level summary from lines.csv
    base_lines_p = base_dir / "lines.csv"
    new_lines_p = new_dir / "lines.csv"
    if base_lines_p.is_file() and new_lines_p.is_file():
        base_lines = _load_csv(base_lines_p)
        new_lines = _load_csv(new_lines_p)
        base_counts = Counter(r.get("final_status", "") for r in base_lines)
        new_counts = Counter(r.get("final_status", "") for r in new_lines)

        print("\n--- LINE-LEVEL FINAL_STATUS COUNTS ---")
        all_statuses = sorted(set(base_counts.keys()) | set(new_counts.keys()))
        for st in all_statuses:
            b_cnt = base_counts.get(st, 0)
            n_cnt = new_counts.get(st, 0)
            diff = n_cnt - b_cnt
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            print(f"  {st:20s}: base={b_cnt:5d} -> new={n_cnt:5d} ({diff_str})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Diff two regression runs")
    parser.add_argument("--base", type=Path, required=True, help="Base run directory")
    parser.add_argument("--new", type=Path, required=True, help="New run directory")
    args = parser.parse_args()

    diff_runs(args.base, args.new)


if __name__ == "__main__":
    main()
