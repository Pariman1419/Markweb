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

---

## [2026-11-04] Mark Eng answers: COO warning and REVISION_CONFLICT

### Context & Symptom
- **Component / Path**: [`mark_engine/compare/engine.py`](file:///D:/CIM%20Project/mark-web/mark_engine/compare/engine.py), [`mark_engine/documents/resolve.py`](file:///D:/CIM%20Project/mark-web/mark_engine/documents/resolve.py)
- **Question / Issue**: two open items from `09-mark-eng-confirmation.md` (THAIL abbreviation; ADI2606077/078 rev B vs C).

### Root Cause
- COO: MATCH was silent, so a user could not tell the Oracle text differs from the full name. Only prefixes of 4+ letters were accepted.
- Revision: the resolver trusted `CUST_BOM_REVISION` even when Oracle's own `PRODUCT_NO` named another revision.

### Resolution & Code Fix
- `LineComparison.warning` (new): COO short form `TH`…`THAILAN` stays MATCH and carries `COO_ABBREVIATED: Oracle THAIL, expected THAILAND`. Runner writes `warning`; metrics `warning_lines`.
- `HOLD:REVISION_CONFLICT` with `DocumentResolution.hold_detail` ("CUST_BOM_REVISION=B but PRODUCT_NO ADMFS7201-ABS068387C-A has rev C"); only for letter revisions, so `ENG-1` vs `B-ENG-1` is not a conflict.
- R1: 13 warning lines, 2 new holds, DIFF 67 → 57, agreement 82.7%, BUG 0.

### Prevention / Rules Learned
- "Accept but show" is kept as a field next to MATCH, not a new status, so agreement numbers stay comparable.
- When two Oracle fields disagree, hold with the cause instead of choosing one.

---

## [2026-11-04] Old human review cross-checked against R1; OCRFIX-6 erased LOT NUMBER

### Context & Symptom
- **Component / Path**: [`mark_engine/encode/ocr_fix.py`](file:///D:/CIM%20Project/mark-web/mark_engine/encode/ocr_fix.py)
- **Question / Issue**: R0 review files `mark/experiments/abs_vs_db/review/diff_review_2026-11-04*.csv` (132 reviewed rows) checked against R1 run 7. Five lines noted "LAST 2 DIGIT LOT NUMBERU1 ตีความผิดปะ" were DIFF in R1 with expected `LAST 2 DIGIT`.

### Root Cause
- `R07-OCRFIX-6` returned `""` for `(LOT) NUMBERU\d`, deleting the field. The catalog rule only drops the suffix (`(X+)U\d` → ``). Same pattern as the OCRFIX-7 bug.

### Resolution & Code Fix
- Keep `LOT NUMBER`, drop only `U\d`; ADI1039 LOT then gives `XX`. 5 lines DIFF → MATCH_LOT (verified against SLR lot). Agreement 82.7% → 83.0%, DIFF 57 → 52, BUG 0.

### Prevention / Rules Learned
- An OCR-noise rule must never return an empty string for a whole field; drop only the noise.
- Old human review notes are a cheap source of regression cases — check them after every R1 run.

---

## [2026-11-04] RULE_CONFLICT on ENG-n ELRs: Oracle splits the revision over two fields

### Context & Symptom
- **Component / Path**: [`mark_engine/documents/resolve.py`](file:///D:/CIM%20Project/mark-web/mark_engine/documents/resolve.py)
- **Question / Issue**: 11 ELRs (46 lines, 45 already equal to Oracle) flagged `RULE_CONFLICT`: file `ABS034529D-ENG-1` (rev `D-ENG-1`) vs Oracle `CUST_BOM_REVISION = ENG-1`.

### Root Cause
- Oracle keeps the letter in `CUST_BOM_NO` (`ABS034529D`) and the ENG part in `CUST_BOM_REVISION`. The resolver compared the file revision with `CUST_BOM_REVISION` only (user-confirmed, D-24).
- First fix skipped `E`: guard `rev.startswith(letter)` is true for `ENG-1` when the letter is `E` (ADI2606066). Fixed to `startswith(letter + "-")`, with a test.

### Resolution & Code Fix
- `_oracle_revision(bom_no, bom_rev)`: letter suffix of `CUST_BOM_NO` + `-` + `CUST_BOM_REVISION`.
- RULE_CONFLICT 25 → 14 ELR; NEEDS_REVIEW 210 → 164; agreement 85.9%; BUG 0.

### Prevention / Rules Learned
- A revision can be spread over several Oracle fields; build it once in one function and test each letter, including the ones that collide with the ENG prefix.

---

## [2026-11-04] Old review verdicts as final status; revision alerts with cause

### Context & Symptom
- **Component / Path**: [`mark_engine/regression/review_overlay.py`](file:///D:/CIM%20Project/mark-web/mark_engine/regression/review_overlay.py), [`mark_engine/documents/resolve.py`](file:///D:/CIM%20Project/mark-web/mark_engine/documents/resolve.py)
- **Question / Issue**: user: lines already reviewed should follow the old review; revision configuration problems must be real alerts so the user can fix them (D-25, D-26).

### Root Cause
- R1 had no place for human verdicts, so reviewed lines reappeared as DIFF / NEEDS_REVIEW.
- RULE_CONFLICT only carried a flag name; the user could not see what to fix.

### Resolution & Code Fix
- `final_status` per line after compare: reviewed answer = expected ≠ Oracle → DB_WRONG; = Oracle ≠ expected → HUMAN_FIXED; = both → MATCH; anything else (stale verdict) or a held line → system status kept.
- `DocumentResolution.review_detail`: "REVISION_MISMATCH: Oracle ABS065744 rev B but folder has only ABS065744C (rev C)" and "PRODUCT_NO_ABS_MISMATCH: …" (new check, 4 ELR in Jan–Jun).
- First version applied verdicts to HOLD lines (ADI2603041, ADI2603055/056); restricted to compared lines, with a test.

### Prevention / Rules Learned
- Keep the system result and the human result in separate fields; metrics stay honest and the backlog still shrinks.

---

## [2026-11-04] HUMAN_FIXED lines fixed at the OCR (re-OCR on tight crops, no GT)

### Context & Symptom
- **Component / Path**: [`mark_engine/adapters/snapshot.py`](file:///D:/CIM%20Project/mark-web/mark_engine/adapters/snapshot.py)
- **Question / Issue**: 6 lines were HUMAN_FIXED from the old review. User: fix the OCR; for "มีบอกในภาพ" look at the drawing.

### Root Cause
- Drawings checked: legend rows read as one box add a phantom `N` (`LINE 2: LHYB` → `LHYBN`, `LINE 4: UJH` → `UJHN`); a solid ADI logo inside the line crop is read as `S` (`ADW` → `SAD`).
- R0 already re-read these (`reocr.py`) but chose trim_logo rows with human GT, so R1 had dropped all re-reads.

### Resolution & Code Fix
- `_load_reocr`: use a re-read when it differs from the first read and scores ≥ 0.9 (ignores `kept`/`gt`); applied to the auto key `image|SIDE|n` and the human-crop `sample_id`, only when the first read is unchanged. 5 lines → MATCH.
- Parity: `OCR_SOURCE_CHANGED` checked after SAME.
- Not fixable by OCR: ADI2602089 T5 — the drawing shows `0.0 #YWW` with identical glyphs; Oracle has `O.0#YWW`.

### Prevention / Rules Learned
- Look at the drawing before calling a line an OCR error; a cached re-read can be reused only with a selection rule that does not see GT or Oracle.

---

## [2026-11-04] Template C ELRs held before layout (garbled ABS text, CUST_BOM_NO absent)

### Context & Symptom
- **Component / Path**: [`mark_engine/documents/resolve.py`](file:///D:/CIM%20Project/mark-web/mark_engine/documents/resolve.py)
- **Question / Issue**: user: ABS with the legend layout (picture example + `LINE n:` text) must be read from the text below. Layout already does this; Jan-Apr Template C ELRs never reached it (HOLD BOM_NOT_FOUND).

### Root Cause
- ABS065710-ENG-2.pdf (and ~20 other ABS files) have a garbled text layer, so `classify` finds neither ABS###### nor Brand/Marking → OTHER.
- ADI2603049-052 etc.: Oracle CUST_BOM_NO (ABS065577) is not in the folder; the folder has the ABS named in PRODUCT_NO.

### Resolution & Code Fix
- Filename fallback after content classification, only if no content-read ABS has the same number (first version broke ADI2601043: a zip held a second ABS067786_ENG-2.pdf; test added).
- PRODUCT_NO ABS used when CUST_BOM_NO is absent, with `review_detail` alert; BOM_NOT_FOUND hold_detail lists the ABS in the folder.

### Prevention / Rules Learned
- Check why a layout case is missing before adding layout logic: here the documents gate held it.

---

## [2026-11-04] SLR {Lot-4} not checked: "Same date code with SLR…" flagged the whole ELR

### Context & Symptom
- **Component / Path**: [`mark_engine/slr/parse.py`](file:///D:/CIM%20Project/mark-web/mark_engine/slr/parse.py)
- **Question / Issue**: user: ADI2601023 BOTTOM 2 is `XXXX`; the SLR says `Line 2 {Lot‐4}` and gives the lot — why not read?

### Root Cause
- The SLR was parsed correctly (lot 7230523, `{Lot-4}`). The note "Same date code with SLR230744, SLR230747, SLR230766" matched the marking keyword "date code", so `unresolved` was non-empty → SLR_UNRESOLVED on every line → compare stopped at the review gate before the lot check.
- An earlier unit test had listed this sentence as "still unresolved" without a reason.

### Resolution & Code Fix
- `SAME_DATE_CODE_NOTE_RE` skips the note (it fixes the date value, not the mark format). Test moved, new tests added. 12 ELR: BOTTOM 2 → MATCH_LOT, other lines → MATCH / MATCH_SLR.

### Prevention / Rules Learned
- An ELR-level flag hides line-level checks; when a flag comes from one sentence, check whether that sentence changes the mark at all.

---

## [2026-11-04] R1 review round 1, True/Warning/Error page, review export (backfill)

### Context & Symptom
- **Component / Path**: [`mark_engine/regression/review_overlay.py`](file:///D:/CIM%20Project/mark-web/mark_engine/regression/review_overlay.py), [`scripts/make_review_page.py`](file:///D:/CIM%20Project/mark-web/scripts/make_review_page.py), [`scripts/export_review_csv.py`](file:///D:/CIM%20Project/mark-web/scripts/export_review_csv.py)
- **Question / Issue**: (a) user pasted page verdicts (ADI2602089 T5 = DB_WRONG); (b) page should split lines into True (= DB) / Warning (close, e.g. country name) / Error (not equal) with a summary; (c) save page results as CSV and update all logic docs before the next phase.

### Root Cause
- (a) R0 review folder is read-only, so R1 verdicts had nowhere to live. (b) Topic tabs only listed alerts, not the overall result. (c) Verdicts lived only in the artifact database.

### Resolution & Code Fix
- `reviews/r1_review_2026-11-04.csv` + `load_r1_verdicts` (read after R0 verdicts, later wins; DB_WRONG/SYSTEM_OK = system expected right). After review DB_WRONG 17, HUMAN_FIXED 0 (DB run 13). Commit `a024da1`.
- Page `classify`: True / Warning (COO abbreviation, same rule as D-22) / Error + cause; summary tiles; paging 40 cards. Commit `2823d23`.
- `export_review_csv.py` → `reviews/r1_run14_review_export.csv` (2,318 lines, 13 page verdicts/notes); doc `10-r1-logic-review-and-next-phase.md`; 00/01/03/04/06/08 to run 14. Commit `ea5d2f5`.

### Prevention / Rules Learned
- Every change updates HANDOFF.md and this log in the same commit (user rule 2026-11-04). These three commits had only HANDOFF; this entry backfills them.

---

## [2026-11-04] Next-phase design; Oracle layout tables and NAS now reachable

### Context & Symptom
- **Component / Path**: [`docs/superpowers/specs/2026-11-04-phase1-completion-and-phase2-design.md`](file:///D:/CIM%20Project/mark-web/docs/superpowers/specs/2026-11-04-phase1-completion-and-phase2-design.md)
- **Question / Issue**: user asked to analyse and plan from the unfinished parts of Phase 1, with the microservices architecture diagram, a Dashboard + ELR Preview (TOP only, ACTIVEL 21-cell grid, MARK_REMARK, edit/approve), and new DB / NAS access.

### Root Cause
- Spec §19 open items blocked the plan: `MARK_ID_LAYOUT` gave ORA-00942 through `@actl`; NAS 2026 gave Access denied, so the Jul–Nov blind test could not run.

### Resolution & Code Fix
- Direct connection to ACTL 10.151.26.3:1521 with python-oracledb thick mode (10g needs it; thin gives DPY-3010), read-only transaction: all 4 layout tables readable. `MARK_ID_LAYOUT` = one row per (MARK_ROW 1–5, MARK_COLUMN 1–18, MARK_DATA); missing cells line up with the per-ELR values (assumption, to verify in task A2).
- NAS share mounted non-persistent with the user's account: 1_JAN…11_NOV present.
- Design doc written (part A A1–A8, part B B1–B7). No code changed.

### Prevention / Rules Learned
- Credentials pasted in chat are used only as env vars in the command; never written to repo, memory or logs. Recommend rotating them before go-live.

---

## [2026-11-04] Plan for Phase 1 close-out; credentials moved to .env

### Context & Symptom
- **Component / Path**: [`docs/superpowers/plans/2026-11-04-phase1-closeout-blind-test.md`](file:///D:/CIM%20Project/mark-web/docs/superpowers/plans/2026-11-04-phase1-closeout-blind-test.md), `.gitignore`, `.env.example`
- **Question / Issue**: user answered the open design questions and asked for the plan; asked to keep the Oracle / NAS credentials in `.env` so they are not asked again.

### Root Cause
- `.env` was not in `.gitignore`; writing secrets there would have made them committable.

### Resolution & Code Fix
- `.gitignore` gets `.env`, `.env.*`, `!.env.example`; `git check-ignore .env` confirmed before writing the file. `.env.example` holds names only.
- Plan written: 11 tasks; blind test needs batch OCR/YOLO on the AI server (no paddle / GPU on the dev PC) with a determinism check against R0 May–Jun outputs first.
- ACTIVEL positions go in compare stage, not generate, to keep D-10 (generator never reads `MARK_ID_LAYOUT`).

### Prevention / Rules Learned
- Check `git check-ignore` before writing any secret file. Freeze hashes all of `mark_engine/`, so new engine files must land before the freeze.

---

## [2026-11-04] Closeout layout revision in progress

### Context & Symptom
- The user clarified that ACTIVEL layout is an input to expected generation and fixed cells override generated values.

### Root Cause
- The previous plan treated layout only as a comparison warning and prohibited it from expected generation.

### Resolution & Code Fix
- Added the revised plan, Oracle read-only client, layout parser, top mark ID metadata, and migration/loader preparation. Layout alignment and pipeline integration remain incomplete.
- The full suite passed 232 tests. Oracle read-only query returned 70 layout records for 20168; AI-server SSH authentication succeeded. Migration 0004 was not applied; PostgreSQL password is absent.

### Prevention / Rules Learned
- Validate alignment and fixed-symbol handling against representative layouts before freezing. Never report an unfinished blind run as complete.

---

## [2026-11-05] Closeout deployment and historical validation

### Context & Symptom
- The user needs separate deployment units and a completed Phase 1 blind evaluation. The configured NAS path had one leading backslash, the wheel omitted required rule data, and failures before comparison had no persistent job row.

### Root Cause
- The NAS path was not a valid UNC path; setuptools package data was unspecified; the old database loader stored line rows only. The historic auto/human metric split inferred cohort from month prefixes, misclassifying new months.

### Resolution & Code Fix
- Corrected the NAS configuration example and local ignored `.env`. Added engine, inference and DBA boundaries under `services/`, included rule data in the wheel, added layout-aware generation and per-ELR errors, and preserved job outcomes in migration 0004.
- Applied migration 0004, verified its columns and table, and performed a rollback-only database load without changing existing runs. Retrieved the July–November snapshot and extracted images. Historical OCR/YOLO/re-OCR checks and one-image deployment smoke passed. After fixed-cell alignment and whitespace corrections, layout regression found 107 overflow jobs and 274/274 evaluable independence checks.
- Official blind inference, freeze, blind report, team exports and database load remain open; no completion claim is made.

### Prevention / Rules Learned
- Check wheel contents, preserve job-level failures and verify model provenance, snapshots, image hashes and inference completeness before an official run. Report independence with the number checked and excluded.
- Pre-freeze review identified and corrected middle-of-line FIX duplication, significant whitespace loss, asymmetric independence checks, unsafe loader status, missing-layout ordering and inference provenance validation. The full suite passed 272 tests before the freeze.
- A historical page smoke exposed an additional classification defect: `NEEDS_REVIEW` with equal text appeared under TRUE. Stopped the in-progress blind OCR container, corrected the page, added shifted-line warnings and client runtime checks, and reran the suite (274 passed). Regenerate the freeze before rerunning inference.
- Stopped the replacement batch before completion after identifying that an ABS file could change without changing its name between extraction and comparison. Image index rows now include the ABS SHA-256, extraction validates source stability, and the pipeline compares it before and after generation. The suite passes 276 tests; regenerate the image index and freeze.
- Added a preflight requirement for every source ABS fingerprint and rechecked the suite (277 passed). On resumption the NAS hostname failed DNS and Oracle, PostgreSQL and AI-server connections timed out; the live run is still pending network recovery.
- Once internal connectivity returned, resumed the source-fingerprinted image index. Updated the engine and wheel package versions from 0.1.0 to 0.2.0 as required for the changed behavior, and verified 277 tests pass. Freeze and release bundle need regeneration before inference.

---

## [2026-11-05] Frozen holdout and isolated review

### Context & Symptom
- Phase 1 needed a new DB run, separated deployable source bundles and a review screen. The shared review template used a run-14 local-storage key and could connect to external review storage.

### Root Cause
- The frozen generator originally targeted the historical review. Reusing its storage namespace could carry prior review choices into the holdout review.

### Resolution & Code Fix
- Ran the frozen 0.2.0 engine, validated source ABS and inference hashes, and loaded 402 jobs / 723 lines as run 17. Independence was 113/113 evaluable jobs; 141 jobs failed with layout overflow and 34 were held. Runs 1–14 remained intact.
- Added a separate engine-host review wrapper outside the frozen engine/rules that generates run-specific local storage and disables cloud storage. The local-only page and separate pending/confirmed lists remain in ignored `artifacts/`.
- Disclosed that an aggregate layout check included holdout months after freeze and that the November snapshot is partial; the result is a frozen holdout, not an analyst-blind experiment.

### Prevention / Rules Learned
- Never share review state across runs or activate external storage for local customer-data reviews. Report denominators, excluded jobs and failed jobs alongside agreement; do not claim production readiness from compared-line agreement alone.
- After run 17 was recorded, corrected its note: expected uses Oracle `MARK_ID_LAYOUT` while remaining independent of TOP/BACK mark values. The loader was corrected for future runs; this post-evaluation delivery patch does not change the engine or the recorded run-17 result.

---

## [2026-11-05] Overflow comparison review

### Context & Symptom
- The user requested a local HTML comparison for the 141 run-17 layout-overflow ELRs. Run 17 stored the error but did not store the complete pre-layout Generator text.

### Root Cause
- The frozen pipeline returns a failed job at the first layout error and deliberately does not persist partial expected results.

### Resolution & Code Fix
- Added a read-only diagnostic replay in `services/engine/overflow_review.py` and a local HTML template. It validates run-17 input/output hashes and the archived engine before replay and checks the original ABS source fingerprint.
- All 141 recorded failures were reproduced; independently checking all five rows exposed 188 affected rows in total. The local page shows the Generator, Layout cells, Oracle snapshot and cached image without inventing a partial placement. Review notes stay in browser local storage and can be exported to CSV.
- The Generator text is reconstructed using the SLR available on NAS at replay time. Run 17 did not retain an SLR fingerprint, so the page explicitly warns that text can differ if that SLR changed; reproducing the error alone does not prove every input was unchanged.
- Created a portable local archive with the HTML and all 39 referenced images, and verified all 141 image references resolve within it; the archive remains Git-ignored.
- Verified 282 Python tests, run-17 input/output hashes, frozen engine integrity and offline JavaScript search/navigation checks. Browser automation approval for Edge was denied; a visual screenshot review was therefore not performed.

### Prevention / Rules Learned
- Distinguish the first error recorded for each ELR from additional row errors discovered during diagnostic replay. Never present an inferred overflow substring as an engine result.


---

## [2026-11-05] Run-17 layout overflow: root causes and engine fixes

### Context & Symptom
- 141/402 blind ELRs failed with `LAYOUT_ERROR … overflow`, and coverage was 28.11%. The user reviewed 25 of them in the local overflow page and exported `run17-overflow-review.csv`.

### Root Cause
- `parse_slr` collapsed all whitespace, including PDF line breaks, so a line value continued into the next text line ("line 5 - TNOE\nBalance of the wafer" → "TNOE Balance"). This covered 25005, 24586, 18178, 25119 and the "*Return" text in 24755.
- ADI1039 matched `ASSEMBLY LOT NUMBER` and `COUNTRY OF ORIGIN` before turning `_` into spaces, so the SLR forms `ASSEMBLY_LOT_NUMBER`, `COUNTRY_OF_ORIGIN` and `DATE_CODE` stayed literal.
- `fill_line_with_conflicts` never let a reserved blank cell consume a space in the generated text, so "@* YYWW" in layout "@* ____" pushed one character past the free cells. This covered 23706, 23274 and 24350.
- Any single line that could not be placed failed the whole ELR, discarding lines that were correct. Reviewer: "แจ้งเป็น warning เพราะมีส่วนที่ถูก".

### Resolution & Code Fix
- `mark_engine/slr/parse.py`: keeps a private-use marker for line breaks, and a value stops at the first break after it has started.
- `mark_engine/encode/adi1039.py`:
  - Underscores between letters become spaces before field matching.
  - SLR `DATE CODE` becomes YYWW.
- `mark_engine/generate/mark_layout.py`: a reserved blank cell can absorb a generated space.
- `mark_engine/pipeline.py`:
  - A line overflow becomes line `NEEDS_REVIEW` with warning `LAYOUT_OVERFLOW`, and the ELR stays DONE.
  - When THAILAND does not fit, the line uses THAI, the most frequent ACTL short form (THAI 304, THAIL 40, TH 2, THAILA 2 from a read-only query), then other prefixes. Warning `LAYOUT_COO_ABBREVIATED`.
- `mark_engine/compare/engine.py`: COO abbreviation also accepts expected THAI against other Oracle prefixes.
- Tests: `tests/unit/test_overflow_fixes.py`; 300 passed.
- Regression:
  - **Jan–Jun without layout:** 3 lines changed, all improvements.
  - **Jan–Jun with layout:** failed jobs 107 → 0, agreement 1,378/1,610, independence 381/381, previously completed jobs unchanged.
  - **Blind replay (UNFROZEN, local only):** coverage 113 → 254 ELR, agreement 897/1,127, independence 254/254.

### Prevention / Rules Learned
- Keep PDF line structure when reading SLR line values. Normalise field-name separators before pattern matching.
- Report a layout problem at line level. Never discard a whole ELR because one line cannot be placed.
- Debugging on the July–November set ends its use as a holdout. Re-freeze and evaluate on unseen data before quoting accuracy.

---

## [2026-11-05] Overflow review round 2: ABS notes, letter case, pin-only rows, ordinal SLR lines

### Context & Symptom
- After round 1, blind replay still had 140 `LAYOUT_OVERFLOW` lines and 22 DIFF lines. The user decided:
  - "NO BRAND ON THIS LINE" is a note: ignore it.
  - 22801 is only the braced `{YW}`.
  - "Bajau TC" vs "BAJAU TC" is a case warning.
- The user asked to analyse the remaining patterns against Oracle history.

### Root Cause
- The ABS drafting note text was treated as mark content. Oracle was '@%' on all 92 such lines.
- Layouts 25203/24711/22686 reserve row 1 for the pin mark only, and the ABS draws the pin and logo on one line.
- The SLR form "Second line of brand content / marking: 'X'" had no parser. Parser coverage left it `SLR_UNRESOLVED` in 57 SLRs, the largest unresolved group.
- Pointer sentences ("Ignore Brand on ABS", "Brand as indicated below") were flagged unresolved even when line instructions followed.

### Resolution & Code Fix
- `generator.py`: `R07-ABS-NOTE` removes "NO BRAND/MARK ON THIS LINE".
- `compare/engine.py`: a case-only difference is MATCH (or MATCH_SLR) with `CASE_DIFF`.
- `pipeline.py`:
  - `_place_line` holds the fallbacks applied on overflow: country short form, then a trailing literal after the last ABS `}`.
  - `_reflow_pin_row` splits at the next row's leading fixed symbol, and only when every row fits.
- `slr/parse.py`:
  - `ORDINAL_LINE_RE` reads ordinal brand lines, with quoted values.
  - `POINTER_SENTENCE_RE` sentences are unresolved only if the SLR has no line instruction.
- Results (round 1 → round 2):
  - **Blind:** agreement 897 → 1,019/1,127, DIFF 22 → 7, overflow lines 140 → 0.
  - **Jan–Jun with layout:** agreement 1,378 → 1,435/1,610.
  - **Jan–Jun without layout:** agreement 1,377 → 1,424, DIFF 49 → 22.
  - Independence 100%. 306 tests pass.

### Prevention / Rules Learned
- Check a candidate rule against Oracle history before applying it: 92/92 for the ABS note, 31/36 uppercase for case, ACTL COO frequency for the short form.
- A reflow or trim is applied only on overflow and only when every resulting row fits. It is always shown as a warning.

## 2026-11-05 — Phase 2 trial design (docs only)

### What changed
- Added the Phase 2 trial spec and plan (`docs/superpowers/specs|plans/2026-11-05-phase2-trial*`). No code changed.

### QA decisions
- The test scope is new logic only. `mark_engine` (306 tests) is not re-tested from the API side.
- API route tests use an in-memory fake repo. The real-DB check is the Task 4 manual step: dashboard cards must equal `metrics.json` of the same run.
- Web checks are `tsc` + `vite build` plus the user's walkthrough. There are no UI unit tests.
- Security / monitoring additions (spec §11–15) are tested only where they are new code:
  - session expiry, CSRF and the role matrix;
  - removal of sensitive log fields;
  - 403 without CSRF, metrics scope, and the request-id echo.
- The NGINX rate limit is checked by hand at deploy: the sixth rapid login returns 429.
- CORS has one route test, `test_no_cors_by_default`, which also covers the allowlist case. Security headers are checked by hand at deploy with `curl -I`.
- Cookies have two route tests: `test_cookie_attributes_and_rotation` and `test_csrf_from_other_session_rejected`.
- Performance is pinned by 3 cheap route tests: fixed query count for ELR detail, dashboard cache per run, and ELR list paging. Timing targets are checked by hand from `/api/metrics` on real data, with no benchmark suite.
- Plan analysis added 4 tests for new behaviour: blind detection in the loader, mark-id/line_extra in the snapshot, HOLD cannot be approved, and the five-failure lock via route. The total is 29 new tests; none duplicate engine tests.
- Added the route test `test_reviews_are_per_run` for the user decision that reviews do not carry over between runs.

## 2026-11-05 — Task 1: Trial run + mark_app schema (spec T0, T1)

### What changed
- Bumped engine version to 0.3.0 in `mark_engine/version.py` and `pyproject.toml`.
- Replaced hardcoded "0.2.0" assertion in `tests/unit/test_generator.py:255` with `ENGINE_VERSION`.
- Refactored `scripts/load_r1_to_pg.py` to isolate `is_blind_run(period, metrics)` and added unit tests in `tests/unit/test_load_r1_blind.py`.
- Replayed blind dataset into `artifacts/blind-2026h2/run-trial`: 402 jobs, 0 failed, 1,358 lines identical to `run-overflowfix`.
- Loaded trial run into PostgreSQL (`mark_logic.run` as `run_id = 19`).
- Created and applied `migrations/0005_mark_app_trial.sql` to establish `mark_app` schema with 7 tables (`app_user`, `user_session`, `api_token`, `elr_snapshot`, `line_review`, `approval`, `audit_log`) and configured least-privilege role permissions for `mark_app`.
- Implemented user creation CLI `scripts/create_app_user.py` and token creation CLI `scripts/create_api_token.py`.

### Verification
- `pytest tests -q`: 308 passed in 13.4s.
- DB checks: verified `mark_app.app_user` contains active user, foreign key constraint on `line_review` rejects nonexistent runs/lines, and latest `run_id` is 19.

## 2026-11-05 — Task 2: Snapshot loader (spec T2)

### What changed
- Created `scripts/load_app_snapshot.py` to extract per-ELR metadata, Oracle raw 5-line marks, 5x18 layout grids, SLR facts, and line compare extras (`line_extra`) from run artifacts.
- Created `tests/unit/test_app_snapshot.py` verifying snapshot construction with isolated fixtures.
- Populated `mark_app.elr_snapshot` for trial `run_id = 19` with 402 rows and copied 287 ABS images to file storage.

### Verification
- `pytest tests/unit/test_app_snapshot.py -q`: 3 passed.
- Database query: `select count(*) from mark_app.elr_snapshot where run_id = 19` confirmed 402 rows.

## 2026-11-05 — Task 3: API core logic (pure functions)

### What changed
- Created pure function business modules in `services/api/mark_api/`: `grouping.py`, `workflow.py`, `auth.py`, `logging.py`, `files.py`.
- Added `tests/unit/test_api_core.py` verifying status classification, metrics rollup, approval gating, account lockouts, session expiry, role permissions, log redaction, and path traversal guards.
- Updated `pyproject.toml` with `[project.optional-dependencies] api` and included `mark_api*`.

### Verification
- `pytest tests/unit/test_api_core.py -q`: 8 passed.
- Full suite `pytest tests -q`: 319 passed in 7.2s.

## 2026-11-05 — Task 4: API routes + repository (spec T3)

### What changed
- Created `services/api/mark_api/repo.py` implementing database persistence with connection pooling, slow query monitoring, and audit trails.
- Implemented FastAPI routers `auth`, `mark`, `validation`, `workflow`, and dependencies `deps.py`.
- Configured CSRF verification on unsafe methods, strict SameSite cookies, session rotation on login, and selective CORS support.
- Added comprehensive route testing suite in `tests/unit/test_api_routes.py` (18 tests).

### Verification
- `pytest tests/unit/test_api_routes.py -q`: 18 passed.
- Full suite `pytest tests -q`: 337 passed in 14.6s.
- Real database verification for run 19: TRUE 866, WARNING 214, ERROR 41, HOLD 34 across 1,304 lines and 402 jobs.

## 2026-11-05 — Task 5: Web app (spec T4)

### What changed
- Built the React frontend in `web/` using Vite, TypeScript, and Tailwind CSS.
- Created `ActivelGrid` component rendering 21x5 ACTIVEL character grids with cell differential coloring (red for mismatch, blue for layout reserved).
- Implemented `Dashboard` with 4 status cards, monthly stacked bars, top cause rankings, and search with 300ms debounce.
- Implemented `Preview` page with customer ABS drawing preview, SLR instructions breakdown, system vs. Oracle grid side-by-side, per-line review form with 7 reasons, and approval/rejection actions.
- Configured lazy loading for Preview page via `React.lazy`.

### Verification
- `tsc -b && vite build`: exited 0 with no errors.
- Bundle size: initial JavaScript chunk is 87.98 kB gzip (target ≤ 300 kB).

## 2026-11-05 — Task 6: Deploy on 10.153.90.17 (spec T5)

### What changed
- Created containerization manifests: `services/api/Dockerfile`, `web/Dockerfile`, `web/nginx.conf`, `web/security_headers.conf`, and `docker-compose.yml`.
- Configured NGINX reverse proxy with burst-limited nodelay request zones, JSON structured access logging, security headers (CSP, nosniff, DENY), and `no-store` API caching.
- Synchronized `.env.example` and documentation in `services/README.md`.

### Verification
- Configuration validation: docker compose and NGINX configurations structured per specifications §12, §16, and §18. Ready for deployment on host 10.153.90.17.

## 2026-11-05 — Phase 2 trial review fix-ups

### What changed
- Same-origin check for unsafe methods.
- No cookie fallback for Bearer requests.
- Corrected the secure cookie prefixes.
- Route-template metrics.
- `http.request` logging with `request_id`; `username` is no longer logged.
- NGINX JSON access log and `$http_host`.
- `.dockerignore` files, root README and configurable web port.

### Tests (6 new, 343 total)
- `test_cross_origin_post_rejected`
- `test_invalid_bearer_does_not_fall_back_to_cookie`
- `test_secure_cookie_names`
- `test_metrics_key_on_route_template`
- `test_http_request_logged_with_request_id_and_template`
- `test_failed_login_log_has_no_username`

### Manual (localhost:8088, docker compose)
- `/api/ready` 200; security headers present; SPA fallback 200.
- 7th rapid login returns 429, logged as JSON with `limit_req: REJECTED`.

## 2026-11-05 — Jenkins pipeline
- The pipeline reruns the existing suites (pytest, `npm run build`). It adds no new unit tests.
- The smoke stage checks the deployed stack: ready 200, 401 without login, `no-store` and CSP on `/api`.
- The first green build is still pending: it needs the user's Jenkins setup (service logon, credentials, job).
- Build #4 failed at test collection: an unpinned FastAPI with Starlette 1.10 requires `httpx2`.
  - Fixed in cf30405 by pinning `fastapi<0.142` and declaring `httpx` in `dev`.
- Builds #4–#5: `if not exist reports mkdir reports && pytest` ran pytest only inside the `if`, so build #5 skipped tests and republished #4's stale report (UNSTABLE).
  - Fixed: the stale report is removed first, pytest runs as its own step, and `junit` no longer allows an empty report.
- Build #5: tests, web build and images passed. Deploy failed because cmd `copy` rejects a source path with `/` (`ENV_FILE`).
  - Fixed: the path is converted to backslashes.
- Build #6: 343 tests, 2 failed (`tests/regression/test_r1`). They need `artifacts/regression-r1/`, which is git-ignored customer data.
  - CI now runs with `--ignore=tests/regression`; R1 stays a local gate.
- **Build #8: SUCCESS.**
  - 340 passed, plus web build, images, deploy, and smoke `smoke OK: http://localhost:8088`.
  - Manual recheck: ready 200, 401 without login, SPA 200.

## 2026-11-05 — Login audit / admin plan (design only)
- No code yet. The plan adds about 13 tests and duplicates none: the existing lockout and no-username tests are kept as they are.

## 2026-11-05 — Task 1: Audit rows carry client_ip and request_id (migration 0006)

### What changed
- Created `migrations/0006_audit_context.sql` adding `client_ip inet`, `request_id text`, and `audit_log_action_created_idx` to `mark_app.audit_log`.
- Added `audit_ctx` helper in `mark_api.deps` reading `X-Real-IP` and `request_id`.
- Extended `Repo.audit` and `FakeRepo.audit` to record `client_ip` and `request_id`.
- Wired `**audit_ctx(request)` into `auth.login_ok`, `auth.logout`, `review.saved`, and `approval.saved`.

### Verification
- `test_review_audit_carries_ip_and_request_id` passed.
- Full test suite: 341 unit tests passed.

## 2026-11-05 — Task 2: Audit failed logins, lockouts and expired sessions

### What changed
- Added `session_status(session, now)` in `mark_api.auth` returning `ok`, `absolute`, or `idle`.
- Implemented `safe_audit` in `mark_api.deps` which fails open and records `db.error` so audit failures cannot disrupt user login.
- Enriched `login` endpoint to write `auth.login_failed` (reasons: `unknown_user`, `locked`, `inactive`, `bad_password`), `auth.locked` on account lockout, and `auth.login_ok`.
- Audited `auth.session_expired` in `current_user` before session row deletion (audited only once).
- Preserved privacy: unknown usernames are never recorded in `audit_log` or logs (`user_id = None`).

### Verification
- Added 6 unit tests covering: `session_status` idle/absolute expiry, unknown user audit without username, 5th failure lockout audit, locked and inactive login attempts, single audit for expired session, and fail-open on DB audit error.
- Full suite: 347 unit tests passed.

## 2026-11-05 — Task 3: Admin API for users, unlock, activity, events

### What changed
- Added `admin` action to role permission matrix for `admin` only; forbidden for `engineer` and `mark_eng_approver` (403).
- Implemented `Repo` methods: `admin_users`, `unlock_user`, `activity` (running 3 grouped queries), and `audit_events`.
- Created `services/api/mark_api/routers/admin.py` under `/api/admin` with endpoints for users, account unlocking (audited), activity trends (run progress, velocity, login issues), and paginated events.
- Enforced date range validation: maximum 92 days, `from <= to`, Asia/Bangkok date grouping.

### Verification
- Added 4 route unit tests + 1 permission test (forbidden for engineer, unlock clears lock with audit and CSRF requirement, state calculation, date range validation).
- Executed direct query on live PostgreSQL DB: `admin_users` retrieved user `kam` and `activity` verified `total_elrs == 402` for run 19.
- Full suite: 351 unit tests passed.

## 2026-11-05 — Task 4: Web /admin page

### What changed
- Created `web/src/pages/Admin.tsx` implementing:
  - Users table with account state badges and audited Unlock button.
  - Activity overview with date range selector, run progress cards, per-user reviews/approvals table, and daily auth event summary.
  - Paginated audit log explorer (50 items/page) with user and action filter dropdowns for investigating login failures.
- Added `/admin` lazy route in `web/src/App.tsx` and protected with role check (redirecting non-admin to `/`).
- Added "Admin" link in Dashboard header for admin users.
- Declared types `AdminUser`, `ActivityData`, and `AuditEvent` in `web/src/api.ts`.

### Verification
- `tsc -b && vite build` succeeded with 0 errors.
- Bundle budget compliance: initial JS bundle 88.07 kB gzip (limit ≤ 300 kB), Admin chunk 4.37 kB gzip.

## 2026-11-05 — Task 5: Persistent API log file

### What changed
- Added `RotatingFileHandler` (10 MB × 5 files) to `services/api/mark_api/logging.py`, writing JSON lines to `<MARK_LOG_DIR>/api.jsonl`.
- Preserved `current_request_id` ContextVar instance across module reloads to prevent decoupling in test environments.
- Updated `docker-compose.yml` to mount `${MARK_LOG_HOST_DIR:-./logs}:/app/logs` with `MARK_LOG_DIR=/app/logs`.
- Updated `.env.example`, `.gitignore`, `.dockerignore`, and added `MARK_LOG_HOST_DIR` parameter in `Jenkinsfile`.

### Verification
- `test_log_event_also_writes_file` verified file creation and redaction of sensitive fields.
- `docker compose config` parsed and validated volume mount and environment.
- Full suite: 352 unit tests passed.

## 2026-11-05 — Login audit: review and CI fix
- Independent re-run of agent commits 8aa889a..5c565f4: 352 unit tests passed locally.
- The Jenkins build for 5c565f4 failed at collection, because `zoneinfo` had no `tzdata` in the clean venv.
  - Fixed by using a fixed UTC+7 in `routers/admin.py`; 352 tests pass.
- DB check: migration 0006 columns are present, and there is 1 admin user.

## 2026-11-05 — Live admin check and `/api/runs` fix
- Live via NGINX: lockout 401×5 → 423; rate limit 429; admin unlock 403 without CSRF, 200, 404 for unknown; 422 for over 92 days; events carry IP and request_id.
- Found: `Repo.runs()` used a non-existent column, `mark_logic.run.created_at`, which gave 500 on the real DB. Fixed with `run_at as created_at`.
- Smoke of all `Repo` reads on the real DB (run 19): all OK.
- Gap: unit tests use a fake repo and cannot catch column-name errors. The real-DB read smoke is the check for that.
- 352 unit tests pass.

## 2026-11-05 — Empty ELR table diagnosed (plan only)
- Called `list_elrs(run=19)` against the real DB: `AttributeError: 'NoneType' object has no attribute 'split'` at `routers/mark.py:63` (NULL `warning`).
- Fixes are planned in `2026-11-05-trial-acceptance-and-monitor.md`, Task 1.

## 2026-11-05 — Acceptance Task 1: NULL-safe ELR list/detail and visible load error

### What changed
- Created `_text(v)` helper in `services/api/mark_api/routers/mark.py` returning `""` for `None` values and `str(v)` otherwise.
- Updated all accesses to `warning`, `detail`, `hold_reason`, `hold_detail`, `abs_no`, and `compare_rules` in `list_elrs` and `get_elr` to use `_text(val)`, fixing `AttributeError: 'NoneType' object has no attribute 'split'`.
- Added `loadError` banner in `web/src/pages/Dashboard.tsx` displaying Thai server error descriptions and a retry button.
- Updated `ElrTable.tsx` to display an explicit error row when `hasError` is true instead of the misleading "No ELR packages found" message.

### Verification
- `test_elrs_and_detail_handle_null_text_fields` verified 200 responses when all text columns are None.
- `tsc -b && vite build` succeeded with 0 errors.
- Full suite: 353 unit tests passed.

## 2026-11-05 — Acceptance Task 2: Read-only real-DB acceptance check and Jenkins stage

### What changed
- Created `scripts/check_trial_readonly.py` implementing 8 acceptance checks against PostgreSQL and router endpoints (`runs`, `dashboard_cards`, `elrs_total`, `elrs_pages`, `elr_detail`, `oracle_raw`, `expected_match`, `admin_reads`).
- Strictly protects customer privacy: prints one `OK` or `FAIL` line per check with short summaries; never prints mark strings, SLR texts, or file paths.
- Added non-blocking `Real-DB check` stage in `Jenkinsfile` wrapped in `catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE')`.
- Updated `services/README.md` with documentation on running the check script.

### Verification
- Executed `python scripts/check_trial_readonly.py --run 19` against live DB (exit code 0):
```
OK runs found run 19 in 16 runs
OK dashboard_cards TRUE 866, WARNING 214, ERROR 41, HOLD 34
OK elrs_total total=402 jobs=402
OK elrs_pages 402 unique ELRs across 9 pages
OK elr_detail sampled 20 ELRs OK
OK oracle_raw sampled 20 snapshots have 5 oracle_top_raw entries
OK expected_match sampled 20 ELRs line expected values match
OK admin_reads admin_users (4), activity, audit_events (15) OK
```
- Full suite: 353 unit tests passed.

## 2026-11-05 — Acceptance Task 3: /api/metrics per spec §15

### What changed
- Created `services/api/mark_api/metrics.py` extracting `InProcessMetrics` singleton out of `app.py` to prevent circular imports.
- Added route ring buffers via `collections.deque(maxlen=1000)` computing nearest-rank p50 and p95 duration percentiles.
- Added counters for `login_ok`, `login_failed`, `login_locked`, and `db_error`.
- Added `Repo.active_sessions()` querying `mark_app.user_session` where `expires_at > now()`.
- Wired counters into `routers/auth.py` and `Repo._execute` database exception handler.
- Updated `GET /api/metrics` to return `metrics.snapshot(repo.active_sessions())` (passing `None` if DB error).
- Removed `rate_limited` from API metrics as 429 responses are terminated directly by NGINX and logged in NGINX JSON access logs.

### Verification
- `test_metrics_percentiles_and_cap` verified nearest-rank calculation, p50/p95, and 1000-sample deque cap.
- `test_metrics_counts_logins` verified login failure and success counters, presence of `active_sessions`, and absence of `rate_limited`.
- Full suite: 355 unit tests passed.

## 2026-11-05 — E2E walkthrough found review FK bug
- `scripts/e2e_walkthrough.py`, run against localhost:8088 on run 19:
  - **Passed:** login, dashboard, search/open, preview (ABS image plus Oracle grid), approve-blocked (409).
  - **Failed:** `review_line_4` returned 500 (`ForeignKeyViolation line_review_run_id_elr_no_abs_no_side_line_no_fkey`).
- **Cause:** the review used the snapshot abs (`-ENG-2` suffix) and not `line_result.abs_no`. All 1358 run-19 lines are affected.
- **Fix:** take `abs_no`/`side` from the line row; unknown line → 404.
- **Tests:** 356 unit tests pass. The E2E re-run after deploy is recorded in the next entry.

## 2026-11-05 — Acceptance Task 4: Dashboard cache LRU 8 and lazy ABS thumbnail

### What changed
- In `services/api/mark_api/routers/validation.py`: replaced `_dashboard_cache` dict with `OrderedDict` bounded by `_CACHE_MAX = 8`.
  - Cache hit: `move_to_end(run)`.
  - Cache store: evicts least recently used via `popitem(last=False)` when exceeding 8 entries.
- In `web/src/pages/Preview.tsx`: added `loading="lazy"` to thumbnail `<img>` on line 259, while keeping modal zoomed preview eager.

### Verification
- `test_dashboard_cache_lru_8` verified 9 unique runs store 8 entries and evict run 100.
- `tsc -b && vite build` built web bundle with 0 errors.
- Full suite: 357 unit tests passed.

## 2026-11-05 — E2E walkthrough PASS 12/12 (after the review FK fix)
- **Result:** `scripts/e2e_walkthrough.py --run 19` against deployed `a42a483` passed 12/12. Steps: login, dashboard (50 rows), search/open, preview (image plus grid), approve blocked (409), review ×2 (200), approve (200), admin login, admin events. It then cleaned up its rows (2 reviews, 1 approval).
- **Timings via NGINX:** `/api/elrs` page 1 0.16 s, `/api/dashboard` 0.06 s, `/api/runs` 0.05 s. The dashboard table fills in under 1 s with no console errors.
- **Gap:** admin events show no ELR or run column.

## 2026-11-05 — Flow check: TO-BE diagram vs engine
- **Matches:** layout gate (Type E, not ZY), ADI1039 and Symbol decode, compare with TOP_MARK1–5.
- **Missing in the engine:** CURRENT_STEP filter, Cust Assy TBD gate, line-count gate (more than 5), notify.
- **Rule differs:** SLR selection (Marking Comment vs CUST_REQ_NO).
- **Engine-only, absent from the diagram:** document HOLD reasons and Skip Mark.
- Any new gate must be regressed on run 19 before merge (spec §7).


## 2026-11-05 — Engine Gates Task 1: G1 Cust Assy TBD holds the job

### What changed
- In `mark_engine/pipeline.py`: restructured eligibility checks into explicit ordered gates:
  1. `STATUS == 'C'` → `NOT_ELIGIBLE`
  2. `CUST_ASSY_LOT == 'TBD'` (G1) → `HOLD:CUST_ASSY_TBD` (TBD takes precedence over ZY layout per user gate order)
  3. `top_type_code != 'E'` or `top_layout_code == 'ZY'` → `NOT_ELIGIBLE`
  4. Document resolution gate (as before)
- Job result for TBD sets `ProcessingStatus.HOLD`, `hold_reason="CUST_ASSY_TBD"`, `resolution=None`, and `LineStatus.NOT_MEASURABLE` for each Oracle line.

### Verification
- `test_cust_assy_tbd_gate` tested 5 cases: `" tbd "`, `"Tbd"`, `"TBD"` on closed ELR (stays NOT_ELIGIBLE), `"1STBOND"` (not TBD), and `None`.
- Full suite: 362 unit tests passed.
