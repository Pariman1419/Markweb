"""Optional cache helpers shared by the worker and API."""
import json
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from functools import lru_cache

logger = logging.getLogger(__name__)

# The deployed API has one Uvicorn process.  Entries are trusted only after this
# process has loaded them from PostgreSQL; restart or Redis errors drop trust.
# The lock also serializes session mutations with cache fills.
session_cache_lock = threading.RLock()
_trusted_sessions = {}
_next_session_cleanup = 0.0


def reset_session_cache_state():
    global _next_session_cleanup
    with session_cache_lock:
        _trusted_sessions.clear()
        _next_session_cleanup = 0.0


def _aware(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def cache_session(client, token_hash, ttl, load_fn, *, sliding=True):
    """Cache a validated session profile; never cache credentials or account locks."""
    key = f"mark:session:{token_hash}"
    global _next_session_cleanup
    with session_cache_lock:
        if client is None:
            _trusted_sessions.clear()
        monotonic_now = time.monotonic()
        if monotonic_now >= _next_session_cleanup:
            for token, (_, deadline) in list(_trusted_sessions.items()):
                if deadline <= monotonic_now:
                    _trusted_sessions.pop(token, None)
            _next_session_cleanup = monotonic_now + 60
        if client is not None and token_hash in _trusted_sessions:
            try:
                raw = client.get(key)
                if raw:
                    profile = json.loads(raw)
                    expires_at = _aware(profile["expires_at"])
                    remaining = int((expires_at - datetime.now(timezone.utc)).total_seconds())
                    user_id, deadline = _trusted_sessions[token_hash]
                    if remaining > 0 and deadline > monotonic_now and profile["active"] and profile["user_id"] == user_id:
                        if sliding and not client.expire(key, min(900, ttl, remaining)):
                            raise RuntimeError("Session cache key disappeared")
                        if sliding:
                            _trusted_sessions[token_hash] = (user_id, monotonic_now + min(900, ttl, remaining))
                        return ({"token_hash": token_hash, "user_id": profile["user_id"],
                                 "csrf_hash": profile["csrf_hash"], "expires_at": expires_at,
                                 "last_seen_at": None},
                                {"user_id": profile["user_id"], "username": profile["username"],
                                 "role": profile["role"], "active": True})
                _trusted_sessions.pop(token_hash, None)
            except Exception:
                logger.warning("Redis session cache read failed")
                _trusted_sessions.clear()
                client = None
        row = load_fn()
        if client is None or not row:
            return row
        session, user = row
        now = datetime.now(timezone.utc)
        try:
            expires_at = _aware(session.get("expires_at"))
            seen_at = _aware(session.get("last_seen_at"))
            locked_until = _aware(user.get("locked_until"))
            if (not expires_at or expires_at <= now or not user.get("active", True)
                    or (seen_at and seen_at + timedelta(minutes=60) < now)
                    or (locked_until and locked_until > now)):
                return row
            lifetime = min(900, ttl, int((expires_at - now).total_seconds()))
            if seen_at:
                lifetime = min(lifetime, int((seen_at + timedelta(minutes=60) - now).total_seconds()))
            if lifetime <= 0:
                return row
            profile = {"user_id": user["user_id"], "username": user["username"],
                       "role": user["role"], "active": True, "csrf_hash": session["csrf_hash"],
                       "expires_at": expires_at.isoformat()}
            client.set(key, json.dumps(profile), ex=lifetime)
            _trusted_sessions[token_hash] = (user["user_id"], time.monotonic() + lifetime)
        except Exception:
            logger.warning("Redis session cache write failed")
            _trusted_sessions.clear()
        return row


def invalidate_session(client, token_hash):
    with session_cache_lock:
        _trusted_sessions.pop(token_hash, None)
        if client is not None:
            try:
                client.delete(f"mark:session:{token_hash}", f"mark:sessiontouch:{token_hash}")
            except Exception:
                _trusted_sessions.clear()
                logger.warning("Redis session invalidation failed")


def invalidate_user_sessions(client, user_id):
    with session_cache_lock:
        for token in [token for token, (uid, _) in _trusted_sessions.items() if uid == user_id]:
            invalidate_session(client, token)


def session_touch_due(client, token_hash):
    if client is None:
        return True
    try:
        return bool(client.set(f"mark:sessiontouch:{token_hash}", "1", nx=True, ex=60))
    except Exception:
        reset_session_cache_state()
        return True


def _write_ephemeral(client, key, value, ttl):
    if client is not None:
        try:
            client.set(key, json.dumps(value), ex=ttl)
        except Exception:
            logger.warning("Redis state write failed")


def _read_ephemeral(client, key):
    if client is not None:
        try:
            value = client.get(key)
            return json.loads(value) if value else None
        except Exception:
            logger.warning("Redis state read failed")
    return None


def record_worker_heartbeat(client, worker_id):
    import mark_engine
    _write_ephemeral(client, "mark:worker:heartbeat", {
        "worker_id": worker_id, "pid": os.getpid(),
        "last_beat": datetime.now(timezone.utc).isoformat(),
        "version": mark_engine.__version__,
    }, 30)


def get_worker_heartbeat(client):
    return _read_ephemeral(client, "mark:worker:heartbeat")


def set_active_job(client, elr_no, run_id, worker_id, started_at=None):
    _write_ephemeral(client, f"mark:job:active:{elr_no}", {
        "run_id": run_id, "elr_no": elr_no, "worker_id": worker_id,
        "started_at": started_at or datetime.now(timezone.utc).isoformat(),
    }, 120)


def get_active_job(client, elr_no, fallback=None):
    if client is not None:
        try:
            value = client.get(f"mark:job:active:{elr_no}")
            if value:
                return json.loads(value)
        except Exception:
            logger.warning("Redis job state read failed")
    return fallback() if fallback else None


def clear_active_job(client, elr_no):
    if client is not None:
        try:
            client.delete(f"mark:job:active:{elr_no}")
        except Exception:
            logger.warning("Redis job state deletion failed")


def check_rate_limit(client, user_id, action, limit, window_sec, fallback=None):
    """Atomically admit a request using Redis server time; use fallback on outage."""
    def unavailable():
        if fallback:
            try:
                return fallback()
            except Exception:
                logger.warning("Rate limit database fallback unavailable")
        return True, 0
    if client is None:
        return unavailable()
    script = """
local t = redis.call('TIME')
local now = t[1] * 1000000 + t[2]
local window = tonumber(ARGV[2]) * 1000000
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  return {0, math.max(1, math.ceil((tonumber(oldest[2]) + window - now) / 1000000))}
end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return {1, 0}
"""
    try:
        allowed, retry = client.eval(script, 1, f"mark:ratelimit:user:{user_id}:{action}",
                                     limit, window_sec, secrets.token_hex(16))
        return bool(allowed), int(retry)
    except Exception:
        logger.warning("Redis rate limit unavailable")
        return unavailable()


@contextmanager
def optional_lock(key, ttl=120):
    """A fast advisory lock; callers must also retain a durable database lock."""
    client = get_redis()
    token = secrets.token_hex(16)
    acquired = False
    if client is not None:
        try:
            acquired = bool(client.set(key, token, nx=True, ex=ttl))
        except Exception:
            logger.warning("Redis lock unavailable; using database lock")
            client = None
    try:
        yield
    finally:
        if client is not None and acquired:
            try:
                client.eval("if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end", 1, key, token)
            except Exception:
                logger.warning("Redis lock release failed")


def _build_redis_client(url):
    import redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry
    return redis.Redis.from_url(url, socket_connect_timeout=0.3, socket_timeout=0.3,
                                retry=Retry(NoBackoff(), 0), retry_on_timeout=False)


@lru_cache(maxsize=1)
def _cached_redis_client(url):
    return _build_redis_client(url)


def get_redis():
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        # Exceptions are not cached, so a worker that starts before optional
        # Redis dependencies/configuration are available can recover on its
        # next heartbeat instead of keeping a cached None forever.
        return _cached_redis_client(url)
    except Exception as exc:
        logger.warning("Redis client unavailable (%s)", type(exc).__name__)
        return None


# Keep the existing integration-test and operational cache reset hook.
get_redis.cache_clear = _cached_redis_client.cache_clear


def cache_json(client, key, ttl, load):
    available = client is not None
    if client is not None:
        try:
            cached = client.get(key)
            if cached is not None:
                return json.loads(cached)
        except Exception:
            logger.warning("Redis cache read failed")
            available = False
    value = load()
    if available:
        try:
            client.set(key, json.dumps(value), ex=ttl)
        except Exception:
            logger.warning("Redis cache write failed")
    return value


def cache_dashboard(client, key, ttl, load):
    """A single Redis hash guards writes against concurrent invalidation/eviction."""
    if client is None:
        return load()
    token = secrets.token_hex(16)
    try:
        version, cached = client.eval(
            "local v=redis.call('hget',KEYS[1],'v'); "
            "if not v then v=ARGV[1]; redis.call('hset',KEYS[1],'v',v); "
            "redis.call('expire',KEYS[1],ARGV[2]); end; "
            "return {v, redis.call('hget',KEYS[1],'data') or false}",
            1, key, token, ttl,
        )
        if cached is not None:
            return json.loads(cached)
    except Exception:
        logger.warning("Redis dashboard read failed")
        return load()
    value = load()
    try:
        client.eval(
            "if redis.call('hget',KEYS[1],'v') == ARGV[1] then "
            "redis.call('hset',KEYS[1],'data',ARGV[2]); "
            "redis.call('expire',KEYS[1],ARGV[3]); return 1 end; return 0",
            1, key, version, json.dumps(value), ttl,
        )
    except Exception:
        logger.warning("Redis dashboard write failed")
    return value


def publish_event(client, event, data):
    if client is None:
        return
    try:
        client.publish("mark_events", json.dumps({
            "event": event, "timestamp": datetime.now(timezone.utc).isoformat(), "data": data,
        }))
    except Exception:
        logger.warning("Redis event publication failed")


def notify_revision(run_id, elr_no, revision, result=None):
    client = get_redis()
    if client is None:
        return
    try:
        client.delete(f"mark:dashboard:{run_id}")
    except Exception:
        logger.warning("Redis cache invalidation failed")
    data = {"run_id": run_id, "elr_no": elr_no, "revision": revision}
    if result is not None:
        data["result"] = result
    publish_event(client, "revision_saved", data)
