"""Validation and Dashboard endpoints."""
from typing import Any
from fastapi import APIRouter, Depends, Query

from mark_api.deps import current_user, get_repo, require
from mark_api.grouping import summarize
from mark_api.repo import Repo
from mark_api.redis_client import get_redis
from mark_engine.adapters.redis_cache import cache_dashboard

router = APIRouter(tags=["validation"])

def clear_dashboard_cache() -> None:
    """Retained for callers that clear the former process-local cache."""


@router.get("/dashboard")
def dashboard(run: int = Query(...), user: dict[str, Any] = Depends(require("read")), repo: Repo = Depends(get_repo)):
    return cache_dashboard(
        get_redis(), f"mark:dashboard:{run}", 30,
        lambda: summarize(repo.lines(run), repo.jobs(run)),
    )
