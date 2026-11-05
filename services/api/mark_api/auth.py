"""Authentication, role checks, and token utilities."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Any, Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(hash_str: str, password: str) -> bool:
    try:
        return _hasher.verify(hash_str, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def login_state(user: dict[str, Any], now: datetime) -> Literal["OK", "LOCKED", "INACTIVE"]:
    if not user.get("active", True):
        return "INACTIVE"
    locked_until = user.get("locked_until")
    if locked_until:
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        if locked_until > now:
            return "LOCKED"
    return "OK"


def new_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, digest


def session_status(session: dict[str, Any], now: datetime) -> Literal["ok", "absolute", "idle"]:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    expires_at = session.get("expires_at")
    if expires_at:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now > expires_at:
            return "absolute"

    last_seen_at = session.get("last_seen_at")
    if last_seen_at:
        if last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
        if now > last_seen_at + timedelta(minutes=60):
            return "idle"

    return "ok"


def session_valid(session: dict[str, Any], now: datetime) -> bool:
    return session_status(session, now) == "ok"



def csrf_ok(cookie: str | None, header: str | None) -> bool:
    if not cookie or not header:
        return False
    return hmac.compare_digest(cookie, header)


def can(role: str, action: Literal["read", "review", "approve", "metrics"]) -> bool:
    matrix = {
        "engineer": {"read", "review", "approve"},
        "mark_eng_approver": {"read", "review", "approve"},
        "admin": {"read", "metrics"},
        "metrics_token": {"metrics"},
    }
    allowed = matrix.get(role, set())
    return action in allowed
