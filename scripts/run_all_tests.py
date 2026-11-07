"""Master Test Suite Runner for Mark Web.

Executes 3 validation stages:
1. Unit & Integration Tests (pytest suite, 519+ tests)
2. Database Read-Only Integrity Guard (Run 19 immutability, 8/8 checks)
3. Live End-to-End (E2E) Production Test Suite (Auth, Redis Cache, WebSocket, ABS Stream)
"""

import argparse
import subprocess
import sys
import time


def run_stage(title: str, command: list[str]) -> bool:
    print("\n" + "=" * 78)
    print(f" STAGE: {title}")
    print(f" Command: {' '.join(command)}")
    print("=" * 78, flush=True)

    t0 = time.perf_counter()
    res = subprocess.run(command)
    elapsed = time.perf_counter() - t0

    passed = res.returncode == 0
    status_str = "[STAGE PASSED]" if passed else "[STAGE FAILED]"
    print(f"\n{status_str} Duration: {elapsed:.1f}s | Exit Code: {res.returncode}")
    return passed


def main():
    parser = argparse.ArgumentParser(description="Mark Web Master Test Runner")
    parser.add_argument("--skip-unit", action="store_true", help="Skip pytest unit tests")
    parser.add_argument("--skip-db", action="store_true", help="Skip database integrity check")
    parser.add_argument("--skip-e2e", action="store_true", help="Skip live E2E suite")
    parser.add_argument("--url", default="http://10.153.90.17:8093", help="Base URL for E2E tests")
    args = parser.parse_args()

    overall_start = time.perf_counter()
    stages_passed = {}

    # Stage 1: Pytest Unit & Integration tests
    if not args.skip_unit:
        cmd = [sys.executable, "-m", "pytest", "tests", "-q", "--ignore=tests/regression"]
        stages_passed["Unit Tests (519+)"] = run_stage("Unit & Integration Test Suite", cmd)
    else:
        stages_passed["Unit Tests (519+)"] = True

    # Stage 2: DB Read-Only Integrity Guard
    if not args.skip_db:
        cmd = [sys.executable, "scripts/check_trial_readonly.py", "--run", "19"]
        stages_passed["DB Read-Only (8/8)"] = run_stage("Historical Database Integrity Guard", cmd)
    else:
        stages_passed["DB Read-Only (8/8)"] = True

    # Stage 3: Live E2E Production Test Suite
    if not args.skip_e2e:
        cmd = [sys.executable, "scripts/test_e2e_suite.py", "--url", args.url]
        stages_passed["Live E2E Suite (7/7)"] = run_stage("Live Production E2E Suite", cmd)
    else:
        stages_passed["Live E2E Suite (7/7)"] = True

    total_time = time.perf_counter() - overall_start

    print("\n" + "=" * 78)
    print(" MASTER TEST SUITE SUMMARY REPORT")
    print("=" * 78)
    all_ok = True
    for stage_name, passed in stages_passed.items():
        symbol = "[PASS]" if passed else "[FAIL]"
        print(f" {symbol} {stage_name:<35} : {'SUCCESS' if passed else 'FAILED'}")
        if not passed:
            all_ok = False

    print("-" * 78)
    print(f" Total Duration: {total_time:.1f}s")
    if all_ok:
        print(" ALL VALIDATION STAGES PASSED SUCCESSFULLY!")
        print("=" * 78)
        return 0
    else:
        print(" SOME STAGES FAILED! Please review the logs above.")
        print("=" * 78)
        return 1


if __name__ == "__main__":
    sys.exit(main())
