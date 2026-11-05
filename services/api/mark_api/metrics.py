"""In-process metrics collection with route ring buffers and percentile computation."""
from collections import deque
import math
from typing import Any, Literal


def _percentile(v: list[float], q: float) -> float:
    if not v:
        return 0.0
    n = len(v)
    idx = min(n - 1, max(0, math.ceil(q * (n + 1)) - 1))
    return v[idx]


class InProcessMetrics:
    def __init__(self) -> None:
        self.requests: dict[str, int] = {
            "total": 0,
            "2xx": 0,
            "3xx": 0,
            "4xx": 0,
            "5xx": 0,
        }
        self.login_ok: int = 0
        self.login_failed: int = 0
        self.login_locked: int = 0
        self.db_error: int = 0
        self.durations: dict[str, deque[float]] = {}

    def record_request(self, status_code: int, duration_ms: float, route: str) -> None:
        self.requests["total"] += 1
        cls = f"{status_code // 100}xx"
        if cls in self.requests:
            self.requests[cls] += 1
        if route not in self.durations:
            self.durations[route] = deque(maxlen=1000)
        self.durations[route].append(duration_ms)

    def inc(self, name: Literal["login_ok", "login_failed", "login_locked", "db_error"]) -> None:
        if hasattr(self, name):
            setattr(self, name, getattr(self, name) + 1)

    def snapshot(self, active_sessions: int | None = None) -> dict[str, Any]:
        routes_summary: dict[str, dict[str, Any]] = {}
        for route, deq in self.durations.items():
            v = sorted(deq)
            routes_summary[route] = {
                "count": len(deq),
                "p50_ms": _percentile(v, 0.50),
                "p95_ms": _percentile(v, 0.95),
            }
        return {
            "requests": dict(self.requests),
            "login_ok": self.login_ok,
            "login_failed": self.login_failed,
            "login_locked": self.login_locked,
            "db_error": self.db_error,
            "active_sessions": active_sessions,
            "routes": routes_summary,
        }


metrics = InProcessMetrics()
