"""Optional cache helpers shared by the worker and API."""
import json
import logging
import os
import secrets
from contextlib import contextmanager
from functools import lru_cache

logger = logging.getLogger(__name__)


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


@lru_cache(maxsize=1)
def get_redis():
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis
        from redis.backoff import NoBackoff
        from redis.retry import Retry
        return redis.Redis.from_url(url, socket_connect_timeout=0.3, socket_timeout=0.3,
                                    retry=Retry(NoBackoff(), 0), retry_on_timeout=False)
    except Exception:
        logger.warning("Redis client unavailable")
        return None


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


def notify_revision(run_id, elr_no, revision):
    client = get_redis()
    if client is None:
        return
    try:
        client.delete(f"mark:dashboard:{run_id}")
    except Exception:
        logger.warning("Redis cache invalidation failed")
    try:
        client.publish("mark_events", json.dumps({
            "run_id": run_id, "elr_no": elr_no, "revision": revision,
        }))
    except Exception:
        logger.warning("Redis event publication failed")
