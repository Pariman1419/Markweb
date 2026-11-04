# Phase 1 deployment boundaries

The current Phase 1 application is an offline/batch engine, not a set of network APIs. Deploy the following units separately; do not start a web service or scheduler from this directory.

| Deployment unit | Files | Host and responsibilities |
|---|---|---|
| Engine worker | `mark_engine/`, `pyproject.toml`, selected `scripts/` | Application host: resolve documents, generate and compare marks, prepare snapshots/reports and load a new DB run. Oracle and NAS credentials are required only here. |
| Inference worker | `services/inference/`, approved model files | AI host (A100): read extracted PNG batch, produce inference cache. No Oracle or PostgreSQL credentials. |
| Database migration | `migrations/0004_line_result_review_columns.sql` | DBA-controlled PostgreSQL host/session. Run the UP section separately; no application credential needs DDL. |
| Reference data | `mark_engine/rules/data/`, `mark_engine/encode/data/` | Ship with the engine package, versioned together with engine code. |

Batch exchange is through a secured staging directory: the engine host sends `images/*.png`; the AI host returns `det_rec.json`, `detections.json` and, once implemented, `reocr.csv` plus model provenance. The receiving runner must validate batch completeness and hashes before use. Customer files and secrets do not belong in Git or a deploy bundle.

These are file and responsibility boundaries, not yet production deployment packages: cache validation, re-OCR, reproducible model verification and official blind-run entry points are still incomplete. The web UI, orchestration and independently deployable online services are Phase 2 work.
