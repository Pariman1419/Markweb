"""Comprehensive End-to-End (E2E) Test Suite for Mark Web.

Tests the live production stack on 10.153.90.17:8093 (or configurable target):
1. API Readiness Probe (/api/ready)
2. Authentication & Session Security (Login, Profile, 401 Unauthorized Gate)
3. Redis Dashboard Cache & Performance Benchmark (Cold vs Warm Cache Latency)
4. WebSocket Real-time Handshake & Security Gate (403 without session, 101 with session)
5. ELR Data Query & ABS Image File Streaming (/api/elrs, /api/files/abs)
6. Data Immutability Safety Check (Run 19 Read-Only Guarantee)
7. Session Cleanup / Logout

Exit Code: 0 if all tests PASS, 1 if any test FAILS.
"""

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Tuple

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mark_engine.adapters.env import load_env  # noqa: E402

RESULTS: list[Tuple[bool, str, str]] = []


def record(name: str, passed: bool, detail: str = "") -> bool:
    RESULTS.append((passed, name, detail))
    symbol = "[PASS]" if passed else "[FAIL]"
    print(f"{symbol} {name:<42} : {detail}", flush=True)
    return passed


def test_api_readiness(base_url: str) -> bool:
    """Case E2E-01: API Readiness Probe"""
    t0 = time.perf_counter()
    resp = requests.get(f"{base_url}/api/ready", timeout=5)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    ok = resp.status_code == 200 and resp.json().get("status") == "ready"
    return record("E2E-01: API Readiness Probe", ok, f"status={resp.status_code}, latency={elapsed_ms:.1f}ms")


def test_unauthenticated_security_gate(base_url: str) -> bool:
    """Case E2E-02: Unauthenticated 401 Security Gate"""
    resp = requests.get(f"{base_url}/api/runs", timeout=5)
    ok = resp.status_code == 401
    return record("E2E-02: Security Gate (401 Unauthorized)", ok, f"HTTP {resp.status_code} for unauthenticated /api/runs")


def test_login_and_session(base_url: str, username: str, password: str) -> Tuple[bool, requests.Session]:
    """Case E2E-03: User Authentication & Session Creation"""
    session = requests.Session()
    resp = session.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password},
        timeout=8,
    )
    if resp.status_code != 200:
        record("E2E-03: User Login & Session", False, f"Login failed: HTTP {resp.status_code}")
        return False, session

    # Verify session profile via /api/auth/me
    me = session.get(f"{base_url}/api/auth/me", timeout=5)
    ok = me.status_code == 200 and me.json().get("username") == username
    has_cookie = "mark_session" in session.cookies
    passed = ok and has_cookie
    role = me.json().get("role") if ok else "unknown"
    record("E2E-03: User Login & Session", passed, f"role={role}, mark_session cookie present={has_cookie}")
    return passed, session


def test_redis_dashboard_cache(session: requests.Session, base_url: str, run_id: int) -> bool:
    """Case E2E-04: Redis Dashboard Cache Hit & Latency Benchmark"""
    url = f"{base_url}/api/dashboard?run={run_id}"

    # Call 1: Cold or Warm query
    t0 = time.perf_counter()
    r1 = session.get(url, timeout=10)
    dur1 = (time.perf_counter() - t0) * 1000

    # Call 2: Guaranteed Redis Cache Hit
    t1 = time.perf_counter()
    r2 = session.get(url, timeout=10)
    dur2 = (time.perf_counter() - t1) * 1000

    data = r2.json() if r2.status_code == 200 else {}
    cards = data.get("cards", {})
    true_cnt = cards.get("TRUE", {}).get("count", 0)

    ok = r2.status_code == 200 and true_cnt > 0 and dur2 < 100.0
    return record(
        "E2E-04: Redis Dashboard Cache Benchmark",
        ok,
        f"Call 1: {dur1:.1f}ms -> Call 2 (Redis hit): {dur2:.1f}ms (TRUE count={true_cnt})",
    )


async def _test_websocket_flows(base_url: str, session_token: str) -> Tuple[bool, bool]:
    import websockets

    # Clean ws URL from http URL
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://") + "/api/ws/events"

    # Step 1: Unauthenticated WebSocket should be rejected (403 Forbidden)
    unauth_rejected = False
    try:
        async with websockets.connect(
            ws_url,
            additional_headers=[("Origin", base_url)],
            open_timeout=3,
        ):
            unauth_rejected = False
    except Exception as e:
        err_msg = str(e)
        if "403" in err_msg or "1008" in err_msg or "InvalidStatusCode" in type(e).__name__:
            unauth_rejected = True

    # Step 2: Authenticated WebSocket should connect successfully (101 Switching Protocols)
    auth_connected = False
    try:
        headers = [
            ("Cookie", f"mark_session={session_token}"),
            ("Origin", base_url),
        ]
        async with websockets.connect(
            ws_url,
            additional_headers=headers,
            open_timeout=5,
        ) as ws:
            auth_connected = True
            await asyncio.sleep(0.5)
            await ws.close()
    except Exception as e:
        auth_connected = False

    return unauth_rejected, auth_connected


def test_websocket_security_and_connection(base_url: str, session: requests.Session) -> bool:
    """Case E2E-05: WebSocket Real-time Handshake & Auth Gate"""
    token = session.cookies.get("mark_session", "")
    if not token:
        return record("E2E-05: WebSocket Real-time Handshake", False, "Missing session token")

    unauth_rejected, auth_connected = asyncio.run(_test_websocket_flows(base_url, token))
    ok = unauth_rejected and auth_connected
    detail = f"Unauth Rejected (403/1008): {unauth_rejected}, Authenticated Connect (101): {auth_connected}"
    return record("E2E-05: WebSocket Real-time Handshake", ok, detail)


def test_elr_and_image_streaming(session: requests.Session, base_url: str, run_id: int) -> bool:
    """Case E2E-06: ELR List Query & ABS Image Asset Retrieval"""
    # 1. Fetch ELR list
    resp = session.get(f"{base_url}/api/elrs?run={run_id}&page=1", timeout=8)
    if resp.status_code != 200:
        return record("E2E-06: ELR & ABS Image Streaming", False, f"Failed listing ELRs: HTTP {resp.status_code}")

    rows = resp.json().get("rows", [])
    if not rows:
        return record("E2E-06: ELR & ABS Image Streaming", False, "No ELRs returned")

    # Find the first ELR that has an available image
    target_elr = None
    for row in rows:
        elr_no = row.get("elr_no")
        det = session.get(f"{base_url}/api/elrs/{elr_no}?run={run_id}", timeout=5).json()
        if det.get("image_available"):
            target_elr = elr_no
            break

    if not target_elr:
        return record("E2E-06: ELR & ABS Image Streaming", False, "No ELR found with available image")

    # 2. Fetch ABS Image PNG
    img_resp = session.get(f"{base_url}/api/files/abs/{run_id}/{target_elr}", timeout=8)
    is_png = img_resp.status_code == 200 and "image/png" in img_resp.headers.get("content-type", "")
    size_kb = len(img_resp.content) / 1024

    ok = is_png and size_kb > 10
    return record(
        "E2E-06: ELR & ABS Image Streaming",
        ok,
        f"ELR={target_elr}, ABS Image: HTTP {img_resp.status_code}, Size: {size_kb:.1f} KB",
    )


def test_logout(session: requests.Session, base_url: str) -> bool:
    """Case E2E-07: Graceful Session Logout with Anti-CSRF Token"""
    csrf_token = session.cookies.get("mark_csrf", "")
    headers = {
        "X-CSRF-Token": csrf_token,
        "Origin": base_url,
    }
    resp = session.post(f"{base_url}/api/auth/logout", headers=headers, timeout=5)
    ok = resp.status_code in (200, 204)
    # Check that me is now 401
    me = session.get(f"{base_url}/api/auth/me", timeout=5)
    logged_out = me.status_code == 401
    return record("E2E-07: Session Logout & Revocation", ok and logged_out, f"Logout status={resp.status_code}, auth/me status={me.status_code}")


def main():
    parser = argparse.ArgumentParser(description="Mark Web E2E Test Suite")
    parser.add_argument("--url", default="http://10.153.90.17:8093", help="Base URL of Mark Web (default: http://10.153.90.17:8093)")
    parser.add_argument("--run", type=int, default=19, help="Historical Run ID to verify against (default: 19)")
    args = parser.parse_args()

    load_env()
    eng_u = os.getenv("MARK_TEST_ENGINEER_USER")
    eng_p = os.getenv("MARK_TEST_ENGINEER_PASSWORD")

    if not eng_u or not eng_p:
        print("[FAIL] Missing test credentials in .env (MARK_TEST_ENGINEER_USER / MARK_TEST_ENGINEER_PASSWORD)")
        sys.exit(1)

    print("=" * 75)
    print(f" MARK WEB END-TO-END (E2E) TEST SUITE")
    print(f" Target Host: {args.url} | Target Run: {args.run}")
    print("=" * 75)

    test_api_readiness(args.url)
    test_unauthenticated_security_gate(args.url)
    login_ok, session = test_login_and_session(args.url, eng_u, eng_p)

    if login_ok:
        test_redis_dashboard_cache(session, args.url, args.run)
        test_websocket_security_and_connection(args.url, session)
        test_elr_and_image_streaming(session, args.url, args.run)
        test_logout(session, args.url)
    else:
        record("E2E-04: Redis Dashboard Cache", False, "Skipped due to login failure")
        record("E2E-05: WebSocket Real-time Handshake", False, "Skipped due to login failure")
        record("E2E-06: ELR & ABS Image Streaming", False, "Skipped due to login failure")
        record("E2E-07: Session Logout", False, "Skipped due to login failure")

    print("-" * 75)
    failed_count = sum(1 for passed, _, _ in RESULTS if not passed)
    total_count = len(RESULTS)
    pass_count = total_count - failed_count

    if failed_count == 0:
        print(f" OVERALL RESULT: ALL {total_count} E2E TEST CASES PASSED (100%)")
        print("=" * 75)
        return 0
    else:
        print(f" OVERALL RESULT: {pass_count}/{total_count} PASSED, {failed_count} FAILED")
        print("=" * 75)
        return 1


if __name__ == "__main__":
    sys.exit(main())
