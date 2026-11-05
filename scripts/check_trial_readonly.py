"""Read-only real-DB acceptance check for trial runs (spec §8).

Checks 8 acceptance points against PostgreSQL and router functions without modifying DB state.
Never prints customer mark values, SLR text, or file paths.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "services" / "api"
for p in (REPO_ROOT, API_ROOT):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

from mark_api.repo import Repo
from mark_api.routers.mark import list_runs, list_elrs, get_elr
from mark_api.routers.validation import dashboard
from mark_engine.adapters.env import load_env


def check_runs(repo: Repo, run: int) -> tuple[bool, str]:
    try:
        runs = list_runs(user={}, repo=repo)
        found = any(r.get("run_id") == run for r in runs)
        if not found:
            return False, f"run {run} not found in runs list ({len(runs)} runs)"
        return True, f"found run {run} in {len(runs)} runs"
    except Exception as e:
        return False, f"exception: {type(e).__name__}"


def check_dashboard_cards(repo: Repo, run: int) -> tuple[bool, str]:
    try:
        d = dashboard(run=run, user={}, repo=repo)
        cards = d.get("cards", {})
        for k in ("TRUE", "WARNING", "ERROR", "HOLD"):
            if k not in cards:
                return False, f"missing card {k}"
        c_true = cards["TRUE"].get("count")
        c_warn = cards["WARNING"].get("count")
        c_err = cards["ERROR"].get("count")
        c_hold = cards["HOLD"].get("count")
        summary_str = f"TRUE {c_true}, WARNING {c_warn}, ERROR {c_err}, HOLD {c_hold}"
        if run == 19:
            expected = (866, 214, 41, 34)
            actual = (c_true, c_warn, c_err, c_hold)
            if actual != expected:
                return False, f"counts mismatch: expected TRUE 866, WARNING 214, ERROR 41, HOLD 34; got {summary_str}"
        return True, summary_str
    except Exception as e:
        return False, f"exception: {type(e).__name__}"


def check_elrs_total(repo: Repo, run: int) -> tuple[bool, str, list[dict[str, Any]], int]:
    try:
        jobs = repo.jobs(run)
        p1 = list_elrs(run=run, page=1, user={}, repo=repo)
        total = p1.get("total")
        jobs_count = len(jobs)
        if total != jobs_count:
            return False, f"list_elrs total ({total}) != repo.jobs count ({jobs_count})", jobs, total or 0
        if run == 19 and total != 402:
            return False, f"run 19 total expected 402, got {total}", jobs, total
        return True, f"total={total} jobs={jobs_count}", jobs, total
    except Exception as e:
        return False, f"exception: {type(e).__name__}", [], 0


def check_elrs_pages(repo: Repo, run: int, total: int, fallback_elrs: list[str]) -> tuple[bool, str, list[str]]:
    try:
        page_size = 50
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        all_elrs: list[str] = []
        for p in range(1, total_pages + 1):
            res = list_elrs(run=run, page=p, user={}, repo=repo)
            rows = res.get("rows", [])
            for r in rows:
                all_elrs.append(r["elr_no"])
        unique_elrs = sorted(set(all_elrs))
        if len(all_elrs) != total:
            return False, f"walked {len(all_elrs)} rows, expected {total}", unique_elrs or fallback_elrs
        if len(unique_elrs) != total:
            return False, f"unique elr count ({len(unique_elrs)}) != total ({total})", unique_elrs or fallback_elrs
        return True, f"{len(unique_elrs)} unique ELRs across {total_pages} pages", unique_elrs
    except Exception as e:
        return False, f"exception: {type(e).__name__}", fallback_elrs


def check_elr_detail(repo: Repo, run: int, sample_elrs: list[str]) -> tuple[bool, str, dict[str, Any]]:
    details: dict[str, Any] = {}
    try:
        for elr in sample_elrs:
            d = get_elr(elr=elr, run=run, user={}, repo=repo)
            details[elr] = d
        return True, f"sampled {len(sample_elrs)} ELRs OK", details
    except Exception as e:
        return False, f"exception on sample: {type(e).__name__}", details


def check_oracle_raw(sample_elrs: list[str], details: dict[str, Any]) -> tuple[bool, str]:
    try:
        for elr in sample_elrs:
            d = details.get(elr)
            if not d:
                return False, "missing detail for sampled ELR"
            snap = d.get("snapshot")
            if not snap:
                return False, "missing snapshot for sampled ELR"
            raw = snap.get("oracle_top_raw")
            if not isinstance(raw, list) or len(raw) != 5:
                count = len(raw) if isinstance(raw, list) else "non-list"
                return False, f"oracle_top_raw has {count} entries, expected 5"
        return True, f"sampled {len(sample_elrs)} snapshots have 5 oracle_top_raw entries"
    except Exception as e:
        return False, f"exception: {type(e).__name__}"


def check_expected_match(repo: Repo, run: int, sample_elrs: list[str], details: dict[str, Any]) -> tuple[bool, str]:
    try:
        for elr in sample_elrs:
            d = details.get(elr)
            if not d:
                return False, "missing detail for sampled ELR"
            detail_lines = d.get("lines", [])
            repo_lines = repo.lines_for_elr(run, elr)
            if len(detail_lines) != len(repo_lines):
                return False, f"line count mismatch ({len(detail_lines)} vs {len(repo_lines)})"
            for i, dl in enumerate(detail_lines):
                rl = repo_lines[i]
                exp_d = dl.get("expected") or ""
                exp_r = rl.get("expected") or ""
                if str(exp_d) != str(exp_r):
                    return False, f"line {i+1} expected mismatch"
        return True, f"sampled {len(sample_elrs)} ELRs line expected values match"
    except Exception as e:
        return False, f"exception: {type(e).__name__}"


def check_admin_reads(repo: Repo, run: int) -> tuple[bool, str]:
    try:
        today = datetime.now(timezone.utc).date()
        d_from = today - timedelta(days=13)
        d_to = today
        users = repo.admin_users()
        repo.activity(d_from, d_to, run)
        aud = repo.audit_events(d_from, d_to, user_id=None, action=None, page=1)
        return True, f"admin_users ({len(users)}), activity, audit_events ({len(aud)}) OK"
    except Exception as e:
        return False, f"exception: {type(e).__name__}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only acceptance check against real DB for a trial run.")
    parser.add_argument("--run", type=int, required=True, help="Run ID to check (e.g. 19)")
    parser.add_argument("--env-file", type=str, default=None, help="Path to .env file")
    parser.add_argument("--sample", type=int, default=20, help="Number of ELRs to sample for detail checks (default: 20)")
    args = parser.parse_args()

    if args.env_file:
        load_env(Path(args.env_file), override=True)
    else:
        load_env()

    repo = Repo()
    run = args.run
    sample_size = args.sample
    all_passed = True

    # Check 1: runs
    ok_runs, val_runs = check_runs(repo, run)
    if ok_runs:
        print(f"OK runs {val_runs}")
    else:
        print(f"FAIL runs {val_runs}")
        all_passed = False

    # Check 2: dashboard_cards
    ok_dash, val_dash = check_dashboard_cards(repo, run)
    if ok_dash:
        print(f"OK dashboard_cards {val_dash}")
    else:
        print(f"FAIL dashboard_cards {val_dash}")
        all_passed = False

    # Check 3: elrs_total
    ok_tot, val_tot, jobs, total = check_elrs_total(repo, run)
    if ok_tot:
        print(f"OK elrs_total {val_tot}")
    else:
        print(f"FAIL elrs_total {val_tot}")
        all_passed = False

    fallback_elrs = sorted(j.get("elr_no", "") for j in jobs if j.get("elr_no"))

    # Check 4: elrs_pages
    ok_pages, val_pages, unique_elrs = check_elrs_pages(repo, run, total, fallback_elrs)
    if ok_pages:
        print(f"OK elrs_pages {val_pages}")
    else:
        print(f"FAIL elrs_pages {val_pages}")
        all_passed = False

    # Determine sample ELRs (first N by elr_no)
    target_elrs = unique_elrs if unique_elrs else fallback_elrs
    sample_elrs = target_elrs[:sample_size]

    # Check 5: elr_detail
    ok_detail, val_detail, details = check_elr_detail(repo, run, sample_elrs)
    if ok_detail:
        print(f"OK elr_detail {val_detail}")
    else:
        print(f"FAIL elr_detail {val_detail}")
        all_passed = False

    # Check 6: oracle_raw
    ok_oracle, val_oracle = check_oracle_raw(sample_elrs, details)
    if ok_oracle:
        print(f"OK oracle_raw {val_oracle}")
    else:
        print(f"FAIL oracle_raw {val_oracle}")
        all_passed = False

    # Check 7: expected_match
    ok_match, val_match = check_expected_match(repo, run, sample_elrs, details)
    if ok_match:
        print(f"OK expected_match {val_match}")
    else:
        print(f"FAIL expected_match {val_match}")
        all_passed = False

    # Check 8: admin_reads
    ok_admin, val_admin = check_admin_reads(repo, run)
    if ok_admin:
        print(f"OK admin_reads {val_admin}")
    else:
        print(f"FAIL admin_reads {val_admin}")
        all_passed = False

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
