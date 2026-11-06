# B3 History, Queue, Worker and Scan API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. Steps marked **[USER]** wait for the user. Do not tick them yourself.

**Goal:** an ELR at Oracle step 6 gets checked automatically, exactly once per real change, through a Postgres queue and a worker. The flow runs `mark_engine` with the A100 inference service. Each check is stored as a revision in a daily `mark_logic` run that the existing web pages already show. The API can start a scan, look an ELR up, and check one ELR against Oracle on request.

**Architecture:**
- **Fingerprints** of the Oracle row and of the resolved ABS/SLR decide whether an ELR needs checking (spec §4).
- **API side:** `POST /api/scans` reads Oracle (read-only), applies G0, and enqueues `work_item` rows.
- **Worker side:** a separate process claims items with `FOR UPDATE SKIP LOCKED` and runs the existing `process_elr` with `MARK_INFERENCE=service`. It writes results into the day's run with the same row builders as the existing loaders, records an `elr_revision`, creates notifications, and sends `NOTIFY mark_events`.
- **Out of scope** (separate plans):
  - Airflow DAGs (spec §9 step 4).
  - WebSocket and the new web UI (step 5).

**Tech Stack:** Python 3.12, psycopg2, FastAPI (existing `services/api`), `mark_engine`, the inference client from B4.

**Spec:** `docs/superpowers/specs/2026-11-05-auto-review-flow-design.md` §2.1, §2.2 G0, §3, §4, §5, §7, §8. Read §4 in full before Task 2.

## Global Constraints

- **Read-only sources:**
  - Oracle: use `SET TRANSACTION READ ONLY` through the existing `oracle_client`.
  - NAS: read only.
  - Inference: through `MARK_INFERENCE` and the B4 client.
- **`mark_logic` is insert-only for new runs [user 2026-11-05: results become a daily run].**
  - Never update or delete rows in existing runs.
  - Never touch runs 1–19, or R0 `D:\CIM Project\mark`.
  - New runs have `period` = `auto-YYYY-MM-DD`, with the suffix `.2`, `.3` … only when that ELR already has a row in that day's run (see Task 4).
- **DB roles:**
  - A new login role `mark_worker` gets: INSERT/SELECT on `mark_logic.run`, `job_result`, `line_result`; SELECT on the rest of `mark_logic`; and the `mark_app` tables it needs.
  - It gets no UPDATE or DELETE on `mark_logic`.
  - `mark_app` (the API role) gets read on the new tables, plus INSERT on `scan` and `work_item` and UPDATE on `notification.read_*`.
  - Passwords live only in `.env` (`MARK_WORKER_PG_PASSWORD`) and are never printed.
- **Applying migrations to the real DB `10.151.28.2/mark_web` is a [USER] step.** Write the UP and DOWN files and test them on a throwaway schema or local Postgres first.
- **Approved results are history [user]:** never update an `elr_revision`, `job_result`, `line_result` or `approval` row that belongs to an earlier revision.
- **Customer data** (ABS images, OCR text) never goes into git or logs. Logs carry ELR numbers, counts and reason codes only.
- **Process:**
  - Every commit updates HANDOFF §4 and `docs/qa/QA_LOG.md`.
  - Add no duplicate tests.
  - A task is done only after push and a green Jenkins build.
  - `git pull --rebase` before push.
  - **Only one agent works in this working tree.**
- **Dev-machine scope:** run everything from `10.151.97.18`. Do not deploy to `10.153.90.17`, and do not touch Airflow `10.151.28.3`.

## Review Focus

1. **The same ELR arrives twice in one scan, or in overlapping scans** (the watermark minus 5 min overlap). Exactly one `work_item` may be active per ELR. Enforce it with a partial unique index on `work_item(elr_no) where state in ('queued','running','retry')`.
2. **Data edited back to an old value:** compare (`oracle_fp`, `docs_fp`) against **every** earlier revision of that ELR. On a match, record `same_as_rev=N` in the scan counts and create no revision (spec §4).
3. **The worker dies mid-item:** an item stuck in `running` with `updated_at` older than 15 min returns to `retry` on the next claim. It is never lost and never run twice at the same time.
4. **Inference service down:** retry 3 times (after 1, 5 and 15 min), then record the job as HOLD `INFERENCE_FAILED` and add a notification. The worker must never fall back to the cache silently.
5. **Version-only change** (engine or model version): no automatic re-check. Only `recheck` (manual) re-runs it (spec §4).

## File Structure

| File | Role |
|---|---|
| `migrations/0007_auto_review.sql` and `migrations/0007_auto_review_down.sql` | Tables `scan`, `elr_revision`, `work_item`, `notification`; view `latest_job_result`; role `mark_worker`; grants |
| `mark_engine/history/fingerprint.py` | `oracle_fp`, `docs_fp`, `version_fp`, `result_fp` |
| `mark_engine/history/decide.py` | the pure decision table of spec §4 |
| `services/worker/oracle_source.py` | read ELR rows from Oracle (by time window or by ELR) and turn them into `ElrMeta`/`OracleMark` |
| `services/worker/queue.py` | enqueue, claim, finish, retry (SQL) |
| `services/worker/results.py` | write one ELR's result into the day's run, plus `elr_snapshot` and the ABS image |
| `services/worker/main.py` | the worker loop (`python -m services.worker.main`) |
| `services/api/mark_api/routers/scans.py` | `/api/scans`, `/api/scans/retry`, `/api/elrs/lookup`, `/api/elrs/{elr}/oracle-check`, `/api/elrs/{elr}/recheck`, `/api/notifications` |
| `tests/unit/test_history.py`, `tests/unit/test_worker.py`, `tests/unit/test_scans_api.py` | tests |

---

### Task 1: Migration 0007

**Files:**
- Create: `migrations/0007_auto_review.sql`
- Create: `migrations/0007_auto_review_down.sql`
- Modify: `migrations/README.md` (one row)

**Interfaces:** the tables are exactly spec §5, plus:
- `scan.counts jsonb`, holding `found`, `queued`, `unchanged`, `skipped`, `same_as_rev` and per-reason skip counts.
- `elr_revision`:
  - `unique(elr_no, revision)` and `unique(elr_no, oracle_fp, docs_fp)`;
  - `run_id` references `mark_logic.run`;
  - `changed` is one of `new`/`oracle`/`docs`/`both`/`manual`;
  - `changed_fields text[]` (Oracle field names that changed).
- `work_item`:
  - `reason` is one of `scan`/`user`/`recheck`/`retry_docs`;
  - a partial unique index on `(elr_no) where state in ('queued','running','retry')`;
  - an index on `(state, next_attempt_at)`.
- `notification`: `unique(elr_no, kind, revision)`, so one ELR gets one notice per reason per revision (spec §7). The kinds are: `not_in_system`, `not_in_oracle`, `not_eligible`, `hold`, `failed`, `inference_failed`, `changed_after_approve`, `scan_failed`.
- **View `mark_app.latest_job_result`:** for each `elr_no`, the `job_result` row of the highest `elr_revision.revision`, with `run_id` and `revision`.

- [x] **Step 1: Write UP and DOWN.** DOWN drops only what UP created. It never touches `mark_logic` rows.
- [x] **Step 2: Test on a throwaway database or schema** (local Postgres, or a `mark_web` schema named `t0007_<date>` that is dropped afterwards). Apply UP, then DOWN, then UP. Record the commands and their results in QA_LOG.
- [x] **Step 3:** Commit `feat(db): 0007 auto-review history, queue, notifications`, then push and wait for a green Jenkins build.
- [x] **Step 4: [USER] Apply 0007 to `10.151.28.2/mark_web`.** Give the user the exact command, then check that the role and tables exist (names only) and that row counts in runs 1–19 are unchanged.

### Task 2: Fingerprints and the decision table

**Files:**
- Create: `mark_engine/history/__init__.py`, `fingerprint.py`, `decide.py`
- Test: `tests/unit/test_history.py`

**Interfaces:**
- **`ORACLE_FP_FIELDS`:** the tuple from spec §4 (`PRODUCT_NO`, `CUST_ASSY_LOT`, `TOP_MARK1`–`5`, `TOP_MARK_ID`, `TOP_TYPE_CODE`, `TOP_LAYOUT_CODE`, `MARK_REMARK`, `MARK_REQUIRE`, `CUST_REQ_NO`, `CURRENT_STEP`, `STATUS`).
- **`oracle_fp(row: Mapping[str, Any]) -> str`:** sha256 of canonical JSON (sorted keys, `None` → `""`, strings with trailing spaces stripped).
- **`docs_fp(resolution: DocumentResolution | None) -> str`:** sha256 of the sorted `(role, path, sha256)` of the resolved ABS and SLR. `None` or a HOLD with no files gives the sha256 of `"none"`.
- **`version_fp(engine_version: str, model_version: str) -> str`**
- **`result_fp(job: JobResult) -> str`:** sha256 of the expected mark lines plus every line's status.
- **`changed_oracle_fields(old_row, new_row) -> list[str]`**
- **`Decision`** is a dataclass with `action: Literal["check","skip_unchanged","skip_same_as_rev","skip_not_eligible"]`, `changed: str | None` and `same_as_rev: int | None`.
- **`decide(pending_reason: str | None, prev: list[RevisionKey], oracle_fp: str, docs_fp: str | None, manual: bool) -> Decision`:**
  - `RevisionKey` = (`revision`, `oracle_fp`, `docs_fp`).
  - `docs_fp=None` means it hasn't been computed yet (see "cheap first").
  - Order:
    1. `manual` → `check` / `manual`.
    2. `pending_reason` → `skip_not_eligible`.
    3. No previous revision → `check` / `new`.
    4. Equal to the latest revision → `skip_unchanged`.
    5. Equal to an older revision → `skip_same_as_rev`.
    6. Otherwise → `check` with `oracle`, `docs` or `both`.
- **Cheap first (spec §4):** the worker computes `docs_fp` only when `oracle_fp` is unchanged and a quick NAS check (path + size + mtime of the last resolved files, stored in `elr_revision.docs_probe jsonb`) shows a change. Otherwise it reuses the stored `docs_fp`.

- [x] **Step 1: Tests.**
  - `test_oracle_fp_ignores_field_order_and_trailing_spaces`
  - `test_oracle_fp_changes_on_each_field`: parametrize over every field in `ORACLE_FP_FIELDS`.
  - `test_docs_fp_changes_with_revision_file`
  - `test_decide_table`: parametrize one case per row of spec §4, including manual, same-as-older-revision and version-only.
  - `test_changed_oracle_fields_names_only`
- [x] **Step 2:** Run them. Expected: FAIL.
- [x] **Step 3:** Implement.
- [x] **Step 4:** Run the unit suite. Expected: all pass.
- [x] **Step 5:** Commit `feat(engine): input fingerprints and re-check decision (spec §4)`, then push and wait for a green Jenkins build.

### Task 3: Oracle source and the queue

**Files:**
- Create: `services/worker/__init__.py`, `oracle_source.py`, `queue.py`
- Test: `tests/unit/test_worker.py`

**Interfaces:**
- **`oracle_source.py`:**
  - `fetch_window(conn, from_ts: datetime, to_ts: datetime) -> list[dict]`: ELR rows with `LAST_DATE` in the window. It reuses the field list and the join of `scripts/fetch_oracle_snapshot.py`; move that constant into `mark_engine/adapters/oracle_snapshot.py` so the script and the worker share it.
  - `fetch_one(conn, elr_no: str) -> dict | None`
  - `fetch_pending_step(conn, review_step: str) -> list[dict]`: every ADI ELR at the step, with STATUS other than C. Used for the initial load.
  - `to_engine(row) -> tuple[ElrMeta, OracleMark, MarkLayout | None]`: through the existing `rows_to_meta` / `layout_json` path.
- **`queue.py`:** these take a psycopg2 connection and use plain SQL.
  - `enqueue(cur, scan_id: int | None, elr_no: str, reason: str) -> bool`: `insert … on conflict do nothing` on the partial unique index. Returns whether the row was inserted.
  - `claim(cur, worker_id: str) -> WorkItem | None`: `select … where state in ('queued','retry') and next_attempt_at <= now() order by created_at for update skip locked limit 1`, then sets `running` and `attempts+1`. Before that, it resets items stuck in `running` for more than 15 min to `retry`.
  - `finish(cur, item_id, revision: int | None)`
  - `fail(cur, item_id, error: str, retry_in: timedelta | None)`
- The retry delays are `RETRY_DELAYS = (1, 5, 15)` minutes. After the third failure, the item becomes `failed`.

- [x] **Step 1: Tests.**
  - **Oracle source:** use a fake connection that records SQL. `test_fetch_window_uses_read_only_and_bind_params` asserts read-only and no string-formatted values.
  - **Queue:** use the existing test-DB approach if the repo has one. Otherwise use a `FakeCursor` that implements the SQL contract. Tests:
    - `test_enqueue_is_idempotent_per_active_elr`
    - `test_claim_skips_locked_and_future_items`
    - `test_stuck_running_returns_to_retry`
    - `test_fail_backoff_then_failed`
- [x] **Step 2:** Run them. Expected: FAIL.
- [x] **Step 3:** Implement.
- [x] **Step 4:** Run the unit suite. Expected: all pass.
- [ ] **Step 5:** Commit `feat(worker): Oracle source and Postgres SKIP LOCKED queue`, then push and wait for a green Jenkins build.

### Task 4: Results writer and worker loop

**Files:**
- Create: `services/worker/results.py`
- Create: `services/worker/main.py`
- Modify: `scripts/load_r1_to_pg.py` and `scripts/load_app_snapshot.py`. Move `job_row`, `line_row`, `build_snapshot_rows` and `copy_images` into importable functions, either in `services/worker/results.py` or a shared module. The scripts import them, and their behaviour must not change.
- Test: `tests/unit/test_worker.py`

**Interfaces:**
- **`day_run_for(cur, elr_no: str, day: date) -> int`:**
  - Returns the `run_id` of the first run with `period` `auto-YYYY-MM-DD`, then `.2`, `.3`, … that has **no** `job_result` row for this ELR.
  - It creates that run (insert only) when it is missing.
  - The run row records `git_commit`, the engine version, the model version from `Health`, and `note='auto-review'`.
- **`write_result(cur, job: JobResult, meta, oracle_row, resolution, revision_info) -> int`:**
  - Inserts the `job_result` and `line_result` rows, the `elr_snapshot` row, and the `elr_revision` row.
  - Copies the ABS page image to `MARK_FILES_ROOT/<run_id>/…`, the same as `copy_images`.
  - Returns the new `revision`.
- **`notify_for(cur, job, revision, prev_approved: bool) -> list[str]`:**
  - Inserts notifications per spec §7: HOLD, FAILED, `INFERENCE_FAILED`, and `changed_after_approve` when the previous revision has an `approval` row.
  - It skips this when `result_unchanged`.
  - Then runs `NOTIFY mark_events, '<json {elr_no, run_id, revision, kind}>'`.
- **`main.py` loop:** `claim` → `fetch_one` (fresh Oracle row) → `pending_reason` (G0) → `decide` → `process_elr` (with `MARK_INFERENCE` from env, normally `service`) → `write_result` → `notify_for` → `finish`. Each item is one transaction.
  - On `InferenceUnavailable`, call `fail` with backoff.
  - After the last retry, write the job as HOLD `INFERENCE_FAILED` (through `write_result`) and add a notification.
  - Options: `--once` (process until the queue is empty, then exit) and `--poll-seconds 5`.
  - Logs carry ELR numbers, actions and reason codes only.

- [x] **Step 1: Tests**, with fakes for Oracle, the engine and inference, and the `FakeCursor` or test DB from Task 3:
  - `test_day_run_reuses_until_elr_repeats_then_suffix`
  - `test_write_result_never_updates_existing_rows`: the SQL log contains only INSERTs for `mark_logic`.
  - `test_approved_revision_kept_and_new_revision_notifies`
  - `test_same_as_old_revision_creates_nothing`
  - `test_inference_down_retries_then_hold_inference_failed`
  - `test_version_only_change_not_rechecked`
  - `test_loader_scripts_unchanged_output`: the refactored `job_row` / `line_row` / `build_snapshot_rows` return the same values as before for one fixture.
- [x] **Step 2:** Run them. Expected: FAIL.
- [x] **Step 3:** Implement.
- [x] **Step 4:** Run the unit suite. Expected: all pass.
- [ ] **Step 5:** Commit `feat(worker): results writer to daily auto run and worker loop`, then push and wait for a green Jenkins build.

### Task 5: Scan and lookup API

**Files:**
- Create: `services/api/mark_api/routers/scans.py`
- Modify: `services/api/mark_api/app.py` (include the router) and `services/api/mark_api/repo.py` (queries).
- Test: `tests/unit/test_scans_api.py`

**Interfaces:**

| Endpoint | Auth | Does |
|---|---|---|
| `POST /api/scans` body `{source: "airflow"\|"initial", from_ts?, to_ts?}` | API token scope `scan:write` | `airflow`: the window runs from the last successful scan's `to_ts` minus 5 min to now (spec §2.1). `initial`: `fetch_pending_step`. It applies G0 and `decide` (the cheap Oracle part only), enqueues work items, writes a `scan` row with counts, and returns them. Only one airflow/initial scan may run at a time (`pg_try_advisory_lock`); if one is already running, return 409. |
| `POST /api/scans/retry` | `scan:write` | Re-enqueue ELRs whose latest revision is HOLD or not approved and still at step 6, with reason `retry_docs`. The worker computes `docs_fp` and skips when nothing changed. |
| `GET /api/elrs/lookup?elr=` | session (engineer/admin) | Returns `{in_system, latest: {run_id, revision, status}, revisions: [...], queued: bool}`. When `in_system` is false, the page offers "check in Oracle". |
| `POST /api/elrs/{elr}/oracle-check` | session and CSRF | `fetch_one`. If not found → a `not_in_oracle` notification and 404 with that reason. If G0 fails → a `not_eligible` notification and 200 with `{queued:false, reason}`. Otherwise enqueue with reason `user` and return `{queued:true}`. |
| `POST /api/elrs/{elr}/recheck` | session and CSRF, role `engineer`/`mark_eng_approver`/`admin` | Enqueue with reason `recheck` (manual), so it always checks. |
| `GET /api/notifications?unread=1` and `POST /api/notifications/{id}/read` | session | Lists notifications, and marks one as read for the current user. |

All endpoints write an `audit_log` row (`scan.started`, `elr.oracle_check`, `elr.recheck`) using the existing helper. The token scope check uses the existing `api_token.scopes`. Extend `scripts/create_api_token.py` to accept `--scope scan:write`.

- [x] **Step 1: Tests.** Use FakeRepo and fakes for the Oracle source; follow the style of `tests/unit/test_api_routes.py`.
  - `test_scan_requires_scan_write_scope`
  - `test_scan_window_from_watermark_minus_5min`
  - `test_concurrent_scan_returns_409`
  - `test_lookup_not_in_system`
  - `test_oracle_check_not_found_notifies`
  - `test_oracle_check_not_eligible_returns_reason`
  - `test_recheck_requires_csrf_and_role`
  - `test_notifications_read_is_per_user`
- [x] **Step 2:** Run them. Expected: FAIL.
- [x] **Step 3:** Implement.
- [x] **Step 4:** Run the unit suite, plus `python scripts/e2e_walkthrough.py --run 19` against `localhost:8088` after rebuilding the API container. Expected: all pass, and E2E is 12/12.
- [x] **Step 5:** Commit `feat(api): scans, lookup, oracle-check, recheck, notifications`, then push and wait for a green Jenkins build.

### Task 6: End-to-end on the dev machine (spec §8)

Runs only after the user's Task 1 Step 4. Use `MARK_INFERENCE=service` and the `mark_worker` role from `.env`.

- [x] **Step 1: Initial load, dry run.**
  - Call `POST /api/scans` with `source=initial`, using a `scan:write` token made by `create_api_token.py`. The token goes into `.env` and is never printed.
  - Record the scan counts. Zero ELRs at step 6 is normal (spec §2.4).
- [x] **Step 2: User path.**
  - **[USER]** The user names one real ELR that is at step 6 (or recently was).
  - Call `oracle-check`, then run the worker with `--once`.
  - Check that the result shows in the API under the new `auto-…` run, and that `lookup` shows revision 1.
- [x] **Step 3: Re-check rules.**
  - Run `recheck` on the same ELR. A new revision is expected, with `changed=manual`.
  - Run `oracle-check` again with no change. Expected: `skip_unchanged`, and no new revision.
- [x] **Step 4: Fingerprint change (simulated).** In a unit-level script, feed the worker the same Oracle row with one `TOP_MARK` changed, through the fake source. Expected: `changed=oracle` and `changed_fields=['TOP_MARK2']`. **Do not** edit Oracle.
- [x] **Step 5: Safety checks.**
  - Row counts and `max(updated)` of runs 1–19 are unchanged.
  - Only INSERTs went into `mark_logic`, which you can check with the `pg_stat_user_tables` deltas.
  - Record everything in QA_LOG and HANDOFF (ELR numbers and counts only).
- [x] **Step 6:** Commit `test(worker): dev end-to-end of scan, oracle-check and recheck`, then push and wait for a green Jenkins build.
