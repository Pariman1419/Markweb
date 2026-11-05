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
