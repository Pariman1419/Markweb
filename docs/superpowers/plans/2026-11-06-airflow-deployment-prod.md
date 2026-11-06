# Implementation Plan: Airflow Production Deployment on 10.151.28.3

> **For Agentic Workers (Codex on Dev Workstation 10.151.97.18):**
> Follow the standard execution workflow. Every command runs locally from the dev workstation (`D:\CIM Project\mark-web-airflow` or main repo) using SSH to `itadmin@10.151.28.3`.
> Steps marked with **[USER]** require explicit confirmation or action from the user.

---

## 1. Overview & Objectives

- **Goal**: Deploy Mark Auto-Review Airflow DAGs to shared production Airflow server `TH1SRAPPDEV5` (`10.151.28.3`) to schedule automated scanning and retries against the production Mark API on `10.153.90.17:8093`.
- **Target Schedules**:
  - `mark_elr_polling`: Runs `*/15 * * * *` (every 15 min), POST `{"source": "airflow"}` to `/api/scans`.
  - `mark_pending_job_retry`: Runs `*/10 * * * *` (every 10 min), POST `{}` to `/api/scans/retry`.
  - `mark_initial_load`: Manual trigger (`schedule=None`), POST `{"source": "initial"}` to `/api/scans`.
- **Delivered Outcome**: Airflow triggers scans periodically; Mark Web on `10.153.90.17` queues work items; the live worker on `.17` evaluates ELRs against A100 inference, Oracle, and NAS CIFS storage.

---

## 2. Architecture & Design

```
┌─────────────────────────────────┐               HTTP POST               ┌───────────────────────────────┐
│     Airflow (10.151.28.3)       │  ───────────────────────────────────> │     Mark Web (10.153.90.17)   │
│  - /data/airflow/dags/mark/*.py │   http://10.153.90.17:8093/api/scans  │  - Port 8093 (API + Web)      │
│  - Connection: mark_api         │   Authorization: Bearer <scan_token>  │  - Worker (1 live container)  │
└─────────────────────────────────┘                                       └───────────────────────────────┘
```

- **Airflow Environment (10.151.28.3)**:
  - Systemd services: `airflow-scheduler.service`, `airflow-webserver.service`.
  - User: `itadmin` (key authentication verified).
  - Airflow binary: `/data/airflow/airflow/bin/airflow`.
  - DAGs folder: `/data/airflow/dags/`.
  - Mark subfolder: `/data/airflow/dags/mark/` (isolated, isolated namespace package).
- **Security & Global Server Isolation**:
  - **Zero touch to other teams**: Do not restart, touch, modify, or delete any existing DAGs, connections, pools, or configurations on `10.151.28.3`.
  - **No root / sudo**: Everything executes as user `itadmin`.
  - **No secrets in history**: The `scan:write` token is piped via stdin and never placed in bash command-line arguments or committed to git.
  - **Safe deployment**: All new DAGs are deployed in a paused state (`is_paused_upon_creation=True`).

---

## 3. User Review Checkpoints

- [ ] **Gate 1**: Token creation confirmation (Token generated and added to `mark_api` connection).
- [ ] **Gate 2**: Smoke test review (Dry-run task test passed before unpausing).
- [ ] **Gate 3**: Authorization to unpause `mark_elr_polling` and `mark_pending_job_retry`.

---

## 4. Phased Implementation Steps

### Phase 1: Deploy DAG Files to 10.151.28.3

- [ ] **Step 1.1**: Create Mark DAG directory on the remote server:
  ```bash
  ssh itadmin@10.151.28.3 "mkdir -p /data/airflow/dags/mark"
  ```
- [ ] **Step 1.2**: Copy DAG and helper files to `/data/airflow/dags/mark/`:
  ```bash
  scp airflow/dags/mark/*.py itadmin@10.151.28.3:/data/airflow/dags/mark/
  ```
- [ ] **Step 1.3**: Validate DAG syntax and import integrity on the server:
  ```bash
  ssh itadmin@10.151.28.3 "/data/airflow/airflow/bin/airflow dags list-import-errors"
  ```
  *Expected Output*: No import errors for `mark_` DAGs.
- [ ] **Step 1.4**: Confirm DAG registration and paused status:
  ```bash
  ssh itadmin@10.151.28.3 "/data/airflow/airflow/bin/airflow dags list | grep mark_"
  ```
  *Expected Output*: `mark_elr_polling`, `mark_pending_job_retry`, `mark_initial_load` appear with `paused=True`.
- **Verification**: `ssh itadmin@10.151.28.3 "ls -la /data/airflow/dags/mark"` lists all 5 Python files.

---

### Phase 2: Token Creation & Airflow Connection Setup

- [ ] **Step 2.1**: Generate `scan:write` token locally from dev machine:
  ```bash
  python scripts/create_api_token.py --name airflow-scan --scope scan:write
  ```
  *(Save token in temporary memory or `.env` `MARK_SCAN_TOKEN`, do not echo to terminal logs)*
- [ ] **Step 2.2**: Register Airflow Connection `mark_api` via SSH stdin:
  ```powershell
  # PowerShell script to deliver token via stdin
  $token = "<GENERATED_TOKEN>"
  $cmd = @"
  python3 -c "
  import sys, subprocess
  token = sys.stdin.read().strip()
  cmd = [
      '/data/airflow/airflow/bin/airflow', 'connections', 'add', 'mark_api',
      '--conn-type', 'http',
      '--conn-host', '10.153.90.17',
      '--conn-port', '8093',
      '--conn-schema', 'http',
      '--conn-password', token
  ]
  subprocess.run(cmd, check=True)
  "
  "@
  $token | ssh itadmin@10.151.28.3 $cmd
  ```
- [ ] **Step 2.3**: Verify connection properties without exposing token:
  ```bash
  ssh itadmin@10.151.28.3 "/data/airflow/airflow/bin/airflow connections get mark_api -o json | python3 -c \"import sys, json; data=json.load(sys.stdin); print('Host:', data.get('host'), 'Port:', data.get('port'), 'Schema:', data.get('schema'))\""
  ```
  *Expected Output*: `Host: 10.153.90.17 Port: 8093 Schema: http`.
- **Verification**: Connection exists with correct host/port and no errors.

---

### Phase 3: Smoke Test (Isolated Task Execution)

- [ ] **Step 3.1**: Test execution of `mark_pending_job_retry` task:
  ```bash
  ssh itadmin@10.151.28.3 "/data/airflow/airflow/bin/airflow tasks test mark_pending_job_retry run_retry 2026-11-06"
  ```
  *Expected Output*: Task succeeds; prints summary count or 0 items.
- [ ] **Step 3.2**: Test execution of `mark_elr_polling` task:
  ```bash
  ssh itadmin@10.151.28.3 "/data/airflow/airflow/bin/airflow tasks test mark_elr_polling run_polling 2026-11-06"
  ```
  *Expected Output*: Task succeeds or skips cleanly if a scan is already running (409 handled as `AirflowSkipException`).
- [ ] **Step 3.3**: Verify scan audit record on production Mark API:
  ```bash
  # Check database or query GET /api/ready
  curl.exe -s http://10.153.90.17:8093/api/ready
  ```
- **Verification**: `mark_app.scan` table on Postgres (`10.151.28.2:5432`) records new scan row with `source='airflow'`.

---

### Phase 4: Production Activation & Rollback Plan

- [ ] **Step 4.1 [USER]**: Trigger initial load DAG once (manual run):
  ```bash
  ssh itadmin@10.151.28.3 "/data/airflow/airflow/bin/airflow dags trigger mark_initial_load"
  ```
- [ ] **Step 4.2 [USER]**: Unpause scheduled DAGs:
  ```bash
  ssh itadmin@10.151.28.3 "/data/airflow/airflow/bin/airflow dags unpause mark_elr_polling"
  ssh itadmin@10.151.28.3 "/data/airflow/airflow/bin/airflow dags unpause mark_pending_job_retry"
  ```
- [ ] **Step 4.3**: Monitor the first 2 scheduled runs (30 minutes):
  ```bash
  ssh itadmin@10.151.28.3 "/data/airflow/airflow/bin/airflow dags list-runs -d mark_elr_polling -o table"
  ```
- **Verification**: All scheduled runs finish with state `success` or `skipped`.

---

## 5. Potential Risks & Mitigation

| Risk | Impact | Mitigation Strategy |
|---|---|---|
| **Conflict with other Airflow DAGs** | High | Place all files strictly in `/data/airflow/dags/mark/`. All DAG IDs use `mark_` prefix. Never restart systemd services. |
| **Airflow Scheduler Down** | Medium | Scheduled DAGs have `catchup=False` and `max_active_runs=1`. When scheduler restarts, API watermark seamlessly covers the gap without backfill storm. |
| **API Timeout / Busy (409)** | Low | DAG task catches `MarkApiBusy` and maps to `AirflowSkipException` (task is skipped gracefully, no retry storm). |
| **Token Compromise / Revocation** | High | Token is generated with minimal scope (`scan:write`). If revoked, task raises `AirflowFailException` immediately without retrying. |
| **Emergency Rollback** | Low | Run rollback script: Pause DAGs (`airflow dags pause mark_*`), remove `/data/airflow/dags/mark/`, delete `mark_api` connection, and revoke token in DB. |
