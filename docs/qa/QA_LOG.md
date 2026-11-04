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
- **Correction (R1 triage, `cb9b74e`)**: `BUG == 0` in `d4fd534` hid 101 real BUG rows (see entry "R1 metrics were not measured" below). After triage `GATE_SPEC_V2` = 37 lines (ADI2602092 now correctly HOLD) and BUG = 0.

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
  - **Correction (R1 triage)**: in `d4fd534` this 100% was a default (no blank-Oracle run). Since `9dce03e` the runner re-runs every ELR with a blank `OracleMark` and compares `ExpectedMark` — 668/668 identical.

### Prevention / Rules Learned
- Enforce domain decoupling at the type signature and AST level, backed by unit tests that spy on data access ordering.

---

## [2026-11-04] R1 metrics were not measured: independence default 1.0 and parity hid BUG rows

### Context & Symptom
- **Component / Path**: [`scripts/run_regression.py`](file:///D:/CIM%20Project/mark-web/scripts/run_regression.py), [`mark_engine/regression/metrics.py`](file:///D:/CIM%20Project/mark-web/mark_engine/regression/metrics.py), [`mark_engine/regression/parity.py`](file:///D:/CIM%20Project/mark-web/mark_engine/regression/parity.py)
- **Question / Issue**: `d4fd534` reported Phase 1 accepted (independence 100%, BUG 0) while Oracle agreement was 25.8% and only 374/2,319 lines were `SAME`.

### Root Cause
- `compute_independence(jobs, blank_jobs=None)` returned `1.0` and the runner never produced `blank_jobs`.
- Parity compared R1 `abs_no` (file stem `ABS066973-ENG-1`) with R0 `ABS066973` → every DONE line became `RESOLVER_CHANGED`, which runs before the `SAME`/`BUG` checks.

### Resolution & Code Fix
- Runner re-runs `process_elr` with `OracleMark(elr_no, ())` and passes `blank_jobs`; metric returns `None` if not measured and pairs by `elr_no` (`9dce03e`).
- Parity normalises `abs_no` to `ABS\d{6}`. Result: SAME 374 → 1,385, real BUG 101 exposed and triaged to 0 (`cb9b74e`).

### Prevention / Rules Learned
- A gate metric must fail closed: "not measured" is `None`, never the passing value.
- Before accepting a parity summary, look at the largest non-SAME bucket by `(reason, r1_status, r0_status)` — `RESOLVER_CHANGED` with MATCH on both sides is a classifier bug, not a resolver change.

---

## [2026-11-04] SLR_UNRESOLVED flagged 191 ELRs because of fab-lot / logistics sentences

### Context & Symptom
- **Component / Path**: [`mark_engine/slr/parse.py`](file:///D:/CIM%20Project/mark-web/mark_engine/slr/parse.py) `MARKING_KEYWORDS_RE`
- **Question / Issue**: 803 lines `NEEDS_REVIEW` with `SLR_UNRESOLVED`, 689 of them already equal to Oracle.

### Root Cause
- Coverage counted any sentence with `lot`, `attachment`, `top`, `line` as marking-related. Real unresolved sentences were the SLR header "SPECIAL LOT REQUEST" (63), "This is an IB Lot." (19), "Fab Lot ID … Wafer #" etc.

### Resolution & Code Fix
- Detector now requires words about the mark itself (`brand*`, `mark(ing)`, `logo`, `symbol`, `laser`, `date code`, `line N`, `top/bottom side`, `attachment for instructions`). Parametrised tests use the real sentences. 803 → 86 lines.

### Prevention / Rules Learned
- Calibrate coverage/flag detectors on the real corpus (group the flagged sentences) before trusting the review count.

---

## [2026-11-04] Encoder gaps found by parity: "n DIGIT LOT NUMBER", COUNTRY OF ORIGINENGn, COO abbreviation

### Context & Symptom
- **Component / Path**: [`mark_engine/encode/adi1039.py`](file:///D:/CIM%20Project/mark-web/mark_engine/encode/adi1039.py), [`ocr_fix.py`](file:///D:/CIM%20Project/mark-web/mark_engine/encode/ocr_fix.py), [`compare/engine.py`](file:///D:/CIM%20Project/mark-web/mark_engine/compare/engine.py)
- **Question / Issue**: 101 parity BUG rows, e.g. `3 DIGIT LOT NUMBERYWW` vs `XXXYWW`, `THAILAND#` vs Oracle `THAIL#`, empty TOP 5 vs `THAILAND`.

### Root Cause
- ADI1039 `{Lot-n}` was only matched in abbreviation form; the ABS legend prints the Table 2 preview text ("7 Digit Lot Number"), often glued to the next field.
- `R07-OCRFIX-7` replaced `COUNTRY OF ORIGINENG4` with `""` instead of stripping the drafting suffix.
- Oracle stores the short COO form; ADI1039 5.5.3 allows it when space is short.

### Resolution & Code Fix
- `R07-ADI1039-LOT` preview-text form (`(?<!\d)(\d)\s*DIGIT\s+LOT\s+NUMBER`, 87 lines); OCRFIX-7 strips `ENGn` only (7 lines); compare step 3b `COO_ABBREVIATED` (13 lines, Mark Eng to confirm). No new rule IDs — `01` §7.

### Prevention / Rules Learned
- Every generate token in `adi1039_tokens.csv` needs a test for both its abbreviation and its preview-text form.

---

## [2026-11-04] Resolver used another ELR's SLR from a nested folder; Oracle BOM revision vs mark revision

### Context & Symptom
- **Component / Path**: [`mark_engine/documents/fingerprint.py`](file:///D:/CIM%20Project/mark-web/mark_engine/documents/fingerprint.py), parity
- **Question / Issue**: last 13 BUG rows — ADI2602092 got `ADBMS1804B` (another product), ADI2606077/078 got a different line split, ADI2605013/2606019 `LHYBN` vs `LHYB`.

### Root Cause
- `2_FEB/ADI2602092/ADI2602095/` holds ADI2602095's ABS + SLR; `fingerprint_folder` used `rglob` and took SLR231729.
- ADI2606077/078: folder has ABS068387 rev B and C, Oracle `CUST_BOM_REVISION = B`, but Oracle TOP_MARK matches rev C. R0 picked the ABS that matched Oracle (R03-ONE-ABS, rejected D-06). Not an engine bug.
- `LHYB` in R0 came from `ocr_reocr.csv` (kept with human GT); R1 uses raw OCR.

### Resolution & Code Fix
- Skip nested folders named after an ELR outside the scanned folder's ELR/range; ADI2602092 → `HOLD:SLR_NOT_FOUND` (only e-mails left).
- Parity: `abs_other_revisions` → `RESOLVER_CHANGED`; `r0_reocr` from `ocr_reocr.csv` → `OCR_SOURCE_CHANGED`. BUG 0, unit 189 / regression 3 passed.
- ADI2606077/078 sent to Mark Eng as a data finding ([`09`](file:///D:/CIM%20Project/mark-web/docs/implementation/09-mark-eng-confirmation.md)).

### Prevention / Rules Learned
- Parity reason codes must come from data (files, resolver output), never from hard-coded ELR lists.
- When Oracle BOM revision and the mark disagree, report it — do not choose the document by Oracle.

---

## [2026-11-04] R1 results written to mark_web as a new run

### Context & Symptom
- **Component / Path**: PostgreSQL `mark_web.mark_logic`, [`scripts/load_r1_to_pg.py`](file:///D:/CIM%20Project/mark-web/scripts/load_r1_to_pg.py), [`08-database-tables.md`](file:///D:/CIM%20Project/mark-web/docs/implementation/08-database-tables.md)
- **Question / Issue**: store R1 in the DB without breaking the frozen R0 baseline (run 3); migrations 0001–0003 are not applied.

### Resolution & Code Fix
- User chose option A: insert `run` + `line_result` only (run 4 = `9dce03e`, run 5 = `cb9b74e` current) and one `status_dictionary` row `NEEDS_REVIEW`. One transaction, dry run first, assertion that runs 1–3 row counts are unchanged; sequence reset after the dry run. `logic_rule` untouched.

### Prevention / Rules Learned
- Rerun = new `run_id`; never update runs 1–3. Password only via `MARK_PG_PASSWORD`; the `postgres` password was shared in chat and should be rotated.

---

## [2026-11-04] GRAPHIC_REMARK_CONFLICT flagged 303 lines that were mostly correct

### Context & Symptom
- **Component / Path**: [`mark_engine/generate/generator.py`](file:///D:/CIM%20Project/mark-web/mark_engine/generate/generator.py)
- **Question / Issue**: 303 NEEDS_REVIEW lines with `GRAPHIC_REMARK_CONFLICT` in 94 ELRs; 259 already equal to Oracle; 53 of them already contained a logo.

### Root Cause
- The check ran per side and only looked at YOLO graphics `%`/`{`. MARK_REMARK declares symbols for the part, so every BOTTOM line was flagged; LTC logo `*` and caret `^`, and logos that come from the drawing text (`{LTC-PARTIAL-LOGO}` → `*`), were not recognised.

### Resolution & Code Fix
- Check once per ELR after all lines are built: conflict only if the remark declares a logo and no expected line contains `% { * ^`. 303 → 4 lines (1 ELR).
- The unhidden lines exposed `{e3}` → `<` where MARK_REMARK says `e3 = Pb-free` (ADI2603063); remark (P20) now beats OCRFIX-5 (P50). Data check: remark `e3` (42 ELR) → Oracle never `<`; remark `<` (94 ELR) → Oracle `<`.
- R1: NEEDS_REVIEW 475 → 210, agreement 65.4% → 82.1%, BUG 0.

### Prevention / Rules Learned
- A review flag must be scoped to what it is about (part-level declaration → part-level check) and must use the same symbol set as the encoder.
- Lowering a review flag can reveal hidden BUG rows — always re-run parity after it.

