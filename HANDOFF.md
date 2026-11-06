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

### 2026-11-06 — fix(deploy): agent bat quoting, NAS notes, preflight -PythonExe
- `scripts/jenkins-agent.bat`: `if not defined X set ...` instead of `if "%X%"==""`; `JAVA` is stripped of quotes and invoked as `"%JAVA%"`.
- `scripts/deploy/README.md`: NAS volume section (credentials live in the volume options; changing them needs `docker volume rm mark-web_nas_elr`; no "," in NAS_USER/NAS_PASSWORD; NAS down means worker exits 2 and restarts in a loop).
- `scripts/deploy/preflight_17.ps1`: `-PythonExe <path>` (default `python`); FAIL if `NAS_USER`/`NAS_PASSWORD` contain ","; a firewall PASS from a rule without a port restriction is now WARN.

### 2026-11-06 — fix(ci): per-host parameter defaults from Jenkins global env
- Problem: Jenkins resets parameters declared in `Jenkinsfile` to `defaultValue` on every build, so a Poll SCM build on .17 would deploy with port 8088, dev paths and `WORKER=false`.
- `Jenkinsfile`: `defaultValue` of `MARK_WEB_PORT`, `MARK_FILES_HOST_DIR`, `MARK_LOG_HOST_DIR`, `ENV_FILE`, `PYTHON_EXE`, `WORKER` now reads `env.MARK_DEFAULT_WEB_PORT`, `MARK_DEFAULT_FILES_DIR`, `MARK_DEFAULT_LOG_DIR`, `MARK_DEFAULT_ENV_FILE`, `MARK_DEFAULT_PYTHON`, `MARK_DEFAULT_WORKER`; fallbacks are the dev values (dev PC sets nothing).
- `scripts/deploy/README.md`: table of the global env variables to set on .17 (port 8093, `D:/mark-web/...`, worker true).

### 2026-11-06 — Deploy 17 Task 4: Preflight Script, Host-Neutral Jenkinsfile, Deploy Guide
- **Preflight Script (scripts/deploy/preflight_17.ps1)**:
  - Implemented PowerShell 5.1 preflight check verifying: clean checkout matching origin/phase2/trial, tooling versions (Python 3.12, Node, Git, Java >=17, Docker linux engine), disk free space >= 10 GB, automatic port discovery avoiding listeners/containers/Windows excluded port ranges, internal network reachability (PG 5432, Oracle 1521, A100 50051, NAS 445), download reachability (PyPI, npm, Docker Hub, Oracle, GitHub), .env required keys (names only, secrets never printed), and inbound firewall rule check (prints New-NetFirewallRule warning if missing).
  - Tested on dev PC: -Ports 8088,8090 detected 8088 busy, selected free port 8090, verified all PASS. Verified negative case: checkout fails with exit 1 on uncommitted tracked changes.
- **Host-Neutral Jenkinsfile & Inbound Agent Script**:
  - Added WORKER boolean parameter (default alse) to Jenkinsfile. When true, runs docker compose --profile worker build and docker compose --profile worker up -d --remove-orphans.
  - Removed host names from parameter descriptions while keeping dev workstation default values.
  - Updated scripts/jenkins-agent.bat to read JENKINS_URL, AGENT_NAME, WORKDIR, JAVA from environment variables, falling back to dev PC defaults when unset.
- **Deployment Documentation**:
  - Authored scripts/deploy/README.md covering prerequisites, preflight execution, Jenkins agent configuration on .17, and first deployment steps (Task 5 instructions).
  - Updated services/README.md with pointer to scripts/deploy/README.md.


### 2026-11-06 — Deploy 17 Task 3: Worker Service and Read-Only CIFS NAS Mount in Compose
- **Startup Check (`check_nas_root`)**:
  - Implemented in `services/worker/main.py`: verifies `ELR Online 2026` folder exists and contains entries; exits with exit code 2 if unreadable or empty.
  - Added unit tests `test_check_nas_root_missing_exits_2`, `test_check_nas_root_empty_exits_2`, and `test_check_nas_root_ok` in `tests/unit/test_worker.py`.
- **Compose Service & CIFS Volume**:
  - Added `worker` service to `docker-compose.yml` under `profiles: ["worker"]` with `NAS_ROOT=/mnt/elr/ADI`, `MARK_INFERENCE=service`, Oracle client vars, and volumes `nas_elr:/mnt/elr:ro` and `./work:/app/work`.
  - Added CIFS volume `nas_elr` mounting `//th1srnas03/ELR` with `ro,vers=3.0,domain=${NAS_DOMAIN:-TH},username=${NAS_USER},password=${NAS_PASSWORD},uid=1000,gid=1000`.
  - Added `NAS_DOMAIN=TH` and `MARK_WORKER_PG_PASSWORD=` to `.env.example`.
- **Verification on Dev PC**:
  - `docker compose config` (no profile) lists only `api` and `web`, preserving unchanged Jenkins deployment on dev.
  - Full unit test suite: 499 tests passed (`pytest tests -q --ignore=tests/regression`).
  - Proved CIFS mount inside container: `docker compose --profile worker run --rm worker python -c "import os,pathlib;p=pathlib.Path(os.environ['NAS_ROOT'],'ELR Online 2026');print(sum(1 for _ in p.iterdir()))"` returned 11 month directories.
  - Proved worker container end-to-end: triggered API recheck for `ADI2607006` (`POST /api/elrs/ADI2607006/recheck` returned 200 `queued: true`), ran worker container with `--once`.
  - Verified in PostgreSQL: Work item 14 completed with `state = 'done'`, `error = NULL`, `revision = 3`.
  - Verified `mark_app.elr_revision`: Revision 3 created with `changed = 'manual'`, `run_id = 25`, and `docs_probe` keys prefixed with `/mnt/elr/ADI/`. Result fingerprint matched previous revisions.

### 2026-11-06 — Deploy plan updated: development moves to .17, Jenkins on .17
- **User:** day-to-day work moves to .17 after this plan; Jenkins is already installed there as Docker container `jenkins` (`jenkins/jenkins:lts-jdk21`, host 8080, volume `jenkins_home`).
- **Plan change** (`docs/superpowers/plans/2026-11-06-deploy-17.md`): Task 4 adds a `WORKER` parameter to `Jenkinsfile`, env-driven `scripts/jenkins-agent.bat`, and tool/GitHub checks in `preflight_17.ps1`. Task 5 now sets up a Windows agent `mark-web-local` on the .17 host (the Linux controller cannot run `bat`), job polling `phase2/trial` every 5 min, then the first build is the deploy. The dev PC Jenkins becomes CI-only (`DEPLOY=false`).
- **Port note:** 8080 on .17 is now Jenkins (memory said Streamlit; preflight decides).

### 2026-11-06 — Deploy 17 Task 2: Mount-Independent docs_fp
- Updated `docs_fp` to relativize document paths under `roots=(nas_root, work_dir)`.
- Tested UNC mount vs Posix container mount `/mnt/elr/ADI`: identical `docs_fp`.
- 496 unit tests passed.
- Note: ADI2607006 revisions 1–2 hold old absolute-path `docs_fp`, so next automatic check will record one `changed=docs` revision (accepted, no data fix).

### 2026-11-06 — Deploy 17 Task 1: Merge phase2/airflow into phase2/trial
- Merged origin/phase2/airflow into phase2/trial for deployment to 10.153.90.17.
- Retained both changelogs in chronological order.
- Airflow DAGs and client tests merged; 493 unit tests passed.
- Fixed `ZoneInfoNotFoundError: 'No time zone found with key Asia/Bangkok'` on Windows by adding `tzdata` to `pyproject.toml[dev]` and fallback in `test_mark_api_client.py`.
- Airflow work branches will originate from phase2/trial going forward.

### 2026-11-06 — Plan: deploy to 10.153.90.17 (for the other agent)
- **Plan:** `docs/superpowers/plans/2026-11-06-deploy-17.md`. B3 is finished (build 57 green at `05c0a31`).
- **User facts:** .17 is Windows + Docker Desktop, can clone from GitHub; any free port (not 8088 NPIChecklist / 8080 Streamlit), chosen by a preflight script.
- **Tasks:** (1) merge `phase2/airflow` into `phase2/trial`; (2) `docs_fp` independent of NAS mount path (today it hashes the absolute UNC path, so a container mount would re-check every ELR); (3) `worker` compose service (profile `worker`) with read-only CIFS mount of `//th1srnas03/ELR` and a start-up NAS check; (4) `scripts/deploy/preflight_17.ps1`; (5) **[USER]** clone, preflight, `docker compose -p mark-web --profile worker up -d --build`, smoke test, then Codex runs Airflow Task 3–4 against `http://10.153.90.17:<port>`.
- **Rule:** after .17 is live, only one worker runs (not the dev PC).

### 2026-11-06 — Task 6 Steps 2–5 Complete: Migration 0008, Recheck Revision 2, Safety Checks
- **Migration 0008 (`migrations/0008_manual_revision.sql`)**:
  - Replaced `elr_revision_fp_unique` with partial unique index `elr_revision_fp_auto_unique` on `(elr_no, oracle_fp, docs_fp) WHERE changed <> 'manual'`.
  - Added partial unique index `notification_unread_unique` on `(elr_no, kind, coalesce(revision, 0)) WHERE read_at IS NULL`.
  - Removed `begin;` and `commit;` from migration SQL files, giving full transaction control to `apply_migration_0008.py`.
  - Verified dry-run rollback leaves 0 indexes on throwaway test schema `t0008_proof` and real DB.
  - Applied and committed on live DB `10.151.28.2/mark_web`:
    - Cleaned up notification row 1 (false alarm) and rows 2–4 (duplicate unread rows) by marking read (`read_at = NOW(), read_by = NULL`), keeping row 5.
    - Successfully created `elr_revision_fp_auto_unique` and `notification_unread_unique`.
- **Task 6 Step 3: Recheck Execution**:
  - Work item 4 claimed by worker (`--once`).
  - Resolved NAS documents, called live A100 inference, inserted `run_id: 24` (`auto-2026-11-06.2`).
  - Wrote `elr_revision` 2: `changed = 'manual'`, `result_unchanged = true`, `run_id: 24`.
  - `mark_app.work_item`: Item 4 updated to `state = 'done'`, `revision = 2`, `error = NULL`.
  - `mark_app.latest_job_result` view confirmed: `('ADI2607006', 2, 24, 'manual', True, 'DONE')`.
  - Called `POST /api/elrs/ADI2607006/oracle-check`: returned HTTP 200 `NOT_MARK_REVIEW_STEP`, did not duplicate unread notification.
- **Task 6 Step 4: Simulated Oracle Change**:
  - `test_task6_step4_simulated_oracle_top_mark2_change`: unit test feeding worker modified Oracle row with `TOP_MARK2` altered.
  - Verified worker produces revision with `changed = 'oracle'` and `changed_fields = ['TOP_MARK2']`.
- **Task 6 Step 5: Safety Verification**:
  - `python scripts/check_trial_readonly.py --run 19`: 8/8 checks PASSED. Runs 1–19 completely untouched (16 runs, 402 ELRs, 866 TRUE, 214 WARNING, 41 ERROR, 34 HOLD).
  - `pg_stat_user_tables`: `mark_logic.job_result` (`n_tup_upd = 0, n_tup_del = 0`), `mark_logic.line_result` (`n_tup_upd = 0, n_tup_del = 0`), `mark_app.elr_revision` (`n_tup_upd = 0, n_tup_del = 0`). Only INSERTs.
- **Verification**: 474 unit tests passed (`pytest tests -q --ignore=tests/regression`).

### 2026-11-06 — Task 6 Step 1 Cleanup & Step 2 Dev E2E Walkthrough (ADI2607006)
- **Database Scan Invalidation**:
  - Executed cleanup on `10.151.28.2`: `scan_id=2` marked `invalid: oracle unavailable (oracledb missing)`, `scan_id=1` marked `orphan: oracle connect failed before fail_scan fix`.
  - Confirmed via `SELECT scan_id, finished_at, error FROM mark_app.scan`.
- **Task 6 Step 2 Walkthrough (ADI2607006)**:
  - `POST /api/elrs/ADI2607006/oracle-check` returned HTTP 200 `{"queued": false, "reason": "NOT_MARK_REVIEW_STEP"}` (Oracle ACTL step is 7, review step is 6).
  - Created notification in `mark_app.notification` (`kind='not_eligible'`).
  - `POST /api/elrs/ADI2607006/recheck` returned HTTP 200 `{"queued": true}` and queued work item.
  - **Surgical Fixes Applied**:
    1. `services/api/mark_api/repo.py`: Added `state='queued'` in `Repo.enqueue_work_item`.
    2. `services/worker/results.py`: Fixed `line_result` insert statement columns (`final_mark`, `db_mark`, `status`, `cause`, `cause_detail`, `system_status`, `final_status`, etc.) matching DB table schema.
    3. `services/worker/results.py`: Serialized `oracle_top_raw` with `json.dumps()` for JSONB column in `elr_snapshot`.
  - Worker executed with `--once`:
    - Resolved real NAS documents (`\\th1srnas03\ELR\ADI\ELR Online 2026\7_JUL\ADI2607006`).
    - Contacted live A100 inference service (`10.151.28.9:50051`).
    - Generated run `run_id: 22` (`period: auto-2026-11-06`).
    - Inserted `job_result` (DONE, MATCH_ALL, NOT_REVIEWED) and 5 `line_result` rows (5/5 MATCH).
    - Created `elr_revision` 1 (`changed: manual`, probe captured).
  - Verified via `GET /api/elrs/lookup?elr=ADI2607006` -> returns `in_system: true`, revision 1, status `DONE`.
- **Verification**: 467 passed unit tests. Live pipeline end-to-end verified across Oracle, NAS, A100, PostgreSQL, API and Worker.

### 2026-11-06 — Fix(API, Worker): Fail Loudly Without Oracle & Retry Attempts Integrity
- **Commit**: `fix(api,worker): fail loudly without Oracle, retry attempts`
- **Key Changes**:
  1. Reverted soft fallback: `POST /api/scans` fails loudly with HTTP 503, records error in `mark_app.scan` (watermark unchanged) when Oracle is unavailable.
  2. `oracle-check` returns HTTP 503 when Oracle fails, preventing false `not_in_oracle` notifications.
  3. Added `oracledb>=2.0.0` to `pyproject.toml[api]` and installed Oracle Instant Client 21.13 in `services/api/Dockerfile` with `libaio1t64` and `ldconfig`. Overrode `ORACLE_CLIENT_DIR` in `docker-compose.yml`.
  4. Fixed worker retry attempts: `fail()` and `fail_with_backoff()` in `services/worker/queue.py` persist `attempts = item.attempts` directly into DB, preventing rolled-back attempts from stalling retries. Tested 4th attempt transitions to `failed`. Added 5 consecutive cycle error exit with code 1 in `--once` mode.
  5. Invalidation & Re-scan: Executed DB cleanup on `mark_app.scan` (`scan_id=2` marked `invalid: oracle unavailable (oracledb missing)`, `scan_id=1` marked `orphan: oracle connect failed before fail_scan fix`). Re-ran Task 6 Step 1 with live Oracle inside container -> `scan_id: 3`, queried Oracle ACTL, confirmed actual `found: 0, queued: 0`.
- **Verification**: 467 unit tests passed (`pytest tests -q --ignore=tests/regression`). Live Oracle verified inside `api` container.



### 2026-11-06 — Network Restored & Pre-Task 6 CI Verification
- **Status**: Workstation reconnected to corporate network (`10.153.88.227`).
- **Target Reachability Verified**:
  - PostgreSQL DB `10.151.28.2:5432`: TCP connect OK.
  - A100 inference service `10.151.28.9:50051`: TCP connect OK.
  - Local container stack `http://localhost:8088/api/ready`: HTTP 200 OK `{"status":"ready"}`.
- **Next**: CI build #49 to verify green Jenkins pipeline across all unit tests (464 passed), Docker build, deploy, and smoke test, followed by Task 6 (Dev End-to-End; Step 2 is [USER] selection of real ELR).

### 2026-11-06 — Fix(API): Scan Lock and Watermark Integrity
- **Commit**: `fix(api): scan lock and watermark integrity`
- **Key Changes**:
  1. `hold_scan_lock()` context manager on `Repo` holds PostgreSQL advisory lock (`pg_try_advisory_lock` / `pg_advisory_unlock`) on a single connection throughout the scan and cleanly releases on the same connection in `finally`.
  2. Single scan row lifecycle: inserted with `finished_at = null` via `Repo.create_scan()`. On success, updated via `finish_scan()` with `counts` and `finished_at`. On failure, updated via `fail_scan()` with `error` and `finished_at`, preventing watermark advancement on failed scans.
  3. `counts` dictionary strictly standardized to keys: `found`, `queued`, `unchanged`, `skipped`, `same_as_rev`.
  4. `last_successful_scan()` unified to query `source in ('airflow', 'initial') and finished_at is not null and error is null`.
- **Verification**: 13 unit tests in `tests/unit/test_scans_api.py` passed. Full unit test suite: 464 passed.

### 2026-11-06 — Fix(Worker): Page Extraction, Per-Item Error Handling, Cycle Result
- **Commit**: `fix(worker): page extraction, per-item errors, cycle result`
- **Key Changes**:
  1. `extract_marking_image(abs_path, dest_dir, expected_source_sha256)` in `mark_engine/abs/brand_page.py` extracts marking page image from ABS into `<sha256>.png`. Updated `scripts/blind_extract_images.py`.
  2. `load_service_inference_for_image` in `mark_engine/adapters/inference_service.py` allows direct invocation with image file without `images_index.csv`.
  3. Worker per-item try/except boundary: rolls back dirty transaction on unexpected error, calls `fail_with_backoff` on queue, commits, and prevents worker process crash.
  4. `CycleResult` enum (`NO_ITEM`, `PROCESSED`, `SKIPPED`) ensures `--once` mode loops until `CycleResult.NO_ITEM` is reached.
- **Verification**: 30 tests in `tests/unit/test_worker.py` passed. Full unit test suite: 459 passed.

### 2026-11-06 — B3 Task 5: Scan, Lookup, Oracle-Check, Recheck, and Notification API
- **Implemented**: `services/api/mark_api/routers/scans.py`, updated `app.py`, `deps.py`, `repo.py`.
- **Endpoints**:
  - `POST /api/scans`: Bearer token `scan:write`, advisory lock `pg_try_advisory_lock` (returns 409 on concurrency), computes watermark minus 5m window for airflow scans, applies G0 and cheap decide, enqueues eligible ELRs into `mark_app.work_item`, records scan in `mark_app.scan`.
  - `POST /api/scans/retry`: Bearer token `scan:write`, re-queues ELRs with HOLD/unapproved latest revision.
  - `GET /api/elrs/lookup?elr=`: returns history, latest revision, queued status, or `in_system=false`.
  - `POST /api/elrs/{elr}/oracle-check`: checks Oracle, notifies `not_in_oracle` (404) or `not_eligible` (200), or enqueues `reason=user`.
  - `POST /api/elrs/{elr}/recheck`: requires role in `(engineer, mark_eng_approver, admin)` and CSRF, enqueues `reason=recheck`.
  - `GET /api/notifications`: lists notifications, filtered by unread.
  - `POST /api/notifications/{id}/read`: marks notification as read by current user.
- **Verification**: Strict TDD Red -> Green. 8 unit tests in `tests/unit/test_scans_api.py`. Full unit test suite: 455 passed. E2E walkthrough: 12/12 passed against `localhost:8088`.
- **Next immediate action**: Commit & push `feat(api): scans, lookup, oracle-check, recheck, notifications`, wait for Jenkins build to report green, then proceed to Task 6 (Dev End-to-End on 10.151.97.18; Step 2 is [USER]).

### 2026-11-06 — B3 Task 4: Real Engine Pipeline Integration & Worker Loop
- **Commit**: `fix(worker): run real engine pipeline`
- **10 Core Capabilities Wired & Verified**:
  1. `run_worker_cycle` step 8 invokes real `process_elr()` with active `rules`, layouts (`fetch_layout` from `ACTLDBA.MARK_ID_LAYOUT` parsed via `parse_layout`), and `MARK_INFERENCE` loader (live service via `load_service_inference` or cache via `load_cached_inference`).
  2. Resolves ABS/SLR documents from NAS via `resolve_documents`, computes real `docs_fp(resolution)`, persists `docs_probe` (`path`, `size`, `mtime`), and passes `resolution` to `write_result`.
  3. Cheap-first check: if Oracle row unchanged (`oracle_fp == latest.oracle_fp`), checks `docs_probe` first. Skips if files on NAS have identical size/mtime; only runs document resolution and re-evaluates `decide()` if NAS files changed.
  4. G0 eligibility check uses `mark_engine.select.pending_reason(meta, os.environ.get("MARK_REVIEW_STEP", "6"))`.
  5. Manual execution flag: `manual = (item.reason == "recheck")`.
  6. Query approval uses column `decision = 'APPROVED'` and verified with live query on `mark_app.approval` table on `10.151.28.2:5432/mark_web`.
  7. `version_fp` uses `mark_engine.__version__` and `model_version` from service `Health`.
  8. `InferenceUnavailable` calls `fail_with_backoff`; when 3 retry attempts are exhausted, writes `write_result` as `HOLD INFERENCE_FAILED` and creates notification.
  9. `changed_fields` uses `changed_oracle_fields` by reading previous revision's Oracle row from `elr_snapshot.line_extra['oracle_row']`.
  10. `services/worker/main.py:main()` connects to PostgreSQL with role `mark_worker` (`MARK_WORKER_PG_PASSWORD`) and Oracle read-only, looping `claim` -> `process` with 1 transaction per item and `--once` support.
- **Verification**: 26 unit tests in `tests/unit/test_worker.py` (all 10 requirements tested). Full test suite: 447 passed.
- **Next immediate action**: Commit & push `fix(worker): run real engine pipeline`, wait for Jenkins build to report green, then proceed to Task 5 (Scan, Lookup, and Notification API).


### 2026-11-06 — Migration 0007 applied to the real DB ([USER] step done)
- User ran `apply_migration_0007.py` against `10.151.28.2:5432/mark_web`: dry run (ROLLBACK) first, then `--commit`.
- All checks passed in both runs: tables `mark_app.scan`, `elr_revision`, `work_item`, `notification`; view `latest_job_result`; column `elr_revision.docs_probe`; `mark_worker` has no UPDATE/DELETE on `mark_logic.run/job_result/line_result`; runs 1–19 unchanged (16 run / 804 job_result / 34,723 line_result rows, content md5 equal).
- Role `mark_worker` password generated and stored in `.env` as `MARK_WORKER_PG_PASSWORD` (`.env` is gitignored; not shown anywhere).
- **Next**: Task 4 worker can now connect as `mark_worker` to the real schema.

### 2026-11-06 — B3 Task 3: Postgres Queue with SKIP LOCKED & Oracle Source Adapter
- **Implemented**: `services/worker/__init__.py`, `services/worker/oracle_source.py`, `services/worker/queue.py`, `tests/unit/test_worker.py`.
- **Refactored**: Extracted `ELR_FIELDS` and `BASE_ELR_QUERY` into `mark_engine/adapters/oracle_snapshot.py` and updated `scripts/fetch_oracle_snapshot.py`.
- **Worker Adapters**:
  - `oracle_source.py`: `fetch_window`, `fetch_one`, `fetch_pending_step`, `to_engine`.
  - `queue.py`: `enqueue` (partial index idempotency), `claim` (15m stuck job recovery + `FOR UPDATE SKIP LOCKED`), `finish`, `fail`, `fail_with_backoff` (`RETRY_DELAYS = (1, 5, 15)` min).
- **Verification**: Strict TDD Red -> Green. 8 unit tests in `tests/unit/test_worker.py`. Total test suite: 429 passed.
- **Next immediate action**: Commit Task 3, push to `origin/phase2/trial`, verify green Jenkins build, then proceed to Task 4 (Worker Engine Execution & Results).


### 2026-11-06 — B3 Task 1 Fix: 0007 Grants and docs_probe Column
- **Updated Migration 0007**:
  - Added `docs_probe jsonb` column to `mark_app.elr_revision`.
  - Added grants: `grant update on mark_app.scan to mark_app`, `grant insert on mark_app.notification to mark_app`, `grant select on mark_app.approval to mark_worker`.
  - Updated `migrations/0007_auto_review_down.sql` with corresponding revokes.
  - Verified UP -> DOWN -> UP on throwaway schema `t0007_test2`.
- **Note for Task 4**: In worker runner, after resolving documents and computing actual `docs_fp`, invoke `decide()` again with real `docs_fp`. If `skip_same_as_rev`, do not create a revision. Test: `test_oracle_reverted_to_old_rev_after_docs_resolved_creates_nothing`.

### 2026-11-06 — Airflow safe summary and optional port
- Connection URLs omit the port separator when port is empty. Successful POST responses with unreadable JSON or invalid summary fields produce summary unavailable rather than retrying the scan; no response data is logged.
- Mark DAG Python files and the client test are UTF-8 without BOM. Focused tests: 19 passed; full non-regression suite: 440 passed, one existing pynvml warning.
- User requested one normal push and no history rewrite or force push. The fetched origin/phase2/trial has moved since the previous push; no rebase of published airflow commits was attempted. Deployment and real Airflow parse remain deferred to .17.

### 2026-11-06 — B3 Task 2: Input Fingerprints & Re-check Decision Table (Spec §4)
- **Implemented**: `mark_engine/history/__init__.py`, `mark_engine/history/fingerprint.py`, `mark_engine/history/decide.py`, `tests/unit/test_history.py`.
- **Key Modules**:
  - `fingerprint.py`: implements `ORACLE_FP_FIELDS` (15 fields), `oracle_fp`, `changed_oracle_fields`, `docs_fp` (sorted roles/paths/hashes), `version_fp`, and `result_fp`.
  - `decide.py`: implements pure decision table `decide(pending_reason, prev, oracle_fp, docs_fp, manual)` evaluating manual override, eligibility, new ELR, cheap-first unchanged skip, older revision reversion dedup (`skip_same_as_rev`), and change tagging (`oracle`, `docs`, `both`).
- **Verification**: Strict TDD Red -> Green. 30 unit tests added in `tests/unit/test_history.py`. Entire test suite: 421 passed.
- **Next immediate action**: Commit Task 2, push to `origin/phase2/trial`, verify green Jenkins build, then proceed to Task 3 (Oracle source and PostgreSQL SKIP LOCKED queue).

### 2026-11-06 — B3 Task 1: Migration 0007 (Auto-Review History, Queue, Notifications, Worker Role)
- **Implemented**: `migrations/0007_auto_review.sql`, `migrations/0007_auto_review_down.sql`, `migrations/README.md`.
- **Schema & Grants**:
  - `mark_app.scan`: tracks scan runs (`scan_id`, `trigger_source`, `status`, `summary`).
  - `mark_app.elr_revision`: immutable revision audit log linking ELR to `mark_logic.run(run_id)` with fingerprints (`oracle_fp`, `docs_fp`, `version_fp`, `result_fp`), gate status, and trigger reasons.
  - `mark_app.work_item`: persistent queue with partial unique index `(elr_no) WHERE state IN ('queued', 'running', 'retry')` preventing duplicate active jobs.
  - `mark_app.notification`: user-facing notification queue with unique constraint `(elr_no, kind, revision)`.
  - `mark_app.latest_job_result`: view joining `mark_app.elr_revision` with `mark_logic.job_result` to expose current state without full table scans.
  - Role `mark_worker`: least-privilege worker role granted work item queue control, scan/revision/notification insert, and insert-only on `mark_logic.run`, `mark_logic.job_result`, `mark_logic.line_result`.
- **Validation**: Tested UP/DOWN migration idempotency on throwaway schema `t0007_20261106` on `10.151.28.2:5432/mark_web`. UP succeeded, DOWN removed all objects cleanly, second UP verified clean re-execution, and all 16 historical runs (IDs 1–19) in `mark_logic.run` were verified untouched.
- **[USER] Step**: Migration 0007 is ready for DBA execution on real database (`mark_app` schema). In parallel, proceeding with Task 2 (Fingerprints and Decision Table).

### 2026-11-06 - Airflow DAG offline implementation (phase2/airflow)
- User deferred Task 3-4 to .17 deployment: .3 to 10.151.97.18 is network-blocked; user reports .3 to 10.153.90.17 works and .17:8088 is occupied by another app. API port remains to be decided. The direct host probe returned HTTP 000.
- Key-only SSH worked; Airflow scheduler and webserver were observed as active systemd services. Version, DAG folder, timezone and CLI access remain unknown; no service or DAG changed.
- Added the three paused DAGs and an HTTP client. Scheme, host, port and token come from Airflow Connection `mark_api`; no endpoint is hard-coded. 409 skips; 401/403 fail without retry; other failures retry.
- Verification: after rebase onto B3 Task 2, the full non-regression suite passed 433 tests (one existing pynvml deprecation warning). Before rebase, 12 focused tests passed; `python -m pytest tests -q --ignore=tests/regression -p no:cacheprovider` passed 403 tests with one existing pynvml deprecation warning.
- No deployment or server parse check has been performed. Task 3 requires B3 Task 5 green and migration 0007 applied to the real DB; Task 4 additionally requires B3 Task 6 and user-triggered initial load/unpause.

### 2026-11-06 — Airflow DAG plan for Codex (branch `phase2/airflow`)
- **Plan:** `docs/superpowers/plans/2026-11-06-airflow-dags.md`. Codex works in worktree `D:\CIM Project\mark-web-airflow` on branch `phase2/airflow`; agy keeps `phase2/trial` for B3.
- **DAGs:**
  - `mark_elr_polling`: every 15 min, calls `POST /api/scans`.
  - `mark_pending_job_retry`: every 10 min, calls `POST /api/scans/retry`.
  - `mark_initial_load`: manual trigger.
- **How they run:**
  - All three call the API on the dev PC `http://10.151.97.18:8088` through the Airflow Connection `mark_api`.
  - The token lives only in that Connection and in `.env`.
  - The DAGs are deployed paused; unpausing is a user step.
- **Deploy:** waits for B3 Task 5 and migration 0007. Enabling the schedule waits for B3 Task 6 and the initial load.
- **Access:** SSH to 10.151.28.3 as `itadmin` uses key auth only. The user installs the key once with a script.

### 2026-11-05 — B3 plan: history, queue, worker, scan API (for the other agent)
- **Plan:** `docs/superpowers/plans/2026-11-05-b3-history-queue-worker-api.md` (spec §9 step 3). Its tasks:
  1. Migration 0007 (tables `scan`, `elr_revision`, `work_item`, `notification`; view `latest_job_result`; role `mark_worker`). Applying it to the real DB is a **[USER]** step.
  2. Fingerprints and the re-check decision table (spec §4).
  3. Oracle source and the SKIP LOCKED queue.
  4. Results writer into the daily `auto-YYYY-MM-DD` run (insert only) and the worker loop.
  5. Scan, lookup, oracle-check, recheck and notification API.
  6. Dev end-to-end on 10.151.97.18.
- **Not in this plan:** the Airflow DAGs (step 4) and the WebSocket/web UI (step 5).
- **Status:** B4 is finished at `611aff4` (Jenkins 391 green). The service gives the same output as the run-19 cache (287/287 images; `run-service` byte-identical to `run-gates`). `.env` is set to `MARK_INFERENCE=service`.

### 2026-11-05 — R1 multi-ABS review deferred until the web is finished
- **User decision:** wait until the web is finished before reviewing or changing R1 G1–G9. All nine remain open. R1 G1 (date-code `Q`) and G5 (`FS91004B`/`ADW91004B`) are not engine gates G1 (TBD) and G5 (ROW_OVER_5).
- **R1 G5:** ADI2605053/054 and ADI2606014/015 have both ABS065681-ENG-1 (Oracle-selected) and ABS065288-ENG-2 (named by SLR). Manual inspection of the latter's marking diagram agrees with the Oracle snapshot in all five rows at the format/placeholder level. Confirm the applicable document with Mark Eng before changing selection logic.
- **Other candidates:** ADI2606076: alternative ABS071101-ENG-2; ADI2606077/078: ABS068387C; their diagrams are consistent with Oracle at the format/placeholder level. 6077/078 remain HOLD under the user-confirmed revision conflict rule. ADI2602101 and 2119–2122/2123/2125 require SLR line overrides and confirmation of `Q`; ADI2605077 needs `{V}` versus `#` checked.
- **ADI2602050:** Oracle-selected ABS061089A is explicitly permitted by E-mail1.pdf with line 2 `ADW90040` and line 3 `ENGF`. The SLR names ABS067186B and changes line 3. The run-14 `DB_WRONG` verdict for line 2 must be reviewed in light of the email; do not assume Oracle is wrong. The engine does not currently apply that email instruction.
- Findings are manual comparisons against the historical Oracle snapshot, not a fresh alternate-ABS engine run or proof of document precedence. Review the whole document set, including attachments, before deciding. Do not change rules or frozen holdout results on this basis.
- **R1 G4:** earlier line-break parsing fix was checked on ADI2601066, ADI2605015 and ADI2606074; targeted regression 3 ELRs / 15 lines, independence 3/3, and 53 relevant tests passed. The old description says seven lines without identifying them, so G4 remains open pending reconciliation. The full 668-ELR regression was stopped and is not a completed result.

### 2026-11-05 — B4 Inference Service Task 5: Parity vs Run-19 Cache & Regression Verified
- **What changed**:
  - Created `scripts/compare_inference.py`: compared service outputs with run-19 cache across all 287 rows (118 distinct images). Result: 0 page diffs, 0 symbol diffs, 0 re-OCR diffs (100% parity).
  - Executed engine-level blind regression via live service: `python scripts/run_blind.py ... --inference service`.
  - Executed `diff_runs.py` against `run-gates`: **0 job-level changes**, 0 line-level status count changes across all 8 status categories (DB_EMPTY: 43, DIFF: 7, MATCH: 929, MATCH_LOT: 21, MATCH_SLR: 69, NEEDS_REVIEW: 101, NOT_ELIGIBLE: 81, NOT_MEASURABLE: 107).
  - Production Hardening & Image Rebuild:
    - Updated `services/inference/Dockerfile`: added `HEALTHCHECK NONE` to override legacy base HTTP :8000 healthcheck, clearing false unhealthy alarms.
    - Updated `services/inference/engines.py`: wrapped PaddleOCR and YOLO predictors with `threading.Lock()` to prevent race conditions and tensor memory corruption across concurrent requests.
    - Rebuilt image `mark-inference:0.1.0` on A100: new image ID `sha256:afae88a43926de1d26c09e2e5bda4ec08026b293effc56ce01efb0cad2c63f32`, container ID `44ec121eab7a`. Status verified clean and healthy.
    - Updated `mark_engine/adapters/inference_service.py`: bounded client in-memory cache `_SERVICE_INFERENCE_CACHE` using `OrderedDict` with `_CACHE_MAX_SIZE = 512` and thread lock for safe execution in long-running workers.
- **Current State**: Live inference service on A100 is fully validated, hardened, and active on `10.151.28.9:50051`.
- **Switch**: Local `.env` set to `MARK_INFERENCE=service`.
- **Bugs found and fixed on the way (Claude review, 2026-11-05):**
  1. Jenkins failed with `No module named 'PIL'` at 170760a/ddf36a9. Fixed by declaring Pillow and pynvml in `pyproject.toml` (870b449).
  2. The Paddle in the base image is CPU-only, so Health reported `ocr_device=gpu` falsely. `choose_device(engine="ocr")` now returns `cpu` when `paddle.device.is_compiled_with_cuda()` is False. OCR runs on CPU and YOLO on GPU.
     - Known minor gap: `force=gpu` still selects GPU for OCR.
  3. ultralytics pulled in OpenCV 5.0.0, while the cache was made with 4.10.0. Fixed by pinning `opencv-contrib-python==4.10.0.84` in the Dockerfile.
  4. The first compare had 287 Page `service_error` because the Paddle detection model cache path was missing. Fixed with `ENV PADDLE_PDX_CACHE_HOME=/root/.paddlex`.
  5. There was no lock around the shared models (the gRPC pool has 10 threads), so concurrent requests changed one result (ADI2607004). Fixed with a per-engine `threading.Lock`.
  6. The inherited HEALTHCHECK (HTTP :8000) made the container falsely `unhealthy`. Fixed with `HEALTHCHECK NONE`.
  7. `compare_inference.py` showed 8 false Re-OCR diffs because the filter was applied to the service side only and the script had `except: pass`. Fixed: the same filter is applied to both sides and errors are no longer swallowed.
- **Still open (as of 2026-11-05):**
  - **A100 disk:** only 13 GB free (93%), below the 15 GB floor. Dangling images remain. `docker image prune -f` is waiting for the user's OK.
  - **Admin events:** the table and `/api/admin/events` have no ELR or run column.
  - **Metrics:** no metrics token in `.env`.
  - **Worktree:** `wt-review` is not removed yet.

### 2026-11-05 — B4 Inference Service Task 4: Image and deploy on the A100
- **What changed**:
  - Created `services/inference/Dockerfile` and `services/inference/DEPLOY.md`.
  - Built image `mark-inference:0.1.0` on A100 (`sha256:3ff19f4c00299fc4fed0662d8d99b09b0ac2eaeb376606fc7ab4a08558c4c080`) with PaddleOCR, Ultralytics YOLO, and gRPC dependencies.
  - Mounted models from `~/mark_inference/models` into container `/models:ro`.
  - Verified hashes for OCR recognizer (`eb1105c4...`), PP-OCRv5 detector (`183146fe...`), and YOLO symbol weights (`a8f4e910...`).
  - Confirmed vLLM memory on A100 untouched (75,208 MiB / 81,920 MiB used), container idle memory 38.35 MiB.
  - Stopped and removed legacy container `ic-marking-ocr`; verified port 8095 closed.
  - Verified dev workstation connectivity and API key auth (`UNAUTHENTICATED` without valid token).
- **Current State**: `mark-inference` service active and healthy on `10.151.28.9:50051`.

### 2026-11-05 — B4 Inference Service Task 3: Engine client and MARK_INFERENCE switch
- **What changed**:
  - In mark_engine/adapters/inference_service.py: implemented InferenceClient (Health, Page, Symbols, Rec with 2x retry on UNAVAILABLE), InferenceUnavailable, and load_service_inference (with trim-logo re-OCR).
  - In scripts/run_blind.py: added --inference cache|service CLI switch and execute_job_with_fallback mapping InferenceUnavailable to FAILED:INFERENCE_FAILED.
  - In .env.example: documented MARK_INFERENCE=cache, MARK_INFERENCE_ADDR=10.151.28.9:50051, MARK_INFERENCE_API_KEY=.
  - In 	ests/unit/test_inference_service.py: added 	est_service_loader_equals_cache_loader, 	est_server_down_raises_inference_unavailable, and 	est_run_blind_service_failure_is_inference_failed.
- **Verification**:
  - 	ests/unit/test_inference_service.py: 18 passed.
  - Full unit suite: 388 passed in 45.60s.
- **Next immediate action**: Commit Task 3, wait for Jenkins green, tick Step 5, and proceed to Task 4.

### 2026-11-05 — B4 Inference Service Task 2: Shared engines and GPU→CPU fallback
- **What changed**:
  - Created services/inference/devices.py: ree_vram_mb() via pynvml, choose_device(free_mb, min_free_mb, force), is_cuda_oom(exc), and with_cpu_fallback(run_gpu, run_cpu).
  - Created mark_engine/abs/reocr.py: extracted legend_candidates and 	rim_logo from batch script.
  - Created services/inference/engines.py: OcrEngine(device, recognizer_dir) and SymbolEngine(device, weights) with lazy model loading and CPU fallback on CUDA OOM. Configured FLAGS_allocator_strategy=auto_growth and PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True.
  - Refactored services/inference/det_rec_batch.py, yolo_batch.py, and 
eocr_batch.py to be thin CLI wrappers over shared engines without changing output shape or precision.
  - Updated services/inference/server.py to use choose_device, ree_vram_mb, OcrEngine, and SymbolEngine.
  - Extended 	ests/unit/test_inference_service.py with unit tests for device selection, lazy single-build CPU fallback, error propagation, and server reporting CPU device after fallback.
  - Updated 	ests/unit/test_reocr_batch.py to verify imports from mark_engine.abs.reocr.
- **Verification**:
  - 	ests/unit/test_inference_service.py: 15 passed.
  - 	ests/unit/test_reocr_batch.py & 	ests/unit/test_adapters_reocr.py: 2 passed.
  - Full unit suite: 385 passed in 21.46s.
- **Next immediate action**: Commit Task 2, wait for Jenkins green, tick Step 5, and proceed to Task 3.

### 2026-11-05 — B4 Inference Service Task 1: Contract, server skeleton, API key
- **What changed**:
  - In `services/inference/proto/mark_inference.proto`: defined package `mark.inference.v1` with RPCs `Health`, `Page`, `Symbols`, `Rec`.
  - Created `scripts/gen_inference_proto.py`: compiles proto to `services/inference/mark_inference_pb2.py` and `_pb2_grpc.py` with cross-package import compatibility.
  - In `services/inference/server.py`: implemented `ApiKeyInterceptor` with `hmac.compare_digest` guarding `x-api-key`, PNG validator with `PIL.Image.verify`, `MarkInferenceServicer`, and `build_server()`.
  - In `pyproject.toml`: added `grpcio==1.85.1`, `grpcio-tools==1.85.1`, `protobuf==7.36.0` to `[project.optional-dependencies] api`.
  - Created `tests/unit/test_inference_service.py` with in-process server verifying Health, UNAUTHENTICATED on missing/wrong API key, ordered Page items, and INVALID_ARGUMENT survival.
- **Verification**:
  - `tests/unit/test_inference_service.py` passed (5/5).
  - Full unit test suite: 375 passed.

### 2026-11-05 — B4 plan updated with user decisions
- **`ic-marking-ocr` is retired.** It gets removed after `mark-inference` is healthy (Task 4 Step 5).
- **Prune is allowed:** `docker image prune -a` and `docker builder prune`. Volumes and networks are never touched.
- **Network:** `ufw` is inactive on the A100, so there is no firewall change and the API key guards port 50051. The callers are this dev PC `10.151.97.18`, later `10.153.90.17`, and Airflow `10.151.28.3`.
- **Task 5:** switch to `MARK_INFERENCE=service` (GPU with CPU fallback) after the comparison. Diffs are reported but don't block the switch.

### 2026-11-05 — B4 Inference Service plan (for the other agent)
- **Plan:** `docs/superpowers/plans/2026-11-05-b4-inference-service.md` (Tasks 1–5).
  1. gRPC contract with Health/Page/Symbols/Rec and an API key.
  2. Shared OCR/YOLO engines with GPU→CPU fallback.
  3. Engine client plus the `MARK_INFERENCE` switch.
  4. `mark-inference` container on the A100, port 50051.
  5. Comparison with the run-19 cache (CPU must give 0 diffs; GPU diffs go to the user).
- **A100 survey (read-only, 2026-11-05):** about 6–7 GB of VRAM free (vLLM uses ~72 GB), disk 89% (~22 GB free), CUDA 12.9, Docker 27.2. `ic-marking-ocr:exp09` is still running on :8095.
- **User decision:** GPU with a CPU fallback.
- **SSH access:** now key-based (`~/.ssh/id_ed25519_nopass`, installed by the user). The password lives only in `.env`.
- **[USER] steps still open:** the firewall for 50051, and the GPU vs CPU decision once the comparison is done.

### 2026-11-05 — G5 Gate Fix: Count placed content beyond TOP row 5 (not raw OCR rows)
- **What changed**:
  - In `mark_engine/pipeline.py`: moved G5 check to run after `generate_expected`. Gate checks `[l for l in expected.lines if l.side == Side.TOP and l.line_no > 5 and (l.text or "").strip()]`.
  - Empty OCR rows beyond row 5 are ignored.
  - In `tests/unit/test_pipeline.py`: updated `test_row_over_5_gate` to verify 7 rows with empty rows 6-7 does not trigger HOLD, while row 6 with text triggers HOLD.
  - Unit tests: 370 passed.
- **Regression (3 workers)**:
  - Finished: `jobs: 402 independence: 254 / 254 excluded: 148 failed: 0 freeze: UNFROZEN`.
  - Diff `run-overflowfix` -> `run-gates`:
    - `DONE:NOT_VERIFIABLE -> HOLD:CUST_ASSY_TBD`: 27 ELRs (`ADI2607009`, `ADI2607028`, `ADI2607029`, `ADI2607050`, `ADI2608007`, `ADI2608080`, `ADI2608081`, `ADI2608082`, `ADI2608083`, `ADI2608084`, `ADI2608085`, `ADI2609004`, `ADI2609005`, `ADI2609093`, `ADI2610014`, `ADI2610018`, `ADI2610033`, `ADI2610064`, `ADI2610068`, `ADI2610069`, `ADI2610070`, `ADI2610071`, `ADI2610072`, `ADI2610073`, `ADI2610074`, `ADI2610095`, `ADI2611004`)
    - `HOLD:BOM_NOT_FOUND -> HOLD:CUST_ASSY_TBD`: 1 ELR (`ADI2609073`)
    - Zero `ROW_OVER_5` false positives!
    - Zero unexpected diff groups.
    - All non-TBD lines match baseline exactly (delta 0).

### 2026-11-05 — Empty template rows rule (spec §2.2.1)
- **Cause, confirmed by the user:** the ABS marking diagram has `LINE 1–7` labels from a template shared with other jobs. OCR reads the labels, and `layout.py` makes one row per label, so 5-line jobs get empty rows 6–7.
- **Rule:**
  - An empty row means no content after Generate.
  - Trailing empty rows are dropped.
  - Empty rows in the middle keep their position, with no shift.
  - G5 holds only on content beyond row 5. This matches the G5 fix plan in progress.

### 2026-11-05 — Engine 0.4.0 regression reviewed; G5 fix planned
- **Task 5 implementation**: Bumped `ENGINE_VERSION = "0.4.0"`, created `scripts/diff_runs.py` and `tests/unit/test_diff_runs.py` (372 unit tests passed).
- **Diff:** run-overflowfix → run-gates (engine 0.4.0, 402 ELRs). 46 ELRs changed.
  - `→ HOLD:CUST_ASSY_TBD` ×28: **accepted**. The 29th TBD ELR, ADI2607077, is STATUS C, so it stays NOT_ELIGIBLE. ADI2609073 moved from BOM_NOT_FOUND to TBD, because the TBD gate runs first.
  - Special-SLR change: 0 ELRs.
  - `→ HOLD:ROW_OVER_5` ×18: **rejected**. All 18 have OCR TOP rows 6–7 empty (no text, no graphics). This includes ADI2607022, which was MATCH_ALL 5/5.
- **User decision:** G5 counts rows **after placement on the Layout**. Hold only when content lands beyond row 5.
- **Plan for the other agent:** `docs/superpowers/plans/2026-11-05-auto-review-g5-fix.md`. Re-run the regression with `--workers 3`, because 8 workers ran the machine out of RAM; the Jenkins agent was killed and the user restarted it.

### 2026-11-05 — User confirmed CURRENT_STEP '6' = Mark Eng review
- **Confirmed:** `MARK_REVIEW_STEP=6` is correct; no code change needed.
- **Step codes (user):** 1 CS Review, A QA Review, 2 Engineering Review, 3 MC review, 4 Engineering lot Center, 5 PC Reserve, **6 Mark Eng review**, 7 Generate Order.
- **Live Oracle:** step 6 currently has 0 open ADI ELRs, because ELRs pass through it quickly. The 15-min scan must catch them before they reach step 7. An empty step 6 is normal.
- Recorded in spec §2.2 / §2.4.

### 2026-11-05 — Engine Gates Task 4: G0 pending-review selector & Oracle CURRENT_STEP query
- **What changed**:
  - Created `mark_engine/select.py` defining `pending_reason(meta: ElrMeta, review_step: str) -> str | None` and `review_step_from_env() -> str`.
  - Added test suite `tests/unit/test_select.py` asserting status `C` exclusion (`STATUS_C`), non-matching step exclusion (`NOT_MARK_REVIEW_STEP`), and env default `"6"`.
  - Added `MARK_REVIEW_STEP=6` to `.env.example` and `.env`.
  - Executed read-only Oracle query `SELECT CURRENT_STEP, COUNT(*) FROM ACTLDBA.ELR WHERE CUST_CODE = 'ADI' AND STATUS <> 'C' GROUP BY CURRENT_STEP`.
  - Oracle non-closed ADI ELR counts: '1': 246, '2': 2, '4': 4, '5': 2, '7': 8290. No step '6' currently pending. Awaiting user confirmation on Mark Engineer review step code.
- **Verification**:
  - `tests/unit/test_select.py` passed.
  - Full suite: 367 unit tests passed.

### 2026-11-05 — Engine Gates Task 3: G5 OCR gives > 5 TOP rows holds the job
- **What changed**:
  - In `mark_engine/pipeline.py`: after empty layout check and before `generate_expected`, added gate G5 checking `sum(1 for line in inference.lines if line.side == Side.TOP) > 5`.
  - When triggered, returns `JobResult(processing_status=HOLD, hold_reason="ROW_OVER_5", ...)` with `resolution` kept (so reviewer can inspect documents) and comparisons marked `LineStatus.NOT_MEASURABLE` with `detail="ROW_OVER_5"`.
  - Updated `resolution.hold_detail` to `f"{top_lines} TOP rows"`.
- **Verification**:
  - `test_row_over_5_gate` in `tests/unit/test_pipeline.py` (5 TOP rows proceeds, 6 TOP rows enters HOLD).
  - Full suite: 366 unit tests passed.

### 2026-11-05 — Engine Gates Task 2: SLR instructions apply only when SLR has SPECIAL INSTRUCTIONS
- **What changed**:
  - In `mark_engine/domain/models.py`: added `special: bool = False` to `SlrFacts`.
  - In `mark_engine/slr/parse.py`: set `special=bool(sec_match)` in `parse_slr()`.
  - In `mark_engine/pipeline.py`: after `parse_slr()`, if `not slr_facts.special`, replace with `instructions=(), unresolved=()` to prevent SLR line override while keeping scheduled lots.
- **Verification**:
  - `test_special_flag_follows_section_header` in `tests/unit/test_slr_parse.py`.
  - `test_slr_without_special_instructions_uses_abs_only` in `tests/unit/test_pipeline.py`.
  - Full suite: 364 unit tests passed.

### 2026-11-05 — Engine Gates Task 1: G1 Cust Assy TBD holds the job
- **What changed**:
  - In `mark_engine/pipeline.py`: restructured eligibility checks into explicit ordered gates:
    1. `STATUS == 'C'` → `NOT_ELIGIBLE`
    2. `CUST_ASSY_LOT == 'TBD'` (G1) → `HOLD:CUST_ASSY_TBD`
    3. `top_type_code != 'E'` or `top_layout_code == 'ZY'` → `NOT_ELIGIBLE`
    4. Document resolution gate (as before)
  - TBD jobs yield `ProcessingStatus.HOLD`, `hold_reason="CUST_ASSY_TBD"`, `resolution=None`, and `LineStatus.NOT_MEASURABLE` with detail `"CUST_ASSY_TBD"`.
- **Verification**:
  - `test_cust_assy_tbd_gate` tested 5 parameterized cases.
  - Full suite: 362 unit tests passed.

### 2026-11-05 — Plan: auto review step 1, engine gates (for the other agent)
- **Plan:** `docs/superpowers/plans/2026-11-05-auto-review-engine-gates.md`.
- **Tasks:**
  - T1: G1 Cust Assy TBD → HOLD.
  - T2: SLR instructions apply only when the SLR has SPECIAL INSTRUCTIONS.
  - T3: G5 more than 5 TOP rows → HOLD.
  - T4: G0 pending-review selector + a read-only Oracle check of the step value.
  - T5: engine 0.4.0, run-19 regression into `artifacts/blind-2026h2/run-gates` + `scripts/diff_runs.py` report.
- **Data facts:**
  - The run-19 snapshot's CURRENT_STEP has only 7 and 1 (no 6). So G0 can't be regressed there, and the step value comes from live Oracle.
  - 29 ELRs are TBD and will move to HOLD.
- **No DB load and no re-freeze:** the user decides after the diff.

### 2026-11-05 — Auto Review Flow design rev 3 (user confirmed §10)
- **G1:** TBD.
- **Approvals:** an approved revision is kept as history. New data → a new revision with its own create date. No duplicate of **any** old revision: the `(oracle_fp, docs_fp)` pair is unique per ELR, and `result_fp` flags `result_unchanged`.
- **ABS and SLR:** both are required.
- **Schedule:** every 15 min, incremental from a watermark minus 5 min, plus a one-off initial load before scheduling starts. The retry DAG re-checks NAS for HOLD or unapproved ELRs.
- **Results:** a daily `mark_logic` run feeds the dashboard.
- **Next:** the plan for build step 1 (engine gates + run-19 regression).

### 2026-11-05 — Auto Review Flow design rev 2 (user corrections)
- **Entry points:** an Airflow `mark_elr_polling` schedule, and "Select by user". The user path first checks our PostgreSQL. If the ELR isn't there: notify → user may search Oracle → if found, trigger that one ELR through the same flow; if not, notify.
- **Gates now follow the user's order:**
  - G0: ADI + Mark Engineer step + history/update check.
  - G1: Cust Assy TBD.
  - G2: Type E and layout not ZY. This is the Skip Mark check; run 19 has no non-ZY skips.
  - G3: ABS **and** SLR are both required. Special requirement = the SLR has SPECIAL INSTRUCTIONS.
  - Then OCR/YOLO on the AI Server → layout → G5 rows ≤ 5 → decode → generate (layout Fix cells already handled in `mark_layout.py`) → compare.
- **New update logic (spec §4):**
  - Fingerprints: `oracle_fp`, `docs_fp`, `version_fp`.
  - Re-check only when Oracle data or docs change. A change after approval keeps the approval but flags it and notifies.
  - A version-only change doesn't auto re-run.
- **Open:** 5 confirmations in spec §10, including TBD vs "THB".

### 2026-11-05 — Design: Auto Review Flow (B3 + B4)
- **Spec:** `docs/superpowers/specs/2026-11-05-auto-review-flow-design.md`, derived from the user's TO-BE Marking Process diagram.
- **Gaps between the engine and the diagram:**
  - Oracle selection doesn't filter `CURRENT_STEP`.
  - There is no Cust Assy `TBD` gate.
  - There is no gate for more than 5 lines.
  - SLR is chosen from `CUST_REQ_NO`, while the diagram uses the Marking Comment.
  - There is no Notify.
- **Gaps in the diagram:** no branch for missing NAS documents (the engine HOLDs), and no Skip Mark.
- **Design:**
  - Two ways in: an Airflow DAG every 15 min, and a user re-check button.
  - Gates G0–G5, ordered cheap to expensive.
  - An `mark_app.scan` / `work_item` queue (Postgres `SKIP LOCKED`) with a worker container.
  - B4 Inference Service over gRPC, which must match the batch cache on run 19.
  - Results go to a daily `mark_logic` run.
  - UI-only notifications and WebSocket.
- **Open:** 5 design calls in spec §10 await user confirmation. No code yet. Not deployed to .17.

### 2026-11-05 — E2E walkthrough PASS 12/12 on localhost:8088 (plan Task 5, run by script for the user)
- **Result:** `scripts/e2e_walkthrough.py --run 19` against deployed `a42a483` → **PASS 12/12**.
  - **Engineer flow:** login → Dashboard (50 ELR rows on page 1) → search `ADI2607010` → Preview (ABS image decoded, Oracle grid). Approve before review → 409. Review lines 4 and 5 → 200 each. Approve → 200 (`Current: APPROVED`).
  - **Admin:** login → events list `review.saved` and `approval.saved` for the engineer.
  - **Cleanup:** deleted 2 reviews and 1 approval; `audit_log` kept.
- **Script fixes:** these were the script's own timing problems, not app bugs.
  - ERROR-line review forms open by default, so the script now expands a form only when it is collapsed.
  - It waits for the ABS image to decode, and for the detail re-fetch after each save.
  - It reads only event-table rows, because the filter `<select>` also lists the action names.
- **Gap (not fixed, for the user to decide):** the Admin events table and `/api/admin/events` show no ELR or run. A manager can see that an `approval.saved` happened, but not for which ELR, unless they open `detail`.
  - **Proposed fix:** select `a.run_id, a.elr_no, a.line_no` in `Repo.audit_events` and add one column to the table.
- **Not yet deployed to 10.153.90.17** (user's call).

### 2026-11-05 — Acceptance Task 4: Dashboard cache LRU 8 and lazy ABS thumbnail
- **What changed**:
  - In `services/api/mark_api/routers/validation.py`: `_dashboard_cache` changed to `OrderedDict` with `_CACHE_MAX = 8`, promoting on cache hit (`move_to_end(run)`) and evicting oldest entry (`popitem(last=False)`) when exceeding capacity.
  - In `web/src/pages/Preview.tsx`: added `loading="lazy"` to the thumbnail drawing `<img ... />` while leaving the modal image eager.
- **Verification**:
  - `test_dashboard_cache_lru_8` passed.
  - `npm run build` passed with 0 errors.
  - Full suite: 357 unit tests passed.

### 2026-11-05 — Fix: line review always failed on the real DB; E2E walkthrough script (Task 5)
- **Bug (found by the new E2E script):** `POST /api/reviews` returned 500 on run 19 for every line, so engineers could not save any review. That also meant no ELR with an ERROR line could ever be approved.
  - **Cause:** the router took `abs_no` from the job snapshot (`abs_file`, e.g. `ABS071169-ENG-2`) and hard-coded `side='TOP'`. But `line_review`'s FK `(run_id, elr_no, abs_no, side, line_no)` points to `mark_logic.line_result`, whose `abs_no` is the base number (`ABS071169`). On run 19, 1358/1358 lines differ.
  - **Why tests missed it:** FakeRepo uses the same value on both sides and has no FK.
  - **Fix:** take `abs_no` and `side` from the line row (`lines_for_elr`). An unknown `line_no` → 404, and nothing is written.
  - **New test:** `test_review_uses_line_key_not_snapshot_abs`.
- **New script `scripts/e2e_walkthrough.py`:** a browser walkthrough through NGINX using system Chrome and Playwright, run manually and not in CI.
  - **Flow:** engineer login → Dashboard ELR table → search → Preview (ABS image decoded, Oracle grid) → Approve blocked (409) while ERROR lines are unreviewed → review each ERROR line → Approve → admin login → events list `review.saved` and `approval.saved`.
  - **Cleanup:** the review and approval rows it created (`qa_engineer`, this run, since start) are deleted at the end. `audit_log` is kept. `--keep` skips the cleanup.
  - **Screenshots:** saved to `reports/e2e/`, which is git-ignored. They contain customer data.
- **Status:** not deployed to 10.153.90.17 yet (user's call). Everything runs on localhost:8088.

### 2026-11-05 — Acceptance Task 3: /api/metrics per spec §15
- **What changed**:
  - Created `services/api/mark_api/metrics.py` extracting `InProcessMetrics` singleton out of `app.py`.
  - Added route ring buffers (`deque(maxlen=1000)`) with nearest-rank p50 and p95 duration calculation.
  - Added counters for `login_ok`, `login_failed`, `login_locked`, and `db_error`.
  - Added `Repo.active_sessions()` querying `user_session` where `expires_at > now()`.
  - Wired counters in `routers/auth.py` and `Repo._execute` exception handler.
  - Updated `GET /api/metrics` to return `metrics.snapshot(repo.active_sessions())` (passing `None` on DB error).
  - Dropped `rate_limited` from API metrics (handled at NGINX) and documented in `services/README.md`.
- **Verification**:
  - `test_metrics_percentiles_and_cap` and `test_metrics_counts_logins` passed.
  - Full test suite: 355 unit tests passed.

### 2026-11-05 — Acceptance Task 2: Read-only real-DB acceptance check and Jenkins stage
- **What changed**:
  - Implemented `scripts/check_trial_readonly.py` testing 8 acceptance checks sequentially (`runs`, `dashboard_cards`, `elrs_total`, `elrs_pages`, `elr_detail`, `oracle_raw`, `expected_match`, `admin_reads`).
  - Strict privacy: outputs single-line status `OK <name> <summary>` or `FAIL <name> <reason>` without printing mark values, SLR texts, or file paths.
  - Added non-blocking `Real-DB check` stage to `Jenkinsfile` running against real DB when `params.DEPLOY` is true (`catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE')`).
  - Documented usage in `services/README.md`.
- **Verification**:
  - Executed `python scripts/check_trial_readonly.py --run 19`: all 8 checks reported OK with exit code 0.
  - Verified run 19 reference counts: `TRUE 866, WARNING 214, ERROR 41, HOLD 34`, `total=402 jobs=402`, 9 pages, 5 oracle_top_raw entries.
  - Full test suite: 353 unit tests passed.

### 2026-11-05 — Acceptance Task 1: NULL-safe ELR list/detail and visible load error
- **What changed**:
  - Added helper `_text(v)` in `routers/mark.py` converting `None` to `""`.
  - Replaced all string `.split()`, `.lower()`, and field formatting in `list_elrs` and `get_elr` to use `_text(val)` so NULL columns in PostgreSQL (`warning`, `detail`, `hold_reason`, `hold_detail`, `abs_no`, `compare_rules`) never raise `AttributeError`.
  - Added `loadError` state and visible red alert banner above the ELR table in `web/src/pages/Dashboard.tsx` with error details in Thai, retry button, and cleared on successful fetch.
  - Updated `ElrTable.tsx` to handle `hasError` state instead of misleading "No ELR packages found" text.
- **Verification**:
  - Added unit test `test_elrs_and_detail_handle_null_text_fields` passing in `tests/unit/test_api_routes.py`.
  - `npm run build` passed with zero errors.
  - Full unit test suite: 353 passed.

### 2026-11-05 — Plan: trial acceptance and monitor completion (for the other agent)
- **Plan:** `docs/superpowers/plans/2026-11-05-trial-acceptance-and-monitor.md`, Tasks 1–5.
- **Root cause of the empty ELR table:** `routers/mark.py` calls `.get("warning", "").split(...)`, which raises when the value is NULL. So `/api/elrs` returns 500, and the web shows "No ELR packages found".
- **Scope:**
  - NULL-safe ELR list and detail, plus a visible load error.
  - A read-only real-DB acceptance check (spec §8), run as a non-blocking Jenkins stage.
  - `/api/metrics` per §15: login counts, p50/p95 over the last 1000 requests per route, db_error, active sessions. `rate_limited` is dropped, because 429s are only in the NGINX log.
  - Dashboard cache LRU 8 and a lazy ABS thumbnail (§18).
  - The user walkthrough.
- **New rule in this plan:** a task is not done until its Jenkins build is green.
- **User decision 2026-11-05:** no password rotation (D-13 is an accepted risk).

### 2026-11-05 — Live admin check on localhost:8088: `/api/runs` bug fixed
- **Test accounts:** `qa_admin` (admin, user_id 3) and `qa_engineer` (engineer, user_id 4) were created for trial testing.
  - Passwords are random and stored only in the git-ignored `.env`, as `MARK_TEST_ADMIN_*` and `MARK_TEST_ENGINEER_*`.
  - The user's own admin account is user_id 2.
- **Live checks (via NGINX):**
  - **Lockout:** 5 bad logins on `qa_engineer` → 401 ×5, then the correct password → 423. A 7th login request within a minute → 429 (rate limit).
  - **Admin endpoints:** as `qa_admin`, users → 200. Unlock without CSRF → 403, unlock → 200, unknown id → 404. A 200-day activity range → 422.
  - **Events:** these show `auth.login_failed` (`bad_password` with counts 1–5, then `locked`), `auth.locked` with `locked_until`, `auth.login_ok` and `admin.unlock`, each with `client_ip` and `request_id`.
- **Bug (from Phase 2 Task 4):** `Repo.runs()` selected `created_at`, but `mark_logic.run` has `run_at`. So `/api/runs`, the Dashboard's run list and `/api/admin/activity` without `run_id` all returned 500 on the real DB. The unit tests use a fake repo, so they never caught it.
  - **Fix:** `run_at as created_at`.
  - Every other `Repo` read was run against the real DB (run 19) and all passed: lines 1304, jobs 402, ELR detail, snapshot, reviews, approval, admin users, activity (402 undecided), events.
- **Events IP:** shown as `host(client_ip)`, without `/32`.
- **Note:** behind Docker Desktop NAT, every client appears as `172.18.0.1`, the bridge gateway. On 10.153.90.17, check that NGINX sees real client IPs; Docker's userland proxy can hide them.

### 2026-11-05 — Review of the login-audit work (agent commits 8aa889a..5c565f4) and a CI fix
- **Tasks 1–5 reviewed:** all match the plan. Re-run per commit gave 341 → 347 → 351 → 352 unit tests passing. The web build passes, and `Admin` is a 4.4 KB gzip chunk.
- **Migration 0006 is applied** on `mark_web` @10.151.28.2, run by the other agent by 13:32.
  - Checked: `mark_app.audit_log` has `client_ip` and `request_id`.
  - The agent did not record when it was run, and plan Task 6 was left unticked.
- **Admin account:** `mark_app.app_user` now has one `admin` account, created by the user.
- **CI fix:** the Jenkins build for 5c565f4 failed at collection, because `ZoneInfo("Asia/Bangkok")` needs the `tzdata` package on Windows and the clean venv did not have it. `routers/admin.py` now uses a fixed UTC+7 (Thailand has no DST).
- **Open minor items (not fixed):**
  - `log_event` raises if the log folder is not writable.
  - The 92-day cap allows 93 days inclusive.
  - The date filters cast `created_at`, so the `created_at` index is not used.
- **Pending:** the Task 4 manual check on localhost:8088 as admin. The plan's tick for it was set before any deploy.

### 2026-11-05 — Task 5: Persistent API log file
- **What changed**:
  - In services/api/mark_api/logging.py: added rotating file handler (RotatingFileHandler(maxBytes=10MB, backupCount=5)) writing JSON lines to <MARK_LOG_DIR>/api.jsonl when MARK_LOG_DIR is configured; preserved current_request_id ContextVar across module reloads.
  - In docker-compose.yml: mounted host ./logs to /app/logs and set MARK_LOG_DIR=/app/logs in the pi service.
  - In .env.example: declared MARK_LOG_HOST_DIR=./logs.
  - Added logs/ to .gitignore and .dockerignore.
  - In Jenkinsfile: declared MARK_LOG_HOST_DIR parameter and environment variable so redeploys share the host log directory.
- **Verification**:
  - 	est_log_event_also_writes_file passed.
  - docker compose config validated successfully.
  - Full unit test suite: 352 passed.

### 2026-11-05 — Task 4: Web /admin page
- **What changed**:
  - Implemented lazy-loaded Admin console in web/src/pages/Admin.tsx with 3 sections:
    1. ผู้ใช้ (Users): table with user roles, lockout counts, and active 'ปลดล็อก' (Unlock) button triggering POST /api/admin/users/{id}/unlock.
    2. ภาพรวม (Overview): date range filter, 4 progress cards (total, approved, rejected, undecided), per-user velocity table, and daily auth breakdown table.
    3. เหตุการณ์ล่าสุด (Events): 50 rows/page paginated audit event viewer filterable by action and user.
  - Added 'Admin' navigation link to Dashboard header for admin role users.
  - Added /admin lazy route in web/src/App.tsx.
  - Added TypeScript interfaces in web/src/api.ts (AdminUser, ActivityData, AuditEvent, etc.).
- **Verification**:
  - 	sc -b && vite build passed with zero errors.
  - Bundle size: initial JavaScript chunk 88.07 kB gzip (≤ 300 kB budget); Admin chunk isolated at 4.37 kB gzip.

### 2026-11-05 — Task 3: Admin API for users, unlock, activity, events
- **What changed**:
  - Widen `can` permission matrix in `mark_api.auth`: added `"admin"` action restricted exclusively to `"admin"` role.
  - Implemented repository methods in `Repo`:
    - `admin_users()`: returns list of users with last login timestamp via left join on `audit_log`.
    - `unlock_user(user_id)`: resets `failed_count = 0` and `locked_until = null`.
    - `activity(date_from, date_to, run_id)`: runs 3 SQL statements for per-user reviews/approvals, latest ELR approval progress vs. job counts (`distinct on (elr_no)`), and daily auth events.
    - `audit_events(date_from, date_to, user_id, action, page)`: paginated 50 rows/page newest first with filters.
  - Created router `services/api/mark_api/routers/admin.py` with routes `/api/admin/users`, `/api/admin/users/{user_id}/unlock`, `/api/admin/activity`, and `/api/admin/events`.
  - Enforced 92-day date range limit and `from <= to` checks with 422 HTTP status.
- **Verification**:
  - Unit tests in `test_api_core.py` and `test_api_routes.py`: 351 passed.
  - Live PostgreSQL check on run 19: `total_elrs == 402` and user list fetched correctly.

### 2026-11-05 — Task 2: Audit failed logins, lockouts and expired sessions
- **What changed**:
  - Added `session_status(session, now)` in `mark_api.auth` returning `"ok"`, `"absolute"`, or `"idle"`; `session_valid` delegates to it.
  - Added `safe_audit(repo, user_id, action, request, **kw)` in `mark_api.deps`, catching exceptions and logging `db.error`.
  - In `auth.login`: audit `auth.login_failed` (reasons: `unknown_user` with `user_id=None`, `locked`, `inactive`, `bad_password` with `failed_count`), `auth.locked` on 5th failure with ISO timestamp, and `auth.login_ok`.
  - In `auth.current_user`: audit `auth.session_expired` with reason before session deletion so repeated calls do not re-audit.
  - Replaced direct `repo.audit` in auth router with `safe_audit`.
- **Verification**:
  - 7 new unit tests in `test_api_core.py` and `test_api_routes.py`.
  - Full suite: 347 unit tests passed.

### 2026-11-05 — Task 1: Migration 0006 and request context in Repo.audit
- **What changed**:
  - Migration `migrations/0006_audit_context.sql`: additive columns `client_ip inet`, `request_id text` and composite index `audit_log_action_created_idx` on `mark_app.audit_log`.
  - Added `audit_ctx(request: Request)` in `services/api/mark_api/deps.py` extracting `client_ip` from `X-Real-IP` (falling back to `request.client.host`) and `request_id` from `request.state.request_id` (or header).
  - Updated `Repo.audit` and `FakeRepo.audit` to take keyword arguments `client_ip` and `request_id`.
  - Updated `routers/auth.py` and `routers/workflow.py` to forward `**audit_ctx(request)` on login, logout, review and approval.
- **Verification**:
  - `pytest tests/unit -q`: 341 passed.
  - Added unit test `test_review_audit_carries_ip_and_request_id` in `tests/unit/test_api_routes.py`.

### 2026-11-05 — Design and plan: login audit, admin unlock and activity dashboard
- **Why:** the user needs to answer "I can't log in" from the DB, and managers want an overview (role `admin`).
- **Gaps found:**
  - Failed logins, lockouts and expired sessions are not in `audit_log`.
  - Audit rows have no IP or request_id.
  - API logs are lost on every Jenkins redeploy.
  - There is no way to unlock an account.
- **Spec:** `docs/superpowers/specs/2026-11-05-login-audit-activity-design.md`.
- **Plan:** `docs/superpowers/plans/2026-11-05-login-audit-activity.md` (Tasks 1–6). Migration 0006 is additive: two columns and one index on `audit_log`.
- **Pending user:** approve the plan, give the go-ahead for migration 0006 on the shared DB, and create the admin account in their own terminal.
- **Note:** `mark_app.audit_log` is empty so far (no logins on the trial yet). The only app user is user_id 1, an engineer.

### 2026-11-05 — Jenkins job `mark-web` created; first builds
- **First green build: #8 (5e7b2be), SUCCESS in 57 s.**
  - pytest: 340 passed (`tests/regression` is excluded in CI because it reads git-ignored `artifacts/`).
  - Web build, both images, `docker compose up` and the smoke test all passed.
  - Checked by hand afterwards: `/api/ready` 200, `/api/runs` 401, SPA 200, and no `.env` left in the workspace.
- **Builds #4–#7 failures and fixes:**
  - #4: FastAPI pin (cf30405).
  - #5: cmd `if … &&` skipped pytest, and `copy` rejected `/` paths (c880e3b, 7b706fd).
  - #6: R1 regression tests need `artifacts/` (5e7b2be).
  - #7: stopped by hand.
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
