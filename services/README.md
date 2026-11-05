# Phase 1 deployment boundaries

The current Phase 1 application is an offline/batch engine, not a set of network APIs. Deploy the following units separately; do not start a web service or scheduler from this directory.

| Deployment unit | Files | Host and responsibilities |
|---|---|---|
| Engine worker | `mark_engine/`, `pyproject.toml`, selected `scripts/` | Application host: resolve documents, generate and compare marks, prepare snapshots/reports and load a new DB run. Oracle and NAS credentials are required only here. |
| Inference worker | `services/inference/`, approved model files | AI host (A100): read extracted PNG batch, produce inference cache. No Oracle or PostgreSQL credentials. |
| Database migration | `migrations/0004_line_result_review_columns.sql` | DBA-controlled PostgreSQL host/session. Run the UP section separately; no application credential needs DDL. |
| Reference data | `mark_engine/rules/data/`, `mark_engine/encode/data/` | Ship with the engine package, versioned together with engine code. |

Batch exchange is through a secured staging directory: the engine host sends `images/*.png`; the AI host returns `det_rec.json` and `detections.json`, and the engine-side re-OCR client produces `reocr.csv` and model provenance. The receiving runner validates batch completeness and hashes before use. Customer files and secrets do not belong in Git or a deploy bundle.

The separated source bundles are available under ignored `artifacts/release-phase1/`. The frozen holdout was executed and recorded as run 17; its limitations and low coverage are in `docs/implementation/11-blind-test-2026h2.md`. These batch bundles are not production online services: the web UI, orchestration and independently deployable network services are Phase 2 work.

---

## Phase 2 Trial Deployment (10.153.90.17)

The trial environment runs as a standalone Docker Compose stack hosting the FastAPI backend and NGINX-served React frontend.

### Pre-flight Checks on Host (10.153.90.17):
```bash
docker compose version
pg_isready -h 10.151.28.2 -p 5432
```

### Launch Services:
```bash
# 1. Copy repository to host (excluding artifacts/ and secrets)
# 2. Configure .env with MARK_PG_* and MARK_FILES_ROOT
# 3. Mount files storage and start containers:
docker compose up -d --build
# on a workstation where port 80 is taken: MARK_WEB_PORT=8088 docker compose up -d --build
```

### Verification Endpoints:
- Ready probe: `curl -I http://10.153.90.17/api/ready` (expect 200)
- NGINX rate limit check: Rapidly issue 7 requests to `POST /api/auth/login` (7th returns 429)
- Static files caching: `curl -I http://10.153.90.17/api/files/...` (expect `Cache-Control: private, max-age=86400` and CSP)
- API caching: `curl -I http://10.153.90.17/api/runs` (expect `Cache-Control: no-store` and CSP)

### Real-DB Acceptance Check (Read-Only):
To verify that trial run data in PostgreSQL matches expected cards, counts, detail endpoints, and admin queries without altering database state:
```bash
python scripts/check_trial_readonly.py --run 19 [--env-file PATH] [--sample 20]
```
The script runs 8 sequential checks (`runs`, `dashboard_cards`, `elrs_total`, `elrs_pages`, `elr_detail`, `oracle_raw`, `expected_match`, `admin_reads`), prints one `OK` or `FAIL` line per check with short summaries (never printing customer marks, SLR texts, or paths), and exits 0 on success. In CI/CD, the Jenkins `Real-DB check` stage executes this automatically after the smoke test.

## CI/CD with Jenkins (workstation, http://localhost:8080)

The pipeline is defined in `Jenkinsfile` at the repo root. It runs on a Windows agent in this order: Preflight → Python tests (venv + pytest, JUnit report) → Web build (`npm ci`, `npm run build`) → Docker images → Deploy (`docker compose up -d`, project `mark-web`) → Smoke test (`/api/ready` 200, and `/api/runs` 401 with `no-store` + CSP).

One-time setup:
1. **Agent:** the Jenkins service runs as LocalSystem. The workstation's domain policy denies "Log on as a service" to user accounts, so builds run on an inbound agent started under the user's own account.
   - Manage Jenkins → Nodes → New Node `mark-web-local`: Permanent Agent, label `mark-web`, remote root `D:\jenkins-agent`, launch "by connecting it to the controller".
   - Save the agent secret to `%USERPROFILE%\.jenkins-agent-secret`, then run `scripts\jenkins-agent.bat` and keep it open while builds run.
2. **No Jenkins credentials are needed.**
   - The repo is public, so it is cloned over HTTPS.
   - The Deploy stage copies the `.env` from the agent host (parameter `ENV_FILE`) and deletes the copy afterwards.
3. **Job:** New Item → *Pipeline* `mark-web`, then Definition *Pipeline script from SCM* with:
   - Git URL `https://github.com/Pariman1419/Markweb.git`
   - branch `*/phase2/trial`
   - script path `Jenkinsfile`
   - trigger: *Poll SCM* `H/5 * * * *`

Parameters:
- `DEPLOY`: default true.
- `MARK_WEB_PORT`: 8088 on the workstation (IIS uses 80, Jenkins uses 8080); 80 on 10.153.90.17.
- `MARK_FILES_HOST_DIR`: the folder with the ABS images, which are not in git.
- `PYTHON_EXE`: full path if `python` is not on the service PATH.
