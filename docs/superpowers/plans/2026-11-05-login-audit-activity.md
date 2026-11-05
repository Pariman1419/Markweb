# Login Audit, Admin Unlock and Activity Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record every login outcome in `mark_app.audit_log` with IP and request_id, let an admin unlock users, give a manager an activity page, and keep API logs across redeploys.

**Architecture:**
- **Schema:** one additive migration (two columns and one index on `audit_log`).
- **API:** `Repo.audit` gains request context, and the auth router and `current_user` write the new actions. A new `routers/admin.py`, gated by a new `admin` action, serves users, unlock, activity and events.
- **Web:** a lazy `/admin` page.
- **Logs:** an optional rotating file handler.

**Tech Stack:** FastAPI, psycopg2, PostgreSQL 16 (`mark_web`, schema `mark_app`), React 19 + TS + Vite + Tailwind, Docker Compose, Jenkins.

**Spec:** `docs/superpowers/specs/2026-11-05-login-audit-activity-design.md`

## Global Constraints

- **No usernames recorded:** never store or log a typed username. `SENSITIVE_KEYS` already drops `username`, and unknown-user audit rows carry `user_id = None`.
- **IP source:** `client_ip` comes from the `X-Real-IP` header, falling back to `request.client.host`. Nothing else.
- **Audit can't break login:** an audit failure must not change a login response. Catch the exception and `log_event("db.error", ...)`.
- **Query cost:** admin queries are a fixed number of grouped SQL statements per request.
  - Activity range: at most 92 days. Default: the last 14 days, and the latest run.
  - Events: 50 rows per page, newest first.
- **Day boundary:** `(created_at at time zone 'Asia/Bangkok')::date`.
- **Roles:** the new action `"admin"` is allowed only for role `admin`. No new role; no change to the rights for review or approve.
- **Migration:** additive and idempotent (`if not exists`). It runs on the shared DB only after the user says go.
- **Testing and docs:**
  - Do not duplicate existing tests (e.g., `test_five_failures_lock` and `test_failed_login_log_has_no_username` stay as they are).
  - Every commit also updates `HANDOFF.md` §4 and `docs/qa/QA_LOG.md`.

## Review Focus

1. **Spoofed IP.** A client sending its own `X-Real-IP` must not control the recorded IP. NGINX overwrites the header, so the API trusts it, and the dev server is localhost only. Covered by a test that the header value is what gets stored. The NGINX `proxy_set_header X-Real-IP $remote_addr` lines must stay.
2. **Unlock CSRF.** Unlock is a state-changing POST and must fail without the CSRF header. Test it in Task 3.
3. **Unlocking an unknown or non-locked user.** Unknown → 404. A user who is not locked → 200, and still audited. Test it in Task 3.
4. **Bad dates on activity.** `from > to`, a range over 92 days, or a malformed date → 422, not 500. Test it in Task 3.
5. **Expired session audited only once.** A second request with the same dead cookie is "Invalid session" and writes no new audit row, because the session row was deleted. Test it in Task 2.

---

### Task 1: Migration 0006 and request context in `Repo.audit`

**Files:**
- Create: `migrations/0006_audit_context.sql`
- Modify: `services/api/mark_api/repo.py` (`audit`, around lines 183–192)
- Modify: `services/api/mark_api/deps.py` (add `audit_ctx`)
- Modify: `tests/unit/test_api_routes.py` (`FakeRepo.audit` accepts the new kwargs)
- Test: `tests/unit/test_api_routes.py`

**Interfaces:**
- Produces:
  - `Repo.audit(user_id: int | None, action: str, run_id=None, elr_no=None, line_no=None, detail=None, *, client_ip: str | None = None, request_id: str | None = None) -> int`
  - `audit_ctx(request: Request) -> dict[str, str | None]`, which returns `{"client_ip": ..., "request_id": ...}`.

- [x] **Step 1: Write the migration** `migrations/0006_audit_context.sql`, exactly as in spec §5.1, wrapped in `begin; … commit;` like 0005.
- [x] **Step 2: Write the failing test**

```python
def test_review_audit_carries_ip_and_request_id(client, fake_repo):
    csrf = _login(client)
    client.post("/api/reviews",
                json={"run_id": 18, "elr_no": "ADI2607001", "line_no": 1, "reason": "OTHER",
                      "note": "n", "corrected_mark": "VAL", "is_draft": False},
                headers={"X-CSRF-Token": csrf, "X-Real-IP": "10.0.0.7", "X-Request-ID": "req-test-1"})
    row = fake_repo.audit_data[-1]
    assert row["action"] == "review.saved"
    assert row["client_ip"] == "10.0.0.7"          # sent as X-Real-IP header
    assert row["request_id"] == "req-test-1"       # sent as X-Request-ID header
```

- [x] **Step 3: Run it.** `python -m pytest tests/unit/test_api_routes.py -k carries_ip -q`. Expected: FAIL with a KeyError on `client_ip`.
- [x] **Step 4: Implement.**
  - `audit_ctx` in `deps.py`: `request_id` is `request.state.request_id`; `client_ip` is `X-Real-IP` or `request.client.host`.
  - Extend `Repo.audit`'s insert with the two columns. Pass `client_ip` as text; Postgres casts it to `inet`.
  - Pass `**audit_ctx(request)` in every existing `repo.audit(...)` call: auth login_ok and logout, plus workflow review and approval. Add a `request: Request` parameter where a route lacks one.
  - `FakeRepo.audit` stores both new keys.
- [x] **Step 5: Run the whole unit suite.** `python -m pytest tests/unit -q`. Expected: all pass.
- [x] **Step 6: Commit.** Run `git add migrations/0006_audit_context.sql services/api/mark_api tests/unit HANDOFF.md docs/qa/QA_LOG.md`, then `git commit -m "feat: audit rows carry client_ip and request_id (migration 0006)"`.

### Task 2: Audit failed logins, lockouts and expired sessions

**Files:**
- Modify: `services/api/mark_api/auth.py` (add `session_status`; `session_valid` delegates to it)
- Modify: `services/api/mark_api/routers/auth.py` (`login`)
- Modify: `services/api/mark_api/deps.py` (`current_user`)
- Modify: `services/api/mark_api/repo.py` (no change to `audit`; add `safe_audit`)
- Test: `tests/unit/test_api_core.py`, `tests/unit/test_api_routes.py`

**Interfaces:**
- Consumes: `Repo.audit(..., client_ip=, request_id=)` and `audit_ctx(request)` from Task 1.
- Produces:
  - `session_status(session: dict, now: datetime) -> Literal["ok", "absolute", "idle"]`.
  - `safe_audit(repo, user_id, action, request, **kw) -> None`, a module function in `deps.py`. It calls `repo.audit(..., **audit_ctx(request))` and swallows exceptions with `log_event("db.error", where="audit", action=action)`.

- [x] **Step 1: Write the failing tests.**

```python
# test_api_core.py
def test_session_status_absolute_and_idle():
    now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
    assert session_status({"expires_at": now - timedelta(seconds=1), "last_seen_at": now}, now) == "absolute"
    assert session_status({"expires_at": now + timedelta(hours=1), "last_seen_at": now - timedelta(minutes=61)}, now) == "idle"
    assert session_status({"expires_at": now + timedelta(hours=1), "last_seen_at": now}, now) == "ok"

# test_api_routes.py
def test_unknown_user_audited_without_name(client, fake_repo, capsys):
    client.post("/api/auth/login", json={"username": "nobody-xyz", "password": "x" * 12},
                headers={"X-Real-IP": "10.0.0.9"})
    row = fake_repo.audit_data[-1]
    assert (row["action"], row["user_id"], row["detail"]["reason"], row["client_ip"]) == \
           ("auth.login_failed", None, "unknown_user", "10.0.0.9")
    assert "nobody-xyz" not in json.dumps(fake_repo.audit_data, default=str) + capsys.readouterr().out

def test_fifth_failure_audits_failed_and_locked(client, fake_repo):
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "engineer1", "password": "WrongPassword!"})
    actions = [r["action"] for r in fake_repo.audit_data]
    assert actions.count("auth.login_failed") == 5 and actions[-1] == "auth.locked"
    assert fake_repo.audit_data[-2]["detail"] == {"reason": "bad_password", "failed_count": 5}

def test_locked_and_inactive_attempts_audited(client, fake_repo):
    u = fake_repo.users["engineer1"]
    u["locked_until"] = datetime.now(timezone.utc) + timedelta(minutes=10)
    client.post("/api/auth/login", json={"username": "engineer1", "password": "ValidPassword123!"})
    assert fake_repo.audit_data[-1]["detail"] == {"reason": "locked"}
    u["locked_until"], u["active"] = None, False
    client.post("/api/auth/login", json={"username": "engineer1", "password": "ValidPassword123!"})
    assert fake_repo.audit_data[-1]["detail"] == {"reason": "inactive"}

def test_expired_session_audited_once(client, fake_repo):
    _login(client)
    for s in fake_repo.sessions.values():
        s["last_seen_at"] -= timedelta(minutes=61)
    assert client.get("/api/runs").status_code == 401
    assert client.get("/api/runs").status_code == 401
    rows = [r for r in fake_repo.audit_data if r["action"] == "auth.session_expired"]
    assert len(rows) == 1 and rows[0]["detail"] == {"why": "idle"}

def test_audit_failure_does_not_break_login(client, fake_repo, monkeypatch):
    monkeypatch.setattr(fake_repo, "audit", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    assert client.post("/api/auth/login", json={"username": "engineer1", "password": "ValidPassword123!"}).status_code == 200
```

- [x] **Step 2: Run them.** `python -m pytest tests/unit -k "session_status or audited or audit_failure or fifth_failure" -q`. Expected: FAIL.
- [x] **Step 3: Implement.**
  - `session_status` returns `"absolute"` when the 8-hour expiry has passed, and `"idle"` after 60 minutes since `last_seen_at`. Keep `session_valid(...) == (session_status(...) == "ok")`.
  - In `login`, every exit writes one `safe_audit`, with the `detail` from spec §5.2:
    - unknown user → `auth.login_failed`, `user_id=None`, `reason: unknown_user`
    - locked → `auth.login_failed`, `reason: locked`
    - inactive → `auth.login_failed`, `reason: inactive`
    - bad password → `auth.login_failed` with `failed_count`; if the account is now locked, also `auth.locked` with `locked_until` as an ISO string
    - ok → `auth.login_ok`
  - In `current_user`, when `session_status` is not ok: `safe_audit(repo, user["user_id"], "auth.session_expired", request, detail={"why": status})`, before the existing `delete_session`.
  - Replace the Task 1 direct `repo.audit` calls in the auth router with `safe_audit`.
- [x] **Step 4: Run the unit suite.** `python -m pytest tests/unit -q`. Expected: all pass.
- [x] **Step 5: Commit** with message `"feat: audit failed logins, lockouts and expired sessions"`, including HANDOFF and QA_LOG.

### Task 3: Admin API: users, unlock, activity, events

**Files:**
- Create: `services/api/mark_api/routers/admin.py`
- Modify: `services/api/mark_api/auth.py` (`can` matrix: `"admin": {"read", "metrics", "admin"}`, and widen the Literal)
- Modify: `services/api/mark_api/app.py` (`include_router(admin.router, prefix="/api")`)
- Modify: `services/api/mark_api/repo.py` (four methods below)
- Modify: `tests/unit/test_api_routes.py` (FakeRepo stubs and tests)

**Interfaces:**
- Consumes: `safe_audit` (Task 2), `require(action)` (existing).
- Produces the following `Repo` methods, each one SQL statement except `activity`:
  - `admin_users() -> list[dict]` returns `{user_id, username, display_name, role, active, failed_count, locked_until, last_login_at}`. `last_login_at` comes from a left join on `max(created_at)` of `auth.login_ok`, grouped by user.
  - `unlock_user(user_id: int) -> bool` sets `failed_count=0` and `locked_until=null`, and returns False if there is no such row.
  - `activity(date_from: date, date_to: date, run_id: int) -> dict` with keys `per_user_day`, `run_progress` and `auth_per_day`, as in spec §5.3. It runs exactly 3 statements.
    - `run_progress` takes the latest decision per ELR with `distinct on (elr_no) … order by elr_no, created_at desc` over `approval`, against the `count(*)` of `mark_logic.job_result` for the run.
  - `audit_events(date_from, date_to, user_id: int | None, action: str | None, page: int) -> list[dict]`, with `limit 50 offset 50*(page-1)`, joined to `app_user` for `display_name`.
- Routes, all under `/api/admin` with `Depends(require("admin"))`:
  - `GET /users`: adds `state` via `login_state`.
  - `POST /users/{user_id}/unlock`: 404 if `unlock_user` is False, otherwise `safe_audit(admin.unlock, detail={"target_user_id": id})`, then `{"status": "ok"}`.
  - `GET /activity?from=&to=&run_id=`: 422 when `from > to` or the range is over 92 days. Malformed dates are handled by FastAPI's `date` parsing (422). `run_id` defaults to `max(run_id)` from `repo.runs()`.
  - `GET /events?from=&to=&user_id=&action=&page=1`: same date defaults, and `page >= 1`.

- [x] **Step 1: Write the failing tests** (FakeRepo returns canned rows for `admin_users`, `activity` and `audit_events`; `unlock_user` edits `self.users`):

```python
def test_admin_routes_forbidden_for_engineer(client):
    _login(client)
    assert client.get("/api/admin/users").status_code == 403

def test_admin_unlock_clears_lock_and_audits(client, fake_repo):
    fake_repo.users["engineer1"].update(failed_count=5, locked_until=datetime.now(timezone.utc) + timedelta(minutes=15))
    csrf = _login(client, "admin1")
    uid = fake_repo.users["engineer1"]["user_id"]
    assert client.post(f"/api/admin/users/{uid}/unlock").status_code == 403                    # no CSRF header
    r = client.post(f"/api/admin/users/{uid}/unlock", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and fake_repo.users["engineer1"]["locked_until"] is None
    assert fake_repo.audit_data[-1]["detail"] == {"target_user_id": uid}
    assert client.post("/api/admin/users/99999/unlock", headers={"X-CSRF-Token": csrf}).status_code == 404

def test_admin_users_state(client, fake_repo):
    _login(client, "admin1")
    states = {u["username"]: u["state"] for u in client.get("/api/admin/users").json()}
    assert states["engineer1"] == "OK"

def test_admin_activity_range_validation(client):
    _login(client, "admin1")
    assert client.get("/api/admin/activity?from=2026-01-01&to=2026-06-01").status_code == 422   # > 92 days
    assert client.get("/api/admin/activity?from=2026-11-05&to=2026-11-01").status_code == 422   # from > to
    assert client.get("/api/admin/activity?from=bad").status_code == 422
    assert client.get("/api/admin/activity").status_code == 200
```

- [x] **Step 2: Run them.** `python -m pytest tests/unit -k admin -q`. Expected: FAIL with 404s (no router).
- [x] **Step 3: Implement** the repo methods, `routers/admin.py`, the matrix change and router registration.
- [x] **Step 4: Run the unit suite** (all pass). Then the manual SQL check against the real DB, with the 0006 migration applied:

  ```bash
  python -c "from mark_engine.adapters.env import load_env; load_env(); import sys; sys.path.insert(0,'services/api'); from mark_api.repo import Repo; from datetime import date; r=Repo(); print(r.admin_users()); print(r.activity(date(2026,10,23), date(2026,11,5), 19)['run_progress'])"
  ```

  Expected: no SQL error, and `run_progress.total_elrs == 402` for run 19.
- [x] **Step 5: Commit** with message `"feat: admin API for users, unlock, activity and events"`.

### Task 4: Web `/admin` page

**Files:**
- Create: `web/src/pages/Admin.tsx`
- Modify: `web/src/App.tsx` (lazy route `/admin`, like `Preview`)
- Modify: `web/src/api.ts` (types `AdminUser`, `Activity`, `AuditEvent`, using `apiFetch`)
- Modify: `web/src/pages/Dashboard.tsx` (an "Admin" link in the header when `user?.role === 'admin'`)

**Interfaces:**
- Consumes: the Task 3 routes and response shapes (spec §5.3).

- [ ] **Step 1: Build `Admin.tsx`** with three sections, in Thai labels as in spec §5.4:
  - **"ผู้ใช้" (users):** a table, with a state badge and an Unlock button shown only when the state is LOCKED. The POST goes through `apiFetch`, which already sends the CSRF header.
  - **"ภาพรวม" (overview):**
    - two date inputs, default today−13 → today
    - four progress cards in the `StatusCards` style
    - a per-day reviews/approvals bar chart, reusing `MonthlyChart`'s approach
    - a per-user totals table
    - an auth-problems per-day chart
  - **"เหตุการณ์ล่าสุด" (latest events):** a table with user and action filters and next/prev paging.
  - Non-admin users who open `/admin` are redirected to `/`.
- [x] **Step 2: Build.** `cd web && npm run build`. Expected: 0 TS errors. The initial chunk stays ≤ 300 KB gzip, and `Admin` is its own chunk.
- [ ] **Step 3: Manual check** on localhost:8088 after the Jenkins deploy, as admin:
  - Users list shows.
  - Lock a test user with 5 bad logins, then Unlock it.
  - The events table shows `auth.login_failed`, `auth.locked` and `admin.unlock`, each with an IP.
- [x] **Step 4: Commit** with message `"feat: admin page with users, activity overview and auth events"`.

### Task 5: Persistent API log file

**Files:**
- Modify: `services/api/mark_api/logging.py`
- Modify: `docker-compose.yml`, `.env.example`, `.gitignore`, `.dockerignore`
- Test: `tests/unit/test_api_core.py`

**Interfaces:**
- Produces: when `MARK_LOG_DIR` is set, `log_event` also writes the same JSON line to `<MARK_LOG_DIR>/api.jsonl` through a `RotatingFileHandler(maxBytes=10*1024*1024, backupCount=5)`. The handler is created once, lazily.

- [ ] **Step 1: Write the failing test.**

```python
def test_log_event_also_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MARK_LOG_DIR", str(tmp_path))
    import importlib, mark_api.logging as lg; importlib.reload(lg)
    lg.log_event("t.file", user_id=1, username="secret")
    line = (tmp_path / "api.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
    assert json.loads(line)["event"] == "t.file" and "secret" not in line
```

- [ ] **Step 2: Run it.** Expected: FAIL (no file).
- [ ] **Step 3: Implement.**
  - `logging.py`: the handler as described in Interfaces.
  - `docker-compose.yml`, api service:
    - add `MARK_LOG_DIR=/app/logs`
    - add the volume `${MARK_LOG_HOST_DIR:-./logs}:/app/logs`
  - `.env.example`: add `MARK_LOG_HOST_DIR=./logs`.
  - Add `logs/` to `.gitignore` and `.dockerignore`.
  - Jenkinsfile: add a parameter `MARK_LOG_HOST_DIR`, default `D:/CIM Project/mark-web/logs`, exported in `environment`, so that deploys from the Jenkins workspace keep one log folder.
- [ ] **Step 4: Run the unit suite and `docker compose config`.** Expected: pass, and the config is valid.
- [ ] **Step 5: Commit** with message `"feat: API JSON logs also written to a rotating host file"`.

### Task 6: Rollout (needs the user)

- [ ] **Step 1 [USER go-ahead]:** apply `migrations/0006_audit_context.sql` to `mark_web` at 10.151.28.2, as postgres. Verify with `\d mark_app.audit_log`, which should show `client_ip inet` and `request_id text`.
- [ ] **Step 2:** push `phase2/trial`. Jenkins builds and deploys. Expected: SUCCESS and `smoke OK`.
- [ ] **Step 3 [USER]:** create the admin account in the user's own terminal. The password is typed by the user only.
  `python scripts/create_app_user.py <admin-username> --name "<Display Name>" --role admin`
- [ ] **Step 4:** run the Task 4 manual check, then record the results in HANDOFF §4 and QA_LOG.
