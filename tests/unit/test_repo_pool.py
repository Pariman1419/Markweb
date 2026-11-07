import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import pytest
from mark_api.repo import Repo


def test_pool_waits_when_connections_are_busy():
    first_acquired = threading.Event()
    release_first = threading.Event()
    class Pool:
        busy = False
        def getconn(self):
            if self.busy:
                raise RuntimeError('pool exhausted')
            self.busy = True
            return object()
        def putconn(self, connection): self.busy = False
    repo = Repo.__new__(Repo)
    repo.pool = Pool()
    repo._pool_slots = threading.BoundedSemaphore(1)
    def first():
        with repo._conn():
            first_acquired.set()
            assert release_first.wait(3)
    def second():
        assert first_acquired.wait(3)
        with repo._conn(): return True
    with ThreadPoolExecutor(max_workers=2) as executor:
        a = executor.submit(first)
        b = executor.submit(second)
        assert first_acquired.wait(3)
        with pytest.raises(TimeoutError):
            b.result(timeout=0.1)
        release_first.set()
        a.result(timeout=3)
        assert b.result(timeout=3)
