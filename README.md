# mark-web

Mark verification for ADI ELRs. The engine builds the expected TOP/BOTTOM mark from ABS (OCR + symbol detection), SLR and REMARK, and compares it with the values entered in Oracle ACTL / ACTIVEL. The web app lets a Mark Engineer review and approve the results.

| Part | Path |
|---|---|
| Engine (batch) | `mark_engine/`, `scripts/` |
| Inference batch (AI server) | `services/inference/` |
| API (FastAPI) | `services/api/mark_api/` |
| Web (React + Vite) | `web/` |
| DB migrations (PostgreSQL `mark_web`) | `migrations/` |
| Design, plans and status | `docs/superpowers/`, `HANDOFF.md`, `docs/qa/QA_LOG.md` |

## Run locally

Secrets go in `.env` (git-ignored); `.env.example` lists the variable names.

```bash
pip install -e ".[dev,api]"
python -m pytest tests -q

# API + NGINX on http://localhost (reads .env; ABS images under data/files)
docker compose up -d --build
```

Without Docker:

```bash
PYTHONPATH=.:services/api MARK_FILES_ROOT=data/files python -m uvicorn mark_api.app:app --port 8000
cd web && npm ci && npm run dev    # http://localhost:5173, proxies /api to :8000
```

Deployment to the application host is described in `services/README.md`.
