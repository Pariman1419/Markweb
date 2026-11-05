# Mark Automation (`mark-web`)

> **IC Marking Verification and Automated Approval System for ADI ELRs**  
> **Engine Version:** `0.4.0` | **Status:** Phase 1 Complete · Phase 2 Trial Active · Auto-Review B3/B4 In Progress

---

## 1. Executive Summary

**Mark Automation (`mark-web`)** is an automated IC marking verification and quality governance platform engineered for Analog Devices Inc. (ADI) Engineering Lot Requests (ELRs). 

Traditionally, IC package markings (text and symbols printed on semiconductor chips) were manually compared against customer drawings, lot requests, and ERP records. `mark-web` provides:
1. **Automated Specification Decoding**: Derives expected top and back markings directly from engineering source documents (ABS drawings, Special Lot Requests [SLR], Symbol ADI catalog, ADI1039 standards, and ELR remarks) **without seeing ERP target values**.
2. **AI Computer Vision**: Integrates high-precision OCR and YOLO symbol detection running on an A100 GPU inference server.
3. **Automated Multi-Gate Verification**: Executes an ordered, cheap-to-expensive gate pipeline (G0 to G5) checking ERP step states, customer assembly status, document integrity, and row capacity.
4. **Interactive Review & Approval Dashboard**: A modern web interface where Mark Engineers review discrepancies, submit line corrections, and issue cryptographically audited approvals.

---

## 2. System Architecture & Components

The repository is organized into isolated, decoupled components following Clean Hexagonal Architecture:

```
mark-web/
├── mark_engine/              # Pure domain core (zero network/DB IO in core algorithms)
│   ├── domain/               # Frozen dataclasses (ExpectedMark, JobResult, LineComparison)
│   ├── rules/                # Frozen rule manifests (RV-2026-11-04-R0) and registry
│   ├── documents/            # NAS document locator, SHA256 fingerprinting, resolver
│   ├── abs/                  # ABS brand page extraction, layout builder, symbol mapping
│   ├── slr/                  # Special Lot Request parser & coverage analyzer
│   ├── encode/               # Encoders: OCR fix, Symbol ADI, ADI1039 Rev AE, Remark
│   ├── generate/             # ExpectedMarkGenerator (Oracle-independent AST-proven)
│   ├── compare/              # ComparisonEngine (MATCH, MATCH_SLR, MATCH_LOT, DIFF)
│   └── pipeline.py           # process_elr orchestrator enforcing G0–G5 gates
├── services/
│   ├── api/                  # FastAPI backend (mark_api) with auth, CSRF, LRU cache
│   ├── worker/               # Background task consumer (PostgreSQL SKIP LOCKED queue)
│   └── inference/            # B4 gRPC client & GPU/CPU fallback inference service
├── web/                      # React 18 + TypeScript + Vite + Tailwind CSS dashboard
├── migrations/               # PostgreSQL schema migrations (mark_logic & mark_app)
├── docs/                     # Specifications, implementation plans, and QA logs
│   ├── qa/QA_LOG.md          # Technical root causes & architecture decisions log
│   ├── superpowers/plans/    # Detailed phase execution plans
│   └── superpowers/specs/    # System design specifications
└── scripts/                  # CI/CD verification, regression runners, and database loaders
```

### Component Responsibility Matrix

| Component | Technology | Primary Function | Primary Port / Location |
|---|---|---|---|
| **`mark_engine`** | Python 3.10+ | Pure core logic: layout, decoding, generation, comparison | Library package |
| **`mark_api`** | FastAPI, Uvicorn | REST API, session authentication, CSRF, metrics, WebSocket | `:8000` (internal) / `:8088` (NGINX) |
| **`web`** | React, Vite, Tailwind | Engineer dashboard, image zoom preview, review forms | `:5173` (dev) / `:80` (prod container) |
| **B4 Inference** | gRPC, PyTorch, YOLO | Optical character recognition & symbol classification | `10.151.28.9:50051` (A100 server) |
| **Database** | PostgreSQL 15+ | Stores runs, line results, reviews, approvals, audit logs | `10.151.28.2:5432` (`mark_web`) |
| **Job Scheduler**| Apache Airflow | Polls Oracle every 15 min (`mark_elr_polling`) | `10.151.28.3` |

---

## 3. Invariants & Hard Governance

The project strictly enforces 6 non-negotiable architectural invariants:

1. **Oracle Independence (Zero-Leakage Invariant)**:  
   The expected mark must be synthesized exclusively from customer documentation. `ExpectedMarkGenerator.generate()` has **zero access** to Oracle `TOP_MARK1..5` or `BACK_MARK1..5`. This independence is statically verified in CI via Python AST scanning (`test_generator_independence.py`) and dynamic proxy spies.
2. **Immutability of Domain Structures**:  
   All core domain models (`ExpectedMark`, `ExpectedLine`, `ExpectedToken`, `JobResult`, `LineComparison`) are defined as `@dataclass(frozen=True, slots=True)` with immutable tuple/frozenset collections.
3. **No Singular "PASS" Status**:  
   Quality and compliance cannot be reduced to a binary boolean. The system strictly employs multi-axis evaluation:
   - `processing_status`: `DONE` | `HOLD` | `NOT_ELIGIBLE` | `FAILED`
   - `verification_status`: `MATCH_ALL` | `HAS_WARNING` | `HAS_DIFF` | `NOT_VERIFIABLE`
   - `approval_status`: `PENDING_REVIEW` | `APPROVED` | `REJECTED` | `NOT_REQUIRED`
   - `line_status`: `MATCH` | `MATCH_SLR` | `MATCH_SHIFT` | `MATCH_LOT` | `DIFF` | `NEEDS_REVIEW` | `NOT_MEASURABLE`
4. **Strict Dual-Document Requirement (Spec V2)**:  
   Both ABS drawing and SLR specification must exist on NAS. Missing either document immediately halts the job with `HOLD:ABS_NOT_FOUND` or `HOLD:SLR_NOT_FOUND`.
5. **Rule Precedence Hierarchy (Lower numeric value wins)**:  
   - Priority 10: Special Lot Request (`SLR`)
   - Priority 20: Mark Remark (`MARK_REMARK` from ELR)
   - Priority 30: Symbol ADI Catalog (`Symbol ADI.xlsx`)
   - Priority 40: ADI1039 Standard Rev AE (ABS/SLR only; raises `ValueError` on TRS)
   - Priority 50: OCR Correction Rules
6. **Immutable Rule Version Manifests**:  
   Regression tests run against frozen rule manifests (`RV-2026-11-04-R0.json`) and fixed SHA256 hashes (`Symbol ADI.xlsx`: `7858dc40...`).

---

## 4. Quick Start & Developer Guide

### Prerequisites
- Python 3.10 or 3.11
- Node.js 18+ and npm
- Docker & Docker Compose (optional for local full-stack run)
- Access to company network / VPN for NAS (`\\th1srnas03\ADI`) and Oracle ACTLDBA

### Local Python Environment Setup

```bash
# 1. Clone repository and navigate
git clone git@github.com:Pariman1419/Markweb.git
cd Markweb

# 2. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # On Windows PowerShell
# source .venv/bin/activate    # On Linux/macOS

# 3. Install package with dev and API dependencies
pip install -e ".[dev,api]"

# 4. Copy environment template and configure credentials
cp .env.example .env
# Edit .env to set DB and Oracle read-only credentials

# 5. Run full test suite (370+ unit tests)
python -m pytest tests/unit -v
```

### Running Full-Stack Locally via Docker Compose

```bash
# Build and start API and Web frontend
docker compose up -d --build

# Inspect running containers
docker compose ps
# Web application available at: http://localhost:8088
# API Docs available at:        http://localhost:8088/docs
```

### Running Frontend and Backend Separately (Development Mode)

```bash
# Terminal 1: Backend API
export PYTHONPATH=".:services/api"
export MARK_FILES_ROOT="data/files"
python -m uvicorn mark_api.app:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Vite React Frontend
cd web
npm install
npm run dev
# Frontend runs on http://localhost:5173 with API proxying to :8000
```

---

## 5. Key Scripts & Operational Commands

| Script | Purpose | Example Command |
|---|---|---|
| `scripts/diff_runs.py` | Compares two regression runs, detecting status diffs, false positives, and unexpected shifts | `python scripts/diff_runs.py --base artifacts/run-19 --new artifacts/run-gates` |
| `scripts/check_trial_readonly.py` | Non-blocking read-only acceptance check verifying PostgreSQL database health & data privacy | `python scripts/check_trial_readonly.py --run 19` |
| `scripts/e2e_walkthrough.py` | End-to-end automated Playwright test executing complete login-preview-review-approve cycle | `python scripts/e2e_walkthrough.py --run 19` |
| `scripts/run_blind.py` | Executes offline regression against blind test datasets | `python scripts/run_blind.py --input artifacts/blind-2026h2 --workers 3` |
| `scripts/load_r1_to_pg.py` | Atomic transactional loader pushing regression results to `mark_logic` | `python scripts/load_r1_to_pg.py artifacts/run-14 --note "R1 run" --commit` |

---

## 6. Project Documentation Index

Detailed engineering documentation is structured as follows:

| Document | Description |
|---|---|
| [`architecture.md`](file:///D:/CIM%20Project/mark-web/architecture.md) | **System Architecture**: High-level designs, pure core layers, gRPC B4 inference, and deployment topology |
| [`database.md`](file:///D:/CIM%20Project/mark-web/database.md) | **Database Specification**: Complete schema of `mark_logic` and `mark_app`, ER diagram, and migration logs |
| [`workflow.md`](file:///D:/CIM%20Project/mark-web/workflow.md) | **End-to-End Workflows**: Detailed G0–G5 gate pipeline, Airflow polling, user search, and approval flows |
| [`HANDOFF.md`](file:///D:/CIM%20Project/mark-web/HANDOFF.md) | **Living Handoff Log**: Daily development updates, open tasks, decision logs, and agent synchronization |
| [`docs/qa/QA_LOG.md`](file:///D:/CIM%20Project/mark-web/docs/qa/QA_LOG.md) | **Technical QA & Knowledge Base**: Root cause analysis (RCA), bug investigations, and preventive rules |
| [`migrations/README.md`](file:///D:/CIM%20Project/mark-web/migrations/README.md) | **Database Migrations Guide**: Rollout sequence (M0 through 0006) and rollback instructions |

---

## 7. Version History & Milestones

- **`0.1.0` (2026-11-04)**: Phase 1 complete. 12/12 core tasks implemented with 100% test independence and 0 bugs.
- **`0.2.0` (2026-11-04)**: R1 baseline frozen (`FREEZE-R1.json`), rule provenance audit completed.
- **`0.3.0` (2026-11-05)**: Phase 2 Web & Trial platform. Migration 0004 & 0005 applied. 12/12 E2E walkthrough green.
- **`0.4.0` (2026-11-05)**: Auto-Review engine gates implemented:
  - Gate G0: `CURRENT_STEP = '6'` (Mark Eng review) selector.
  - Gate G1: `CUST_ASSY_LOT == 'TBD'` hold gate.
  - Gate G2: SLR `SPECIAL INSTRUCTIONS` requirement isolation.
  - Gate G5: Row over 5 placed content protection (filtering empty template rows).
