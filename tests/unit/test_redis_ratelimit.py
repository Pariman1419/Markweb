from mark_engine.adapters.redis_cache import check_rate_limit


def test_unavailable_redis_is_fail_open():
    class Broken:
        def eval(self, *args):
            raise ConnectionError()
    assert check_rate_limit(Broken(), 1, 'scan_trigger', 5, 60) == (True, 0)
    assert check_rate_limit(None, 1, 'scan_trigger', 5, 60) == (True, 0)


def test_redis_result_provides_retry_delay():
    class Redis:
        def eval(self, *args):
            return [0, 12]
    assert check_rate_limit(Redis(), 1, 'scan_trigger', 5, 60) == (False, 12)


def test_recheck_rejected_when_user_limit_exceeded(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from mark_api.routers import scans
    monkeypatch.setattr(scans, 'get_redis', lambda: object())
    monkeypatch.setattr(scans, 'check_rate_limit', lambda *args: (False, 12))
    with pytest.raises(HTTPException) as exc:
        scans.recheck_elr('ADI1', None, {'user_id': 42}, None)
    assert exc.value.status_code == 429
    assert exc.value.headers['Retry-After'] == '12'


def test_real_sliding_window_enforces_user_isolation_and_ttl():
    import fakeredis
    redis = fakeredis.FakeRedis()
    for _ in range(5):
        assert check_rate_limit(redis, 1, 'scan_trigger', 5, 60) == (True, 0)
    allowed, retry = check_rate_limit(redis, 1, 'scan_trigger', 5, 60)
    assert not allowed and 1 <= retry <= 60
    assert check_rate_limit(redis, 2, 'scan_trigger', 5, 60) == (True, 0)
    assert 0 < redis.ttl('mark:ratelimit:user:1:scan_trigger') <= 60


def test_rate_limit_uses_database_fallback_when_redis_unavailable(monkeypatch):
    from mark_api.routers import scans
    class Repo:
        def rate_limit_status(self, user_id, action, limit, window_sec):
            assert (user_id, action, limit, window_sec) == (42, 'elr.recheck', 10, 60)
            return False, 20
    monkeypatch.setattr(scans, 'get_redis', lambda: None)
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        scans.recheck_elr('ADI1', None, {'user_id': 42}, Repo())
    assert exc.value.status_code == 429
    assert exc.value.headers['Retry-After'] == '20'
