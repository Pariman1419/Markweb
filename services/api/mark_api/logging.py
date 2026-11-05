"""Structured JSON application logging."""
from datetime import datetime, timezone
from contextvars import ContextVar
import json
import sys
from typing import Any

# spec §15: never log credentials, usernames, mark values, SLR text or image paths
SENSITIVE_KEYS = {"password", "token", "username", "mark", "slr_text", "image_path"}

# Set by the request middleware so every event of one request carries the same request_id.
current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)


def log_event(event: str, **fields: Any) -> None:
    now = datetime.now(timezone.utc).isoformat()
    level = fields.pop("level", "INFO")
    request_id = fields.pop("request_id", None) or current_request_id.get()

    payload: dict[str, Any] = {
        "ts": now,
        "level": level,
        "service": "mark-api",
        "request_id": request_id,
        "event": event,
    }

    for k, v in fields.items():
        if k.lower() in SENSITIVE_KEYS:
            continue
        payload[k] = v

    print(json.dumps(payload), file=sys.stdout, flush=True)
