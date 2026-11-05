# Trial Acceptance and Monitor Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the trial usable end to end on real data, by fixing the empty ELR table and proving each `Repo`/router against the real DB. Then bring `/api/metrics` and caching in line with the Phase 2 spec.

**Architecture:** No new design. This plan closes gaps between the code and `docs/superpowers/specs/2026-11-05-phase2-trial-design.md`:
- §8: acceptance criteria
- §15: log and monitor
- §18: performance

The other work is a bug fix plus a read-only real-DB check script that Jenkins runs as a non-blocking stage.

**Tech Stack:** FastAPI, psycopg2, PostgreSQL `mark_web` (read-only use here), React + TS + Vite, Jenkins (Windows agent `mark-web`).

**Spec:** `docs/superpowers/specs/2026-11-05-phase2-trial-design.md` (§8, §15, §18). Bug evidence is in the "Why" section below.

## Why (evidence, 2026-11-05)

- **Empty ELR table:** the Dashboard shows "No ELR packages found matching current filters", while the cards and charts are correct.
  - **Root cause:** in `routers/mark.py:63`, `l.get("warning", "").split(":")` raises `AttributeError: 'NoneType'` when the DB column is NULL. The key exists, so the default `""` is not used.
  - The same pattern is at lines 67 (`detail`) and 71 and 74 (`hold_reason`).
  - `/api/elrs` returns 500, and `Dashboard.tsx:85` only does `console.error`, so the UI looks like "no results".
- **Why tests missed it:** the unit tests use `FakeRepo`, which never has `None` text fields. The earlier `/api/runs` column bug (fixed in 6bb955f) was missed for the same reason.
- **`/api/metrics` (§15):**
  - `login_ok`, `login_failed`, `login_locked` and `rate_limited` are never incremented.
  - There are no p50/p95 values, no `db.error` count, and no active-session count.
  - `durations` grows without bound.
- **§18 gaps:**
  - The dashboard cache is an unbounded dict; the spec says LRU 8.
  - The ABS thumbnail `<img>` lacks `loading="lazy"`.

## Global Constraints

- **Read-only real DB:** never write `mark_logic` or Oracle. The real-DB check script only reads, and never logs mark values, SLR text or image paths.
- **Secrets:** they stay in `.env`, which is git-ignored, and nothing prints them.
- **Tests:** no duplicate tests (user rule). Add only tests that pin the new behaviour.
- **Docs:** every commit also updates `HANDOFF.md` §4 and `docs/qa/QA_LOG.md`.
- **Pushing:** push only after the unit suite passes locally. After pushing, wait for the Jenkins build (http://localhost:8080/job/mark-web) to finish green before ticking the task's last step. **A task is not done while CI is red.**
- **Stop and ask the user before:**
  - any DB write
  - any migration
  - creating or changing app users

## Review Focus

1. **NULL text anywhere in a job or line row** (`warning`, `detail`, `hold_reason`, `hold_detail`, `compare_rules`, `abs_no`) must not 500. Covered by Task 1's test, which nulls every one of these fields.
2. **A failed fetch shows an error, not "no results".** A user must be able to tell "the server failed" from "the filter matched nothing". Covered by Task 1 Step 5 (manual check by stopping the API).
3. **The real-DB check must fail loudly but must not block deploys.** If the DB is unreachable, the Jenkins stage is UNSTABLE and the build still deploys. Covered in Task 2.
4. **p95 with few samples.** One sample → p50 = p95 = that value. Zero samples → the route is absent, not an error. Covered in Task 3's test.
5. **Cache eviction must not serve the wrong run.** The 9th distinct run evicts the least recently used one, and a re-request recomputes. Covered in Task 4's test.

---

### Task 1: NULL-safe ELR list and detail, plus a visible load error

**Files:**
- Modify: `services/api/mark_api/routers/mark.py` (lines 44–110 `list_elrs` and 120–170 `get_elr`)
- Modify: `web/src/pages/Dashboard.tsx` (fetch effects around lines 59, 67 and 85, and the table area)
- Test: `tests/unit/test_api_routes.py`

**Interfaces:**
- Produces: a module helper in `routers/mark.py`, `_text(v: Any) -> str`, which returns `""` for `None` and `str(v)` otherwise. Every `.get(...)` on a DB row that is then used as a string goes through `_text`.

- [ ] **Step 1: Write the failing test**

```python
def test_elrs_and_detail_handle_null_text_fields(client, fake_repo):
    for l in fake_repo.lines_data[18]:
        l.update(warning=None, detail=None, compare_rules=None)
    for j in fake_repo.jobs_data[18]:
        j.update(hold_reason=None, hold_detail=None, abs_no=None)
    _login(client)
    r = client.get("/api/elrs?run=18&page=1")
    assert r.status_code == 200 and r.json()["total"] >= 1
    assert client.get("/api/elrs?run=18&q=adi").status_code == 200
    assert client.get("/api/elrs/ADI2607001?run=18").status_code == 200
```

- [ ] **Step 2: Run it.** `python -m pytest tests/unit/test_api_routes.py -k null_text -q`. Expected: FAIL with 500, or an `AttributeError` traceback.
- [ ] **Step 3: Implement `_text`** and use it at every string use of a row field in `list_elrs` and `get_elr`:
  - `warning`, `detail` and `hold_reason` (lines 63, 67, 71, 74)
  - `abs_no` in the `q` filter and the row
  - the `get_elr` line dict
  - the `job` fallback dict
- [ ] **Step 4: Run the unit suite.** `python -m pytest tests/unit -q`. Expected: all pass.
- [ ] **Step 5: Web.** In `Dashboard.tsx`, add `const [loadError, setLoadError] = useState<string | null>(null)`.
  - **On failure:** each failing fetch (runs, dashboard, ELRs) sets a Thai message:
    - `โหลดรายการ ELR ไม่สำเร็จ (เซิร์ฟเวอร์ผิดพลาด) — ลองใหม่อีกครั้ง`
    - `โหลด Dashboard ไม่สำเร็จ`
    - `โหลดรายการ run ไม่สำเร็จ`
  - **Display:** show it as a red banner above the table.
  - **On success:** clear the message.
  - **Empty table:** only show the table's empty state when the fetch succeeded.
  - Run `cd web && npm run build`. Expected: 0 errors.
- [ ] **Step 6: Commit and push.** Use `git commit -m "fix: NULL-safe ELR list/detail and visible load errors"`, then push and wait for the Jenkins build to be green.

### Task 2: Read-only real-DB acceptance check (spec §8) and a Jenkins stage

**Files:**
- Create: `scripts/check_trial_readonly.py`
- Modify: `Jenkinsfile` (new stage `Real-DB check` after `Smoke test`)
- Modify: `services/README.md` (one paragraph on how to run it)

**Interfaces:**
- Consumes:
  - `Repo()` from `mark_api.repo`
  - router functions `list_runs`, `list_elrs` and `get_elr` (from `routers.mark`) and `dashboard` (from `routers.validation`), called directly with `user={}` and `repo=Repo()`, the way `routers/mark.py` declares them
  - `load_env(path)` from `mark_engine.adapters.env`
- Produces: the CLI `python scripts/check_trial_readonly.py --run 19 [--env-file PATH] [--sample 20]`, which exits 0 when every check passes and 1 otherwise. It prints one line per check, `OK <name> <short value>` or `FAIL <name> <reason>`, and never prints mark values, SLR text or paths.

Checks, in this order (each wrapped so that one failure doesn't hide the others):

| name | pass when |
|---|---|
| `runs` | `list_runs` includes the run |
| `dashboard_cards` | counts equal `TRUE 866, WARNING 214, ERROR 41, HOLD 34` for run 19 (hard-coded reference, spec analysis M4); for other runs, only that all four keys exist |
| `elrs_total` | `list_elrs(page=1)` total equals `len(Repo().jobs(run))` (402 for run 19) |
| `elrs_pages` | walking every page yields `total` unique `elr_no` |
| `elr_detail` | for `--sample` ELRs (first N by `elr_no`), `get_elr` returns without exception |
| `oracle_raw` | for the same sample, `snapshot.oracle_top_raw` has 5 entries |
| `expected_match` | for the same sample, every line's `expected` equals `Repo().lines_for_elr(...)[i]["expected"]` |
| `admin_reads` | `Repo().admin_users()`, `activity(today-13, today, run)` and `audit_events(..., page=1)` run without error |

- [ ] **Step 1: Write the script** to the table above. Put `sys.path.insert(0, <repo root>)` and `services/api` first, as `scripts/create_app_user.py` does.
- [ ] **Step 2: Run it locally.** `python scripts/check_trial_readonly.py --run 19`. Expected: every line OK and exit code 0, after Task 1 is merged. Paste the output, which has no values, into QA_LOG.
- [ ] **Step 3: Jenkins stage.**

```groovy
stage('Real-DB check') {
  when { expression { params.DEPLOY } }
  steps {
    catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
      bat '.venv\\Scripts\\python scripts\\check_trial_readonly.py --run 19 --env-file "%MARK_ENV_FILE_BS%"'
    }
  }
}
```

  `MARK_ENV_FILE_BS` is `params.ENV_FILE.replace('/', '\\')`, set in `environment`.
- [ ] **Step 4: Commit and push.** Use `git commit -m "test: read-only real-DB acceptance check and Jenkins stage"`. Then wait for green. The new stage must show `OK` lines in the console.

### Task 3: `/api/metrics` per spec §15

**Files:**
- Create: `services/api/mark_api/metrics.py` (move `InProcessMetrics` out of `app.py`, which avoids a circular import with routers)
- Modify: `services/api/mark_api/app.py`, `routers/auth.py`, `repo.py`
- Test: `tests/unit/test_api_core.py` (the metrics class) and `tests/unit/test_api_routes.py` (the endpoint shape)

**Interfaces:**
- Produces: `mark_api.metrics.metrics`, a singleton `InProcessMetrics` with:
  - `record_request(status_code: int, duration_ms: float, route: str) -> None`. Durations are kept in `collections.deque(maxlen=1000)` per route.
  - `inc(name: Literal["login_ok", "login_failed", "login_locked", "db_error"]) -> None`
  - `snapshot(active_sessions: int | None) -> dict`, which returns:
    `{"requests": {...}, "login_ok", "login_failed", "login_locked", "db_error", "active_sessions", "routes": {route: {"count", "p50_ms", "p95_ms"}}}`
    - Percentiles use the nearest-rank method on the sorted deque: `p = v[ceil(q*n)-1]`.
- Produces: `Repo.active_sessions() -> int`, which is `select count(*) from mark_app.user_session where expires_at > now()`.
- **`rate_limited` is removed.** NGINX answers 429 before the API sees the request; the count lives in the NGINX JSON log (`limit_req`). Note this in `services/README.md`.

- [ ] **Step 1: Write the failing tests**

```python
def test_metrics_percentiles_and_cap():
    m = InProcessMetrics()
    m.record_request(200, 10.0, "/api/x")
    s = m.snapshot(None)["routes"]["/api/x"]
    assert (s["count"], s["p50_ms"], s["p95_ms"]) == (1, 10.0, 10.0)
    for i in range(1, 1201):
        m.record_request(200, float(i), "/api/y")
    y = m.snapshot(None)["routes"]["/api/y"]
    assert y["count"] == 1000 and y["p95_ms"] == 1151.0   # last 1000 = 201..1200
    assert "/api/z" not in m.snapshot(None)["routes"]

def test_metrics_counts_logins(client, fake_repo):
    # use the metrics_token Bearer pattern from test_engineer_cannot_read_metrics
    before = metrics.login_failed
    client.post("/api/auth/login", json={"username": "engineer1", "password": "WrongPassword!"})
    _login(client)
    body = client.get("/api/metrics", headers={"Authorization": "Bearer tok_test_metrics_12345"}).json()
    assert body["login_failed"] == before + 1 and body["login_ok"] >= 1
    assert "active_sessions" in body and "rate_limited" not in body
```

- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
  - **Login counters:** `routers/auth.py` calls `metrics.inc(...)` next to each existing `auth.login_ok` / `auth.login_failed` / `auth.locked` audit.
  - **DB errors:** `Repo._execute`'s except block calls `metrics.inc("db_error")`.
  - **Endpoint:** `/api/metrics` returns `metrics.snapshot(repo.active_sessions())`, catching a DB error and passing `None` instead.
  - **FakeRepo:** gets `active_sessions()`, which returns `len(self.sessions)`.
- [ ] **Step 4: Run the unit suite.** Expected: all pass.
- [ ] **Step 5: Commit and push.** Use `git commit -m "feat: metrics per spec 15 (login counts, p50/p95 ring buffer, db_error, active sessions)"`, then wait for green.

### Task 4: Spec §18 leftovers (dashboard LRU 8, lazy ABS thumbnail)

**Files:**
- Modify: `services/api/mark_api/routers/validation.py` (lines 12–30)
- Modify: `web/src/pages/Preview.tsx:259` (thumbnail `<img>` only; the zoomed image at :404 stays eager)
- Test: `tests/unit/test_api_routes.py`

**Interfaces:**
- Produces: `_dashboard_cache: OrderedDict[int, dict]` with `_CACHE_MAX = 8`.
  - **On a hit:** `move_to_end(run)`.
  - **On a store:** if the size is over 8, `popitem(last=False)`.
  - `clear_dashboard_cache()` is kept.

- [ ] **Step 1: Write the failing test**

```python
def test_dashboard_cache_lru_8(client, fake_repo):
    from mark_api.routers import validation
    _login(client)
    for run in range(100, 109):                       # 9 distinct runs (FakeRepo returns empty data → still cached)
        client.get(f"/api/dashboard?run={run}")
    assert len(validation._dashboard_cache) == 8 and 100 not in validation._dashboard_cache
```

- [ ] **Step 2: Run it.** Expected: FAIL (9 entries).
- [ ] **Step 3: Implement** the LRU, and add `loading="lazy"` to the thumbnail `<img>`.
- [ ] **Step 4: Run the unit suite and `npm run build`.** Expected: all pass.
- [ ] **Step 5: Commit and push.** Use `git commit -m "perf: dashboard cache LRU 8 and lazy ABS thumbnail"`, then wait for green.

### Task 5: User walkthrough (needs the user)

- [ ] **Step 1 [USER]:** on http://localhost:8088, as the user's engineer account:
  1. Open the Dashboard. The ELR table lists 402 for run 19, 50 per page.
  2. Open one ELR. The ABS image shows. The Oracle 21-cell table matches the user's knowledge of `TOP_MARK1–5`, and the system side matches the expected mark.
  3. Save a review on a line, then Approve or Reject.
- [ ] **Step 2:** confirm in `/admin` (as `qa_admin` or the user's admin account) that the events show `review.saved` and `approval.saved` with IPs, and that activity shows the decision.
- [ ] **Step 3:** record the result in HANDOFF §4 and QA_LOG, including anything the user found wrong.
