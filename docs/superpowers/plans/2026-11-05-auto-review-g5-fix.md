# Auto Review Flow — Step 1 follow-up: G5 counts placed content, not raw OCR rows

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Do this **after** finishing `2026-11-05-auto-review-engine-gates.md` Task 5. The user reviewed that diff on 2026-11-05 (see "Why").

**Goal:** G5 holds a job only when there is real content that can't be placed in TOP rows 1–5.

**Spec:** `docs/superpowers/specs/2026-11-05-auto-review-flow-design.md` §2.2 G5. The user decided on 2026-11-05: "count rows after placement on the Layout".

## Why (run-19 regression, engine 0.4.0)

- **What happened:** G5 counted raw OCR TOP rows, and 18 ELRs went to `HOLD:ROW_OVER_5`, every one with exactly "7 TOP rows".
  - This includes ADI2607022, which was MATCH_ALL 5/5.
- **The extra rows are empty:** in all 18, OCR rows 6 and 7 have **no text and no graphics**. They are empty layout rows. The engine already places only rows 1–5 (`pipeline.py`, `for number in range(1, 6)`).
- **User review of the diff:**
  - `→ HOLD:CUST_ASSY_TBD` ×28 is accepted. ADI2607077 is STATUS C, so it stays NOT_ELIGIBLE.
  - The Special-SLR change affected 0 ELRs, as expected.
  - `→ HOLD:ROW_OVER_5` ×18 is **rejected**; it gets fixed here.

## Global Constraints

The same rules as the engine-gates plan apply:
- Read-only sources.
- No DB load and no re-freeze.
- No duplicate tests.
- Update HANDOFF §4 and QA_LOG with every commit.
- A task is done only after push and a green Jenkins build.

### Task 1: G5 on placed content

**Files:**
- Modify: `mark_engine/pipeline.py`. Move the G5 block from after inference loading to **right after `expected = generate_expected(...)`**, before the layout block.
- Test: `tests/unit/test_pipeline.py`. Extend the existing `test_row_over_5_gate`; do not add a second test.

**Interfaces:**
- **Hold condition:** `[l for l in expected.lines if l.side == Side.TOP and l.line_no > 5 and (l.text or "").strip()]` is non-empty.
- **Hold result:** `hold_reason "ROW_OVER_5"`, `hold_detail f"{n} TOP rows with content beyond row 5"`. Everything else is unchanged from the current G5 return (resolution kept, `layout_source` set).
- **Empty OCR rows beyond 5 are ignored.**

- [ ] **Step 1: Extend the test.** Add a case to `test_row_over_5_gate`'s parametrize: **7 TOP rows where rows 6–7 have `text=""` and `graphics=""`** → not held. Keep the existing `(5, 2, False)` case. Change the `(6, 0, True)` case so row 6 has text `"ADW"`; it must still hold. Pass the row texts in through the parametrize.
- [ ] **Step 2: Run it.** `python -m pytest tests/unit/test_pipeline.py -k row_over_5 -q`. Expected: the new empty-rows case FAILS.
- [ ] **Step 3: Implement** as described in Interfaces.
- [ ] **Step 4: Run the unit suite.** `python -m pytest tests/unit -q -p no:cacheprovider`. Expected: all pass.
- [ ] **Step 5: Regression again.**

  `PYTHONPATH=. python scripts/run_blind.py --oracle artifacts/blind-2026h2/oracle --cache artifacts/blind-2026h2/cache --out artifacts/blind-2026h2/run-gates --months 7_JUL 8_AUG 9_SEP 10_OCT 11_NOV --allow-unfrozen --workers 3`

  Use `--workers 3`, because RAM ran out at 8 on 2026-11-05. Then run `python scripts/diff_runs.py --base artifacts/blind-2026h2/run-overflowfix --new artifacts/blind-2026h2/run-gates`.
  - **Expected:** the only job-level groups are `→ HOLD:CUST_ASSY_TBD` (27 + 1 = 28 ELRs), with **no `ROW_OVER_5`**.
  - **Anything else:** stop and report it.
  - Paste the report (ELR numbers only) into QA_LOG and HANDOFF.
- [ ] **Step 6: Commit and push.** Use `git commit -m "fix(engine): G5 holds only when content lands beyond TOP row 5"`, then wait for Jenkins to go green.
