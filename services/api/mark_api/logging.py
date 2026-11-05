"""Structured JSON application logging."""
from datetime import datetime, timezone
import json
import sys
from typing import Any

SENSITIVE_KEYS = {"password", "token", "mark", "slr_text", "image_path"}


def log_event(event: str, **fields: Any) -> None:
    now = datetime.now(timezone.utc).isoformat()
    level = fields.pop("level", "INFO")
    request_id = fields.pop("request_id", None)

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
