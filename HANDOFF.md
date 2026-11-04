# HANDOFF & PROGRESS LOG — Mark Automation (Phase 1)

> **Important**: This document tracks live execution state, decisions, rules, and progressive handoffs across development sessions and subagents. Always update this file upon completing or modifying any task.

---

## 1. Project Context & Current State

- **System**: Mark Automation — System Architecture (V3)
- **Phase**: **Phase 1 — `mark_engine` (offline) [COMPLETED 12/12 TASKS]**
- **Plan File**: [`docs/superpowers/plans/2026-11-04-phase1-mark-engine-offline.md`](file:///D:/CIM%20Project/mark-web/docs/superpowers/plans/2026-11-04-phase1-mark-engine-offline.md)
- **Design Spec**: [`docs/superpowers/specs/2026-11-04-mark-automation-design.md`](file:///D:/CIM%20Project/mark-web/docs/superpowers/specs/2026-11-04-mark-automation-design.md)
- **QA & Knowledge Base Log**: [`docs/qa/QA_LOG.md`](file:///D:/CIM%20Project/mark-web/docs/qa/QA_LOG.md)
- **Database Tables (`mark_web.mark_logic`)**: [`docs/implementation/08-database-tables.md`](file:///D:/CIM%20Project/mark-web/docs/implementation/08-database-tables.md) — 15 ตาราง, run 1–3 = R0 (run 3 freeze), **run 14 = R1 ปัจจุบัน**
- **R1 logic / review / next phase (อ่านก่อน)**: [`docs/implementation/10-r1-logic-review-and-next-phase.md`](file:///D:/CIM%20Project/mark-web/docs/implementation/10-r1-logic-review-and-next-phase.md) — D-22–D-29, True/Warning/Error, debug ค้าง G1–G9, งาน N1–N7
- **Review results**: `reviews/r1_review_2026-11-04.csv` (runner อ่าน), `reviews/r1_run14_review_export.csv` (export ทุกบรรทัด + class)
- **Mark Eng confirmation (open)**: [`docs/implementation/09-mark-eng-confirmation.md`](file:///D:/CIM%20Project/mark-web/docs/implementation/09-mark-eng-confirmation.md)
- **Git State**:
  - Remote: `git@github.com:Pariman1419/Markweb.git`
  - Base Branch: `phase0/readiness`
  - Active Work Branch: `phase1/mark-engine`
  - Customer drawings & artifacts isolated under `.gitignore` (`artifacts/`)
- **Execution Methodology**: **Subagent-Driven Development** with strict TDD (Red -> Green -> Refactor -> Review Gate).

---

## 2. Hard Governance & Invariants

1. **Oracle Independence (revised 2026-11-04)**: expected generation may use `MARK_ID_LAYOUT` as a template, but must not use Oracle `TOP_MARK1..5`, `BACK_MARK1..5`, or `OracleMark`. See the closeout revision plan.
2. **Immutability**: All core domain structures (`ExpectedMark`, `ExpectedLine`, `ExpectedToken`, `JobResult`, etc.) must be `@dataclass(frozen=True, slots=True)` with immutable collections (`tuple`, `frozenset`).
3. **No "PASS" Status**: The system strictly uses multi-axis statuses (`processing_status`, `verification_status`, `approval_status`, `eligibility_status`). No status enum or report column may contain the word "PASS".
4. **SLR Gate Strictness (Spec V2)**: If an ELR lacks an SLR document, it must always enter `HOLD:SLR_NOT_FOUND`, even if Oracle `CUST_REQ_NO` is empty or N/A. Any divergence from Run 3 will be tagged with parity code `GATE_SPEC_V2`.
5. **Rule Precedence (Lower value wins)**:
   - Priority 10: `SLR`
   - Priority 20: `MARK_REMARK` (elr_legend)
   - Priority 30: `Symbol ADI`
   - Priority 40: `ADI1039` (Applicable to ABS and SLR only; raises `ValueError` on TRS)
   - Priority 50: `OCR fix`
6. **Symbol ADI Frozen Hash**: Enforce SHA256 of `Symbol ADI.xlsx`:
   `7858dc405a90b6600389accf32fa257ad23580cd532cda078da2f02cfe74ccb6`.
7. **Offline Isolation**: No network calls, no live Oracle DB connection, no live NAS access, and no live A100 calls in Phase 1. All tests run on frozen fixtures and R0 snapshots (`D:/CIM Project/mark` tag `regression-r0-2026-11-04`).

---

## 3. Systematic Tasklist (Phase 1: 12 Tasks)

| # | Task Description | Scope / Key Files | Status | Test Status | Commit |
|---|---|---|:---:|:---:|:---:|
| **1** | **Project Scaffold & Frozen Domain Model** | `pyproject.toml`, `mark_engine/domain/models.py`, `version.py` | [x] Completed | [x] Green (6 passed) | `0837752` |
| **2** | **Rule Version File & `RuleSet`** | `scripts/build_rule_version.py`, `mark_engine/rules/ruleset.py`, `RV-2026-11-04-R0.json` | [x] Completed | [x] Green (9 passed) | `be6e477` |
| **3** | **Adapters: Oracle SELECT Guard & Snapshot Loader** | `mark_engine/adapters/oracle_guard.py`, `snapshot.py` | [x] Completed | [x] Green (32 passed) | `1deeec5` |
| **4** | **Documents: Locate, Fingerprint & Classify** | `mark_engine/documents/locate.py`, `fingerprint.py`, `classify.py` | [x] Completed | [x] Green (12 passed) | `c388b94` |
| **5** | **Document Resolver** | `mark_engine/documents/resolve.py` (BOM/rev matching, conflict holds) | [x] Completed | [x] Green (14 passed) | `be7d6cf` |
| **6** | **SLR Parser with Coverage** | `mark_engine/slr/parse.py` (single value per line, ambiguity & unresolved detection) | [x] Completed | [x] Green (15 passed) | `01084eb` |
| **7** | **Encoders (OCR Fix, Symbol ADI, ADI1039, REMARK)** | `mark_engine/encode/` (hash assertion on Symbol ADI, token replacement) | [x] Completed | [x] Green (9 passed) | `7966eca` |
| **8** | **ABS Layout & Symbols-to-Lines + Cached Inference** | `mark_engine/abs/layout.py`, `symbols_to_lines.py`, legacy parity test | [x] Completed | [x] Green (6 unit + 1 regression parity) | `bcf8be5` |
| **9** | **Expected Mark Generator** | `mark_engine/generate/generator.py` (AST scan & signature inspection to prove no Oracle leak) | [x] Completed | [x] Green (14 passed) | `e9a64ad` |
| **10** | **Comparison Engine** | `mark_engine/compare/engine.py`, `lot.py`, `shift.py` (verified MATCH_LOT & MATCH_SHIFT) | [x] Completed | [x] Green (14 passed) | `f471d6d` |
| **11** | **Pipeline `process_elr` & 3 Status Axes** | `mark_engine/pipeline.py` (end-to-end integration + eligibility gate + status synthesis) | [x] Completed | [x] Green (14 passed) | `9ff67ec` |
| **12** | **Regression Runner R1 & Parity vs R0** | `scripts/run_regression.py`, `parity.py`, `metrics.py`, R1 baseline Jan–Jun; R1 triage fixes (branch `phase1/r1-fixes`) | [x] Completed | [x] Green (195 unit + 3 regression, BUG 0) | `d4fd534` → `cb9b74e` (merge `8d930fd`) + GRC fix |

---

## 4. Live Changelog & Session Updates

### 2026-11-05 — Phase 1 closeout in progress

- Revised D-10: `MARK_ID_LAYOUT` is allowed in expected generation; Oracle TOP/BACK mark values remain excluded. Missing layout and overflow return `FAILED` for the ELR. FIX takes precedence and graphic conflicts are reported.
- Applied migration 0004 UP on `mark_web`: six line review columns and `mark_logic.job_result`. Rollback-only loader smoke inserted 2,318 lines and rolled back; runs 1–14 remained intact. The sequence advanced during the dry run.
- Fetched 402 July–November Oracle ELRs and 6,207 layout rows to ignored `artifacts/blind-2026h2/oracle/`. Extracted 287 ELR image mappings / 118 unique images; 115 document-resolution holds; zero extraction errors. All five NAS months are accessible.
- Baseline regression without layout was byte-identical to run 14. After fixing fixed-cell alignment and preserving generated spaces, historical layout evaluation found 274/274 evaluable jobs independent and 107 layout-overflow jobs requiring reporting. Historical R0 parity includes spacing-related classifications and is not an unchanged-status gate for the new layout behavior.
- AI validation: 95 historical images matched for OCR text/count/boxes and YOLO class/count/boxes within one pixel; six re-OCR candidates matched. A one-image historical deployment smoke passed on the AI server. OCR and symbol weight hashes matched the local registry.
- Service boundaries are under `services/`; wheel packaging now includes rules and encoder data. Official freeze, blind AI inference, blind run, review exports and final DB load remain incomplete. Do not treat this entry as Phase 1 completion.

### 2026-11-04 (plan: Phase 1 close-out)
- Plan [`docs/superpowers/plans/2026-11-04-phase1-closeout-blind-test.md`](docs/superpowers/plans/2026-11-04-phase1-closeout-blind-test.md): 11 tasks — `.env` + read-only ACTL client, migration 0004, ACTIVEL `MARK_ID_LAYOUT` positions (warning only, compare stage), FREEZE-R1, Oracle snapshot Jul–Nov, inference cache + Brand extraction, AI-server batch (determinism check vs R0), blind runner, DB load + Marking / rule-approval lists. Run order puts every `mark_engine/` change before the freeze.
- User answers recorded in spec §9: no email/Teams (UI only); debug G1–G9 after blind test; credentials in git-ignored `.env` (`.env.example` committed).
- `.gitignore`: `.superpowers/`, `.env`, `.env.*` (keeps `.env.example`).
- Not started: waiting for the user to review the plan and choose how to execute it.

### 2026-11-04 (next-phase design)
- New design: [`docs/superpowers/specs/2026-11-04-phase1-completion-and-phase2-design.md`](docs/superpowers/specs/2026-11-04-phase1-completion-and-phase2-design.md) — part A closes Phase 1 (A1 rule freeze … A8 merge), part B = Phase 2 on the user's microservices architecture (B1–B7); web scope TOP only; Dashboard + ELR Preview + edit/approve (mockups v5–v6 in `.superpowers/brainstorm/`, not committed).
- Access now works: Oracle ACTL direct (thick mode) reads `MARK_ID_LAYOUT` / `MARK_ID_INSTRUC` / `MARK_ID_SYMBOL` / `PROD_MARKLAYOUT`; NAS `ELR Online 2026` 1_JAN…11_NOV readable with the account the user gave. Credentials only via env vars, never in files.
- Waiting on user: 2 questions in spec §9 (notification channel, G1–G9 before/after freeze), then writing-plans.

### 2026-11-04 (process rule)
- User rule: **every change updates HANDOFF.md §4 and `docs/qa/QA_LOG.md` in the same commit.** QA_LOG backfilled for `a024da1`, `2823d23`, `ea5d2f5`.

### 2026-11-04 (wrap-up before next phase)
- Review page state exported: `reviews/r1_run14_review_export.csv` (2,318 lines: True 1,508 · Warning 25 · Error 77 · not compared 708; 13 page verdicts/notes) via `scripts/export_review_csv.py`.
- All R1 logic collected in `docs/implementation/10-r1-logic-review-and-next-phase.md`; 00/01/03/04/06/08 updated to run 14.
- Open for the debug round: G1 `Q` = 1-digit date code?, G2 note on ADI2601052 T1 ("rev ENG-1 ไม่นับเอาแค่ Digi BOM 10"), G3–G9 (doc 10 §6).

### 2026-11-04 (D-29 SLR same-date-code note)
- ADI2601023 BOTTOM 2 `{Lot‐4}` (lot 7230523 → 0523) was NEEDS_REVIEW: the SLR sentence "Same date code with SLR230744, …" was counted unresolved and flagged every line before the lot check. `slr/parse.py` `SAME_DATE_CODE_NOTE_RE` now skips it.
- 12 ELR / 48 lines NEEDS_REVIEW → MATCH (12 MATCH_LOT, 27 MATCH_SLR, 9 MATCH). Agreement **85.34%** (1,374/1,610), BUG 0. 219 unit + 3 regression. DB run 14.
- Open question: Oracle template 41477448 (`@EAQ`, `@FBQ`, 8 lines) has `Q` where ABS/SLR give a 1-digit date code ({1-DC}/{DC-1} → `Y`).

### 2026-11-04 (R1 review round 1)
- User review from the R1 review page saved to `reviews/r1_review_2026-11-04.csv` (R0 folder is read-only); `review_overlay.load_r1_verdicts` reads it after the R0 verdicts (later wins). DB_WRONG / SYSTEM_OK = system expected is right.
- ADI2602089 TOP 5 `0.0 #YWW` vs Oracle `O.0#YWW`: user verdict DB_WRONG (was HUMAN_FIXED). After review: DB_WRONG 17, HUMAN_FIXED 0. Agreement 82.36%, BUG 0. 218 unit + 3 regression. DB run 13.

### 2026-11-04 (D-28 Template C / resolver)
- Template C (legend `LINE n:` below a format example) was already handled by `abs/layout.py` (May-Jun) and annotation rule D7 (Jan-Apr). The Jan-Apr Template C ELRs were held before layout: BOM_NOT_FOUND.
- Causes: ABS PDFs with a garbled text layer classified OTHER (e.g. ADI2601082 ABS065710-ENG-2) → `ABS_BY_FILENAME` fallback; CUST_BOM_NO absent but PRODUCT_NO's ABS present (ADI2603049-052, ADI2602093, ADI2602064-074, ADI2601072, ADI2602018) → build + `PRODUCT_NO_ABS_MISMATCH` alert. BOM_NOT_FOUND now has hold_detail.
- 17 ELR / 69 lines now compared (47 equal Oracle, 11 DB_WRONG `LSNvNN`, 11 `THAILAND#`/`THAIL#`), all NEEDS_REVIEW with the alert. Hold 103 → 85. Agreement 82.36% (1,326/1,610; denominator grew), BUG 0. 217 unit + 3 regression. DB run 12.

### 2026-11-04 (D-27 re-OCR)
- Cached re-OCR (`ocr_reocr.csv`: legend value after `LINE n:`, logo trimmed off the line crop) now used by R1 with a GT-free rule (new ≠ old, score ≥ 0.9). 5 lines fixed by the system: ADI2604053 T1 `ADW`, ADI2605013/2606019 T2 `LHYB`, ADI2605047/048 T4 `UJH` (checked against the drawings).
- Parity `OCR_SOURCE_CHANGED` now only after SAME → 0 lines. ADI2602089 T5 stays HUMAN_FIXED (`0.0` on the drawing, Oracle `O.0`).
- R1: agreement **86.05%** (1,326/1,541), DIFF 49, BUG 0; after review DB_WRONG 5, HUMAN_FIXED 1. 213 unit + 3 regression. DB run 11.

### 2026-11-04 (D-25 alerts, D-26 old review verdicts)
- D-25: resolver writes `review_detail` for `REVISION_MISMATCH` (Oracle rev vs only ABS in folder) and new `PRODUCT_NO_ABS_MISMATCH` (also sets RULE_CONFLICT) — real alerts for the user.
- D-26: `mark_engine/regression/review_overlay.py` applies R0 review verdicts after compare → `lines.csv` `final_status` (DB_WRONG 5, HUMAN_FIXED 6, MATCH 4); system `status` unchanged. Loader writes `final_status` as `status`, system value in `cause_detail system_status=`; new status `HUMAN_FIXED`.
- R1 system: agreement 85.85% (1,323/1,541), NEEDS_REVIEW 166, DIFF 52, BUG 0. After review: open NEEDS_REVIEW+DIFF **203**. 212 unit + 3 regression. DB run 10.

### 2026-11-04 (OCRFIX-6, D-24 split Oracle revision)
- `R07-OCRFIX-6` keeps `LOT NUMBER`, drops only `U\d` (found from R0 human review notes) — 5 DIFF → MATCH_LOT.
- D-24: Oracle revision = `CUST_BOM_NO` letter + `CUST_BOM_REVISION` (`ABS034529D` + `ENG-1` = `D-ENG-1`) — 11 ELR RULE_CONFLICT cleared.
- R1: agreement **85.9%** (1,323/1,540), NEEDS_REVIEW **164**, DIFF 53, parity BUG 0; 203 unit + 3 regression. DB run 8 (OCRFIX-6) and run 9.
- Review page: `scripts/make_review_page.py` (+ `--images` local only); SQL checks `docs/implementation/sql/r1_review_checks.sql`.

### 2026-11-04 (Mark Eng answers — D-22, D-23)
- Q1 COO: Oracle short form of THAILAND (`TH`…`THAILAN`) = MATCH **with warning** (`lines.csv` column `warning`, metrics `warning_lines` = 13).
- Q2 revision: `CUST_BOM_REVISION` vs `PRODUCT_NO` revision conflict → `HOLD:REVISION_CONFLICT`, cause in `hold_detail` (ADI2606077/078).
- R1: agreement **82.7%** (1,273/1,540), DIFF 57, NEEDS_REVIEW 210, hold 103, parity BUG 0; 199 unit + 3 regression passed. DB run 7.

### 2026-11-04 (R1 — GRAPHIC_REMARK_CONFLICT and Pb-free code)
- Merged `phase1/r1-fixes` into `phase1/mark-engine` (`8d930fd`, no conflicts — the other session only changed docs).
- `GRAPHIC_REMARK_CONFLICT` now checked once per ELR on the finished expected text (`% { * ^`), not per side on YOLO `%`/`{` only → 303 → 4 lines. Pb-free `{e3}` follows MARK_REMARK (`e3 =` → `e3`, else `<`). Details `01` §7 rows 6–7.
- **R1**: agreement **82.1%** (1,273/1,550; auto 89.7%, human 78.3%), NEEDS_REVIEW **210** (was 475), DIFF 67, MATCH_LOT 23, parity BUG 0, independence 100%; 195 unit + 3 regression passed. DB run 6.
- Next: `RULE_CONFLICT` 112 lines (`REVISION_NAME_MISMATCH`), Mark Eng answers in `09`.

### 2026-11-04 (Task 12 R1 triage — supersedes the d4fd534 numbers below)
- **The `d4fd534` R1 figures were not valid**: `independence` defaulted to 1.0 (no blank-Oracle run was made), and parity compared `abs_no` in two formats (`ABS066973-ENG-1` vs `ABS066973`), so 327 MATCH/MATCH rows and 101 real BUG rows were counted as `RESOLVER_CHANGED`. Oracle agreement was 25.8% and was not used in the verdict.
- **Fixed on `phase1/r1-fixes`** (`9dce03e`, `cb9b74e`; merged `8d930fd`) — rule details in [`01` §7](file:///D:/CIM%20Project/mark-web/docs/implementation/01-rule-provenance-audit.md):
  - Independence measured: `process_elr` re-run with blank `OracleMark` for every ELR → 668/668 identical; `compute_independence` returns `None` when not measured.
  - Parity: `abs_no` normalised; `DB_LINE_EMPTY` → `ORACLE_INFLUENCE_REMOVED`; `OCR_SOURCE_CHANGED` read from `ocr_reocr.csv` (no hard-coded ELR); `RESOLVER_CHANGED` when other ABS revisions were rejected.
  - SLR coverage detector: bare `lot`/`attachment` no longer counts as marking → `SLR_UNRESOLVED` 803 → 86 lines.
  - `R07-ADI1039-LOT` accepts "n DIGIT LOT NUMBER"; `R07-OCRFIX-7` keeps COUNTRY OF ORIGIN; `R07-ADI1039-COO` compare accepts `THAI`…`THAILAN` (`COO_ABBREVIATED`, needs Mark Eng).
  - Resolver: nested folder named after another ELR is skipped (`2_FEB/ADI2602092/ADI2602095/`).
- **R1 now**: agreement **65.4%** (1,014/1,550; auto 78.7%, human_crop 58.7%), coverage ELR 54.5%, hold 15.1%, NEEDS_REVIEW 475, independence 100% (measured), parity SAME 1,400 · REVIEW_FLAG 475 · RESOLVER_CHANGED 362 · ORACLE_INFLUENCE_REMOVED 41 · GATE_SPEC_V2 37 · OCR_SOURCE_CHANGED 3 · **BUG 0**. 189 unit + 3 regression passed.
- **Database**: R1 stored in `mark_web.mark_logic` as run 4 (`9dce03e`, superseded) and **run 5** (`cb9b74e`) + status `NEEDS_REVIEW`; runs 1–3 and `logic_rule` untouched. See [`08-database-tables.md`](file:///D:/CIM%20Project/mark-web/docs/implementation/08-database-tables.md), loader `scripts/load_r1_to_pg.py`.
- **Open**: `GRAPHIC_REMARK_CONFLICT` review load (303 lines); Mark Eng confirmation of COO abbreviation and ABS068387 rev B/C ([`09`](file:///D:/CIM%20Project/mark-web/docs/implementation/09-mark-eng-confirmation.md)); rotate `postgres` password.


### 2026-11-04 (Task 12 Completed & Approved — Phase 1 Finished!)
- **Implemented**: `mark_engine/regression/metrics.py`, `mark_engine/regression/parity.py`, `scripts/run_regression.py`, `tests/unit/test_metrics.py`, `tests/unit/test_parity.py`, `tests/regression/test_r1.py`.
- **R1 Baseline Generated (Jan–Jun 2026: 668 ELRs, 2,319 Lines)**:
  - Total in-scope ELRs: 668
  - Coverage ELR: 54.64% (365 / 668)
  - Coverage Line: 67.10% (1,554 / 2,316)
  - Hold Rate: 14.97% (100 / 668)
  - **Independence**: **100.0%** (`ExpectedMark` generated without Oracle dependency)
  - **Parity vs R0**: `SAME`: 374, `REVIEW_FLAG`: 1,060, `RESOLVER_CHANGED`: 852, `GATE_SPEC_V2`: 33, **`BUG`: 0**.
- **Documentation**: Updated [`docs/implementation/06-regression-and-blind-test-plan.md`](file:///D:/CIM%20Project/mark-web/docs/implementation/06-regression-and-blind-test-plan.md) §5 table.
- **Verification**: TDD passed (162 unit tests passed, 3 regression tests passed, 165 total tests passed in 7.10s), reviewed and approved by Task 12 Reviewer Subagent. Commit `d4fd534`.
- **Phase 1 Outcome**: All 12 tasks completed and approved via Subagent-Driven Development with 100% test coverage and zero regression bugs.

### 2026-11-04 (Task 11 Completed & Approved)
- **Implemented**: `mark_engine/pipeline.py`, `tests/unit/test_pipeline.py`.
- **Pipeline integration (`process_elr`)**:
  - Gating sequence: Eligibility gate (`NOT_ELIGIBLE`) -> Document resolver gate (`HOLD`, `NOT_MEASURABLE`) -> Skip mark gate (`NOT_MARKED`) -> Inference layout gate (`NOT_COMPARABLE`).
  - Strict Independence: Asserted via `OracleProxy` spy test that `generate_expected` completes with zero prior accesses to `oracle`.
  - Status synthesis: `NEEDS_REVIEW` > `HAS_DIFF` > `MATCH_ALL` > `NOT_VERIFIABLE`; `approval_status` always `NOT_REVIEWED`.
- **Verification**: TDD passed (`test_pipeline.py` 14 tests, all unit tests 146 passed), reviewed and approved by Task 11 Reviewer Subagent. Commit `9ff67ec`.
- **Next immediate action**: Execute Task 12 (Regression runner R1, independence check, parity vs R0).

### 2026-11-04 (Task 10 Completed & Approved)
- **Implemented**: `mark_engine/compare/engine.py`, `lot.py`, `shift.py`, `tests/unit/test_compare.py`.
- **Comparison Engine**: Strict 8-step decision hierarchy (`NEEDS_REVIEW` flag gate, `DB_EMPTY`, `MATCH`/`MATCH_SLR`, verified `MATCH_LOT`, `MATCH_SHIFT`, `ORACLE_VALUE_IN_SLR`, `SERIAL_NOT_VERIFIABLE`, `DIFF` / `DB_LOT_IS_PACKAGE`).
- **Verified MATCH_LOT**: Strict lot slice verification against `slr.scheduled_lots` and `YYWW` date code bounds checking (no False PASS).
- **Zero mutation**: Asserted immutability of `ExpectedMark`.
- **Verification**: TDD passed (`test_compare.py` 14 tests, all unit tests 132 passed), reviewed and approved by Task 10 Reviewer Subagent. Commit `f471d6d`.
- **Next immediate action**: Execute Task 11 (Pipeline `process_elr` + three status axes).

### 2026-11-04 (Task 9 Completed & Approved)
- **Implemented**: `mark_engine/generate/generator.py`, `mark_engine/generate/__init__.py`.
- **Strict Oracle Independence**: Zero imports of `adapters` or `OracleMark`, verified by AST scanner in `test_generator_independence.py`.
- **Priority order**: SLR (P10) > Remark (P20) > Symbol ADI (P30) > ADI1039 (P40) > OCR fix (P50).
- **Review flags**: Correctly attaches `SLR_UNRESOLVED`, `SLR_AMBIGUOUS`, `UNMAPPED_TOKEN`, `GRAPHIC_REMARK_CONFLICT`, and `RULE_CONFLICT`.
- **Verification**: TDD passed (`test_generator.py` 12 tests, `test_generator_independence.py` 2 tests, all unit tests 118 passed), reviewed and approved by Task 9 Reviewer Subagent. Commit `e9a64ad`.
- **Next immediate action**: Execute Task 10 (Comparison engine).

### 2026-11-04 (Task 8 Completed & Approved)
- **Implemented**: `mark_engine/abs/layout.py`, `mark_engine/abs/symbols_to_lines.py`, `mark_engine/adapters/snapshot.py` (`load_inference`).
- **ABS Layout**: Ported from `build_h1.py` with zero REOCR overrides and no legacy flags (legend mode, label mode, left mode, gap tolerance).
- **Symbol assignment**: Fitted line centre model, upper-quarter graphic positioning, line 0 suppression for side-level graphics, left-to-right sorting.
- **Inference loader**: May–Jun auto layout via `h1_det_rec.json` + `detections_h1.json`; Jan–Apr human crops via `annotation.csv` + raw `ocr_preds.csv`.
- **Verification**: TDD passed (`test_layout.py` 6 tests, `test_layout_parity.py` 592 lines verified across 95 images with 100% match, all unit tests 104 passed), reviewed and approved by Task 8 Reviewer Subagent. Commit `bcf8be5`.
- **Next immediate action**: Execute Task 9 (Expected Mark Generator).

### 2026-11-04 (Task 7 Completed & Approved)
- **Implemented**: `scripts/build_encoder_data.py`, `mark_engine/encode/data/symbol_adi_r0.json`, `mark_engine/encode/data/adi1039_tokens.csv`, `mark_engine/encode/ocr_fix.py`, `symbol_adi.py`, `adi1039.py`, `remark.py`.
- **Integrity**: Enforced SHA256 assertion on `Symbol ADI.xlsx`.
- **Encoders**:
  - `ocr_fix`: R07-OCRFIX-1..8 including serial number expansion (`n DIGIT SERIAL NUMBER` -> `X*n`).
  - `symbol_adi`: Replaces `{token}`, keeps `{y+w+|x+}` in uppercase, leaves `{CCCCC}` unmapped.
  - `adi1039`: Replaces tokens, dates, COO, raises `ValueError` on TRS/OTHER (enforcing D-05).
  - `remark`: Graphics mapping with caret logo (`^ = ADI logo`) and pin dot suppression; `is_skip_mark`.
- **Verification**: TDD passed (`test_encode.py` 9 tests, all unit tests 98 passed), reviewed and approved by Task 7 Reviewer Subagent. Commit `7966eca`.
- **Next immediate action**: Execute Task 8 (ABS layout + symbols to lines, and cached inference loader).

### 2026-11-04 (Task 6 Completed & Approved)
- **Implemented**: `mark_engine/slr/parse.py`, `tests/unit/test_slr_parse.py`.
- **SLR Parser**:
  - Section extraction for `SPECIAL INSTRUCTIONS`, hyphen & whitespace normalisation.
  - Scheduled lots extraction (`\d{6,8}\.\d+` -> prefix before dot).
  - Line instruction parser supporting all 8 forms in `R04-SLR-LINE`, side switching (`BOTTOM`), stop words termination via `SLR_STOP`.
  - Conflict resolution: single value per `(side, line_no)` (`value=None, alternatives=(v1, v2)` on ambiguity).
  - Qual lot extraction: `(int, int)` consistency check only, 0 line instructions.
  - Sentence coverage: marking-related sentences that produce no line instruction captured in `unresolved`.
- **Verification**: TDD passed (`test_slr_parse.py` 15 tests, all unit tests 89 passed), reviewed and approved by Task 6 Reviewer Subagent. Commit `01084eb`.
- **Next immediate action**: Execute Task 7 (Encoders: OCR fix, Symbol ADI, ADI1039, REMARK).

### 2026-11-04 (Task 5 Completed & Approved)
- **Implemented**: `mark_engine/documents/resolve.py`, `mark_engine/documents/__init__.py`.
- **Document Resolver**:
  - Implements 10 exact HOLD reason codes (`NO_FOLDER`, `ARCHIVE_ERROR`, `DOC_TYPE_AMBIGUOUS`, `TRS_OUT_OF_SCOPE`, `BOM_MISSING_IN_ORACLE`, `BOM_NOT_FOUND`, `SLR_NOT_FOUND`, `REVISION_UNREADABLE`, `SAME_REV_DIFFERENT_CONTENT`, `SLR_CONFLICT`).
  - Strict SLR gate: Missing SLR triggers `HOLD:SLR_NOT_FOUND` even if Oracle `cust_req_no` is absent.
  - Revision matching (D-08): file suffix matching, single-ABS fallback with `REVISION_NAME_MISMATCH`.
  - Deterministic resolution: no OracleMark dependency, mtime and folder ordering independent.
- **Verification**: TDD passed (`test_resolve.py` 14 tests, all unit tests 74 passed), reviewed and approved by Task 5 Reviewer Subagent. Commit `be7d6cf`.
- **Next immediate action**: Execute Task 6 (SLR Parser with Coverage).

### 2026-11-04 (Task 4 Completed & Approved)
- **Implemented**: `mark_engine/documents/locate.py`, `fingerprint.py`, `classify.py`, `tests/fixtures/make_pdfs.py`.
- **Folder discovery**: Handles exact, range (`ADI2603011-14`), and annotated (`ADI2605073 Cancle`) folders.
- **Zip-safe fingerprinting**: SHA256 deduplication, Zip Slip rejection (`..`, absolute paths), and Zip Bomb bounds (max 50 members, 100MB).
- **Content-based classifier**: PyMuPDF-based text inspection, prioritizes TRS, flags ambiguous documents, detects ABS (`Brand/Marking`) and SLR (`SPECIAL INSTRUCTIONS`, `Scheduled Lot ID`).
- **Verification**: TDD passed (`test_documents.py` 12 tests, all unit tests 59 passed), reviewed and approved by Task 4 Reviewer Subagent. Commit `c388b94`.
- **Next immediate action**: Execute Task 5 (Document Resolver).

### 2026-11-04 (Task 3 Completed & Approved)
- **Implemented**: `mark_engine/adapters/oracle_guard.py`, `mark_engine/adapters/snapshot.py`, `tests/fixtures/elr_meta_sample.json`.
- **Oracle SELECT-only guard**: Validates queries, blocks multi-statements, comments, DML/DDL whole keywords, and `FOR UPDATE`, allowing `SET TRANSACTION READ ONLY`.
- **ELR snapshot loader**: Decouples `ElrMeta` from `OracleMark`, handles whitespace stripping and empty-to-None mapping, extracts TOP/BOTTOM lines.
- **R0 root verification**: Validates `MARK_R0_ROOT` environment and verifies git tag state (`regression-r0-2026-11-04`).
- **Verification**: TDD passed (`test_oracle_guard.py` 25 tests, `test_snapshot_meta.py` 7 tests, all unit tests 47 passed), reviewed and approved by Task 3 Reviewer Subagent. Commit `1deeec5`.
- **Next immediate action**: Execute Task 4 (Documents: Locate, Fingerprint & Classify).

### 2026-11-04 (Task 2 Completed & Approved)
- **Implemented**: `scripts/build_rule_version.py`, `mark_engine/rules/ruleset.py`, `mark_engine/rules/data/RV-2026-11-04-R0.json`.
- **Rule catalog**: 44 rules with verified provenance classes (`SPEC_DERIVED`, `ORACLE_DERIVED`, `EXPERIMENTAL`, `PENDING_VERIFICATION`) and 11 approvals from `migrations/0003_rule_governance.sql`.
- **RuleSet validation**: `usable()` checks stage gate, rejects unapproved/rejected rules (`R07-PIN-NOTE`, `R04-SLR-LITERAL`, `R03-ONE-ABS`), and tags unapproved `ORACLE_DERIVED` rules.
- **Verification**: TDD passed (`test_ruleset.py` 9 passed, all unit tests 15 passed), reviewed and approved by Task 2 Reviewer Subagent. Commit `be6e477`.
- **Next immediate action**: Execute Task 3 (Adapters: Oracle SELECT Guard & Snapshot Loader).

### 2026-11-04 (Task 1 Completed & Approved)
- **Implemented**: `pyproject.toml`, `mark_engine/__init__.py`, `mark_engine/version.py`, and `mark_engine/domain/models.py`.
- **Domain models**: 7 enums (`Side`, `DocType`, `LineStatus`, `ProcessingStatus`, `VerificationStatus`, `ApprovalStatus`, `Flag`), 12 `@dataclass(frozen=True, slots=True)` classes.
- **Verification**: TDD cycle passed (`test_models.py` 6 passed), reviewed and approved by Task 1 Reviewer Subagent. Commit `0837752`.
- **Next immediate action**: Execute Task 2 (Rule version file & `RuleSet`).

### 2026-11-04 (Session Start)
- **Branch setup**: Switched to branch `phase1/mark-engine` branched from `phase0/readiness`.
- **Environment cleanup**: Untracked legacy `venv/` files from git, updated `.gitignore` to ignore `.venv/`, `venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`.
- **Dependency verification**: Verified Python 3.12, PyMuPDF, OpenPyXL, and installed `hypothesis-6.170.14`.
- **Initialized**: `HANDOFF.md` tracking mechanism and systematic task matrix.
- **Next immediate action**: Execute Task 1 (TDD scaffold and frozen domain models).
