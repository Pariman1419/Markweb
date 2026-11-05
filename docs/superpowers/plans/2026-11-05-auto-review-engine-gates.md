# Auto Review Flow — Step 1: Engine Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the user's new gates to `mark_engine` and measure, on the run-19 inputs, how much they change the results before anything uses them. The gates are: Cust Assy TBD, Special requirement from SPECIAL INSTRUCTIONS, rows ≤ 5, and the pending-review selector.

**Architecture:**
- Gates G1, Special and G5 go inside `process_elr` (`mark_engine/pipeline.py`) as early returns, in the order the user set.
- G0 is a pure selector function that the scanner (build step 3) will call. It is not part of `process_elr`.
- The regression re-runs `scripts/run_blind.py` on the frozen run-19 inputs into a **new artifacts folder**, then diffs it against `run-overflowfix` (run 19's exact output). **Nothing is loaded into the DB.**

**Tech Stack:** Python 3.12, pytest, pymupdf, existing `mark_engine`.

**Spec:** `docs/superpowers/specs/2026-11-05-auto-review-flow-design.md` (§2.2, §2.3, §8, §9 step 1)

## Facts from run 19 data (2026-11-05)

- **`CURRENT_STEP`:** the run-19 Oracle snapshot (`artifacts/blind-2026h2/oracle/elr_meta.json`, 402 ELRs) only has `7` (347) and `1` (55). There is **no `6`**, because it was captured after those ELRs had moved on. So G0 cannot be regressed on run 19, and the Mark Engineer step value must come from live Oracle (Task 4).
- **TBD:** 29 ELRs have `CUST_ASSY_LOT = 'TBD'`, so G1 will move these to HOLD. 3 have `1STBOND`, which must **not** match.
- **Already in the engine, so no new code and no new tests:**
  - ABS+SLR required: `SLR_NOT_FOUND` HOLD, `test_missing_slr_hold`.
  - Type E / layout ZY: `test_type_code_p_not_eligible`, `test_layout_code_zy_not_eligible`.
  - Layout Fix cells: `tests/unit/test_mark_layout.py::test_layout_reserves_fixed_and_blank_cells`, `test_fixed_text_replaces_conflicting_generated_text_in_fully_fixed_row`.

## Global Constraints

- **Read-only sources:** Oracle stays read-only (`connect_actl` + `select` from `mark_engine.adapters.oracle_client`, SELECT only), and NAS stays read-only.
- **Do not touch:**
  - R0 `D:\CIM Project\mark`
  - DB runs 1–19
  - `mark_logic` / `mark_app` (no writes)
  - the untracked `models/`
- **Regression output:** it goes only to `artifacts/blind-2026h2/run-gates/`, which is git-ignored. Do **not** run `scripts/load_r1_to_pg.py`.
- **Privacy:** never print or commit mark values, SLR text or image paths. Reports list ELR numbers and status names only.
- **Tests:** no duplicate tests (user rule). Add only tests that pin new behaviour.
- **Docs:** every commit also updates `HANDOFF.md` §4 and `docs/qa/QA_LOG.md`.
- **Done means pushed and green:** a task is done only after push **and** a green Jenkins build (http://localhost:8080/job/mark-web).
- **Engine version:** `ENGINE_VERSION` goes to `"0.4.0"` in Task 5 (the outputs change). Do not re-freeze (`FREEZE-R1.json`) in this plan; the user decides after reading the diff.
- **Plan ticks:** tick a step only after it is actually done, in order.

## Review Focus

1. **`CUST_ASSY_LOT` lookalikes:** `" tbd "` or `"Tbd"` must HOLD, but `"1STBOND"`, `None` and `""` must not. Covered in Task 1's test.
2. **Closed ELR that is also TBD:** STATUS `C` stays NOT_ELIGIBLE (closed wins), and a TBD on a ZY layout is HOLD (TBD comes before the layout gate, per the user's order). Covered in Task 1's test.
3. **SLR without a SPECIAL INSTRUCTIONS header:** its line instructions are ignored, but its scheduled lots still feed lot encoding. Covered in Task 2's tests.
4. **Two SLRs where only one has the header:** the job counts as Special, because the header is found in the joined text. Covered in Task 2's parse test.
5. **Exactly 5 TOP rows:** not held. 6 TOP rows: HOLD. BOTTOM rows are not counted. Covered in Task 3's test.

---

### Task 1: G1 — Cust Assy TBD holds the job

**Files:**
- Modify: `mark_engine/pipeline.py:166-196` (split the eligibility gate)
- Test: `tests/unit/test_pipeline.py`

**Interfaces:**
- Produces: `hold_reason == "CUST_ASSY_TBD"` with `ProcessingStatus.HOLD`, `verification_status=None`, `resolution=None`, `expected=None`. Each Oracle line becomes `LineComparison(status=NOT_MEASURABLE, detail="CUST_ASSY_TBD")`, the same shape as the document HOLD.
- **Gate order inside `process_elr`:**
  1. `STATUS == 'C'` → NOT_ELIGIBLE
  2. TBD → HOLD
  3. type not `E` or layout `ZY` → NOT_ELIGIBLE
  4. documents (as before)

- [x] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize("lot, status, layout, expect_hold", [
    (" tbd ", "A", "ZY", True),      # TBD wins over the ZY layout gate (user order)
    ("Tbd", "A", "STD", True),
    ("TBD", "C", "STD", False),      # closed ELR stays NOT_ELIGIBLE
    ("1STBOND", "A", "ZY", False),   # contains "TB" but is not TBD
    (None, "A", "ZY", False),
])
def test_cust_assy_tbd_gate(tmp_path: Path, lot, status, layout, expect_hold):
    meta = ElrMeta(elr_no="ADI2601020", status=status, top_type_code="E",
                   top_layout_code=layout, cust_assy_lot=lot)
    oracle = OracleMark(elr_no="ADI2601020", lines=((Side.TOP, 1, "ADW"),))
    job = process_elr(meta, oracle, tmp_path, ["1_JAN"], tmp_path / "work", _rules(),
                      lambda elr, stem: InferenceResult(elr))
    if expect_hold:
        assert (job.processing_status, job.hold_reason) == (ProcessingStatus.HOLD, "CUST_ASSY_TBD")
        assert job.resolution is None and job.verification_status is None
        assert job.comparisons[0].status == LineStatus.NOT_MEASURABLE
        assert job.comparisons[0].detail == "CUST_ASSY_TBD"
    else:
        assert job.comparisons[0].status == LineStatus.NOT_ELIGIBLE
```

- [x] **Step 2: Run the test.** `python -m pytest tests/unit/test_pipeline.py -k cust_assy_tbd -q`. Expected: the first two cases FAIL (they get NOT_ELIGIBLE or a document HOLD instead).
- [x] **Step 3: Implement.** In `process_elr`, split the combined eligibility `if` into the three ordered checks above. TBD means `(meta.cust_assy_lot or "").strip().upper() == "TBD"`.
- [x] **Step 4: Run the unit suite.** `python -m pytest tests/unit -q -p no:cacheprovider`. Expected: all pass.
- [x] **Step 5: Commit and push.** Use `git commit -m "feat(engine): G1 hold when Cust Assy is TBD"`, then push and wait for Jenkins to go green.

### Task 2: Special requirement only when the SLR has SPECIAL INSTRUCTIONS

**Files:**
- Modify: `mark_engine/domain/models.py:150-156` (`SlrFacts`)
- Modify: `mark_engine/slr/parse.py:97-110` (set the flag)
- Modify: `mark_engine/pipeline.py` (SLR extraction block, after `parse_slr`)
- Test: `tests/unit/test_slr_parse.py`, `tests/unit/test_pipeline.py`

**Interfaces:**
- Produces: `SlrFacts.special: bool = False`. `parse_slr(text)` sets it to `True` exactly when the existing `SPECIAL INSTRUCTIONS` section regex matches. **`parse_slr`'s other output is unchanged**, so existing parse tests keep passing.
- Produces: in `process_elr`, when `not slr_facts.special`, use `dataclasses.replace(slr_facts, instructions=(), unresolved=())`. Scheduled lots and the qual lot are kept, and the SLR is still required (G3 is unchanged).

- [x] **Step 1: Write the failing tests**

```python
# tests/unit/test_slr_parse.py
def test_special_flag_follows_section_header() -> None:
    plain = "Line 1: Q1.\nScheduled Lot ID\n7284173.1\n"
    with_header = "HEADER\nSPECIAL INSTRUCTIONS\nLine 1: Q1.\nANALOG\nDEVICES\n"
    assert parse_slr(plain).special is False
    assert parse_slr(plain).scheduled_lots          # lots still parsed without the header
    assert parse_slr(with_header).special is True
    assert parse_slr(plain + "\n" + with_header).special is True   # two SLRs joined, one has it

# tests/unit/test_pipeline.py
def test_slr_without_special_instructions_uses_abs_only(month_tree: Path, tmp_path: Path):
    # same inputs as test_match_slr_match_all, but the SLR has no SPECIAL INSTRUCTIONS header
    _, meta = _setup_elr(month_tree, "ADI2601021", include_slr=True, slr_instruction="Line 1: Q1",
                         special_header=False)
    oracle = OracleMark(elr_no="ADI2601021", lines=((Side.TOP, 1, "Q1"),))
    loader = lambda elr, stem: InferenceResult(
        elr, lines=(LayoutLine(side=Side.TOP, line_no=1, text="ADW", graphics=""),), layout_source="auto")
    job = process_elr(meta, oracle, month_tree, ["1_JAN"], tmp_path / "work", _rules(), loader)
    assert job.comparisons[0].status != LineStatus.MATCH_SLR
    assert all(t.source != "SLR" for line in job.expected.lines for t in line.tokens)
```

  For the pipeline test, give `_setup_elr` a new keyword `special_header: bool = True`. When `False`, it writes the SLR body without the `SPECIAL INSTRUCTIONS` line. Existing callers are unchanged.
- [x] **Step 2: Run the tests.** `python -m pytest tests/unit/test_slr_parse.py tests/unit/test_pipeline.py -k "special" -q`. Expected: FAIL (`special` doesn't exist yet, and the SLR instruction is applied).
- [x] **Step 3: Implement** the field, the flag and the pipeline `replace`, exactly as described in Interfaces.
- [x] **Step 4: Run the unit suite.** Expected: all pass. If an existing test relied on header-less SLR instructions, **stop and report it to the user**, because it is a behaviour change the user must see. Do not edit the old test to make it pass.
- [x] **Step 5: Commit and push.** Use `git commit -m "feat(engine): SLR instructions apply only to Special requirement (SPECIAL INSTRUCTIONS)"`, then wait for green.

### Task 3: G5 — more than 5 TOP rows holds the job

**Files:**
- Modify: `mark_engine/pipeline.py` (right after the empty-inference `NO_LAYOUT` return, before `generate_expected`)
- Test: `tests/unit/test_pipeline.py`

**Interfaces:**
- Produces: when `inference.lines` has more than 5 lines with `side == Side.TOP`, the job is HOLD with `hold_reason "ROW_OVER_5"` and `hold_detail f"{n} TOP rows"`. `resolution` is kept, so the reviewer can still open the documents. `expected=None`. Comparisons are NOT_MEASURABLE with `detail "ROW_OVER_5"`. `layout_source` is set from `inference`.

- [x] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize("top_rows, bottom_rows, expect_hold", [(5, 2, False), (6, 0, True)])
def test_row_over_5_gate(month_tree: Path, tmp_path: Path, top_rows, bottom_rows, expect_hold):
    _, meta = _setup_elr(month_tree, f"ADI26010{30 + top_rows}", include_slr=True)
    lines = tuple(LayoutLine(side=Side.TOP, line_no=i, text="ADW", graphics="") for i in range(1, top_rows + 1)) + \
            tuple(LayoutLine(side=Side.BOTTOM, line_no=i, text="X", graphics="") for i in range(1, bottom_rows + 1))
    oracle = OracleMark(elr_no=meta.elr_no, lines=((Side.TOP, 1, "ADW"),))
    job = process_elr(meta, oracle, month_tree, ["1_JAN"], tmp_path / "work", _rules(),
                      lambda elr, stem: InferenceResult(elr, lines=lines, layout_source="auto"))
    if expect_hold:
        assert (job.processing_status, job.hold_reason) == (ProcessingStatus.HOLD, "ROW_OVER_5")
        assert job.resolution is not None and job.expected is None
        assert job.comparisons[0].detail == "ROW_OVER_5"
    else:
        assert job.hold_reason != "ROW_OVER_5"
```

- [x] **Step 2: Run the test.** Expected: the `6` case FAILS.
- [x] **Step 3: Implement** the gate as described in Interfaces.
- [x] **Step 4: Run the unit suite.** Expected: all pass.
- [x] **Step 5: Commit and push.** Use `git commit -m "feat(engine): G5 hold when OCR gives more than 5 TOP rows"`, then wait for green.

### Task 4: G0 — pending Mark Engineer review selector, and confirm the step value

**Files:**
- Create: `mark_engine/select.py`
- Test: `tests/unit/test_select.py`

**Interfaces:**
- Produces: `pending_reason(meta: ElrMeta, review_step: str) -> str | None`. It returns `None` when the ELR should be processed, otherwise one of these, checked in this order:
  - `"STATUS_C"`: `STATUS` is `C` after strip and upper.
  - `"NOT_MARK_REVIEW_STEP"`: `(meta.current_step or "").strip() != review_step.strip()`.
- `CUST_CODE='ADI'` is enforced in the scanner's SQL (build step 3), not here.
- Produces: `review_step_from_env() -> str`, which returns `os.environ.get("MARK_REVIEW_STEP", "6")`. Build step 3 consumes both.

- [x] **Step 1: Write the failing test**

```python
def test_pending_reason(monkeypatch):
    m = lambda **kw: ElrMeta(elr_no="ADI2601040", **kw)
    assert pending_reason(m(status="R", current_step=" 6 "), "6") is None
    assert pending_reason(m(status="c", current_step="6"), "6") == "STATUS_C"
    assert pending_reason(m(status="R", current_step="7"), "6") == "NOT_MARK_REVIEW_STEP"
    assert pending_reason(m(status="R", current_step=None), "6") == "NOT_MARK_REVIEW_STEP"
    monkeypatch.delenv("MARK_REVIEW_STEP", raising=False)
    assert review_step_from_env() == "6"
```

- [x] **Step 2: Run the test.** Expected: FAIL (module missing).
- [x] **Step 3: Implement** `mark_engine/select.py`.
- [x] **Step 4: Run the unit suite.** Expected: all pass.
- [x] **Step 5: Read-only Oracle check of the step value.** Run one SELECT through `connect_actl()` and `select()`, the same way `scripts/fetch_oracle_snapshot.py` does: `SELECT CURRENT_STEP, COUNT(*) FROM ACTLDBA.ELR WHERE CUST_CODE = 'ADI' AND STATUS <> 'C' GROUP BY CURRENT_STEP`. Record **only the step values and counts** in QA_LOG. Then **[USER]** confirm which value means "Mark Engineer review", and put it in `.env` as `MARK_REVIEW_STEP` (and in `.env.example` with no secret).
- [ ] **Step 6: Commit and push.** Use `git commit -m "feat(engine): G0 pending-review selector"`, then wait for green.

### Task 5: Regression on run-19 inputs and change report

**Files:**
- Modify: `mark_engine/version.py` (`ENGINE_VERSION = "0.4.0"`)
- Create: `scripts/diff_runs.py`
- Test: `tests/unit/test_diff_runs.py`

**Interfaces:**
- Produces:
  - `job_state(row: dict) -> str`, which returns `processing_status` plus `":"` plus (`hold_reason` if HOLD/FAILED, else `verification_status`).
  - `diff_jobs(base: list[dict], new: list[dict]) -> dict[tuple[str, str], list[str]]`, which maps `(old_state, new_state)` to the sorted `elr_no`s for every ELR whose state changed. Rows are the `jobs.csv` rows.
- CLI: `python scripts/diff_runs.py --base DIR --new DIR` prints:
  - a table of `old → new: count`
  - the ELR numbers per group
  - the line-level `final_status` count change from `lines.csv`
  - It prints no mark values.

- [ ] **Step 1: Write the failing test**

```python
def test_diff_jobs_groups_changed_elrs():
    base = [{"elr_no": "A1", "processing_status": "DONE", "hold_reason": "", "verification_status": "MATCH_ALL"},
            {"elr_no": "A2", "processing_status": "DONE", "hold_reason": "", "verification_status": "HAS_DIFF"}]
    new = [{"elr_no": "A1", "processing_status": "DONE", "hold_reason": "", "verification_status": "MATCH_ALL"},
           {"elr_no": "A2", "processing_status": "HOLD", "hold_reason": "CUST_ASSY_TBD", "verification_status": ""}]
    assert diff_jobs(base, new) == {("DONE:HAS_DIFF", "HOLD:CUST_ASSY_TBD"): ["A2"]}
```

- [ ] **Step 2: Run it.** Expected: FAIL. Then **Step 3:** implement `scripts/diff_runs.py`, and **Step 4:** run it again. Expected: PASS.
- [ ] **Step 5: Bump** `ENGINE_VERSION` to `"0.4.0"`, then run the unit suite. Expected: all pass. If a test pins `"0.3.0"`, update that pin only.
- [ ] **Step 6: Regression.**

  `PYTHONPATH=. python scripts/run_blind.py --oracle artifacts/blind-2026h2/oracle --cache artifacts/blind-2026h2/cache --out artifacts/blind-2026h2/run-gates --months 7_JUL 8_AUG 9_SEP 10_OCT 11_NOV --allow-unfrozen`

  Expected: `jobs: 402`, `failed: 0`.
- [ ] **Step 7: Diff.** `python scripts/diff_runs.py --base artifacts/blind-2026h2/run-overflowfix --new artifacts/blind-2026h2/run-gates`.
  - **Expected:** every changed ELR falls into a group explained by Tasks 1–3:
    - `→ HOLD:CUST_ASSY_TBD`: about 29 ELRs, all with `CUST_ASSY_LOT = TBD`
    - `→ HOLD:ROW_OVER_5`
    - changes from SLRs without the header
  - **Any other group is a bug:** stop and report it.
  - Paste the table and groups (ELR numbers only) into QA_LOG and HANDOFF §4.
- [ ] **Step 8: [USER] Review the diff.** The user confirms the changed ELRs are correct, especially the header-less SLR group. **Do not load `run-gates` into the DB, and do not re-freeze.** Both are the user's call after this review.
- [ ] **Step 9: Commit and push.** Use `git commit -m "test: run-19 regression of engine gates (0.4.0) and diff report"`, then wait for green. The `artifacts/` output is not committed.
