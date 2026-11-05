# HANDOFF & PROGRESS LOG — Mark Automation (Phase 1)

> **Important**: This document tracks live execution state, decisions, rules, and progressive handoffs across development sessions and subagents. Always update this file upon completing or modifying any task.

---

## 1. Project Context & Current State

- **System**: Mark Automation — System Architecture (V3)
- **Phase**: **Phase 1 — `mark_engine` (offline) [COMPLETED 12/12 TASKS]**
- **Plan File**: [`docs/superpowers/plans/2026-11-04-phase1-mark-engine-offline.md`](file:///D:/CIM%20Project/mark-web/docs/superpowers/plans/2026-11-04-phase1-mark-engine-offline.md)
- **Design Spec**: [`docs/superpowers/specs/2026-11-04-mark-automation-design.md`](file:///D:/CIM%20Project/mark-web/docs/superpowers/specs/2026-11-04-mark-automation-design.md)
- **QA & Knowledge Base Log**: [`docs/qa/QA_LOG.md`](file:///D:/CIM%20Project/mark-web/docs/qa/QA_LOG.md)
- **Database Tables (`mark_web.mark_logic`)**: [`docs/implementation/08-database-tables.md`](file:///D:/CIM%20Project/mark-web/docs/implementation/08-database-tables.md) — 15 ตาราง, run 1–3 = R0 (run 3 freeze), **run 14 = R1 ปัจจุบัน**
- **R1 logic / review / next phase (อ่านก่อน)**: [`docs/implementation/10-r1-logic-review-and-next-phase.md`](file:///D:/CIM%20Project/mark-web/docs/implementation/10-r1-logic-review-and-next-phase.md) — D-22–D-29, True/Warning/Error, debug ค้าง G1–G9, งาน N1–N7
- **Review results**: `reviews/r1_review_2026-11-04.csv` (runner อ่าน), `reviews/r1_run14_review_export.csv` (export ทุกบรรทัด + class)
- **Mark Eng confirmation (open)**: [`docs/implementation/09-mark-eng-confirmation.md`](file:///D:/CIM%20Project/mark-web/docs/implementation/09-mark-eng-confirmation.md)
- **Git State**:
  - Remote: `git@github.com:Pariman1419/Markweb.git`
  - Base Branch: `phase0/readiness`
  - Active Work Branch: `phase1/mark-engine`
  - Customer drawings & artifacts isolated under `.gitignore` (`artifacts/`)
- **Execution Methodology**: **Subagent-Driven Development** with strict TDD (Red -> Green -> Refactor -> Review Gate).

---

## 2. Hard Governance & Invariants

1. **Oracle Independence (revised 2026-11-04)**: expected generation may use `MARK_ID_LAYOUT` as a template, but must not use Oracle `TOP_MARK1..5`, `BACK_MARK1..5`, or `OracleMark`. See the closeout revision plan.
2. **Immutability**: All core domain structures (`ExpectedMark`, `ExpectedLine`, `ExpectedToken`, `JobResult`, etc.) must be `@dataclass(frozen=True, slots=True)` with immutable collections (`tuple`, `frozenset`).
3. **No "PASS" Status**: The system strictly uses multi-axis statuses (`processing_status`, `verification_status`, `approval_status`, `eligibility_status`). No status enum or report column may contain the word "PASS".
4. **SLR Gate Strictness (Spec V2)**: If an ELR lacks an SLR document, it must always enter `HOLD:SLR_NOT_FOUND`, even if Oracle `CUST_REQ_NO` is empty or N/A. Any divergence from Run 3 will be tagged with parity code `GATE_SPEC_V2`.
5. **Rule Precedence (Lower value wins)**:
   - Priority 10: `SLR`
   - Priority 20: `MARK_REMARK` (elr_legend)
   - Priority 30: `Symbol ADI`
   - Priority 40: `ADI1039` (Applicable to ABS and SLR only; raises `ValueError` on TRS)
   - Priority 50: `OCR fix`
6. **Symbol ADI Frozen Hash**: Enforce SHA256 of `Symbol ADI.xlsx`:
   `7858dc405a90b6600389accf32fa257ad23580cd532cda078da2f02cfe74ccb6`.
7. **Offline Isolation**: No network calls, no live Oracle DB connection, no live NAS access, and no live A100 calls in Phase 1. All tests run on frozen fixtures and R0 snapshots (`D:/CIM Project/mark` tag `regression-r0-2026-11-04`).

---

## 3. Systematic Tasklist (Phase 1: 12 Tasks)

| # | Task Description | Scope / Key Files | Status | Test Status | Commit |
|---|---|---|:---:|:---:|:---:|
| **1** | **Project Scaffold & Frozen Domain Model** | `pyproject.toml`, `mark_engine/domain/models.py`, `version.py` | [x] Completed | [x] Green (6 passed) | `0837752` |
| **2** | **Rule Version File & `RuleSet`** | `scripts/build_rule_version.py`, `mark_engine/rules/ruleset.py`, `RV-2026-11-04-R0.json` | [x] Completed | [x] Green (9 passed) | `be6e477` |
| **3** | **Adapters: Oracle SELECT Guard & Snapshot Loader** | `mark_engine/adapters/oracle_guard.py`, `snapshot.py` | [x] Completed | [x] Green (32 passed) | `1deeec5` |
| **4** | **Documents: Locate, Fingerprint & Classify** | `mark_engine/documents/locate.py`, `fingerprint.py`, `classify.py` | [x] Completed | [x] Green (12 passed) | `c388b94` |
| **5** | **Document Resolver** | `mark_engine/documents/resolve.py` (BOM/rev matching, conflict holds) | [x] Completed | [x] Green (14 passed) | `be7d6cf` |
| **6** | **SLR Parser with Coverage** | `mark_engine/slr/parse.py` (single value per line, ambiguity & unresolved detection) | [x] Completed | [x] Green (15 passed) | `01084eb` |
| **7** | **Encoders (OCR Fix, Symbol ADI, ADI1039, REMARK)** | `mark_engine/encode/` (hash assertion on Symbol ADI, token replacement) | [x] Completed | [x] Green (9 passed) | `7966eca` |
| **8** | **ABS Layout & Symbols-to-Lines + Cached Inference** | `mark_engine/abs/layout.py`, `symbols_to_lines.py`, legacy parity test | [x] Completed | [x] Green (6 unit + 1 regression parity) | `bcf8be5` |
| **9** | **Expected Mark Generator** | `mark_engine/generate/generator.py` (AST scan & signature inspection to prove no Oracle leak) | [x] Completed | [x] Green (14 passed) | `e9a64ad` |
| **10** | **Comparison Engine** | `mark_engine/compare/engine.py`, `lot.py`, `shift.py` (verified MATCH_LOT & MATCH_SHIFT) | [x] Completed | [x] Green (14 passed) | `f471d6d` |
| **11** | **Pipeline `process_elr` & 3 Status Axes** | `mark_engine/pipeline.py` (end-to-end integration + eligibility gate + status synthesis) | [x] Completed | [x] Green (14 passed) | `9ff67ec` |
| **12** | **Regression Runner R1 & Parity vs R0** | `scripts/run_regression.py`, `parity.py`, `metrics.py`, R1 baseline Jan–Jun; R1 triage fixes (branch `phase1/r1-fixes`) | [x] Completed | [x] Green (195 unit + 3 regression, BUG 0) | `d4fd534` → `cb9b74e` (merge `8d930fd`) + GRC fix |

---

## 4. Live Changelog & Session Updates

### 2026-11-05 — Jenkins job `mark-web` created; first builds
- **Job created** at http://localhost:8080/job/mark-web: Pipeline from SCM, `https://github.com/Pariman1419/Markweb.git` `*/phase2/trial`, polls every 5 min.
- **Jenkins fixes made during the first builds:**
  - The global Git tool now points to the user's Git (`C:\Users\41495406\AppData\Local\Programs\Git\cmd\git.exe`), because the LocalSystem controller had no `git.exe` on PATH.
  - Node `mark-web-local` remote root had a leading space (`" D:\jenkins-agent"`) and was corrected to `D:\jenkins-agent`.
- **Dependency fix (found by CI's clean venv, cf30405):** a fresh install pulled FastAPI 0.162 / Starlette 1.10, whose test client needs `httpx2`. Tests had only been run on FastAPI 0.141 / Starlette 0.52 with `httpx` installed by hand.
  - Pinned `fastapi>=0.110.0,<0.142` (this also applies to the API image).
  - Added `httpx>=0.27,<0.29` to `dev`.

### 2026-11-05 — Jenkins CI/CD for mark-web
- **User decisions:**
  - Jenkins (Windows service, localhost:8080, 2.580.2) builds from GitHub after `phase2/trial` is pushed.
  - The service runs under the user's Windows account, so it gets Python, Node and Docker Desktop.
- **Added `Jenkinsfile`:** Preflight → pytest (venv, JUnit) → web build → `docker compose build` → deploy (`.env` from Secret file credential `mark-web-env`, deleted after) → smoke test (`/api/ready` 200; `/api/runs` 401 with `no-store` + CSP).
  - Parameters: `DEPLOY`, `MARK_WEB_PORT`, `MARK_FILES_HOST_DIR`, `PYTHON_EXE`.
- **Compose:** image folder is now `${MARK_FILES_HOST_DIR:-./data/files}`, because ABS images are not in git.
- **`.gitignore`:** added `reports/`.
- **Redacted** the two credential mentions in `docs/implementation/00-phase0-readiness.md:57` and `07-open-decisions.md:21`.
  - Earlier commits still contain them, and so does `origin/phase0/readiness`. Rotation remains D-13.
- **Setup steps:** `services/README.md` → "CI/CD with Jenkins".
- **Service logon failed:** running the service as `TH\41495406` failed with Event 7041, "user has not been granted the requested logon type" (domain policy).
  - The service goes back to LocalSystem.
  - Builds run instead on inbound agent `mark-web-local` (label `mark-web`), started with `scripts/jenkins-agent.bat` under the user's account (JDK 25). `Jenkinsfile` uses `agent { label 'mark-web' }`.
- **Done since:**
  - The service is back on LocalSystem.
  - Node `mark-web-local` is connected; the secret is in `%USERPROFILE%\.jenkins-agent-secret`.
  - `phase2/trial` is pushed by the user.
- **No Jenkins credentials:** the GitHub repo is public, so it is cloned over HTTPS, and Deploy copies `.env` from the agent host (`ENV_FILE`).
  - **Warning:** because the repo is public, older commits (and `origin/phase0/readiness`) expose the credential mentions, internal IPs and hostnames. Rotate the DB/Oracle passwords (D-13) and consider making the repo private.

### 2026-11-05 — Phase 2 trial: review fix-ups and localhost integration
- **Reviewed Tasks 1–6 (another agent).** All met the plan, except for the items fixed below.
- **Security:**
  - An unsafe request whose `Origin` is not this site's own host (or in `MARK_CORS_ORIGINS`) now gets 403 (spec §11).
  - A Bearer request with an invalid token now gets 401 instead of falling back to the session cookie (Bearer requests skip CSRF).
  - Cookie names with `MARK_COOKIE_SECURE=true` are now `__Secure-mark_session` (Path=/api) and `__Host-mark_csrf`. The earlier `__Host-mark_session` would have been rejected by browsers because `__Host-` requires Path=/.
- **Middleware:**
  - The CSRF/session check now uses the dependency override, so tests no longer reach the real DB.
  - Metrics and logs are keyed on the route template (`/api/elrs/{elr}`).
- **Logging (spec §15):**
  - The API now writes `http.request` for every request.
  - Events of one request share a `request_id` taken from NGINX `X-Request-ID`.
  - `client_ip` comes from `X-Real-IP`.
  - `username` is no longer logged.
- **NGINX:**
  - Added `log_format json` with `access_log /dev/stdout` (the Task 6 entry said JSON logging existed, but it did not).
  - `proxy_set_header Host $http_host`, which keeps the port so the Origin check works on non-80 ports.
- **Build:**
  - Added root and `web/` `.dockerignore`, so `.env`, `artifacts/`, `data/`, `models/` and `node_modules` stay out of build contexts.
  - Added the root `README.md`; `pyproject.toml` references it, and the API image did not build without it.
  - Host port is now `MARK_WEB_PORT` (default 80).
  - Vite proxy uses `changeOrigin: false`.
  - Removed the template `hero.png`; the page title is now "Mark Review".
- **Localhost check:** `docker compose up` with `MARK_WEB_PORT=8088` (IIS holds 80 and Jenkins holds 8080 on this workstation).
  - `/api/ready` returned 200 (DB as role `mark_app`, files root readable).
  - `/api/*` has `Cache-Control: no-store`, CSP and `X-Frame-Options`.
  - The SPA fallback returned 200.
  - Of 8 rapid logins, the 7th and 8th got 429. The NGINX JSON log shows `limit_req: REJECTED`, and the API log shows `http.request` with the same request_id scheme.
- **Tests:** 343 passed (6 new). `npm run build` passes, with an initial JS of 88 KB gzip.
- **Notes for the record:**
  - Run 19's `git_commit` is `829867e`: the agent loaded it before committing the 0.3.0 bump. Its output is byte-identical to `run-overflowfix`.
  - The agent wrote to the shared DB during Tasks 1–2: run 19, migration 0005, 1 app user, and 402 snapshots.
  - `mark_app` currently uses the same password as the admin DB user. Set a separate one before using .17.
- **Not yet done:**
  - A walkthrough of login → review → approve with the user's own account.
  - Deploy to 10.153.90.17 (the user will clone and build it there).

### 2026-11-05 — Task 6: Deploy on 10.153.90.17 (spec T5)
- Created `services/api/Dockerfile` (Python 3.12-slim, uvicorn with 1 worker).
- Created `web/Dockerfile` (multi-stage Node 24 alpine build and NGINX alpine runtime).
- Created `web/nginx.conf` with 3 rate-limit zones (`login` 5r/m, `files` 10r/s, `api` 20r/s all with `nodelay` and 429 status), JSON logging, and security headers inclusion.
- Created `web/security_headers.conf` (CSP, nosniff, same-origin referrer, frame deny).
- Created `docker-compose.yml` linking `api` and `web` with json-file log rotation (20m x 10) and read-only files mount.
- Updated `.env.example` with full `MARK_PG_*`, `MARK_FILES_ROOT`, and cookie/cors settings.
- Updated `services/README.md` with preflight checks and deployment instructions for 10.153.90.17.


### 2026-11-05 — Task 5: Web app (spec T4)
- Scaffolded Vite React 19 + TypeScript app in `web/` with Tailwind CSS v4, Lucide icons, and React Router v7.
- Implemented `web/src/api.ts` with credentials, CSRF token handling, and typed client methods.
- Created components:
  - `ActivelGrid`: 21x5 matrix comparing Oracle and system characters, highlighting differences in red and reserved layout spaces in blue.
  - `StatusCards`: 4 cards (True, Warning, Error, HOLD) with counts, percentages, top causes, and interactive filter toggles.
  - `MonthlyChart`: stacked monthly verification volume with month filter.
  - `CauseChart`: top Error driver and HOLD blocker horizontal bars with cause filter.
  - `ElrTable`: 50-row paginated table with real-time status badges, search debounced at 300ms, and deep linking to Preview.
  - `LineReviewForm`: per-line reason selector (7 values), corrected mark inputs, draft/confirm reviews.
- Created pages: `Login`, `Dashboard`, and `Preview` (lazy-loaded with `React.lazy`).
- Build verification: `tsc -b && vite build` passed with exit code 0; initial JS chunk is 87.98 kB gzip (well below 300 kB target).


### 2026-11-05 — Task 4: API routes + repository (spec T3)
- Implemented `Repo` in `services/api/mark_api/repo.py` connecting via `ThreadedConnectionPool` (1..10) with 5s timeout and slow query logging (>500ms).
- Created FastAPI app `services/api/mark_api/app.py` and routers:
  - `auth`: `POST /auth/login` (rate limit, lockout after 5 failures, session rotation), `POST /auth/logout`, `GET /auth/me`.
  - `mark`: `GET /runs`, `GET /elrs` (paged at 50, filters), `GET /elrs/{elr}` (fixed 4-query limit), `GET /files/abs/{run}/{elr}` (stream with ETag & traversal guard).
  - `validation`: `GET /dashboard?run=` with in-memory per-run caching.
  - `workflow`: `POST /reviews`, `POST /approvals` (blocks approval on unreviewed ERROR lines and blocks approval on HOLD).
  - System: `GET /api/health`, `GET /api/ready`, `GET /api/metrics`.
- Implemented double-submit CSRF protection and exact SameSite/HttpOnly cookie attributes.
- Granted `mark_app` usage on `mark_logic` schema.
- Verified 18 unit route tests (`tests/unit/test_api_routes.py`) and full suite (337 passed).
- Live DB verification on run 19 matched exact reference counts: TRUE 866, WARNING 214, ERROR 41, HOLD 34.


### 2026-11-05 — Task 3: API core logic (pure functions)
- Implemented `services/api/mark_api/`:
  - `grouping.py`: `classify_line` (TRUE/WARNING/ERROR/NONE), `classify_job`, `summarize` with cards, monthly trends, and error/hold cause breakdowns.
  - `workflow.py`: `approve_blockers` enforcing that ERROR lines must have non-draft reviews with both reason and corrected_mark before approval.
  - `auth.py`: argon2 password hashing/verification, account lock after 5 failures, session validity (8h absolute, 60m idle), CSRF double-submit token checking, and role permissions.
  - `logging.py`: structured JSON logger dropping sensitive fields (`password`, `token`, `mark`, `slr_text`, `image_path`).
  - `files.py`: `safe_file` directory traversal guard.
- Added optional `api` dependency in `pyproject.toml` and package include for `services/api`.
- Verified with 8 unit tests in `tests/unit/test_api_core.py`. Total test suite passes (319 tests).


### 2026-11-05 — Task 2: Snapshot loader (spec T2)
- Implemented `scripts/load_app_snapshot.py` with `build_snapshot_rows` and CLI with `--commit`.
- Added unit tests in `tests/unit/test_app_snapshot.py` covering 5 Oracle rows, 5x18 layout grid, `top_mark_id` float parsing, `line_extra` jsonb, and HOLD ELR image nullability. All passed.
- Loaded snapshots for trial run `run_id = 19` into `mark_app.elr_snapshot`: 402 ELRs inserted, 287 ABS images copied to `data/files/abs/19/<sha256>.png`.
- Verified in DB: `select count(*) from mark_app.elr_snapshot where run_id = 19` returns exactly 402.


### 2026-11-05 — Task 1: Trial run + mark_app schema (spec T0, T1)
- Engine version bumped to 0.3.0 in `mark_engine/version.py` and `pyproject.toml`.
- Extracted `is_blind_run` in `scripts/load_r1_to_pg.py`; added unit test `tests/unit/test_load_r1_blind.py`. All 308 engine unit tests pass.
- Executed blind replay `scripts/run_blind.py` for Jul–Nov 2026 into `artifacts/blind-2026h2/run-trial`: 402 jobs, 0 failed, 1,358 lines identical to `run-overflowfix`.
- Loaded trial run to PostgreSQL as `run_id = 19`.
- Created and applied `migrations/0005_mark_app_trial.sql`: created `mark_app` schema with 7 tables (`app_user`, `user_session`, `api_token`, `elr_snapshot`, `line_review`, `approval`, `audit_log`), indexes, constraints, and role permissions.
- Created helper scripts `scripts/create_app_user.py` and `scripts/create_api_token.py`.
- Verified in DB: user count >= 1, FK integrity on `line_review` rejects invalid references, and max `run_id` is 19.


### 2026-11-05 — Phase 2 trial design and plan
- The user will trial the web app alone first. Spec: `docs/superpowers/specs/2026-11-05-phase2-trial-design.md`. Plan: `docs/superpowers/plans/2026-11-05-phase2-trial.md` (6 tasks).
- Scope is B1 + B2 of the earlier Phase 2 design, in this order:
  - a trial run of the Jul–Nov replay after `dd57846`, loaded as a new run_id (not a holdout);
  - migration 0005, with 6 `mark_app` tables (app_user, user_session, elr_snapshot, line_review, approval, audit_log);
  - a snapshot loader;
  - one FastAPI app with Auth / Mark / Validation / Workflow routers;
  - React Dashboard + ELR Preview;
  - Docker Compose on 10.153.90.17.
- Deferred: B3–B7 (Airflow, inference API, LLM, notification), FREEZE-R2 (next holdout), Redis/Kong.
- Tests cover only new logic (grouping, approve guard, auth, file path guard, snapshot builder). The engine is not re-tested.
- Added design spec §11–15:
  - **Tokens:** opaque session cookie + double-submit CSRF; API tokens for system calls.
  - **Auth:** argon2id; lock after 5 failures for 15 min; role matrix.
  - **Rate limits:** NGINX `limit_req` (login 5/min, files 10/s, api 20/s).
  - **WebSocket:** deferred to B3, using PG LISTEN/NOTIFY.
  - **gRPC:** deferred to B4, internal Mark ↔ Inference only.
  - **Keys:**
    - `mark_app` PK/FK/index, with FKs into `mark_logic.line_result` / `job_result`.
    - `line_review` uses the full key including `abs_no` and `side`.
    - `audit_log`, `line_review` and `approval` are append-only.
  - **Logging:** JSON logs with `request_id` from NGINX; `/api/health`, `/api/ready`, `/api/metrics`; alert thresholds.
- Added spec §16 on CORS: same-origin only, no CORS middleware unless the `MARK_CORS_ORIGINS` allowlist is set, plus NGINX security headers (CSP, nosniff, frame deny, `no-store` on `/api`).
- Added spec §17 on cookies:
  - Two cookies only: `mark_session` (HttpOnly, Path=/api) and `mark_csrf` (Path=/). Both are SameSite=Strict, host-only, 8 h.
  - Both are rotated on login and cleared with `Max-Age=0`.
  - All of a user's sessions are deleted on lock or reset.
  - `Secure` and the `__Host-`/`__Secure-` prefixes switch on via `MARK_COOKIE_SECURE` once HTTPS is in place.
- User decision: WebSocket and gRPC are deferred to the next round.
- Added spec §18 on performance and Big-O:
  - **Sizing:** sized for J=10k ELR and L=50k lines per run.
  - **Dashboard:** O(L+J) once, then cached per run.
  - **ELR detail:** 4 fixed queries, O(log N + k), no N+1.
  - **ELR list:** paged at 50 rows.
  - **Images:** streamed with ETag.
  - **Connections:** pool of 1–10, `statement_timeout` 5 s.
  - **Frontend:** initial JS ≤ 300 KB gzip.
  - **Targets:** p95 dashboard ≤ 300 ms cold, detail ≤ 150 ms.
  - **Redesign trigger:** L > 50k or > 20 concurrent users.
- **User decision:** reviews are per run (a new run is reviewed again).
- **Defaults pending confirmation:** DB_EMPTY counts as Error; the trial runs on HTTP.
- **Handoff:** the plan is handed to another agent; Claude monitors. The plan has a "For the Executing Agent" section: branch `phase2/trial`, one `Task N:` commit per task, stop before shared-DB writes or deploys, and record any mismatch under "Blocked" in §4.
- Analysed the design and plan against the real artifacts and DB (`docs/superpowers/specs/2026-11-05-phase2-trial-analysis.md`). Fixed 4 blockers and 9 inconsistencies; 3 decisions are waiting on the user.
  - The loader rejected UNFROZEN runs as blind.
  - `compare_rules`/`flags` are not `line_result` columns; they are now stored as `elr_snapshot.line_extra`.
  - Columns are `final_mark`/`db_mark`.
  - The engine version test was pinned to `"0.2.0"`.
  - NGINX now uses `nodelay` and separate locations for `/api/files`.
  - 1 uvicorn worker.
  - Card reference values: TRUE 866 / WARNING 214 / ERROR 41 / HOLD 34.
- Facts checked against the DB on 2026-11-05: the `line_result` PK is `(run_id, elr_no, abs_no, side, line_no)`, and line status is in `final_status`.

### 2026-11-05 — Engine fixes from the run-17 overflow review (post-holdout, not frozen)

- Source: user review CSV of 25/141 overflow ELRs (`run17-overflow-review.csv`). Fixes applied to every ELR showing the same pattern, including unreviewed ones:
  - **Line overflow no longer fails the ELR** (review: "แจ้งเป็น warning เพราะมีส่วนที่ถูก"). The line keeps its unplaced text, becomes `NEEDS_REVIEW` with warning `LAYOUT_OVERFLOW: …`, and the other lines are compared. Missing layout still returns `FAILED`. This revises D-10.
  - **SLR value stops at the PDF text-line break** (`mark_engine/slr/parse.py`). Before this fix, the next line's text was appended to the value: "TNOE Balance", "TCE-2-W9 HOLD BALANCE OF THE", "ENGBU1Q Expedite", "ENGA 3065 (Pre-Probe Qty)…", "*Return". A value that starts on the next text line is still read.
  - **SLR underscore field names are encoded** (`adi1039.py`). `ASSEMBLY_LOT_NUMBER` becomes XXXXXXXXX and `COUNTRY_OF_ORIGIN` becomes the country. `DATE_CODE`/`DATE CODE` becomes YYWW, for SLR only (MARK_ID 24755).
  - **Reserved blank cells absorb the generator's separator space** (`mark_layout.py`; MARK_ID 23706 `@* ____`, 23274, 24350).
  - **Country name shortened when THAILAND does not fit.** The pipeline places THAI, the most common short form in ACTL history: ADI ELRs 2019–2026 read-only query gave THAILAND 537, THAI 304, THAIL 40, TH 2, THAILA 2. Warning `LAYOUT_COO_ABBREVIATED`; compare still reads any Oracle prefix (THAIL…) as `COO_ABBREVIATED`.
- Verification (local, not loaded to DB):
  - **Jan–Jun without layout vs run 14:** only 3 lines changed, all `NEEDS_REVIEW` → `MATCH_SLR` ("ENGBU1Q 7ADC44285… -" → ENGBU1Q).
  - **Jan–Jun with layout vs `regression-r1-layout-frozen`:** 107 failed jobs → 0. Coverage 274 → 381 ELR. Agreement 1,051/1,184 → 1,378/1,610. Independence 381/381. The 274 previously completed jobs are unchanged.
  - **Blind Jul–Nov (`artifacts/blind-2026h2/run-overflowfix`, UNFROZEN) vs run 17:** 141 failed → 0. ELR coverage 113 → 254 of 402. Line coverage 504 → 1,127. Agreement 459/504 → 897/1,127. Independence 254/254. The 227 previously completed and HOLD jobs are unchanged. 140 lines remain `LAYOUT_OVERFLOW` for review.
  - 300 unit tests pass.
- Not a holdout result: the July–November set has now been used for debugging. The engine changed after FREEZE-R1, so a new freeze and fresh data (full November/December) are needed before reporting accuracy. `services/engine/overflow_review.py` checks the run-17 archived engine and will refuse to run on the changed engine.
- Round 2, from the user's decisions plus pattern analysis of the Jan–Nov results, SLRs and Oracle:
  - **ABS drafting note dropped** (`generator.py`, `R07-ABS-NOTE`): "NO BRAND/MARK ON THIS LINE" is removed and the line keeps its graphics only. Oracle is '@%' on all 92 such lines.
  - **Case-only difference is a match with warning** (`compare/engine.py`, detail `CASE_DIFF`), e.g. "Bajau TC" vs "BAJAU TC". 31 of 36 such Oracle lines were all uppercase.
  - **Trailing literal after the last ABS `{token}` is dropped, only when the row overflows** (22801 `{ADI-PARTIAL-LOGO}{YW}X` → `%  YW`, user). Warning `LAYOUT_TRAILING_LITERAL_DROPPED`.
  - **Pin-only first row reflow** (`pipeline._reflow_pin_row`): the layout row 1 holds only `@` and row 2 starts with `%`, so "@% XXX" splits into '@' / '%XXX' and the lines below move down one row. Warning `LAYOUT_REFLOW`. Applies to MARK_ID 25203, 24711, 22686.
  - **SLR "Second line of brand content / marking: 'GL3G'" read as a line-2 instruction**, quoted value. Before this fix the sentence was always `SLR_UNRESOLVED`; the existing test asserting that was moved to a positive test.
  - **SLR pointer sentences**: "*Ignore Brand on ABS", "Brand as indicated below", "Use the attached ABS and markings below" are no longer `SLR_UNRESOLVED` when the SLR gives line instructions.
- Round-2 results (round 1 → round 2):
  - **Blind:** agreement 897 → 1,019/1,127 (90.4%); DIFF 22 → 7; NEEDS_REVIEW 208 → 101; `LAYOUT_OVERFLOW` lines 140 → 0.
  - **Jan–Jun with layout:** agreement 1,378 → 1,435/1,610; DIFF 5 → 1; overflow lines 46 → 14.
  - **Jan–Jun without layout:** agreement 1,377 → 1,424; DIFF 49 → 22.
  - Independence unchanged at 100%. 306 unit tests pass.
  - One expected value changed without a status change: ADI2602074 line 2, LSNv11 → LSNv011. Its SLR on NAS literally says "LSNv011" while ABS and Oracle say LSNv11. It stays NEEDS_REVIEW (RULE_CONFLICT).
- Still review-gated on blind: the 25203/24711 lines now equal Oracle but keep `RULE_CONFLICT`/`SLR_UNRESOLVED`, because the SLR points to an attached "Glacier MPW instructions" document. Round-1 outputs are kept in `*.v1` folders.

### 2026-11-05 — Run 17 overflow comparison page

- Built `artifacts/blind-2026h2/overflow-review/index.html` from the frozen run-17 inputs, replaying only failed jobs without modifying the DB or original result. All 141 recorded errors reproduced; checking all five TOP rows found 188 rows with layout-placement errors. Additional errors are labeled as replay findings, not original per-job counts.
- The local page compares Generator text, reserved/fixed/free Layout cells, Oracle cells and ABS image. Review decisions remain in local browser storage and can be exported to CSV. Images are linked to the local cache, so the cache and HTML must remain together.
- Generator text is reconstructed from the SLR currently on NAS; unlike ABS, SLR content was not fingerprinted in run 17, so unchanged SLR inputs cannot be independently established.
- A portable local archive `artifacts/blind-2026h2/overflow-review-bundle.zip` contains the page and its 39 referenced images; it contains customer data and is Git-ignored.
- The browser-control approval system did not permit opening Edge for visual QA. Offline JavaScript checks verified 141 records, search, navigation and image section; 282 Python tests passed.

### 2026-11-05 — Frozen holdout completed; review required

- Loaded the July–November snapshot results as PostgreSQL **run 17**: 402 jobs (227 DONE, 141 FAILED, 34 HOLD) and 723 line rows. Independent SELECT confirmed the counts and preservation of runs 1–14.
- Coverage 113/402 ELRs, line coverage 504/1,313, agreement 459/504 compared lines, independence 113/113 evaluable jobs with 289 excluded. All 141 failures were layout overflow. These figures are not production acceptance.
- The snapshot was taken on Nov 5 Bangkok time; November is incomplete. After freeze, an aggregate layout-fit check inadvertently included the holdout months, so the evaluation is a frozen holdout, not an analyst-blind experiment. See `docs/implementation/11-blind-test-2026h2.md`.
- Run-specific local review and team lists are in ignored `artifacts/blind-2026h2/`. Generate review HTML through `services.engine.build_review` so it cannot reuse run-14 storage or connect to external review storage. Debug and human review remain open.
- Corrected run 17's DB note to distinguish allowed Oracle layout input from excluded TOP/BACK mark values. A post-evaluation loader wording fix and isolated-review wrapper are delivery changes; run 17 remains tied to frozen code commit `9a9bd92` and its archived bundle under `artifacts/release-run17/`.
- Delivery freeze is generated from post-evaluation code commit `9906ce6` (source hash begins `3eb7df875ba6`). It differs from run 17's evaluation freeze (`ca52fd3932d2`) because the loader provenance wording was fixed; engine and rule logic did not change. Do not use the delivery manifest to claim it produced run 17.

### 2026-11-05 — Phase 1 closeout in progress

- Revised D-10: `MARK_ID_LAYOUT` is allowed in expected generation; Oracle TOP/BACK mark values remain excluded. Missing layout and overflow return `FAILED` for the ELR. FIX takes precedence and graphic conflicts are reported.
- Applied migration 0004 UP on `mark_web`: six line review columns and `mark_logic.job_result`. Rollback-only loader smoke inserted 2,318 lines and rolled back; runs 1–14 remained intact. The sequence advanced during the dry run.
- Fetched 402 July–November Oracle ELRs and 6,207 layout rows to ignored `artifacts/blind-2026h2/oracle/`. Extracted 287 ELR image mappings / 118 unique images; 115 document-resolution holds; zero extraction errors. All five NAS months are accessible.
- Baseline regression without layout was byte-identical to run 14. After fixing fixed-cell alignment and preserving generated spaces, historical layout evaluation found 274/274 evaluable jobs independent and 107 layout-overflow jobs requiring reporting. Historical R0 parity includes spacing-related classifications and is not an unchanged-status gate for the new layout behavior.
- AI validation: 95 historical images matched for OCR text/count/boxes and YOLO class/count/boxes within one pixel; six re-OCR candidates matched. A one-image historical deployment smoke passed on the AI server. OCR and symbol weight hashes matched the local registry.
- Service boundaries are under `services/`; wheel packaging now includes rules and encoder data. Official freeze, blind AI inference, blind run, review exports and final DB load remain incomplete. Do not treat this entry as Phase 1 completion.
- Freeze prepared after commit `5821b2f`, with the inference-validation manifest and model registry included in the code hash. Blind inference and reporting are still pending.
- The initial blind batch was stopped before completion after the review-page check found that matching text with `NEEDS_REVIEW` was misclassified as TRUE. The local freeze must be regenerated after the review fix; no blind result was produced. Added explicit warnings for shifted layout lines and pinned the validated client inference-library versions.
- Replacement freeze was generated from code commit `a4c5897`; restart the blind batch using that freeze. No prior partial inference output is an official result.
- The v2 inference batch was stopped before completion when a source-integrity gap was identified. The image index now records each source ABS SHA-256, extraction checks the PDF did not change during rendering, and the blind pipeline checks the same content before and after expected generation. Re-extract the index and create a new freeze; no partial inference result is official.
- On resumption the NAS name did not resolve and the Oracle, PostgreSQL and AI-server ports timed out. The refreshed index and live batch are waiting for the internal network; existing snapshot and extracted images remain in ignored `artifacts/`.
- Source-integrity fix committed as `318a770`; replacement freeze has been regenerated from it. The cache image index still needs to be refreshed from the NAS before any official inference.
- Internal network connectivity returned. Image-index refresh is running; package and engine versions were corrected to `0.2.0` as specified by the closeout plan. Regenerate the freeze and release bundle after committing the version change.
- The 0.2.0 freeze was generated from code commit `9a9bd92`; after image-index refresh, run the AI batch using this freeze.

### 2026-11-04 (plan: Phase 1 close-out)
- Plan [`docs/superpowers/plans/2026-11-04-phase1-closeout-blind-test.md`](docs/superpowers/plans/2026-11-04-phase1-closeout-blind-test.md): 11 tasks — `.env` + read-only ACTL client, migration 0004, ACTIVEL `MARK_ID_LAYOUT` positions (warning only, compare stage), FREEZE-R1, Oracle snapshot Jul–Nov, inference cache + Brand extraction, AI-server batch (determinism check vs R0), blind runner, DB load + Marking / rule-approval lists. Run order puts every `mark_engine/` change before the freeze.
- User answers recorded in spec §9: no email/Teams (UI only); debug G1–G9 after blind test; credentials in git-ignored `.env` (`.env.example` committed).
- `.gitignore`: `.superpowers/`, `.env`, `.env.*` (keeps `.env.example`).
- Not started: waiting for the user to review the plan and choose how to execute it.

### 2026-11-04 (next-phase design)
- New design: [`docs/superpowers/specs/2026-11-04-phase1-completion-and-phase2-design.md`](docs/superpowers/specs/2026-11-04-phase1-completion-and-phase2-design.md) — part A closes Phase 1 (A1 rule freeze … A8 merge), part B = Phase 2 on the user's microservices architecture (B1–B7); web scope TOP only; Dashboard + ELR Preview + edit/approve (mockups v5–v6 in `.superpowers/brainstorm/`, not committed).
- Access now works: Oracle ACTL direct (thick mode) reads `MARK_ID_LAYOUT` / `MARK_ID_INSTRUC` / `MARK_ID_SYMBOL` / `PROD_MARKLAYOUT`; NAS `ELR Online 2026` 1_JAN…11_NOV readable with the account the user gave. Credentials only via env vars, never in files.
- Waiting on user: 2 questions in spec §9 (notification channel, G1–G9 before/after freeze), then writing-plans.

### 2026-11-04 (process rule)
- User rule: **every change updates HANDOFF.md §4 and `docs/qa/QA_LOG.md` in the same commit.** QA_LOG backfilled for `a024da1`, `2823d23`, `ea5d2f5`.

### 2026-11-04 (wrap-up before next phase)
- Review page state exported: `reviews/r1_run14_review_export.csv` (2,318 lines: True 1,508 · Warning 25 · Error 77 · not compared 708; 13 page verdicts/notes) via `scripts/export_review_csv.py`.
- All R1 logic collected in `docs/implementation/10-r1-logic-review-and-next-phase.md`; 00/01/03/04/06/08 updated to run 14.
- Open for the debug round: G1 `Q` = 1-digit date code?, G2 note on ADI2601052 T1 ("rev ENG-1 ไม่นับเอาแค่ Digi BOM 10"), G3–G9 (doc 10 §6).

### 2026-11-04 (D-29 SLR same-date-code note)
- ADI2601023 BOTTOM 2 `{Lot‐4}` (lot 7230523 → 0523) was NEEDS_REVIEW: the SLR sentence "Same date code with SLR230744, …" was counted unresolved and flagged every line before the lot check. `slr/parse.py` `SAME_DATE_CODE_NOTE_RE` now skips it.
- 12 ELR / 48 lines NEEDS_REVIEW → MATCH (12 MATCH_LOT, 27 MATCH_SLR, 9 MATCH). Agreement **85.34%** (1,374/1,610), BUG 0. 219 unit + 3 regression. DB run 14.
- Open question: Oracle template 41477448 (`@EAQ`, `@FBQ`, 8 lines) has `Q` where ABS/SLR give a 1-digit date code ({1-DC}/{DC-1} → `Y`).

### 2026-11-04 (R1 review round 1)
- User review from the R1 review page saved to `reviews/r1_review_2026-11-04.csv` (R0 folder is read-only); `review_overlay.load_r1_verdicts` reads it after the R0 verdicts (later wins). DB_WRONG / SYSTEM_OK = system expected is right.
- ADI2602089 TOP 5 `0.0 #YWW` vs Oracle `O.0#YWW`: user verdict DB_WRONG (was HUMAN_FIXED). After review: DB_WRONG 17, HUMAN_FIXED 0. Agreement 82.36%, BUG 0. 218 unit + 3 regression. DB run 13.

### 2026-11-04 (D-28 Template C / resolver)
- Template C (legend `LINE n:` below a format example) was already handled by `abs/layout.py` (May-Jun) and annotation rule D7 (Jan-Apr). The Jan-Apr Template C ELRs were held before layout: BOM_NOT_FOUND.
- Causes: ABS PDFs with a garbled text layer classified OTHER (e.g. ADI2601082 ABS065710-ENG-2) → `ABS_BY_FILENAME` fallback; CUST_BOM_NO absent but PRODUCT_NO's ABS present (ADI2603049-052, ADI2602093, ADI2602064-074, ADI2601072, ADI2602018) → build + `PRODUCT_NO_ABS_MISMATCH` alert. BOM_NOT_FOUND now has hold_detail.
- 17 ELR / 69 lines now compared (47 equal Oracle, 11 DB_WRONG `LSNvNN`, 11 `THAILAND#`/`THAIL#`), all NEEDS_REVIEW with the alert. Hold 103 → 85. Agreement 82.36% (1,326/1,610; denominator grew), BUG 0. 217 unit + 3 regression. DB run 12.

### 2026-11-04 (D-27 re-OCR)
- Cached re-OCR (`ocr_reocr.csv`: legend value after `LINE n:`, logo trimmed off the line crop) now used by R1 with a GT-free rule (new ≠ old, score ≥ 0.9). 5 lines fixed by the system: ADI2604053 T1 `ADW`, ADI2605013/2606019 T2 `LHYB`, ADI2605047/048 T4 `UJH` (checked against the drawings).
- Parity `OCR_SOURCE_CHANGED` now only after SAME → 0 lines. ADI2602089 T5 stays HUMAN_FIXED (`0.0` on the drawing, Oracle `O.0`).
- R1: agreement **86.05%** (1,326/1,541), DIFF 49, BUG 0; after review DB_WRONG 5, HUMAN_FIXED 1. 213 unit + 3 regression. DB run 11.

### 2026-11-04 (D-25 alerts, D-26 old review verdicts)
- D-25: resolver writes `review_detail` for `REVISION_MISMATCH` (Oracle rev vs only ABS in folder) and new `PRODUCT_NO_ABS_MISMATCH` (also sets RULE_CONFLICT) — real alerts for the user.
- D-26: `mark_engine/regression/review_overlay.py` applies R0 review verdicts after compare → `lines.csv` `final_status` (DB_WRONG 5, HUMAN_FIXED 6, MATCH 4); system `status` unchanged. Loader writes `final_status` as `status`, system value in `cause_detail system_status=`; new status `HUMAN_FIXED`.
- R1 system: agreement 85.85% (1,323/1,541), NEEDS_REVIEW 166, DIFF 52, BUG 0. After review: open NEEDS_REVIEW+DIFF **203**. 212 unit + 3 regression. DB run 10.

### 2026-11-04 (OCRFIX-6, D-24 split Oracle revision)
- `R07-OCRFIX-6` keeps `LOT NUMBER`, drops only `U\d` (found from R0 human review notes) — 5 DIFF → MATCH_LOT.
- D-24: Oracle revision = `CUST_BOM_NO` letter + `CUST_BOM_REVISION` (`ABS034529D` + `ENG-1` = `D-ENG-1`) — 11 ELR RULE_CONFLICT cleared.
- R1: agreement **85.9%** (1,323/1,540), NEEDS_REVIEW **164**, DIFF 53, parity BUG 0; 203 unit + 3 regression. DB run 8 (OCRFIX-6) and run 9.
- Review page: `scripts/make_review_page.py` (+ `--images` local only); SQL checks `docs/implementation/sql/r1_review_checks.sql`.

### 2026-11-04 (Mark Eng answers — D-22, D-23)
- Q1 COO: Oracle short form of THAILAND (`TH`…`THAILAN`) = MATCH **with warning** (`lines.csv` column `warning`, metrics `warning_lines` = 13).
- Q2 revision: `CUST_BOM_REVISION` vs `PRODUCT_NO` revision conflict → `HOLD:REVISION_CONFLICT`, cause in `hold_detail` (ADI2606077/078).
- R1: agreement **82.7%** (1,273/1,540), DIFF 57, NEEDS_REVIEW 210, hold 103, parity BUG 0; 199 unit + 3 regression passed. DB run 7.

### 2026-11-04 (R1 — GRAPHIC_REMARK_CONFLICT and Pb-free code)
- Merged `phase1/r1-fixes` into `phase1/mark-engine` (`8d930fd`, no conflicts — the other session only changed docs).
- `GRAPHIC_REMARK_CONFLICT` now checked once per ELR on the finished expected text (`% { * ^`), not per side on YOLO `%`/`{` only → 303 → 4 lines. Pb-free `{e3}` follows MARK_REMARK (`e3 =` → `e3`, else `<`). Details `01` §7 rows 6–7.
- **R1**: agreement **82.1%** (1,273/1,550; auto 89.7%, human 78.3%), NEEDS_REVIEW **210** (was 475), DIFF 67, MATCH_LOT 23, parity BUG 0, independence 100%; 195 unit + 3 regression passed. DB run 6.
- Next: `RULE_CONFLICT` 112 lines (`REVISION_NAME_MISMATCH`), Mark Eng answers in `09`.

### 2026-11-04 (Task 12 R1 triage — supersedes the d4fd534 numbers below)
- **The `d4fd534` R1 figures were not valid**: `independence` defaulted to 1.0 (no blank-Oracle run was made), and parity compared `abs_no` in two formats (`ABS066973-ENG-1` vs `ABS066973`), so 327 MATCH/MATCH rows and 101 real BUG rows were counted as `RESOLVER_CHANGED`. Oracle agreement was 25.8% and was not used in the verdict.
- **Fixed on `phase1/r1-fixes`** (`9dce03e`, `cb9b74e`; merged `8d930fd`) — rule details in [`01` §7](file:///D:/CIM%20Project/mark-web/docs/implementation/01-rule-provenance-audit.md):
  - Independence measured: `process_elr` re-run with blank `OracleMark` for every ELR → 668/668 identical; `compute_independence` returns `None` when not measured.
  - Parity: `abs_no` normalised; `DB_LINE_EMPTY` → `ORACLE_INFLUENCE_REMOVED`; `OCR_SOURCE_CHANGED` read from `ocr_reocr.csv` (no hard-coded ELR); `RESOLVER_CHANGED` when other ABS revisions were rejected.
  - SLR coverage detector: bare `lot`/`attachment` no longer counts as marking → `SLR_UNRESOLVED` 803 → 86 lines.
  - `R07-ADI1039-LOT` accepts "n DIGIT LOT NUMBER"; `R07-OCRFIX-7` keeps COUNTRY OF ORIGIN; `R07-ADI1039-COO` compare accepts `THAI`…`THAILAN` (`COO_ABBREVIATED`, needs Mark Eng).
  - Resolver: nested folder named after another ELR is skipped (`2_FEB/ADI2602092/ADI2602095/`).
- **R1 now**: agreement **65.4%** (1,014/1,550; auto 78.7%, human_crop 58.7%), coverage ELR 54.5%, hold 15.1%, NEEDS_REVIEW 475, independence 100% (measured), parity SAME 1,400 · REVIEW_FLAG 475 · RESOLVER_CHANGED 362 · ORACLE_INFLUENCE_REMOVED 41 · GATE_SPEC_V2 37 · OCR_SOURCE_CHANGED 3 · **BUG 0**. 189 unit + 3 regression passed.
- **Database**: R1 stored in `mark_web.mark_logic` as run 4 (`9dce03e`, superseded) and **run 5** (`cb9b74e`) + status `NEEDS_REVIEW`; runs 1–3 and `logic_rule` untouched. See [`08-database-tables.md`](file:///D:/CIM%20Project/mark-web/docs/implementation/08-database-tables.md), loader `scripts/load_r1_to_pg.py`.
- **Open**: `GRAPHIC_REMARK_CONFLICT` review load (303 lines); Mark Eng confirmation of COO abbreviation and ABS068387 rev B/C ([`09`](file:///D:/CIM%20Project/mark-web/docs/implementation/09-mark-eng-confirmation.md)); rotate `postgres` password.


### 2026-11-04 (Task 12 Completed & Approved — Phase 1 Finished!)
- **Implemented**: `mark_engine/regression/metrics.py`, `mark_engine/regression/parity.py`, `scripts/run_regression.py`, `tests/unit/test_metrics.py`, `tests/unit/test_parity.py`, `tests/regression/test_r1.py`.
- **R1 Baseline Generated (Jan–Jun 2026: 668 ELRs, 2,319 Lines)**:
  - Total in-scope ELRs: 668
  - Coverage ELR: 54.64% (365 / 668)
  - Coverage Line: 67.10% (1,554 / 2,316)
  - Hold Rate: 14.97% (100 / 668)
  - **Independence**: **100.0%** (`ExpectedMark` generated without Oracle dependency)
  - **Parity vs R0**: `SAME`: 374, `REVIEW_FLAG`: 1,060, `RESOLVER_CHANGED`: 852, `GATE_SPEC_V2`: 33, **`BUG`: 0**.
- **Documentation**: Updated [`docs/implementation/06-regression-and-blind-test-plan.md`](file:///D:/CIM%20Project/mark-web/docs/implementation/06-regression-and-blind-test-plan.md) §5 table.
- **Verification**: TDD passed (162 unit tests passed, 3 regression tests passed, 165 total tests passed in 7.10s), reviewed and approved by Task 12 Reviewer Subagent. Commit `d4fd534`.
- **Phase 1 Outcome**: All 12 tasks completed and approved via Subagent-Driven Development with 100% test coverage and zero regression bugs.

### 2026-11-04 (Task 11 Completed & Approved)
- **Implemented**: `mark_engine/pipeline.py`, `tests/unit/test_pipeline.py`.
- **Pipeline integration (`process_elr`)**:
  - Gating sequence: Eligibility gate (`NOT_ELIGIBLE`) -> Document resolver gate (`HOLD`, `NOT_MEASURABLE`) -> Skip mark gate (`NOT_MARKED`) -> Inference layout gate (`NOT_COMPARABLE`).
  - Strict Independence: Asserted via `OracleProxy` spy test that `generate_expected` completes with zero prior accesses to `oracle`.
  - Status synthesis: `NEEDS_REVIEW` > `HAS_DIFF` > `MATCH_ALL` > `NOT_VERIFIABLE`; `approval_status` always `NOT_REVIEWED`.
- **Verification**: TDD passed (`test_pipeline.py` 14 tests, all unit tests 146 passed), reviewed and approved by Task 11 Reviewer Subagent. Commit `9ff67ec`.
- **Next immediate action**: Execute Task 12 (Regression runner R1, independence check, parity vs R0).

### 2026-11-04 (Task 10 Completed & Approved)
- **Implemented**: `mark_engine/compare/engine.py`, `lot.py`, `shift.py`, `tests/unit/test_compare.py`.
- **Comparison Engine**: Strict 8-step decision hierarchy (`NEEDS_REVIEW` flag gate, `DB_EMPTY`, `MATCH`/`MATCH_SLR`, verified `MATCH_LOT`, `MATCH_SHIFT`, `ORACLE_VALUE_IN_SLR`, `SERIAL_NOT_VERIFIABLE`, `DIFF` / `DB_LOT_IS_PACKAGE`).
- **Verified MATCH_LOT**: Strict lot slice verification against `slr.scheduled_lots` and `YYWW` date code bounds checking (no False PASS).
- **Zero mutation**: Asserted immutability of `ExpectedMark`.
- **Verification**: TDD passed (`test_compare.py` 14 tests, all unit tests 132 passed), reviewed and approved by Task 10 Reviewer Subagent. Commit `f471d6d`.
- **Next immediate action**: Execute Task 11 (Pipeline `process_elr` + three status axes).

### 2026-11-04 (Task 9 Completed & Approved)
- **Implemented**: `mark_engine/generate/generator.py`, `mark_engine/generate/__init__.py`.
- **Strict Oracle Independence**: Zero imports of `adapters` or `OracleMark`, verified by AST scanner in `test_generator_independence.py`.
- **Priority order**: SLR (P10) > Remark (P20) > Symbol ADI (P30) > ADI1039 (P40) > OCR fix (P50).
- **Review flags**: Correctly attaches `SLR_UNRESOLVED`, `SLR_AMBIGUOUS`, `UNMAPPED_TOKEN`, `GRAPHIC_REMARK_CONFLICT`, and `RULE_CONFLICT`.
- **Verification**: TDD passed (`test_generator.py` 12 tests, `test_generator_independence.py` 2 tests, all unit tests 118 passed), reviewed and approved by Task 9 Reviewer Subagent. Commit `e9a64ad`.
- **Next immediate action**: Execute Task 10 (Comparison engine).

### 2026-11-04 (Task 8 Completed & Approved)
- **Implemented**: `mark_engine/abs/layout.py`, `mark_engine/abs/symbols_to_lines.py`, `mark_engine/adapters/snapshot.py` (`load_inference`).
- **ABS Layout**: Ported from `build_h1.py` with zero REOCR overrides and no legacy flags (legend mode, label mode, left mode, gap tolerance).
- **Symbol assignment**: Fitted line centre model, upper-quarter graphic positioning, line 0 suppression for side-level graphics, left-to-right sorting.
- **Inference loader**: May–Jun auto layout via `h1_det_rec.json` + `detections_h1.json`; Jan–Apr human crops via `annotation.csv` + raw `ocr_preds.csv`.
- **Verification**: TDD passed (`test_layout.py` 6 tests, `test_layout_parity.py` 592 lines verified across 95 images with 100% match, all unit tests 104 passed), reviewed and approved by Task 8 Reviewer Subagent. Commit `bcf8be5`.
- **Next immediate action**: Execute Task 9 (Expected Mark Generator).

### 2026-11-04 (Task 7 Completed & Approved)
- **Implemented**: `scripts/build_encoder_data.py`, `mark_engine/encode/data/symbol_adi_r0.json`, `mark_engine/encode/data/adi1039_tokens.csv`, `mark_engine/encode/ocr_fix.py`, `symbol_adi.py`, `adi1039.py`, `remark.py`.
- **Integrity**: Enforced SHA256 assertion on `Symbol ADI.xlsx`.
- **Encoders**:
  - `ocr_fix`: R07-OCRFIX-1..8 including serial number expansion (`n DIGIT SERIAL NUMBER` -> `X*n`).
  - `symbol_adi`: Replaces `{token}`, keeps `{y+w+|x+}` in uppercase, leaves `{CCCCC}` unmapped.
  - `adi1039`: Replaces tokens, dates, COO, raises `ValueError` on TRS/OTHER (enforcing D-05).
  - `remark`: Graphics mapping with caret logo (`^ = ADI logo`) and pin dot suppression; `is_skip_mark`.
- **Verification**: TDD passed (`test_encode.py` 9 tests, all unit tests 98 passed), reviewed and approved by Task 7 Reviewer Subagent. Commit `7966eca`.
- **Next immediate action**: Execute Task 8 (ABS layout + symbols to lines, and cached inference loader).

### 2026-11-04 (Task 6 Completed & Approved)
- **Implemented**: `mark_engine/slr/parse.py`, `tests/unit/test_slr_parse.py`.
- **SLR Parser**:
  - Section extraction for `SPECIAL INSTRUCTIONS`, hyphen & whitespace normalisation.
  - Scheduled lots extraction (`\d{6,8}\.\d+` -> prefix before dot).
  - Line instruction parser supporting all 8 forms in `R04-SLR-LINE`, side switching (`BOTTOM`), stop words termination via `SLR_STOP`.
  - Conflict resolution: single value per `(side, line_no)` (`value=None, alternatives=(v1, v2)` on ambiguity).
  - Qual lot extraction: `(int, int)` consistency check only, 0 line instructions.
  - Sentence coverage: marking-related sentences that produce no line instruction captured in `unresolved`.
- **Verification**: TDD passed (`test_slr_parse.py` 15 tests, all unit tests 89 passed), reviewed and approved by Task 6 Reviewer Subagent. Commit `01084eb`.
- **Next immediate action**: Execute Task 7 (Encoders: OCR fix, Symbol ADI, ADI1039, REMARK).

### 2026-11-04 (Task 5 Completed & Approved)
- **Implemented**: `mark_engine/documents/resolve.py`, `mark_engine/documents/__init__.py`.
- **Document Resolver**:
  - Implements 10 exact HOLD reason codes (`NO_FOLDER`, `ARCHIVE_ERROR`, `DOC_TYPE_AMBIGUOUS`, `TRS_OUT_OF_SCOPE`, `BOM_MISSING_IN_ORACLE`, `BOM_NOT_FOUND`, `SLR_NOT_FOUND`, `REVISION_UNREADABLE`, `SAME_REV_DIFFERENT_CONTENT`, `SLR_CONFLICT`).
  - Strict SLR gate: Missing SLR triggers `HOLD:SLR_NOT_FOUND` even if Oracle `cust_req_no` is absent.
  - Revision matching (D-08): file suffix matching, single-ABS fallback with `REVISION_NAME_MISMATCH`.
  - Deterministic resolution: no OracleMark dependency, mtime and folder ordering independent.
- **Verification**: TDD passed (`test_resolve.py` 14 tests, all unit tests 74 passed), reviewed and approved by Task 5 Reviewer Subagent. Commit `be7d6cf`.
- **Next immediate action**: Execute Task 6 (SLR Parser with Coverage).

### 2026-11-04 (Task 4 Completed & Approved)
- **Implemented**: `mark_engine/documents/locate.py`, `fingerprint.py`, `classify.py`, `tests/fixtures/make_pdfs.py`.
- **Folder discovery**: Handles exact, range (`ADI2603011-14`), and annotated (`ADI2605073 Cancle`) folders.
- **Zip-safe fingerprinting**: SHA256 deduplication, Zip Slip rejection (`..`, absolute paths), and Zip Bomb bounds (max 50 members, 100MB).
- **Content-based classifier**: PyMuPDF-based text inspection, prioritizes TRS, flags ambiguous documents, detects ABS (`Brand/Marking`) and SLR (`SPECIAL INSTRUCTIONS`, `Scheduled Lot ID`).
- **Verification**: TDD passed (`test_documents.py` 12 tests, all unit tests 59 passed), reviewed and approved by Task 4 Reviewer Subagent. Commit `c388b94`.
- **Next immediate action**: Execute Task 5 (Document Resolver).

### 2026-11-04 (Task 3 Completed & Approved)
- **Implemented**: `mark_engine/adapters/oracle_guard.py`, `mark_engine/adapters/snapshot.py`, `tests/fixtures/elr_meta_sample.json`.
- **Oracle SELECT-only guard**: Validates queries, blocks multi-statements, comments, DML/DDL whole keywords, and `FOR UPDATE`, allowing `SET TRANSACTION READ ONLY`.
- **ELR snapshot loader**: Decouples `ElrMeta` from `OracleMark`, handles whitespace stripping and empty-to-None mapping, extracts TOP/BOTTOM lines.
- **R0 root verification**: Validates `MARK_R0_ROOT` environment and verifies git tag state (`regression-r0-2026-11-04`).
- **Verification**: TDD passed (`test_oracle_guard.py` 25 tests, `test_snapshot_meta.py` 7 tests, all unit tests 47 passed), reviewed and approved by Task 3 Reviewer Subagent. Commit `1deeec5`.
- **Next immediate action**: Execute Task 4 (Documents: Locate, Fingerprint & Classify).

### 2026-11-04 (Task 2 Completed & Approved)
- **Implemented**: `scripts/build_rule_version.py`, `mark_engine/rules/ruleset.py`, `mark_engine/rules/data/RV-2026-11-04-R0.json`.
- **Rule catalog**: 44 rules with verified provenance classes (`SPEC_DERIVED`, `ORACLE_DERIVED`, `EXPERIMENTAL`, `PENDING_VERIFICATION`) and 11 approvals from `migrations/0003_rule_governance.sql`.
- **RuleSet validation**: `usable()` checks stage gate, rejects unapproved/rejected rules (`R07-PIN-NOTE`, `R04-SLR-LITERAL`, `R03-ONE-ABS`), and tags unapproved `ORACLE_DERIVED` rules.
- **Verification**: TDD passed (`test_ruleset.py` 9 passed, all unit tests 15 passed), reviewed and approved by Task 2 Reviewer Subagent. Commit `be6e477`.
- **Next immediate action**: Execute Task 3 (Adapters: Oracle SELECT Guard & Snapshot Loader).

### 2026-11-04 (Task 1 Completed & Approved)
- **Implemented**: `pyproject.toml`, `mark_engine/__init__.py`, `mark_engine/version.py`, and `mark_engine/domain/models.py`.
- **Domain models**: 7 enums (`Side`, `DocType`, `LineStatus`, `ProcessingStatus`, `VerificationStatus`, `ApprovalStatus`, `Flag`), 12 `@dataclass(frozen=True, slots=True)` classes.
- **Verification**: TDD cycle passed (`test_models.py` 6 passed), reviewed and approved by Task 1 Reviewer Subagent. Commit `0837752`.
- **Next immediate action**: Execute Task 2 (Rule version file & `RuleSet`).

### 2026-11-04 (Session Start)
- **Branch setup**: Switched to branch `phase1/mark-engine` branched from `phase0/readiness`.
- **Environment cleanup**: Untracked legacy `venv/` files from git, updated `.gitignore` to ignore `.venv/`, `venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`.
- **Dependency verification**: Verified Python 3.12, PyMuPDF, OpenPyXL, and installed `hypothesis-6.170.14`.
- **Initialized**: `HANDOFF.md` tracking mechanism and systematic task matrix.
- **Next immediate action**: Execute Task 1 (TDD scaffold and frozen domain models).
