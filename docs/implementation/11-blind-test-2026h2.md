# Phase 1 closeout: July–November 2026 blind evaluation

**Status: frozen holdout evaluation completed and loaded as DB run 17, with material limitations below.**

## Inputs and safeguards

- Oracle snapshot: 402 ELRs across July–November 2026; 6,207 layout cells, fetched 2026-11-04 17:02 UTC (2026-11-05 00:02 Bangkok). November is only a partial month as of that cutoff. The snapshot and source customer documents are stored only under ignored `artifacts/`.
- Document extraction: 287 ELR/image mappings, 118 unique images, 115 document-resolution holds and no image-extraction exceptions.
- Expected generation uses the current `MARK_ID_LAYOUT` snapshot, not TOP/BACK mark values. Fixed layout values override corresponding generator symbols. Missing layouts and overflow are recorded as job errors.
- A prior freeze was superseded by a source-integrity fix and engine version update; the replacement freeze was generated from code commit `9a9bd92` (engine 0.2.0). The image index has been refreshed with source ABS hashes. Weights and customer images are not bundled.

## Historical checks before blind inference

- An unchanged-path R1 regression produced byte-identical line, job and parity-summary CSV/JSON artifacts to run 14.
- Historical layout hypothesis: all 2,188 nonblank TOP lines with a layout in the January–June snapshot matched the reserved blank and fixed cells (100%; threshold 95%). This validates the observed historical sample, not every possible layout.
- **Blindness limitation:** the historical metadata file also contained July–November ELRs. After the final engine freeze, the layout hypothesis check inadvertently included them and exposed an aggregate reserved-cell fit statistic to the operator. Engine/rules were already frozen, and no changes should be made in response to that exposure; report this as a frozen holdout evaluation rather than an analyst-blind experiment.
- With layout enabled, 274 of 274 evaluable historical ELRs were independent when Oracle marks were blanked; 394 ELRs had no expected result to evaluate. There were 107 per-ELR layout overflows/errors. This was historical evaluation, not a blind result.
- On 95 historical images, OCR text and box counts matched, OCR boxes differed by no more than one pixel, and YOLO classes, counts and boxes met the same tolerance. Six re-OCR candidates matched their reference text and scores. The historical sample did not trigger an auto-layout logo-trim candidate.
- Migration 0004 was applied. A 2,318-line database load was tested with rollback; old runs were unchanged. The rolled-back insert advanced the run sequence.

## Frozen holdout results

The 402-ELR snapshot was processed without changing the frozen engine or rules. The AI batch used 118 unique images, with 11 re-OCR candidates. Inference files, models, source ABS documents and snapshot hashes were checked by the runner. The independently recorded freeze identifies engine version 0.2.0 and code commit `9a9bd92`.

| Measure | Result | Meaning |
|---|---:|---|
| ELR coverage | 113 / 402 = **28.11%** | ELRs with at least one compared line |
| Line coverage | 504 / 1,313 = **38.39%** | Compared lines divided by Oracle lines, including failed jobs in the denominator |
| Hold rate | 34 / 402 = **8.46%** | Document resolution HOLD; separate from failures |
| Oracle agreement | 459 / 504 = **91.07%** | Matches among compared lines only; not accuracy over all ELRs |
| Independence | **113 / 113 = 100%** | Expected results unchanged after blanking TOP/BACK marks; 289 jobs produced no expected result and were excluded |
| Failed jobs | **141 / 402 = 35.07%** | All reported `LAYOUT_ERROR` overflow; no partial result was counted as a comparison |

The 34 HOLDs comprise 22 `BOM_NOT_FOUND`, 8 `SLR_NOT_FOUND`, 2 `NO_FOLDER`, one `REVISION_CONFLICT` and one `SLR_CONFLICT`. Among line results there were 7 `DIFF`, 38 `NEEDS_REVIEW`, 31 `DB_EMPTY` and 2 position warnings. These are system findings awaiting human review; no blind-set line was labelled confirmed `DB_WRONG`.

The `jobs.csv` artifact and the review page's processing-error panel contain ELR, MARK_ID and row for the 141 errors. Overflow messages currently do not include the complete generated text; investigation can reproduce it from the underlying documents and inference cache. The high error count and low coverage are material limitations, not a successful production-readiness result. G1–G9 debugging and any rule change are deferred to work after this holdout.

## Database and deliverables

- Migration 0004 was applied, then a dry-run was rolled back. The frozen results were loaded as **run 17**, with 723 line records and 402 job records: 227 DONE, 141 FAILED and 34 HOLD. Runs 1–14 were retained.
- Local review: `artifacts/blind-2026h2/run/review.html`; metrics and CSVs are beside it. Generate or regenerate it through `python -m services.engine.build_review`: the wrapper assigns a run-specific local storage key and disables cloud storage, so earlier review decisions cannot be reused. The underlying frozen generator still uses a shared key; do not call it directly for the holdout page. Customer-containing artifacts are Git-ignored and must not be published.
- Local team lists: `artifacts/blind-2026h2/team-lists/`; the confirmed DB-wrong list has 0 rows, the pending list has 76 rows, and the rule-approval list covers D-22–D-29. The list's `effect_lines_run14` values have not been measured and are blank.
- The source bundle that reproduces run 17 is archived in `artifacts/release-run17/` (evaluation hash prefix `ca52fd3932d2`). Separate delivery bundles and hashes are in `artifacts/release-phase1/` (delivery hash prefix `3eb7df875ba6`); these include a post-evaluation loader wording correction and therefore have a different source freeze. Engine and rule logic are unchanged; the delivery freeze did not produce run 17. See `services/README.md`. Neither bundle contains customer images, model weights or `.env`.

## Interpretation and remaining work

This completes the requested Phase 1 implementation and frozen holdout execution through the stated snapshot cutoff. It does **not** establish production readiness: the sample is not analyst-blind as noted above, November is incomplete, coverage is 28.11%, and the 141 errors and 76 pending review lines need investigation. The report is not a full-month November result. Phase 2 web, orchestration and production services remain separate work; notification in this phase is on screen only.
