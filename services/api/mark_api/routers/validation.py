"""Validation and Dashboard endpoints."""
from typing import Any

from fastapi import APIRouter, Depends, Query

from mark_api.deps import current_user, get_repo, require
from mark_api.grouping import summarize
from mark_api.repo import Repo

router = APIRouter(tags=["validation"])

# In-memory dashboard cache per run_id
_dashboard_cache: dict[int, dict[str, Any]] = {}


def clear_dashboard_cache() -> None:
    _dashboard_cache.clear()


@router.get("/dashboard")
def dashboard(run: int = Query(...), user: dict[str, Any] = Depends(require("read")), repo: Repo = Depends(get_repo)):
    if run in _dashboard_cache:
        return _dashboard_cache[run]

    lines = repo.lines(run)
    jobs = repo.jobs(run)
    res = summarize(lines, jobs)
    _dashboard_cache[run] = res
    return res
