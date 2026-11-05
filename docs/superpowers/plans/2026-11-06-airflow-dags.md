# Airflow DAGs for Auto Review — Implementation Plan (for Codex)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. Steps marked **[USER]** wait for the user. Do not tick them yourself.

**Goal:** Airflow on TH1SRAPPDEV5 (`10.151.28.3`) calls the Mark API on the dev machine (`http://10.151.97.18:8088`) on a fixed schedule:
- `POST /api/scans` every 15 minutes;
- `POST /api/scans/retry` every 10 minutes;
- a manual DAG for the one-time initial load.

The DAGs do nothing else.

**Architecture:**
- **DAG logic:** three thin DAG files plus one helper module. The helper is plain Python with no Airflow import, so it can be unit-tested in Jenkins.
- **Server-side work:** the API decides the time window from its own watermark, applies G0, and queues work. The DAGs send no window and never touch Oracle, NAS or Postgres (spec §2.1, §3).
- **Credentials:** the API URL and the `scan:write` token live in the Airflow Connection `mark_api`.

**Tech Stack:** Apache Airflow (the version already installed on the server; Task 1 finds it), Python stdlib `urllib` for HTTP. No new dependency.

**Spec:** `docs/superpowers/specs/2026-11-05-auto-review-flow-design.md` §2.1, §3, §7, §9 step 4. The API contract is in `docs/superpowers/plans/2026-11-05-b3-history-queue-worker-api.md` **Task 5**. agy is building that API now on `phase2/trial`.

## Where Codex works

- **Worktree and branch:** `D:\CIM Project\mark-web-airflow`, branch `phase2/airflow`. **Do not work in `D:\CIM Project\mark-web`.** agy is executing B3 there, and only one agent may work in a working tree.
- **Commits:** commit and push to `origin/phase2/airflow` only.
- **Merging:** the merge into `phase2/trial` is a **[USER]** step, done between agy's tasks. Jenkins builds `phase2/trial`. Until then, run the same command locally: `.venv\Scripts\python -m pytest tests -q --ignore=tests/regression`. Use the venv of the main checkout, or create one in the worktree.
- **Before each push:** `git fetch` and rebase `phase2/airflow` onto `origin/phase2/trial`.

## Global Constraints

- **Shared Airflow server [user: reuse the existing Airflow, separate Mark DAG group]:**
  - Never change, pause, delete or restart other people's DAGs, services, containers, `airflow.cfg`, pools or variables.
  - No `pip install` on the server.
  - Files go only into a `mark/` subfolder of the DAGs folder.
- **SSH key only:** `ssh 10.151.28.3` uses `~/.ssh/id_ed25519_nopass` as `itadmin` (the config is already set; the user installs the key once).
  - Never log in with the password, never put `AIRFLOW_SSH_PASSWORD` in any command, file or log, and never use `sudo`.
  - If a step needs root, stop and ask the user.
- **Token:**
  - The `scan:write` token is created on the dev machine with `scripts/create_api_token.py` (B3 Task 5) and stored only in the Airflow Connection `mark_api` (password field) and in the local `.env` `MARK_SCAN_TOKEN`.
  - Never print it, commit it or pass it on a command line that the shell history keeps. Read it from a file with mode 600 that you delete afterwards, or from stdin.
- **New DAGs are paused:** every DAG has `is_paused_upon_creation=True`. Unpausing is **[USER]**.
- **No backfill:**
  - Scheduled DAGs use `catchup=False`, `max_active_runs=1`, `max_active_tasks=1`, a fixed `start_date` of 2026-11-01 and timezone `Asia/Bangkok`.
  - Retries: `retries=2`, `retry_delay=2 min`, `execution_timeout=10 min`.
- **No customer data** in DAG logs or git. Log only counts and the `scan_id` from the API response.
- **Dev only:** the API base URL is `http://10.151.97.18:8088` for now. Moving to `10.153.90.17` later changes only the Connection's host, not the DAG code.
- **Every commit updates HANDOFF §4 and `docs/qa/QA_LOG.md`.** Add no duplicate tests.

## Review Focus

1. **A scan is still running when the next run starts:** the API returns 409. The task must end as **skipped**, not failed, and must not retry.
2. **Dev machine off or API down** (connection refused or timeout): the task fails after its retries, with an error message that names the URL but not the token. The next run starts normally. Nothing piles up, because `max_active_runs=1` and `catchup=False`.
3. **Token wrong or expired** (401/403): fail immediately, without retrying, with the message "mark_api token rejected". Retrying cannot fix it.
4. **Airflow scheduler restarts, or a DAG is paused for a day:** no backfill burst (`catchup=False`). The API watermark covers the gap, because the next scan sweeps from the last successful `to_ts`.
5. **The DAG file is imported by a scheduler with other people's DAGs:** importing makes no network call and does no heavy work at module level, and the file name and `dag_id` are prefixed `mark_` so they cannot collide.

## File Structure

| File | Role |
|---|---|
| `airflow/dags/mark/mark_api_client.py` | `call_mark_api(base_url, token, path, body, timeout) -> dict` plus the error mapping. No Airflow import. |
| `airflow/dags/mark/mark_elr_polling.py` | schedule `*/15 * * * *`; posts `{"source":"airflow"}` to `/api/scans` |
| `airflow/dags/mark/mark_pending_job_retry.py` | schedule `*/10 * * * *`; posts `{}` to `/api/scans/retry` |
| `airflow/dags/mark/mark_initial_load.py` | `schedule=None` (manual trigger only); posts `{"source":"initial"}` to `/api/scans` |
| `airflow/README.md` | how to deploy, set the Connection, unpause and roll back |
| `tests/unit/test_mark_api_client.py` | unit tests of the helper (fake HTTP server, stdlib only) |

---

### Task 1: Server discovery (read-only)

The user installs the SSH key first (**[USER]**, Claude gives the script). Then:

- [ ] **Step 1:** `ssh 10.151.28.3 'echo ok'` succeeds without a password prompt. If it fails, stop and tell the user.
- [ ] **Step 2: Find out how Airflow runs, without changing anything.**
  - Check `docker ps --format '{{.Names}} {{.Image}}'` filtered to airflow, or `systemctl list-units | grep -i airflow`.
  - Find the Airflow version (`airflow version` inside the scheduler container or venv).
  - Find the host path of the DAGs folder (from the container mounts, or `airflow config get-value core dags_folder`).
  - Find the scheduler's timezone, and whether the `airflow` CLI can run as `itadmin` (directly or via `docker exec`, without sudo).
- [ ] **Step 3: Check the network path to the API.**
  - Run `curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://10.151.97.18:8088/api/health`, from the host and also from inside the scheduler/worker container when Airflow is containerized. Expected: `200`.
  - If it fails, stop. **[USER]** must allow inbound TCP 8088 from `10.151.28.3` in the dev PC's Windows firewall. Claude does not change firewall settings.
- [ ] **Step 4: Record the findings in `airflow/README.md` and QA_LOG.** Write down the version, deploy path, CLI access and curl result. Write no secrets and no list of other teams' DAGs.
  - If the Airflow version is older than 2.4, the `schedule=` argument does not exist. Use `schedule_interval=` in Task 2 and write that down.
- [ ] **Step 5:** Commit `docs(airflow): server discovery for Mark DAGs`, then push `phase2/airflow`.

### Task 2: Helper and DAG files

**Interfaces:**
- **`call_mark_api(base_url: str, token: str, path: str, body: dict, timeout: float = 120.0) -> dict`:**
  - Sends a POST with JSON and `Authorization: Bearer <token>`, and returns the parsed JSON.
  - It raises:
    - `MarkApiBusy` on 409;
    - `MarkApiAuthError` on 401/403;
    - `MarkApiError(status, url)` on other 4xx/5xx and on connection or timeout errors.
  - No message contains the token.
- **`summarize(resp: dict) -> str`:** one log line with `scan_id` and the counts (`found`, `queued`, `unchanged`, `skipped`), in the shape of the B3 Task 5 `scan.counts`.
- **The DAG task callable:**
  - Reads `BaseHook.get_connection("mark_api")`. The base URL is `conn.schema` (default `http`) + `://` + `conn.host` + `:` + `conn.port`; the token is `conn.password`.
  - On `MarkApiBusy` → raise `AirflowSkipException`.
  - On `MarkApiAuthError` → raise `AirflowFailException` (no retry).
  - Everything else propagates, so normal retries apply.
  - The connection lookup happens inside the callable, never at import.
- **DAG settings:**
  - `dag_id` = the file name;
  - `tags=["mark"]`;
  - the settings from Global Constraints;
  - `mark_initial_load` has `schedule=None`, `retries=0` and `execution_timeout=60 min`.

- [ ] **Step 1: Write the tests.** They use `http.server` on `127.0.0.1` with a random port in a thread.
  - `test_posts_json_with_bearer_and_returns_body`
  - `test_409_raises_busy`
  - `test_401_and_403_raise_auth_error`
  - `test_500_raises_api_error_with_url_not_token`: assert the token string is not in `str(exc)`.
  - `test_connection_refused_raises_api_error`
  - `test_summarize_counts_line`
- [ ] **Step 2:** Run `pytest tests/unit/test_mark_api_client.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement the helper and the three DAG files. Make `airflow/dags/mark` importable from tests through the path setup in `conftest.py` or the test itself, and add no Airflow dependency to `pyproject.toml`.
- [ ] **Step 4:** Run the full unit suite. Expected: all pass; the count is the previous number plus 6.
- [ ] **Step 5: Parse check of the DAG files on the server** (no deploy yet).
  - Copy the folder to a temp dir under `~/mark_dag_check/` on 10.151.28.3.
  - Run `python -c "import ast,sys; [ast.parse(open(f).read()) for f in sys.argv[1:]]" *.py` with the server's Airflow Python.
  - Delete the temp dir afterwards.
- [ ] **Step 6:** Commit `feat(airflow): mark_elr_polling, mark_pending_job_retry, mark_initial_load DAGs`, then push `phase2/airflow`.

### Task 3: Deploy paused, then smoke test

**Prerequisites:** agy's B3 Task 5 (API scans endpoints) is pushed and green, and migration 0007 is on the real DB (B3 Task 1 Step 4). If they are not, stop here and wait.

- [ ] **Step 1: Copy the DAG files.** Use `scp` to put `airflow/dags/mark/*.py` into `<dags_folder>/mark/`, creating only that subfolder.
  - Then check: `airflow dags list-import-errors` shows nothing for `mark_*`;
  - `airflow dags list | grep mark_` shows all three as **paused**.
- [ ] **Step 2: [USER] Create the token on the dev machine.** The user runs `python scripts/create_api_token.py --name airflow-scan --scope scan:write` and saves it to `.env` `MARK_SCAN_TOKEN`. Codex never sees it printed.
- [ ] **Step 3: Create the Connection `mark_api`.**
  - Settings: type `http`, host `10.151.97.18`, port `8088`, schema `http`, password = the token.
  - Pass the token over SSH stdin from `.env`, never as a command-line argument on either machine. One way: `python - <<'PY'` on the server reading stdin, then `airflow connections add mark_api --conn-uri ...` built in that process.
  - Check with `airflow connections get mark_api -o json | python -c "…print host/port only…"`.
- [ ] **Step 4: Smoke test without unpausing.**
  - Run `airflow tasks test mark_pending_job_retry <task_id> 2026-11-06`. Expected: success and a log line with counts.
  - Then run `airflow tasks test mark_elr_polling <task_id> 2026-11-06`. Expected: success (or skipped on 409).
  - Check that the API wrote a `scan` row with `source=airflow` (count via API or DB, names only).
- [ ] **Step 5:** Record the results in QA_LOG and HANDOFF. Commit `test(airflow): deploy paused and smoke test`, then push `phase2/airflow`.

### Task 4: Turn on (after B3 Task 6)

- [ ] **Step 1: [USER] Initial load.** The user triggers `mark_initial_load` once in the Airflow UI, or Codex runs `airflow dags trigger mark_initial_load` after the user says go. Record the scan counts.
- [ ] **Step 2: [USER] Unpause** `mark_elr_polling` and `mark_pending_job_retry`.
- [ ] **Step 3: Watch the first 4 runs** (1 hour).
  - Each run is success or skipped, never failed.
  - The API `scan` rows have contiguous windows: each `from_ts` = the previous `to_ts` − 5 min.
- [ ] **Step 4: Write the rollback in `airflow/README.md`:**
  1. Pause both DAGs.
  2. Delete `<dags_folder>/mark/`.
  3. Run `airflow connections delete mark_api`.
  4. Revoke the token in `mark_app.api_token`.
- [ ] **Step 5:** Commit `docs(airflow): enabled schedule, first runs verified`, then push `phase2/airflow`. **[USER]** merges into `phase2/trial` and checks that Jenkins is green.

## Known limits (state, do not build)

- **The dev PC must be on.** When it is off, runs fail and the watermark catches up later. The permanent fix is the move to `10.153.90.17`, which changes only the Connection host.
- **Scan failures alert nobody yet:** a run that fails after retries shows only in the Airflow UI. Web notifications for a failed scan (`scan_failed`, spec §7) come with spec §9 step 5.
