# Phase 2 Trial (Dashboard + ELR Preview + Review) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The user (Mark Engineer) logs in, sees a Dashboard of the latest Jul–Nov run, opens any ELR's Preview (system vs Oracle ACTIVEL grids + ABS image), records line reviews and approves.

**Architecture:** One FastAPI app (`services/api/`) with routers named after the architecture's services (Auth, Mark, Validation, Workflow). It reads run results from `mark_logic.line_result`/`job_result` and per-ELR context from a new `mark_app.elr_snapshot`, and writes only `mark_app`. React + TS + Vite SPA (`web/`) served by NGINX, which also proxies `/api`. Docker Compose on 10.153.90.17.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, psycopg2 (already used by `scripts/load_r1_to_pg.py`), argon2-cffi, pytest · React 18, TypeScript, Vite, react-router, a chart library (builder's choice) · NGINX · Docker Compose · PostgreSQL `mark_web` @ 10.151.28.2.

**Spec:** `docs/superpowers/specs/2026-11-05-phase2-trial-design.md`

## Global Constraints

- Never write Oracle or `mark_logic`. The web app writes only to `mark_app`.
- Keep runs 1–17 and `logic_rule` untouched. A new run gets a new `run_id`.
- No passwords in the repo. Read everything from `.env` / env vars (`MARK_PG_*`, `MARK_FILES_ROOT`, `MARK_SESSION_HOURS=8`).
- TOP MARK only in the UI.
- Customer ABS images stay on the internal network. They are served only from under `MARK_FILES_ROOT`.
- Same-origin only. Do not add FastAPI `CORSMiddleware` unless `MARK_CORS_ORIGINS` is set (default empty). See spec §16.
- Out of scope this round: WebSocket (B3) and gRPC (B4). They are designed in spec §13; do not build them now.
- Do not duplicate `mark_engine` tests. Test only new logic (grouping, approve guard, auth, path guard, snapshot builder), plus one happy-path test per endpoint. For web, `tsc` + `vite build` passing is enough.
- Every task updates `HANDOFF.md` §4 and `docs/qa/QA_LOG.md` in the same commit (project rule).
- Commit on branch `phase1/mark-engine` or a new `phase2/trial` branch. Do not push until the user says.

## Review Focus

- HOLD ELR without an ABS image or with no line results: Preview still opens and shows the HOLD reason plus "ไม่มีภาพ ABS" (pinned in Task 4).
- Line present on only one side (Oracle row 4 has text, expected has no row 4, or the reverse): the grid shows the empty side and doesn't crash (pinned in Task 2, which always stores 5 Oracle rows).
- Approve, then Reject, then Approve again: the latest decision is current, and every decision is in `audit_log` (pinned in Task 4).
- Five wrong passwords: the account locks for 15 minutes, and login returns 423 even with the right password (pinned in Task 3).
- A file request with `..` or an absolute path returns 404 and reads nothing (pinned in Task 3).

---

### Task 1: Trial run + `mark_app` schema (spec T0, T1)

**Files:**
- Modify: `mark_engine/version.py` (`ENGINE_VERSION = "0.3.0"`), `pyproject.toml` (`version = "0.3.0"`)
- Create: `migrations/0005_mark_app_trial.sql`, `scripts/create_app_user.py`, `scripts/create_api_token.py`
- Modify: `migrations/README.md`, `HANDOFF.md`, `docs/qa/QA_LOG.md`

**Interfaces:**
- Produces: the 7 `mark_app` tables exactly as in spec §4 + §14 (PK / FK / unique / check / index columns are listed there).
  - Column specifics not in the spec:
    - `elr_snapshot.oracle_top_raw` is jsonb with 5 raw 21-char strings.
    - `elr_snapshot.layout_cells` is jsonb 5×18; null means a free cell.
    - `image_path` is relative to `MARK_FILES_ROOT`.
    - `slr_instructions` is jsonb `[{line,value,quote}]`.
    - `user_session.csrf_hash`.
  - Reason values: `'DB_WRONG','OCR_WRONG','SYMBOL_WRONG','SLR_ECN_CHANGE','RULE_MISSING','LAYOUT_WRONG','OTHER'`.
- Grants: `mark_app` role gets usage on `mark_app` and select on `mark_logic`.
  - `select, insert` only on `line_review`, `approval`, `audit_log`.
  - `select, insert, update, delete` on `app_user`, `user_session`, `api_token`, `elr_snapshot`.
  - `references` on `mark_logic.line_result` / `job_result` goes to the migration owner.
- Produces: CLI `python scripts/create_api_token.py <name> --scope metrics:read --days 90`. It prints the token once and stores only its sha256.
- Produces: CLI `python scripts/create_app_user.py <username> --name "<display>" --role engineer` (prompts for the password with `getpass`).

- [ ] **Step 1:** Bump engine version to 0.3.0 and run the full suite: `python -m pytest tests -q`. Expected: 306 passed.
- [ ] **Step 2:** Commit (`chore: engine 0.3.0 after overflow review fixes`). Then run the replay from the clean tree: `PYTHONPATH=. python scripts/run_blind.py --oracle artifacts/blind-2026h2/oracle --cache artifacts/blind-2026h2/cache --out artifacts/blind-2026h2/run-trial --months 7_JUL 8_AUG 9_SEP 10_OCT 11_NOV --allow-unfrozen`. Expected: `jobs: 402 … failed: 0`.
- [ ] **Step 3:** Dry-run the load: `python scripts/load_r1_to_pg.py artifacts/blind-2026h2/run-trial --period 2026-07..2026-11-replay --note "debug replay after overflow review, commit <sha>, not a holdout"`. Expected: "rolled back". **[USER]** Then re-run it with `--commit` and record the new run_id.
- [ ] **Step 4:** Write `0005_mark_app_trial.sql`:
  - An UP block in `begin…commit` with the tables, keys and indexes of spec §14.
  - The grants above.
  - A commented DOWN block, as in `0004`.
- [ ] **Step 5:** Write `scripts/create_app_user.py` (argon2 `PasswordHasher`; reject passwords shorter than 12 characters; `--reset` updates the hash and clears the lock) and `scripts/create_api_token.py`. Both use psycopg2 with the connection from env.
- [ ] **Step 6 [USER/DBA]:** Apply the 0005 UP section on `mark_web`, then create your user. Verify: `select count(*) from mark_app.app_user` returns 1. Inserting a `line_review` with a non-existent `(run_id, elr_no, abs_no, side, line_no)` fails on the FK. And `select max(run_id) from mark_logic.run` returns the new run.
- [ ] **Step 7:** Commit (`feat(db): migration 0005 mark_app trial schema; app user script`) with HANDOFF and QA_LOG.

### Task 2: Snapshot loader (spec T2)

**Files:**
- Create: `scripts/load_app_snapshot.py`, `tests/unit/test_app_snapshot.py`

**Interfaces:**
- Consumes: run artifact layout from Task 1:
  - `artifacts/blind-2026h2/oracle/elr_meta.json`
  - `oracle/mark_layout.json`
  - `cache/images_index.csv`
  - `cache/images/*.png`
  - `run-trial/jobs.csv`
- Consumes: the SLR PDFs used by the engine, via `run-trial/work/<elr>/**/SLR*.pdf` and `mark_engine.slr.parse.parse_slr`.
- Produces: `build_snapshot_rows(run_id: int, oracle_dir: Path, cache_dir: Path, run_dir: Path) -> list[dict]`, with keys matching `mark_app.elr_snapshot` columns.
- Produces CLI: `python scripts/load_app_snapshot.py --run-id N --oracle … --cache … --run … [--commit]`. It copies each image to `$MARK_FILES_ROOT/abs/<run_id>/<sha256>.png` and sets `image_path` relative to that root. Without `--commit` it rolls back.

- [ ] **Step 1: Write failing tests** with a tiny fixture: 1 ELR meta dict, a 2-row layout and a 1×1 PNG in `tmp_path`.

```python
def test_snapshot_row_has_five_oracle_rows_and_layout_grid(tmp_path):
    row = build_snapshot_rows(18, oracle, cache, run)[0]
    assert len(row['oracle_top_raw']) == 5 and row['oracle_top_raw'][4] == ''
    assert len(row['layout_cells']) == 5 and len(row['layout_cells'][0]) == 18
    assert row['layout_cells'][0][0] == '@' and row['layout_cells'][0][5] is None  # unlisted = free

def test_hold_elr_without_image_has_null_image_path(tmp_path):
    assert build_snapshot_rows(18, oracle, cache, run_hold_only)[0]['image_path'] is None
```

- [ ] **Step 2:** Run `python -m pytest tests/unit/test_app_snapshot.py -q`. Expected: FAIL (ImportError).
- [ ] **Step 3:** Implement `build_snapshot_rows` and the CLI. Use `execute_values` with `on conflict (run_id, elr_no) do update`, so a re-load is idempotent.
- [ ] **Step 4:** Run the tests. Expected: PASS. **[USER]** Run the CLI with `--commit` for the Task 1 run. Expected: 402 rows, and the image count equals the ELRs with an image in `images_index.csv`.
- [ ] **Step 5:** Commit (`feat(app): elr_snapshot loader for trial run`) with HANDOFF and QA_LOG.

### Task 3: API core logic (pure functions)

**Files:**
- Create: `services/api/mark_api/__init__.py`, `grouping.py`, `workflow.py`, `auth.py`, `files.py`, `logging.py`
- Test: `tests/unit/test_api_core.py`

**Interfaces:**
- Produces: `classify_line(status: str, warning: str) -> Literal['TRUE','WARNING','ERROR','NONE']`. Mapping per spec §5:
  - TRUE: MATCH / MATCH_SLR / MATCH_LOT with an empty warning.
  - WARNING: any of those three with a warning, plus MATCH_SHIFT and NEEDS_REVIEW.
  - ERROR: DIFF, DB_EMPTY, NOT_MARKED.
  - NONE: everything else.
- Produces: `classify_job(processing_status: str) -> Literal['HOLD','FAILED','DONE']`.
- Produces: `summarize(lines: list[dict], jobs: list[dict]) -> dict` with keys:
  - `cards {TRUE, WARNING, ERROR, HOLD}`: each `{count, pct, top_cause}`. Lines for TRUE/WARNING/ERROR, ELRs for HOLD; job FAILED counts as ERROR.
  - `monthly`: `[{month 'YYYY-MM' from elr_no ADIyymm, TRUE, WARNING, ERROR}]`.
  - `error_causes`, `hold_causes`: `[{cause, count}]`. Cause = `detail`, or `hold_reason` up to the first ':'.
- Produces: `approve_blockers(lines: list[dict], latest_reviews: dict[int, dict]) -> list[int]`. Returns the line numbers classified ERROR that have no non-draft review with both `reason` and `corrected_mark`.
- Produces auth helpers:
  - `hash_password(p: str) -> str`, `verify_password(h: str, p: str) -> bool`.
  - `login_state(user: dict, now) -> Literal['OK','LOCKED','INACTIVE']`. Lock rule: 5 failures, then 15 minutes.
  - `new_token() -> tuple[str, str]`: (raw, sha256 hex), using `secrets.token_urlsafe(32)`.
  - `session_valid(session: dict, now) -> bool`: false once past `expires_at` (8 h) or `last_seen_at` + 60 min.
  - `csrf_ok(cookie: str | None, header: str | None) -> bool`: both present, compared with `hmac.compare_digest`.
  - `can(role: str, action: Literal['read','review','approve','metrics']) -> bool`: the spec §11 matrix.
- Produces: `services/api/mark_api/logging.py` with `log_event(event: str, **fields)`, which writes one JSON line to stdout with `ts, level, service='mark-api', request_id, event` + fields. It drops any field named `password`, `token`, `mark`, `slr_text` or `image_path`.
- Produces: `safe_file(root: Path, relative: str) -> Path | None`. It returns None if the resolved path is outside `root` or does not exist.

- [ ] **Step 1: Write failing tests**

```python
def test_classify_line():
    assert classify_line('MATCH', '') == 'TRUE'
    assert classify_line('MATCH', 'CASE_DIFF: …') == 'WARNING'
    assert classify_line('NEEDS_REVIEW', '') == 'WARNING'
    assert classify_line('DIFF', '') == 'ERROR'
    assert classify_line('NOT_ELIGIBLE', '') == 'NONE'

def test_summarize_counts_failed_job_as_error_and_hold_by_elr():
    s = summarize([{'elr_no': 'ADI2607001', 'line_no': 1, 'status': 'MATCH', 'warning': '', 'detail': ''}],
                  [{'elr_no': 'ADI2607001', 'processing_status': 'DONE', 'hold_reason': ''},
                   {'elr_no': 'ADI2607002', 'processing_status': 'HOLD', 'hold_reason': 'BOM_NOT_FOUND: x'}])
    assert s['cards']['TRUE']['count'] == 1 and s['cards']['HOLD']['count'] == 1
    assert s['hold_causes'] == [{'cause': 'BOM_NOT_FOUND', 'count': 1}]
    assert s['monthly'][0]['month'] == '2026-07'

def test_approve_blocked_until_error_line_has_reason_and_value():
    lines = [{'line_no': 2, 'status': 'DIFF', 'warning': ''}]
    assert approve_blockers(lines, {}) == [2]
    assert approve_blockers(lines, {2: {'reason': 'DB_WRONG', 'corrected_mark': 'X', 'is_draft': True}}) == [2]
    assert approve_blockers(lines, {2: {'reason': 'DB_WRONG', 'corrected_mark': 'X', 'is_draft': False}}) == []

def test_lock_after_five_failures():
    now = datetime(2026, 11, 5, tzinfo=timezone.utc)
    assert login_state({'active': True, 'locked_until': now + timedelta(minutes=15)}, now) == 'LOCKED'

def test_session_idle_and_absolute_expiry():
    now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
    assert session_valid({'expires_at': now + timedelta(hours=1), 'last_seen_at': now - timedelta(minutes=59)}, now)
    assert not session_valid({'expires_at': now + timedelta(hours=1), 'last_seen_at': now - timedelta(minutes=61)}, now)
    assert not session_valid({'expires_at': now - timedelta(seconds=1), 'last_seen_at': now}, now)

def test_csrf_and_roles():
    assert csrf_ok('a', 'a') and not csrf_ok('a', None) and not csrf_ok(None, None)
    assert can('engineer', 'approve') and not can('engineer', 'metrics')
    assert can('admin', 'metrics') and not can('admin', 'approve')

def test_log_event_drops_sensitive_fields(capsys):
    log_event('auth.login_failed', user_id=None, password='x', token='y', elr_no='ADI2607001')
    line = json.loads(capsys.readouterr().out)
    assert line['event'] == 'auth.login_failed' and line['elr_no'] == 'ADI2607001'
    assert 'password' not in line and 'token' not in line

def test_safe_file_rejects_traversal(tmp_path):
    (tmp_path / 'abs').mkdir(); (tmp_path / 'abs' / 'a.png').write_bytes(b'x')
    assert safe_file(tmp_path, 'abs/a.png') is not None
    assert safe_file(tmp_path, '../secret') is None and safe_file(tmp_path, 'C:/Windows/win.ini') is None
```

- [ ] **Step 2:** Run `python -m pytest tests/unit/test_api_core.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement the five modules. Add to `pyproject.toml` an optional extra `api = ["fastapi", "uvicorn[standard]", "psycopg2-binary", "argon2-cffi"]` and `services/api` to the setuptools package include.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit (`feat(api): grouping, approve guard, auth and file guard`) with HANDOFF and QA_LOG.

### Task 4: API routes + repository (spec T3)

**Files:**
- Create: `services/api/mark_api/repo.py`, `deps.py`, `app.py`, `routers/{auth,mark,validation,workflow}.py`
- Test: `tests/unit/test_api_routes.py`

**Interfaces:**
- Consumes: Task 3 functions; Task 1 tables.
- Produces: `class Repo` with these methods. It uses psycopg2 `ThreadedConnectionPool(1, 10)` from `MARK_PG_*`, sets `statement_timeout=5s`, and keeps a fixed number of queries per endpoint (spec §18):
  - `runs()`
  - `lines(run_id)`, `jobs(run_id)`: TOP side only
  - `snapshot(run_id, elr)`
  - `latest_reviews(run_id, elr) -> dict[int, dict]`
  - `add_review(...)`, `add_approval(...)`, `latest_approval(run_id, elr)`
  - `audit(user_id, action, run_id, elr, line_no, detail)`
  - `user_by_name`, `record_login(user_id, ok)`, `create_session`, `session_user(token_hash)`, `delete_session`
- Produces: dependencies `get_repo()`, `current_user()` and `require(action)`.
  - Session cookie `mark_session` and CSRF cookie `mark_csrf` with exactly the attributes and lifecycle of spec §17 (`MARK_COOKIE_SECURE` env switches on `Secure` and the `__Host-`/`__Secure-` names).
  - `last_seen_at` is written at most once a minute.
  - Locking, password reset or deactivating a user deletes all of that user's sessions.
  - Every unsafe method checks `csrf_ok` and `Origin`.
  - `current_user` also accepts `Authorization: Bearer` API tokens, for the metrics scope only.
- Produces: request middleware that:
  - reads or creates `X-Request-ID` and echoes it back;
  - logs `http.request` with `route` set to the path template;
  - feeds an in-process `Metrics` object (counts per status class, p50/p95 per route, login ok/failed/locked counters).
- Repo wraps each query with a timer that logs `db.slow_query` when over 500 ms, and `db.error` on exceptions.
- Endpoints (prefix `/api`):
  - `GET /health`, `GET /ready` (DB `select 1` with a 2 s timeout plus `MARK_FILES_ROOT` readable → 200/503), `GET /metrics` (`require('metrics')`)
  - `POST /auth/login {username, password}` → 200 / 401 / 423
  - `POST /auth/logout`, `GET /auth/me`
  - `GET /runs`
  - `GET /dashboard?run=` → `summarize(...)`
  - `GET /elrs?run=&month=&result=&cause=&q=&page=` → `{total, page, rows}`, with 50 rows per page. Each row is `{elr_no, month, abs_file, result, true_lines, total_lines, cause}`. `q` matches ELR, ABS and SLR file names.
  - `GET /elrs/{elr}?run=` → `{snapshot, job, lines:[{line_no, expected, oracle, status, group, warning, detail, compare_rules}], reviews, approval, image_available}`
  - `GET /files/abs/{run}/{elr}`: a `FileResponse` stream with `ETag` = `abs_sha256` and `Cache-Control: private, max-age=86400`. A matching `If-None-Match` returns 304.
  - `POST /reviews {run_id, elr_no, line_no, reason, note, corrected_mark, is_draft}`
  - `POST /approvals {run_id, elr_no, decision}` → 409 with `{blocked_lines}` when `approve_blockers` is non-empty and decision is APPROVED
- Every write also writes `audit_log`.

- [ ] **Step 1: Write failing tests** using `fastapi.testclient.TestClient`, with `app.dependency_overrides[get_repo]` set to an in-memory `FakeRepo` defined in the test file that implements the methods above. Tests:
  - `test_requires_login`: `GET /api/runs` → 401.
  - `test_login_then_dashboard`: 200, and `cards` has the 4 keys.
  - `test_elr_detail_hold_without_image`: `image_available is False`, and `job.processing_status == 'HOLD'`.
  - `test_approve_blocked_then_allowed`: 409 `{blocked_lines:[2]}`; then POST a non-draft review; then 200.
  - `test_latest_decision_wins_and_all_audited`: approve, then reject, then approve. `latest_approval.decision == 'APPROVED'`, and the fake audit has 3 approval rows.
  - `test_file_traversal_404`: snapshot `image_path='../x'` → 404.
  - `test_post_without_csrf_403`: logged in, `POST /api/reviews` without `X-CSRF-Token` → 403.
  - `test_engineer_cannot_read_metrics`: engineer → 403 on `/api/metrics`; a fake API token with `metrics:read` → 200 with key `requests`.
  - `test_request_id_echoed`: the response has an `X-Request-ID` header.
  - `test_elr_detail_fixed_query_count`: the FakeRepo counts calls. For an ELR with 5 lines, `GET /api/elrs/{elr}` makes ≤ 4 repo calls (no per-line calls).
  - `test_dashboard_cached_per_run`: two `GET /api/dashboard?run=18` calls → `Repo.lines` is called once.
  - `test_elrs_paged`: with 120 fake jobs, `GET /api/elrs?run=18&page=2` returns 50 rows and `total == 120`.
  - `test_cookie_attributes_and_rotation`:
    - After login, `Set-Cookie` for `mark_session` contains `HttpOnly`, `SameSite=Strict`, `Path=/api`, `Max-Age=28800` and no `Domain`.
    - `mark_csrf` has `Path=/` and no `HttpOnly`.
    - A second login returns a different session value, and the old one gets 401.
    - Logout sends both cookies with `Max-Age=0`.
  - `test_csrf_from_other_session_rejected`: session A's cookie with session B's CSRF token → 403.
  - `test_no_cors_by_default`: `OPTIONS /api/runs` with `Origin: http://evil.example` and `Access-Control-Request-Method: GET` → the response has no `access-control-allow-origin` header. With `MARK_CORS_ORIGINS=http://ok.example`, that origin gets it echoed and `evil.example` does not.
- [ ] **Step 2:** Run `python -m pytest tests/unit/test_api_routes.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement the repository SQL and the routers. `lines()` reads `mark_logic.line_result` for `side='TOP'` and returns `final_status` as `status` (spec §14).
- [ ] **Step 4:** Run the tests and the full suite. Expected: PASS. **[USER]** Run `uvicorn services.api.mark_api.app:app --port 8000` against the DB, then log in and open `/api/dashboard?run=<new>`. The card counts must equal the line statuses in `run-trial/metrics.json`. Then open `/api/metrics`: p95 is within the spec §18 targets (dashboard ≤ 300 ms cold, elr detail ≤ 150 ms).
- [ ] **Step 5:** Commit (`feat(api): auth, mark, validation, workflow routers`) with HANDOFF and QA_LOG.

### Task 5: Web app (spec T4)

**Files:**
- Create: `web/` (Vite React-TS template), `web/src/api.ts`
- Create pages: `web/src/pages/{Login,Dashboard,Preview}.tsx`
- Create components: `web/src/components/{ActivelGrid,StatusCards,MonthlyChart,CauseChart,ElrTable,LineReviewForm}.tsx`

**Interfaces:**
- Consumes: Task 4 endpoints. Use `fetch` with `credentials: 'include'`; a 401 redirects to `/login`.
- Produces: `ActivelGrid({rows: string[5], other: string[5], layout: (string|null)[5][18] | null})`. Columns are A B C + 1–18, and `other` is the opposite side's rows.
  - The Oracle side shows raw chars 1–21.
  - The system side shows A–C blank and 1–18 from `expected`.
  - Cell colours: red = this cell's char differs from the same cell in `other` (checked first), blue = reserved by the layout (non-null and blank), white = has a character.

- [ ] **Step 1:** Scaffold with `npm create vite@latest web -- --template react-ts`. Add react-router and a chart library. Set the dev proxy `/api → http://localhost:8000`.
- [ ] **Step 2:** Build the Login page and Dashboard (spec §6):
  - Dashboard: run selector, 4 cards, monthly stacked bars, Error and HOLD cause charts.
  - Clicking a chart bar sets the `cause` filter.
  - Search plus the ELR table. Clicking a row opens `/elr/:elr?run=`.
- [ ] **Step 3:** Build the Preview:
  - Left side: ABS image (click to enlarge), SLR instructions used, system grid, and per-line source / rule / warning.
  - Right side: MARK_ID + layout code, MARK_REMARK, MARK_REQUIRE, TOP_TEMPLATE_REMARK, Oracle grid.
  - Line review form with a reason dropdown (7 values from Task 1), note and corrected value.
  - Buttons: บันทึกร่าง / Approve / Reject. On 409, list the blocked line numbers.
  - A HOLD job shows its reason instead of grids.
- [ ] **Step 4:** Run `npm run build` (runs `tsc -b && vite build`). Expected: exit 0, no type errors, and the initial JS chunk is ≤ 300 KB gzip (Vite prints sizes). Preview is loaded via `React.lazy`, and the search box is debounced at 300 ms. **[USER]** Run the dev server against the local API, then walk the flow: login → dashboard → filter → ELR → review → approve.
- [ ] **Step 5:** Commit (`feat(web): dashboard and ELR preview for trial`) with HANDOFF and QA_LOG.

### Task 6: Deploy on 10.153.90.17 (spec T5)

**Files:**
- Create: `services/api/Dockerfile`, `web/Dockerfile` (build, then NGINX), `web/nginx.conf`, `docker-compose.yml`
- Modify: `.env.example` (add `MARK_PG_HOST`, `MARK_PG_DB`, `MARK_PG_USER`, `MARK_PG_PASSWORD`, `MARK_FILES_ROOT`, `MARK_SESSION_HOURS`), `services/README.md` (trial deployment section)

**Interfaces:**
- Consumes: Tasks 4–5.
- Produces:
  - Compose services `api` (uvicorn :8000, `.env` via `env_file`, `MARK_FILES_ROOT` mounted read-only) and `web` (NGINX :80 serving `dist/`).
  - `location /api/ { proxy_pass http://api:8000; proxy_set_header X-Request-ID $request_id; }` and an SPA fallback `try_files $uri /index.html`.
  - The three `limit_req_zone` zones of spec §12 (`login` 5r/m burst 5, `files` 10r/s burst 20, `api` 20r/s burst 40), returning `limit_req_status 429`, plus `client_max_body_size 1m`.
  - `log_format json` with `request_id, status, request_time, upstream_response_time, uri`.
  - `gzip on; gzip_min_length 1024; gzip_types application/json text/css application/javascript;`
  - Security headers from spec §16 via `add_header ... always` (CSP, nosniff, Referrer-Policy, X-Frame-Options); `Cache-Control: no-store` on `/api/`.
  - Compose `logging: {driver: json-file, options: {max-size: 20m, max-file: '10'}}` on both services.

- [ ] **Step 1:** Write the Dockerfiles, `nginx.conf` and compose file. Build locally with `docker compose build`. Expected: both images build.
- [ ] **Step 2 [USER/ops]:** On 10.153.90.17, copy the repo (without `artifacts/` or `.env`), create `.env`, mount the files root, then run `docker compose up -d`. Verify: `curl http://10.153.90.17/api/ready` returns 200, and the login page loads from a workstation browser. Six rapid wrong logins: the sixth returns 429 from NGINX, and `docker compose logs web` shows the JSON line for it.
- [ ] **Step 3:** Commit (`chore(deploy): docker compose for phase 2 trial`) with HANDOFF and QA_LOG.
