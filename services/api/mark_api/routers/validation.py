"""Validation and Dashboard endpoints."""
from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, Depends, Query

from mark_api.deps import current_user, get_repo, require
from mark_api.grouping import summarize
from mark_api.repo import Repo

router = APIRouter(tags=["validation"])

_CACHE_MAX = 8
# In-memory dashboard cache per run_id (LRU 8)
_dashboard_cache: OrderedDict[int, dict[str, Any]] = OrderedDict()


def clear_dashboard_cache() -> None:
    _dashboard_cache.clear()


@router.get("/dashboard")
def dashboard(run: int = Query(...), user: dict[str, Any] = Depends(require("read")), repo: Repo = Depends(get_repo)):
    if run in _dashboard_cache:
        _dashboard_cache.move_to_end(run)
        return _dashboard_cache[run]

    lines = repo.lines(run)
    jobs = repo.jobs(run)
    res = summarize(lines, jobs)
    _dashboard_cache[run] = res
    if len(_dashboard_cache) > _CACHE_MAX:
        _dashboard_cache.popitem(last=False)
    return res
