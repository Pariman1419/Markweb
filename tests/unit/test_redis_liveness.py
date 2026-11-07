from mark_engine.adapters import redis_cache


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}
    def set(self, key, value, ex=None, **kwargs):
        self.values[key] = value
        self.ttls[key] = ex
        return True
    def get(self, key):
        return self.values.get(key)
    def delete(self, key):
        self.values.pop(key, None)


def test_worker_and_job_keys_have_bounded_ttl():
    client = FakeRedis()
    redis_cache.record_worker_heartbeat(client, 'worker-1')
    assert redis_cache.get_worker_heartbeat(client)['worker_id'] == 'worker-1'
    assert client.ttls['mark:worker:heartbeat'] == 30
    redis_cache.set_active_job(client, 'ADI1', 23, 'worker-1')
    assert redis_cache.get_active_job(client, 'ADI1')['run_id'] == 23
    assert client.ttls['mark:job:active:ADI1'] == 120
    redis_cache.clear_active_job(client, 'ADI1')
    assert redis_cache.get_active_job(client, 'ADI1') is None


def test_worker_cache_outage_does_not_raise():
    class Broken:
        def __getattr__(self, name):
            raise ConnectionError('offline')
    client = Broken()
    redis_cache.record_worker_heartbeat(client, 'worker-1')
    assert redis_cache.get_worker_heartbeat(client) is None
    redis_cache.set_active_job(client, 'ADI1', None, 'worker-1')
    assert redis_cache.get_active_job(client, 'ADI1') is None
    redis_cache.clear_active_job(client, 'ADI1')


def test_elr_detail_exposes_active_job(monkeypatch):
    from mark_api.routers import mark
    class Repo:
        def snapshot(self, *args): return None
        def lines_for_elr(self, *args): return []
        def latest_reviews(self, *args): return []
        def latest_approval(self, *args): return None
    monkeypatch.setattr(mark, 'get_redis', lambda: object())
    monkeypatch.setattr(mark, 'get_active_job', lambda client, elr, fallback: {'elr_no': elr})
    assert mark.get_elr('ADI1', 23, {}, Repo())['is_processing'] is True


def test_worker_marks_claimed_job_and_clears_it(monkeypatch):
    from types import SimpleNamespace
    from contextlib import nullcontext
    from services.worker import main
    events = []
    monkeypatch.setattr(main, 'claim', lambda *args: SimpleNamespace(elr_no='ADI1', item_id=1))
    monkeypatch.setattr(main, 'fail', lambda *args: None)
    monkeypatch.setattr(main, 'optional_lock', lambda *args: nullcontext())
    monkeypatch.setattr(main, 'get_redis', lambda: None)
    monkeypatch.setattr(main, 'set_active_job', lambda *args: events.append(('set', args[1])))
    monkeypatch.setattr(main, 'clear_active_job', lambda *args: events.append(('clear', args[1])))
    main.run_worker_cycle(None, None, oracle_row=None)
    assert events == [('set', 'ADI1'), ('clear', 'ADI1')]


def test_worker_status_reports_missing_heartbeat(monkeypatch):
    from mark_api import app as app_module
    monkeypatch.setattr(app_module, 'get_redis', lambda: None)
    assert app_module.worker_status() == {'status': 'unknown', 'heartbeat': None}


def test_job_refresh_preserves_started_at_and_new_run_id():
    client = FakeRedis()
    redis_cache.set_active_job(client, 'ADI1', None, 'worker-1', '2026-11-07T00:00:00+00:00')
    redis_cache.set_active_job(client, 'ADI1', 27, 'worker-1', '2026-11-07T00:00:00+00:00')
    job = redis_cache.get_active_job(client, 'ADI1')
    assert job['run_id'] == 27
    assert job['started_at'] == '2026-11-07T00:00:00+00:00'


def test_job_marker_is_cleared_after_transaction_commit(monkeypatch):
    from services.worker import main
    events = []
    class Conn:
        def __enter__(self): return self
        def __exit__(self, *args): events.append('commit')
        def cursor(self): return self
    def cycle(*args, pending_cleanup, **kwargs):
        pending_cleanup.append(('redis', 'ADI1'))
        return main.CycleResult.PROCESSED
    monkeypatch.setattr(main, 'run_worker_cycle', cycle)
    monkeypatch.setattr(main, 'clear_active_job', lambda *args: events.append('clear'))
    main.run_transaction(Conn(), None, 'worker-1')
    assert events == ['commit', 'commit', 'clear']


def test_elr_processing_falls_back_to_database_when_redis_fails(monkeypatch):
    from mark_api.routers import mark
    class Repo:
        def snapshot(self, *args): return None
        def lines_for_elr(self, *args): return []
        def latest_reviews(self, *args): return []
        def latest_approval(self, *args): return None
        def is_elr_processing(self, elr): return elr == 'ADI1'
    class Broken:
        def get(self, key): raise ConnectionError('offline')
    monkeypatch.setattr(mark, 'get_redis', lambda: Broken())
    assert mark.get_elr('ADI1', 23, {}, Repo())['is_processing'] is True


def test_worker_uses_transaction_lock_for_postgres_liveness_fallback(monkeypatch):
    from types import SimpleNamespace
    from contextlib import nullcontext
    from services.worker import main
    statements = []
    class Cursor:
        def execute(self, sql, params): statements.append((sql, params))
    monkeypatch.setattr(main, 'claim', lambda *args: SimpleNamespace(elr_no='ADI1', item_id=1, scan_id=None))
    monkeypatch.setattr(main, 'fail', lambda *args: None)
    monkeypatch.setattr(main, 'optional_lock', lambda *args: nullcontext())
    monkeypatch.setattr(main, 'get_redis', lambda: None)
    main.run_worker_cycle(Cursor(), None, oracle_row=None, conn_pg=object())
    assert any('pg_advisory_xact_lock' in sql and params == ('ADI1',) for sql, params in statements)


def test_worker_status_reports_degraded_when_redis_is_available_but_heartbeat_missing(monkeypatch):
    from mark_api import app as app_module
    class Redis:
        def get(self, key): return None
        def ping(self): return True
    monkeypatch.setattr(app_module, 'get_redis', lambda: Redis())
    assert app_module.worker_status()['status'] == 'degraded'


def test_evicted_active_job_falls_back_to_database():
    redis = FakeRedis()
    assert redis_cache.get_active_job(redis, 'ADI1', lambda: True) is True


def test_worker_identifies_redis_connectivity_in_postgres_session(monkeypatch):
    from services.worker import main as worker
    assert worker.worker_redis_status(None, configured=False) == 'unconfigured'
    class Online:
        def ping(self): return True
    class Offline:
        def ping(self): raise ConnectionError('offline')
    assert worker.worker_redis_status(Online(), configured=True) == 'online'
    assert worker.worker_redis_status(Offline(), configured=True) == 'offline'
