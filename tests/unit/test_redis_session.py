import json
from datetime import datetime, timedelta, timezone

import fakeredis
import pytest

from mark_engine.adapters import redis_cache


@pytest.fixture
def redis_client():
    redis_cache.reset_session_cache_state()
    return fakeredis.FakeRedis()


def make_row():
    now = datetime.now(timezone.utc)
    return ({'token_hash': 'digest', 'user_id': 2, 'csrf_hash': 'csrf',
             'expires_at': now + timedelta(hours=1), 'last_seen_at': now},
            {'user_id': 2, 'username': 'user', 'role': 'engineer', 'active': True,
             'display_name': 'User Two', 'password_hash': 'secret', 'locked_until': None})


def test_cache_hit_sliding_and_sensitive_fields(redis_client):
    row = make_row()
    calls = []
    def load():
        calls.append(1)
        return row
    assert redis_cache.cache_session(redis_client, 'digest', 900, load) == row
    redis_client.expire('mark:session:digest', 25)
    session, user = redis_cache.cache_session(redis_client, 'digest', 900, load)
    assert calls == [1]
    assert session['csrf_hash'] == 'csrf'
    assert user['role'] == 'engineer'
    assert redis_client.ttl('mark:session:digest') > 800
    cached = json.loads(redis_client.get('mark:session:digest'))
    assert set(cached) == {'user_id', 'username', 'role', 'csrf_hash', 'active', 'expires_at'}
    assert 'secret' not in json.dumps(cached)


def test_cache_expiry_miss_and_logout(redis_client):
    row = make_row()
    redis_cache.cache_session(redis_client, 'digest', 900, lambda: row)
    redis_client.delete('mark:session:digest')
    assert redis_cache.cache_session(redis_client, 'digest', 900, lambda: None) is None
    redis_cache.cache_session(redis_client, 'digest', 900, lambda: row)
    redis_cache.invalidate_session(redis_client, 'digest')
    assert redis_cache.cache_session(redis_client, 'digest', 900, lambda: None) is None


def test_outage_then_recovery_cannot_revive_logged_out_session(redis_client):
    redis_cache.cache_session(redis_client, 'digest', 900, make_row)
    class Offline:
        def delete(self, *args): raise ConnectionError('offline')
    redis_cache.invalidate_session(Offline(), 'digest')
    assert redis_cache.cache_session(redis_client, 'digest', 900, lambda: None) is None


def test_restart_does_not_trust_old_redis_entries(redis_client):
    redis_cache.cache_session(redis_client, 'digest', 900, make_row)
    redis_cache.reset_session_cache_state()
    assert redis_cache.cache_session(redis_client, 'digest', 900, lambda: None) is None


def test_redis_failure_falls_back_to_db(redis_client):
    class Broken:
        def get(self, *args): raise ConnectionError('offline')
    row = make_row()
    assert redis_cache.cache_session(Broken(), 'digest', 900, lambda: row) == row


def test_websocket_cache_cannot_extend_database_idle_expiry(redis_client):
    session, user = make_row()
    session['last_seen_at'] = datetime.now(timezone.utc) - timedelta(minutes=59, seconds=50)
    redis_cache.cache_session(redis_client, 'digest', 900, lambda: (session, user), sliding=False)
    assert 0 < redis_client.ttl('mark:session:digest') <= 10


def test_user_wide_invalidation_for_all_warm_sessions(redis_client):
    redis_cache.cache_session(redis_client, 'digest', 900, make_row)
    row = make_row()
    row[0]['token_hash'] = 'second'
    redis_cache.cache_session(redis_client, 'second', 900, lambda: row)
    redis_cache.invalidate_user_sessions(redis_client, 2)
    assert redis_cache.cache_session(redis_client, 'digest', 900, lambda: None) is None
    assert redis_cache.cache_session(redis_client, 'second', 900, lambda: None) is None


def test_cache_fill_cannot_race_session_revocation(redis_client):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    loaded = threading.Event()
    release = threading.Event()
    database = {'row': make_row()}
    def load():
        row = database['row']
        loaded.set()
        assert release.wait(3)
        return row
    def revoke():
        assert loaded.wait(3)
        with redis_cache.session_cache_lock:
            redis_cache.invalidate_session(redis_client, 'digest')
            database['row'] = None
    with ThreadPoolExecutor(max_workers=2) as executor:
        read = executor.submit(redis_cache.cache_session, redis_client, 'digest', 900, load)
        deleted = executor.submit(revoke)
        assert loaded.wait(3)
        release.set()
        assert read.result(timeout=3) is not None
        deleted.result(timeout=3)
    assert redis_cache.cache_session(redis_client, 'digest', 900, lambda: database['row']) is None
