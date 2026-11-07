"""High-Concurrency Load & Responsiveness Benchmark for Mark Web.

Measures throughput (RPS) and latency percentiles (Min, Mean, P50, P90, P95, P99, Max)
under concurrent workloads across 4 distinct production subsystems:
1. Public Health / Readiness Probe (GET /api/ready)
2. Redis-Cached Aggregation Endpoint (GET /api/dashboard?run=19)
3. PostgreSQL Database Query & Pagination (GET /api/elrs?run=19&page=1)
4. Heavy Asset Streaming (GET /api/files/abs/19/ADI2607003 ~130KB PNG)

Usage:
    python scripts/test_load_performance.py [--url http://10.153.90.17:8093] [--concurrency 10] [--requests 100]
"""

import argparse
import concurrent.futures
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mark_engine.adapters.env import load_env  # noqa: E402


@dataclass
class BenchmarkResult:
    name: str
    total_requests: int
    concurrency: int
    duration_sec: float
    status_counts: dict[int, int] = field(default_factory=dict)
    latencies_ms: List[float] = field(default_factory=list)
    total_bytes: int = 0

    @property
    def rps(self) -> float:
        return self.total_requests / self.duration_sec if self.duration_sec > 0 else 0.0

    @property
    def throughput_kbps(self) -> float:
        return (self.total_bytes / 1024.0) / self.duration_sec if self.duration_sec > 0 else 0.0

    def percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_lat = sorted(self.latencies_ms)
        idx = int(math.ceil((p / 100.0) * len(sorted_lat))) - 1
        return sorted_lat[max(0, min(idx, len(sorted_lat) - 1))]

    @property
    def min_ms(self) -> float:
        return min(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.latencies_ms) if self.latencies_ms else 0.0

    @property
    def mean_ms(self) -> float:
        return sum(self.latencies_ms) / len(self.latencies_ms) if self.latencies_ms else 0.0


def create_pooled_session(concurrency: int, cookies: dict | None = None) -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=concurrency * 2,
        pool_maxsize=concurrency * 2,
        max_retries=Retry(total=2, backoff_factor=0.1, status_forcelist=[502, 503, 504]),
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    if cookies:
        session.cookies.update(cookies)
    return session


def run_benchmark(
    name: str,
    target_fn: Callable[[requests.Session], requests.Response],
    total_requests: int,
    concurrency: int,
    session: requests.Session,
) -> BenchmarkResult:
    latencies = []
    status_counts = {}
    total_bytes = 0

    def worker_task(_):
        t0 = time.perf_counter()
        try:
            resp = target_fn(session)
            latency = (time.perf_counter() - t0) * 1000.0
            return resp.status_code, latency, len(resp.content)
        except Exception:
            latency = (time.perf_counter() - t0) * 1000.0
            return 0, latency, 0

    print(f"[*] Running Benchmark: {name} ({total_requests} reqs @ concurrency={concurrency})...", end="", flush=True)
    t_start = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker_task, i) for i in range(total_requests)]
        for f in concurrent.futures.as_completed(futures):
            code, lat, nbytes = f.result()
            status_counts[code] = status_counts.get(code, 0) + 1
            latencies.append(lat)
            total_bytes += nbytes

    t_duration = time.perf_counter() - t_start
    print(f" Done ({t_duration:.2f}s, {total_requests / t_duration:.1f} RPS)")

    return BenchmarkResult(
        name=name,
        total_requests=total_requests,
        concurrency=concurrency,
        duration_sec=t_duration,
        status_counts=status_counts,
        latencies_ms=latencies,
        total_bytes=total_bytes,
    )


def print_results_table(results: List[BenchmarkResult]):
    print("\n" + "=" * 115)
    print(f"{'ENDPOINT / WORKLOAD':<35} | {'RPS':>7} | {'MIN':>6} | {'MEAN':>6} | {'P50':>6} | {'P95':>6} | {'P99':>6} | {'MAX':>6} | {'STATUS':<15}")
    print("=" * 115)

    for r in results:
        status_str = ", ".join(f"{k}:{v}" for k, v in sorted(r.status_counts.items()))
        print(
            f"{r.name:<35} | {r.rps:>7.1f} | {r.min_ms:>5.1f}m | {r.mean_ms:>5.1f}m | "
            f"{r.percentile(50):>5.1f}m | {r.percentile(95):>5.1f}m | {r.percentile(99):>5.1f}m | "
            f"{r.max_ms:>5.1f}m | {status_str:<15}"
        )
    print("=" * 115)


def main():
    parser = argparse.ArgumentParser(description="Mark Web Concurrency & Load Benchmark")
    parser.add_argument("--url", default="http://10.153.90.17:8093", help="Base URL of Mark Web target")
    parser.add_argument("--concurrency", type=int, default=10, help="Number of concurrent workers (default: 10)")
    parser.add_argument("--requests", type=int, default=100, help="Total requests per endpoint test (default: 100)")
    parser.add_argument("--run", type=int, default=19, help="Historical run to benchmark against (default: 19)")
    args = parser.parse_args()

    load_env()
    eng_u = os.getenv("MARK_TEST_ENGINEER_USER")
    eng_p = os.getenv("MARK_TEST_ENGINEER_PASSWORD")

    if not eng_u or not eng_p:
        print("[FAIL] Missing credentials in .env")
        sys.exit(1)

    print("=" * 80)
    print(" MARK WEB LOAD & RESPONSIVENESS BENCHMARK SUITE")
    print(f" Target Host: {args.url}")
    print(f" Concurrency: {args.concurrency} threads | Volume: {args.requests} requests / test")
    print("=" * 80)

    # 1. Establish authenticated session
    auth_session = requests.Session()
    login_resp = auth_session.post(
        f"{args.url}/api/auth/login",
        json={"username": eng_u, "password": eng_p},
        timeout=8,
    )
    if login_resp.status_code != 200:
        print(f"[FAIL] Could not log in: HTTP {login_resp.status_code}")
        sys.exit(1)

    print(f"[OK] Authenticated session established for user: {eng_u}")
    session_cookies = dict(auth_session.cookies)
    pooled_session = create_pooled_session(args.concurrency, session_cookies)

    # Find sample ELR with image
    elrs_resp = pooled_session.get(f"{args.url}/api/elrs?run={args.run}&page=1").json()
    sample_elr = "ADI2607003"
    for row in elrs_resp.get("rows", []):
        elr_no = row.get("elr_no")
        det = pooled_session.get(f"{args.url}/api/elrs/{elr_no}?run={args.run}").json()
        if det.get("image_available"):
            sample_elr = elr_no
            break

    print(f"[OK] Selected representative image sample: ELR={sample_elr}\n")

    results = []

    # Benchmark 1: API Readiness Probe
    results.append(
        run_benchmark(
            name="1. API Ready Probe (/api/ready)",
            target_fn=lambda s: s.get(f"{args.url}/api/ready", timeout=5),
            total_requests=args.requests,
            concurrency=args.concurrency,
            session=pooled_session,
        )
    )

    # Benchmark 2: Redis Cached Dashboard Cards
    results.append(
        run_benchmark(
            name="2. Redis Cache (/api/dashboard)",
            target_fn=lambda s: s.get(f"{args.url}/api/dashboard?run={args.run}", timeout=5),
            total_requests=args.requests,
            concurrency=args.concurrency,
            session=pooled_session,
        )
    )

    # Benchmark 3: PostgreSQL Database Query & Pagination
    results.append(
        run_benchmark(
            name="3. DB Query (/api/elrs?page=1)",
            target_fn=lambda s: s.get(f"{args.url}/api/elrs?run={args.run}&page=1", timeout=8),
            total_requests=args.requests,
            concurrency=args.concurrency,
            session=pooled_session,
        )
    )

    # Benchmark 4: Static File Asset Streaming (~130KB PNG)
    results.append(
        run_benchmark(
            name="4. File Stream (/api/files/abs)",
            target_fn=lambda s: s.get(f"{args.url}/api/files/abs/{args.run}/{sample_elr}", timeout=8),
            total_requests=args.requests,
            concurrency=args.concurrency,
            session=pooled_session,
        )
    )

    # Print summary table
    print_results_table(results)

    # SLA Assessment
    print("\n--- SLA & RESPONSIVENESS EVALUATION ---")
    redis_res = results[1]
    ready_res = results[0]

    all_200 = all(r.status_counts.get(200, 0) == r.total_requests for r in results)
    redis_fast = redis_res.percentile(95) < 80.0
    ready_fast = ready_res.percentile(95) < 40.0

    print(f"[*] Zero-Error Concurrency Check : {'PASS (100% HTTP 200)' if all_200 else 'FAIL (Contains errors)'}")
    print(f"[*] Redis Cache Responsiveness  : P95 = {redis_res.percentile(95):.1f}ms (Target: < 80ms) -> {'PASS' if redis_fast else 'WARN'}")
    print(f"[*] Edge Readiness Latency       : P95 = {ready_res.percentile(95):.1f}ms (Target: < 40ms) -> {'PASS' if ready_fast else 'WARN'}")
    print(f"[*] Total Throughput Generated   : {sum(r.total_bytes for r in results) / (1024 * 1024):.2f} MB transferred")
    print("=" * 80)


if __name__ == "__main__":
    main()
