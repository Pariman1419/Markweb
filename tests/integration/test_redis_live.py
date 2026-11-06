"""Opt-in integration test against an isolated Redis instance."""
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("MARK_REDIS_INTEGRATION"), reason="requires isolated Redis")


def test_live_cache_and_outage_fallback(monkeypatch):
    import time
    redis = pytest.importorskip("redis")
    from mark_engine.adapters.redis_cache import cache_json, get_redis

    client = redis.Redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=0.3, socket_timeout=0.3)
    key = "mark:test:" + uuid.uuid4().hex
    calls = []
    try:
        def load():
            calls.append(1)
            return {"value": 7}

        assert cache_json(client, key, 30, load) == {"value": 7}
        assert cache_json(client, key, 30, load) == {"value": 7}
        assert len(calls) == 1
        assert 0 < client.ttl(key) <= 30
        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
        get_redis.cache_clear()
        offline = get_redis()
        started = time.monotonic()
        assert cache_json(offline, key, 30, load) == {"value": 7}
        assert time.monotonic() - started < 2
        assert len(calls) == 2
    finally:
        get_redis.cache_clear()
        client.delete(key)
        client.close()


def test_live_websocket_receives_pubsub_without_database(monkeypatch):
    from datetime import datetime, timedelta, timezone
    import json
    redis = pytest.importorskip("redis")
    from fastapi.testclient import TestClient
    from mark_api.app import app
    from mark_api.deps import get_repo
    from mark_api.routers import ws
    from mark_api.redis_client import get_async_redis

    channel = "mark:test:events:" + uuid.uuid4().hex
    now = datetime.now(timezone.utc)

    class Repo:
        def session_user(self, token_hash):
            return ({"expires_at": now + timedelta(minutes=5), "last_seen_at": now},
                    {"role": "engineer", "active": True})

    app.dependency_overrides[get_repo] = lambda: Repo()
    monkeypatch.setattr(ws, "EVENT_CHANNEL", channel)
    get_async_redis.cache_clear()
    monkeypatch.setattr(ws, "get_async_redis", get_async_redis)
    publisher = redis.Redis.from_url(os.environ["REDIS_URL"])
    try:
        with TestClient(app) as client:
            client.cookies.set("mark_session", "integration-test", path="/api")
            with client.websocket_connect("/api/ws/events", headers={"origin": "http://testserver"}) as socket:
                publisher.publish(channel, json.dumps({"run_id": 12345}))
                assert socket.receive_json() == {"run_id": 12345}
    finally:
        publisher.close()
        get_async_redis.cache_clear()
        app.dependency_overrides.clear()


def test_invalidation_prevents_inflight_stale_cache_write():
    from threading import Event, Thread
    redis = pytest.importorskip("redis")
    from mark_engine.adapters.redis_cache import cache_dashboard

    client = redis.Redis.from_url(os.environ["REDIS_URL"])
    key = "mark:test:dashboard:" + uuid.uuid4().hex
    started, resume = Event(), Event()

    def old_load():
        started.set()
        assert resume.wait(5)
        return {"value": "old"}

    thread = Thread(target=lambda: cache_dashboard(client, key, 30, old_load))
    try:
        thread.start()
        assert started.wait(5)
        client.delete(key)
        assert cache_dashboard(client, key, 30, lambda: {"value": "new"}) == {"value": "new"}
        resume.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert cache_dashboard(client, key, 30, lambda: {"value": "wrong"}) == {"value": "new"}
    finally:
        resume.set()
        thread.join(timeout=5)
        client.delete(key)
        client.close()


def test_async_client_fails_fast_during_outage(monkeypatch):
    import asyncio
    import time
    redis = pytest.importorskip("redis")
    from mark_api.redis_client import get_async_redis

    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    get_async_redis.cache_clear()
    client = get_async_redis()

    async def run():
        try:
            with pytest.raises(redis.exceptions.ConnectionError):
                await client.ping()
        finally:
            await client.aclose()

    start = time.monotonic()
    try:
        asyncio.run(run())
        assert time.monotonic() - start < 2
    finally:
        get_async_redis.cache_clear()
