"""Shared, optional Redis connections for synchronous and async API code."""
from functools import lru_cache
import logging
import os

from mark_engine.adapters.redis_cache import get_redis

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_async_redis():
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        from redis.asyncio import Redis
        from redis.backoff import NoBackoff
        from redis.retry import Retry
        return Redis.from_url(url, socket_connect_timeout=0.3, socket_timeout=0.3,
                              retry=Retry(NoBackoff(), 0), retry_on_timeout=False)
    except Exception:
        logger.warning("Redis websocket client unavailable")
        return None


__all__ = ["get_redis", "get_async_redis"]
