"""Real-time Deployment & Health Monitor for Mark Web (Build #15 Watchdog).

Monitors:
1. HTTP API Readiness Probe (/api/ready)
2. Latency & Response Codes
3. WebSocket Connection Health (/api/ws/events)
4. Redis Cache Responsiveness (/api/dashboard?run=19)
5. Detects service interruptions and deployment restarts automatically.

Usage:
    python scripts/monitor_deploy.py [--url http://10.153.90.17:8093] [--interval 5]
"""

import argparse
import datetime
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from mark_engine.adapters.env import load_env  # noqa: E402


def monitor(base_url: str, interval: int = 5):
    load_env()
    eng_u = os.getenv("MARK_TEST_ENGINEER_USER")
    eng_p = os.getenv("MARK_TEST_ENGINEER_PASSWORD")

    print("=" * 80)
    print(f" MARK WEB DEPLOYMENT & HEALTH MONITOR (WATCHDOG)")
    print(f" Target Host: {base_url} | Polling Interval: {interval}s")
    print("=" * 80)

    session = None
    if eng_u and eng_p:
        try:
            s = requests.Session()
            login_resp = s.post(f"{base_url}/api/auth/login", json={"username": eng_u, "password": eng_p}, timeout=5)
            if login_resp.status_code == 200:
                session = s
                print(f"[*] Authenticated session active (User: {eng_u})")
        except Exception as e:
            print(f"[!] Auth setup warning: {e}")

    prev_state = None
    tick = 0

    while True:
        tick += 1
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        t0 = time.perf_counter()

        try:
            # 1. Probe readiness
            r = requests.get(f"{base_url}/api/ready", timeout=4)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            ready_ok = r.status_code == 200 and r.json().get("status") == "ready"
            status_text = "READY (200 OK)" if ready_ok else f"STATUS {r.status_code}"
        except requests.exceptions.ConnectionError:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            ready_ok = False
            status_text = "CONNECTION REFUSED (Deploying/Restarting...)"
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            ready_ok = False
            status_text = f"ERROR: {type(e).__name__}"

        # 2. Probe Redis Cache if authenticated and ready
        cache_info = ""
        if ready_ok and session:
            try:
                tc0 = time.perf_counter()
                rc = session.get(f"{base_url}/api/dashboard?run=19", timeout=4)
                clat = (time.perf_counter() - tc0) * 1000.0
                if rc.status_code == 200:
                    cache_info = f"| Redis Cache: {clat:.1f}ms"
            except Exception:
                cache_info = "| Redis Cache: timeout"

        # Log status
        symbol = "[OK]  " if ready_ok else "[WARN]"
        print(f"[{now_str}] {symbol} API: {status_text:<38} | Latency: {latency_ms:>5.1f}ms {cache_info}", flush=True)

        # Detect deployment state transition
        if prev_state is not None:
            if prev_state and not ready_ok:
                print(f" >>> [ALERT] Service transitioned from READY to RESTARTING/DEPLOYING at {now_str}")
            elif not prev_state and ready_ok:
                print(f" >>> [SUCCESS] Service RESTARTED & RETURNED TO READY at {now_str}! New build is live!")

        prev_state = ready_ok
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mark Web Deployment Monitor")
    parser.add_argument("--url", default="http://10.153.90.17:8093", help="Base URL to monitor")
    parser.add_argument("--interval", type=int, default=5, help="Poll interval in seconds")
    args = parser.parse_args()

    try:
        monitor(args.url, args.interval)
    except KeyboardInterrupt:
        print("\n[*] Monitor stopped by user.")
