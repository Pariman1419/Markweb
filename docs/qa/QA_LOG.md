# Mark Automation — Technical Q&A & Knowledge Base Log

> Managed via the `/qa-logger` skill to record architectural decisions, bug investigations, root causes, and verification resolutions for long-term project memory.

---

## [2026-11-04] Verification of Symbol and Logic Rule Data between Offline Package and PostgreSQL Database

### Context & Symptom
- **Component / Path**: `mark_engine/encode/data/`, `mark_engine/rules/data/`, PostgreSQL `mark_web` (`10.151.28.2:5432/mark_logic`)
- **Question / Issue**: In Phase 1 implementation, does the engine fetch Symbol ADI and rule metadata dynamically from PostgreSQL, or does it read from CSV / JSON files inside the package? Has the data already inserted in the DB been verified?

### Root Cause
- Under Phase 1 requirements (offline pure core execution), the engine is intentionally designed with zero live network or DB dependencies to guarantee 100% deterministic regression test runs and test execution in offline / CI environments.

### Resolution & Code Fix
- **Live DB Audit**: Queried `10.151.28.2:5432/mark_web` schema `mark_logic` directly and verified:
  - `logic_rule`: 44 rules (all columns including `rule_stage`, `priority`, `rule_origin`, `document_scope` match 100%).
  - `symbol_profile`: 29 symbols (matches `Symbol ADI.xlsx (Summary)`).
  - `encoder_alias`: 17 symbols (aliases like `•` -> pin1 dot, `<` -> pin1 ˂).
  - `adi1039_token`: 42 tokens (matches ADI1039 Rev AE).
  - `remark_profile`: 598 rows (ELR legend declarations).
- **Offline Artifact Sync**: In Phase 1, `scripts/build_rule_version.py` and `scripts/build_encoder_data.py` snapshot this exact data into `RV-2026-11-04-R0.json`, `symbol_adi_r0.json`, and `adi1039_tokens.csv`.
- **Phase 2 Transition**: In Phase 2 (FastAPI Backend & Dramatiq Workers), a live database repository layer will connect to `mark_web` so updates in `mark_logic` or UI rule approvals propagate directly without code changes.

### Prevention / Rules Learned
- Always keep frozen rule version manifests (e.g. `RV-2026-11-04-R0`) immutable for regression testing, while allowing live DB repositories in production phases to load versioned rules.

---

## [2026-11-04] Strict Spec V2 SLR Gate vs Legacy Run 3 Gate Relaxation

### Context & Symptom
- **Component / Path**: [`mark_engine/documents/resolve.py`](file:///D:/CIM%20Project/mark-web/mark_engine/documents/resolve.py), [`mark_engine/pipeline.py`](file:///D:/CIM%20Project/mark-web/mark_engine/pipeline.py)
- **Question / Issue**: In Run 3, ELRs without an SLR were allowed to proceed if Oracle `CUST_REQ_NO` was empty or `N/A`. Does the new V3 architecture allow this?

### Root Cause
- Run 3 relaxed the SLR gate to maximize coverage on Jan–Jun historical data. However, the system design spec anti-goal states: *"Jobs with incomplete document checks (missing SLR) must NEVER be reported as MATCH_ALL — they must always enter HOLD"*.

### Resolution & Code Fix
- In Task 5 and Task 11, `resolve_documents()` strictly enforces `HOLD:SLR_NOT_FOUND` whenever an SLR is absent from the folder, regardless of whether Oracle `CUST_REQ_NO` is empty.
- In Task 12 regression comparison, these 33 divergent lines were cleanly categorized under parity reason code `GATE_SPEC_V2` with zero unexplained bugs (`BUG == 0`).

### Prevention / Rules Learned
- Anti-goals defined in the specification take precedence over legacy heuristic shortcuts. Never condition business rules on Oracle data fields when the goal is independent specification verification.

---

## [2026-11-04] Complete Oracle Mark Decoupling & Zero-Leakage Invariant in Expected Mark Generation

### Context & Symptom
- **Component / Path**: [`mark_engine/generate/generator.py`](file:///D:/CIM%20Project/mark-web/mark_engine/generate/generator.py), [`mark_engine/compare/engine.py`](file:///D:/CIM%20Project/mark-web/mark_engine/compare/engine.py)
- **Question / Issue**: Ensuring that `ExpectedMark` is generated with zero visibility into Oracle's `TOP_MARK1..5` or `BACK_MARK1..5`.

### Root Cause
- In the legacy prototype scripts (`experiments/abs_vs_db`), SLR candidate selection and fallback text were conditioned on matching Oracle's database values, inflating accuracy to 98.7% by "explaining Oracle" rather than verifying from source documents.

### Resolution & Code Fix
- Implemented Task 9 with strict architectural boundaries:
  - `generate_expected()` has no parameter, type annotation, or import of `OracleMark`.
  - Static AST scanner in [`tests/unit/test_generator_independence.py`](file:///D:/CIM%20Project/mark-web/tests/unit/test_generator_independence.py) asserts zero occurrences of `OracleMark`, `TOP_MARK`, or `BACK_MARK` in `generator.py`.
  - Dynamic `OracleProxy` spy in [`tests/unit/test_pipeline.py`](file:///D:/CIM%20Project/mark-web/tests/unit/test_pipeline.py) asserts zero attribute accesses on `OracleMark` until `generate_expected` has completely finished.
  - Regression metric `independence` verified at **100.0%** across all 668 historical jobs.

### Prevention / Rules Learned
- Enforce domain decoupling at the type signature and AST level, backed by unit tests that spy on data access ordering.
