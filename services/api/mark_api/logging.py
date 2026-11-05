"""Structured JSON application logging."""
from datetime import datetime, timezone
from contextvars import ContextVar
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
from typing import Any

# spec §15: never log credentials, usernames, mark values, SLR text or image paths
SENSITIVE_KEYS = {"password", "token", "username", "mark", "slr_text", "image_path"}

# Set by the request middleware so every event of one request carries the same request_id.
# Preserve the ContextVar instance across module reloads so existing references (e.g. in app.py) don't diverge.
_existing_ctx = getattr(sys.modules.get("mark_api.logging"), "current_request_id", None)
if _existing_ctx is not None:
    current_request_id = _existing_ctx
else:
    current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)

_file_logger: logging.Logger | None = None


def _get_file_logger() -> logging.Logger | None:
    global _file_logger
    log_dir = os.getenv("MARK_LOG_DIR")
    if not log_dir:
        return None
    if _file_logger is None:
        p = Path(log_dir)
        p.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger(f"mark_api.file_logger.{os.getpid()}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.handlers.clear()
        handler = RotatingFileHandler(
            p / "api.jsonl",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        _file_logger = logger
    return _file_logger


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

    line = json.dumps(payload)
    print(line, file=sys.stdout, flush=True)

    file_logger = _get_file_logger()
    if file_logger:
        file_logger.info(line)
