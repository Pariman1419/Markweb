"""Redis cache behavior stays optional for callers."""
from mark_engine.adapters.redis_cache import cache_json


class MemoryRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex):
        self.values[key] = value

    def eval(self, script, numkeys, key, *args):
        if "return {v," in script:
            entry = self.values.setdefault(key, {"v": args[0]})
            return [entry["v"], entry.get("data")]
        entry = self.values.get(key)
        if entry and entry["v"] == args[0]:
            entry["data"] = args[1]
            return 1
        return 0


def test_cache_miss_then_hit():
    redis = MemoryRedis()
    calls = []

    def load():
        calls.append(1)
        return [{"MARK_ID": 7, "MARK_DATA": "A"}]

    assert cache_json(redis, "layout:7", 60, load) == [{"MARK_ID": 7, "MARK_DATA": "A"}]
    assert cache_json(redis, "layout:7", 60, load) == [{"MARK_ID": 7, "MARK_DATA": "A"}]
    assert len(calls) == 1


def test_cache_falls_back_when_redis_is_unavailable():
    class Offline:
        def get(self, key):
            raise ConnectionError("offline")

        def set(self, key, value, ex):
            raise TimeoutError("offline")

    assert cache_json(Offline(), "layout:7", 60, lambda: [7]) == [7]


def test_layout_cache_avoids_second_oracle_query(monkeypatch):
    from services.worker import oracle_source

    client = MemoryRedis()
    calls = []
    monkeypatch.setattr(oracle_source, "get_redis", lambda: client, raising=False)
    monkeypatch.setattr(oracle_source, "select", lambda *args: calls.append(1) or [{"MARK_ID": 7}])
    assert oracle_source.fetch_layout(None, 7) == [{"MARK_ID": 7}]
    assert oracle_source.fetch_layout(None, 7) == [{"MARK_ID": 7}]
    assert len(calls) == 1


def test_dashboard_uses_redis_and_falls_back_to_database(monkeypatch):
    from mark_api.routers import validation

    class Repo:
        calls = 0

        def lines(self, run):
            self.calls += 1
            return []

        def jobs(self, run):
            return []

    repo = Repo()
    client = MemoryRedis()
    monkeypatch.setattr(validation, "get_redis", lambda: client, raising=False)
    validation.clear_dashboard_cache()
    validation.dashboard(run=91, user={}, repo=repo)
    validation.dashboard(run=91, user={}, repo=repo)
    assert "mark:dashboard:91" in client.values
    assert repo.calls == 1

    monkeypatch.setattr(validation, "get_redis", lambda: None)
    validation.dashboard(run=91, user={}, repo=repo)
    assert repo.calls == 2


def test_revision_notification_invalidates_dashboard_and_publishes(monkeypatch):
    from mark_engine.adapters import redis_cache

    class Redis:
        def __init__(self):
            self.deleted = []
            self.published = []

        def delete(self, key):
            self.deleted.append(key)

        def publish(self, channel, payload):
            self.published.append((channel, payload))

    redis = Redis()
    monkeypatch.setattr(redis_cache, "get_redis", lambda: redis)
    redis_cache.notify_revision(21, "ADI123", 2)
    assert redis.deleted == ["mark:dashboard:21"]
    assert redis.published[0][0] == "mark_events"
    import json
    assert json.loads(redis.published[0][1])["data"]["run_id"] == 21


def test_revision_notification_does_not_fail_when_redis_is_down(monkeypatch):
    from mark_engine.adapters import redis_cache

    class Offline:
        def delete(self, key):
            raise ConnectionError("offline")

        def publish(self, channel, payload):
            raise TimeoutError("offline")

    monkeypatch.setattr(redis_cache, "get_redis", lambda: Offline())
    redis_cache.notify_revision(21, "ADI123", 2)


def test_redis_client_factory_retries_after_startup_failure(monkeypatch):
    from mark_engine.adapters import redis_cache

    attempts = []
    client = object()

    def build(url):
        attempts.append(url)
        if len(attempts) == 1:
            raise ImportError("temporary Redis client initialization failure")
        return client

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    redis_cache.get_redis.cache_clear()
    monkeypatch.setattr(redis_cache, "_build_redis_client", build)

    assert redis_cache.get_redis() is None
    assert redis_cache.get_redis() is client
    assert attempts == ["redis://redis:6379/0", "redis://redis:6379/0"]


def test_worker_publishes_only_after_transaction_commits(monkeypatch):
    from services.worker import main

    events = []

    class Context:
        def __init__(self, name):
            self.name = name
        def __enter__(self):
            return self
        def __exit__(self, *args):
            events.append(f"{self.name} committed")
        def cursor(self):
            return Context("cursor")

    def cycle(*args, pending_notifications, **kwargs):
        pending_notifications.append((21, "ADI123", 2))
        return main.CycleResult.PROCESSED

    monkeypatch.setattr(main, "run_worker_cycle", cycle)
    monkeypatch.setattr(main, "notify_revision", lambda *args: events.append("published"), raising=False)
    main.run_transaction(Context("transaction"), None, "worker-1")
    assert events == ["cursor committed", "transaction committed", "published"]


def test_worker_does_not_publish_when_commit_fails(monkeypatch):
    import pytest
    from services.worker import main

    class Cursor:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            raise RuntimeError("commit failed")
        def cursor(self):
            return Cursor()

    def cycle(*args, pending_notifications, **kwargs):
        pending_notifications.append((21, "ADI123", 2))
        return main.CycleResult.PROCESSED

    published = []
    monkeypatch.setattr(main, "run_worker_cycle", cycle)
    monkeypatch.setattr(main, "notify_revision", lambda *args: published.append(args))
    with pytest.raises(RuntimeError, match="commit failed"):
        main.run_transaction(Connection(), None, "worker-1")
    assert published == []


def test_redis_lock_degrades_when_unavailable(monkeypatch):
    from mark_engine.adapters import redis_cache

    class Offline:
        def set(self, *args, **kwargs):
            raise ConnectionError("offline")

    monkeypatch.setattr(redis_cache, "get_redis", lambda: Offline())
    with redis_cache.optional_lock("mark:test:scan"):
        pass


def test_redis_lock_contention_still_uses_database_lock(monkeypatch):
    from mark_engine.adapters import redis_cache

    class Busy:
        def set(self, *args, **kwargs):
            return None

    monkeypatch.setattr(redis_cache, "get_redis", lambda: Busy())
    with redis_cache.optional_lock("mark:test:scan"):
        pass


def test_revision_event_uses_typed_envelope(monkeypatch):
    import json
    from mark_engine.adapters import redis_cache
    sent = []
    class Redis:
        def delete(self, key): pass
        def publish(self, channel, payload): sent.append(json.loads(payload))
    monkeypatch.setattr(redis_cache, 'get_redis', lambda: Redis())
    redis_cache.notify_revision(21, 'ADI1', 2)
    assert sent[0]['event'] == 'revision_saved'
    assert sent[0]['data'] == {'run_id': 21, 'elr_no': 'ADI1', 'revision': 2}
    assert sent[0]['timestamp']


def test_worker_publishes_progress_after_commit(monkeypatch):
    from services.worker import main
    events = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, query, params): events.append(('query', params))
        def fetchone(self): return (2, 4)
    class Conn:
        def __enter__(self): return self
        def __exit__(self, *args): events.append(('commit',))
        def cursor(self): return Cursor()
    def cycle(*args, pending_progress, **kwargs):
        pending_progress.append((142, 'ADI1'))
        return main.CycleResult.PROCESSED
    monkeypatch.setattr(main, 'run_worker_cycle', cycle)
    monkeypatch.setattr(main, 'get_redis', lambda: object())
    monkeypatch.setattr(main, 'publish_event', lambda client, event, data: events.append((event, data)))
    main.run_transaction(Conn(), None, 'worker-1')
    progress = next(item[1] for item in events if item[0] == 'job_progress')
    assert progress == {'scan_id': 142, 'completed': 2, 'total': 4, 'current_elr': 'ADI1', 'percent': 50.0}
    assert events.index(('commit',)) < next(i for i, item in enumerate(events) if item[0] == 'job_progress')


def test_worker_revision_event_contains_dashboard_result(monkeypatch):
    import json
    from mark_engine.adapters import redis_cache
    events = []
    class Redis:
        def delete(self, key): pass
        def publish(self, channel, payload): events.append(json.loads(payload))
    monkeypatch.setattr(redis_cache, 'get_redis', lambda: Redis())
    redis_cache.notify_revision(21, 'ADI1', 2, 'TRUE')
    assert events[0]['data']['result'] == 'TRUE'
