# Deployment Guide — 10.153.90.17

This document details the one-time setup and deployment of Mark Automation (API, Web, and Worker) to the production host `10.153.90.17`.

---

## 1. Prerequisites on 10.153.90.17 Host

1. **Jenkins Controller (already running as Docker container `jenkins`)**:
   - Ensure restart policy survives reboots:
     ```powershell
     docker update --restart unless-stopped jenkins
     ```
   - Ensure Docker Desktop is configured to start automatically at user sign-in.
   - Verify required plugins are installed: `Pipeline`, `Git`, `JUnit`.

2. **Host Tools (installed on Windows host, outside Docker)**:
   - **Git**: `git --version`
   - **Python 3.12**: `python --version` (on system PATH)
   - **Node.js LTS**: `node --version`
   - **Java 21**: Required to run `agent.jar` for the Jenkins inbound agent.

---

## 2. Code, Secrets, and Preflight

1. **Clone repository**:
   ```powershell
   git clone -b phase2/trial https://github.com/Pariman1419/Markweb.git D:\mark-web
   cd D:\mark-web
   ```

2. **Secrets & Static Data**:
   - Place production `.env` in `D:\mark-web-secrets\.env` (outside repository root).
   - Copy ABS reference files to `D:\mark-web\data\files`.

3. **Run Preflight Verification**:
   ```powershell
   .\scripts\deploy\preflight_17.ps1 -EnvFile D:\mark-web-secrets\.env -PythonExe "<path to python.exe>" -WritePort
   ```
   - Preflight verifies:
     - Clean checkout matching `origin/phase2/trial`
     - Python 3.12, Node, Git, Java (>=17), Docker linux engine
     - Disk free space >= 10 GB
     - Auto-selects first free port (avoids IIS, Jenkins 8080, NPIChecklist 8088, containers, excluded ranges)
     - Internal TCP reachability (Postgres 5432, Oracle 1521, A100 50051, NAS CIFS 445)
     - External downloads (PyPI, npm, Docker Hub, Oracle, GitHub)
     - `.env` required keys present (key names only, secrets never displayed)
     - Firewall inbound allow check
   - If preflight prints a `New-NetFirewallRule` suggestion, run that command in an elevated PowerShell prompt.

---

## 3. Jenkins Inbound Agent Setup

The Jenkins controller runs as a Linux container and cannot directly run Windows `.bat`/PowerShell steps or access Windows host Python/Docker. The build runs on an inbound Windows agent (`mark-web-local`):

1. **Create Node in Jenkins** (`http://localhost:8080`):
   - Manage Jenkins → Nodes → New Node:
     - Name: `mark-web-local`
     - Type: Permanent Agent
     - Remote root directory: `D:\jenkins-agent`
     - Labels: `mark-web`
     - Usage: Use this node as much as possible
     - Launch method: Launch agent by connecting it to the controller (Inbound / WebSocket)
     - Check **Use WebSocket**
2. **Save Secret**:
   - Copy the secret key displayed on the node page into:
     ```
     %USERPROFILE%\.jenkins-agent-secret
     ```
3. **Launch & Automate Agent**:
   - Test launch:
     ```cmd
     set JENKINS_URL=http://localhost:8080
     set JAVA="<path to java.exe 21>"
     scripts\jenkins-agent.bat
     ```
   - Confirm node shows connected/online in Jenkins.
   - Configure a Windows Task Scheduler task to run `scripts\jenkins-agent.bat` at user logon so the agent persists across sign-ins.

---

## 4. Pipeline Job Configuration (`mark-web`)

1. **Create Pipeline Job**:
   - New Item → Pipeline → Name: `mark-web`
   - Build Triggers: Check **Poll SCM** with schedule `H/5 * * * *`
   - Pipeline Definition: **Pipeline script from SCM**
     - SCM: Git
     - Repository URL: `https://github.com/Pariman1419/Markweb.git`
     - Branch Specifier: `*/phase2/trial`
     - Script Path: `Jenkinsfile`
2. **Parameter defaults**: do not type values into "Build with Parameters" (a Poll SCM build resets them).
   Set the per-host defaults as Jenkins global environment variables, see "Per-host parameter defaults" below.

---

### Per-host parameter defaults (Jenkins global environment variables)

Jenkins resets every parameter declared in `Jenkinsfile` to its `defaultValue` on each build, so a build started by Poll SCM never keeps values typed into "Build with Parameters". The defaults therefore come from the Jenkins global environment; the fallbacks are the dev workstation values (the dev PC needs nothing set).

On .17 set these under Manage Jenkins -> System -> Global properties -> Environment variables:

| Variable | Value on .17 | Parameter |
|---|---|---|
| `MARK_DEFAULT_WEB_PORT` | `8093` | `MARK_WEB_PORT` (fallback `8088`) |
| `MARK_DEFAULT_FILES_DIR` | `D:/mark-web/data/files` | `MARK_FILES_HOST_DIR` |
| `MARK_DEFAULT_LOG_DIR` | `D:/mark-web/logs` | `MARK_LOG_HOST_DIR` |
| `MARK_DEFAULT_ENV_FILE` | `D:/mark-web-secrets/.env` | `ENV_FILE` |
| `MARK_DEFAULT_PYTHON` | `C:\Users\ProautomationSV\AppData\Local\Programs\Python\Python312\python.exe` | `PYTHON_EXE` (fallback `python`) |
| `MARK_DEFAULT_WORKER` | `true` | `WORKER` (fallback `false`) |

Save, then run the job once manually: Jenkins re-reads the parameter definitions only after a build has started, so the first build after a change of these variables may still show the old defaults. Check the parameters page of the next build (and `docker ps` for `mark-web-worker-1`).

### NAS volume (`nas_elr`)

- The worker reads the NAS through the compose volume `nas_elr` (CIFS, read-only, `//th1srnas03/ELR` mounted at `/mnt/elr`). The credentials are stored in the volume options, not in the container: Docker creates the volume once, from `NAS_DOMAIN`/`NAS_USER`/`NAS_PASSWORD` in `.env` at that moment.
- After changing the NAS password (or user/domain) the volume still holds the old one. Remove it and redeploy: `docker compose --profile worker stop worker`, `docker volume rm mark-web_nas_elr`, then run the Jenkins build again.
- `NAS_USER` and `NAS_PASSWORD` must not contain "," (the CIFS options are comma-separated). `preflight_17.ps1` fails when they do.
- `NAS_USER` is the plain user name; the domain goes in `NAS_DOMAIN` (default `TH`).
- If the NAS is down or the credentials are wrong, the worker exits with code 2 (`NAS root not readable`) and `restart: unless-stopped` restarts it in a loop until the NAS is back; check `docker logs mark-web-worker-1`.

## 5. Decommissioning Dev PC Deployment

To ensure only **one** worker runs against the production database:
1. Stop any running native worker on the dev workstation (`10.151.97.18`).
2. On dev PC Jenkins (`http://localhost:8080` on dev), change job `mark-web` parameter `DEPLOY=false` (or disable the job) so dev PC functions strictly as CI (unit testing).

---

## 6. Verification Checklist

1. **Jenkins Build on .17**:
   - All stages pass: Preflight → Python tests → Web build → Docker images → Deploy → Smoke test (`smoke OK`) → Real-DB check (8/8 OK).
   - Check `docker ps`: `mark-web-api`, `mark-web-web`, and `mark-web-worker` are running alongside `jenkins`.
2. **Network Access**:
   - From dev PC: `curl.exe -I http://10.153.90.17:<port>/api/ready` -> returns HTTP 200 `{"status":"ready"}`.
   - From Codex server (`10.151.28.3`): `curl -sS -o /dev/null -w "%{http_code}" http://10.153.90.17:<port>/api/ready` -> returns 200.
3. **Worker Logs**:
   - Run `docker logs mark-web-worker-1 --tail 30` -> shows `Starting auto-review worker`, no `NAS root not readable` errors.
4. **End-to-End Walkthrough**:
   - Trigger manual recheck for an ELR (e.g., ADI2607006) via the web UI or API.
   - Worker automatically processes the item and writes the next revision (`changed = manual`).

---

## 7. Production Deployment Record (10.153.90.17)

- **Status**: Live & Verified
- **Base URL**: `http://10.153.90.17:8093`
- **Commit SHA**: `a8a5fde`
- **Jenkins Controller**: Build #3 (`SUCCESS`, 496 tests passed, 3 skipped, Smoke OK, Real-DB check 8/8)
- **Active Containers**: `mark-web-api-1`, `mark-web-web-1` (listening on `0.0.0.0:8093->80/tcp`), `mark-web-worker-1` (connected to CIFS mount `nas_elr` at `/mnt/elr`).
- **End-to-End Verification (from Dev Workstation)**:
  - `curl.exe -i http://10.153.90.17:8093/api/ready` -> HTTP 200 `{"status":"ready"}`
  - `curl.exe -i http://10.153.90.17:8093/api/runs` -> HTTP 401 Unauthorized (`Cache-Control: no-store`, CSP intact)
  - `POST http://10.153.90.17:8093/api/elrs/ADI2607006/recheck` -> HTTP 200 `{"queued": true}` (work item 15)
  - Worker on `.17` processed item 15 to `done`, producing `elr_revision` 4 (`changed: manual`, `run_id: 26`, `result_unchanged: true`, `docs_probe` keys prefixed with `/mnt/elr/ADI/`).
  - Read-only integrity: `check_trial_readonly.py --run 19` confirmed 8/8 OK; runs 1–19 remain completely untouched.
- **Operational Note on Windows User Environment**:
  - Windows user-level environment variables take precedence over values defined in `.env` during Docker Compose variable substitution. Ensure host user environment does not shadow `.env` credentials when creating or recreating CIFS volumes.

