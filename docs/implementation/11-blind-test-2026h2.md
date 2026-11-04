# Phase 1 closeout: July–November 2026 blind evaluation

**Status: pending — internal network unavailable; not yet a final result.**

## Inputs and safeguards

- Oracle snapshot: 402 ELRs across July–November 2026; 6,207 layout cells. The snapshot and source customer documents are stored only under ignored `artifacts/`.
- Document extraction: 287 ELR/image mappings, 118 unique images, 115 document-resolution holds and no image-extraction exceptions.
- Expected generation uses the current `MARK_ID_LAYOUT` snapshot, not TOP/BACK mark values. Fixed layout values override corresponding generator symbols. Missing layouts and overflow are recorded as job errors.
- A prior freeze was superseded by a source-integrity fix; the replacement freeze was generated from code commit `318a770`. The image index must be refreshed from NAS before the official AI batch. Weights and customer images are not bundled.

## Historical checks before blind inference

- An unchanged-path R1 regression produced byte-identical line, job and parity-summary CSV/JSON artifacts to run 14.
- With layout enabled, 274 of 274 evaluable historical ELRs were independent when Oracle marks were blanked; 394 ELRs had no expected result to evaluate. There were 107 per-ELR layout overflows/errors. This was historical evaluation, not a blind result.
- On 95 historical images, OCR text and box counts matched, OCR boxes differed by no more than one pixel, and YOLO classes, counts and boxes met the same tolerance. Six re-OCR candidates matched their reference text and scores. The historical sample did not trigger an auto-layout logo-trim candidate.
- Migration 0004 was applied. A 2,318-line database load was tested with rollback; old runs were unchanged. The rolled-back insert advanced the run sequence.

## Blind results

Pending AI batch, frozen evaluation, independent-check gate and DB load. Do not cite this document as a completed Phase 1 report until those steps finish and results are recorded here.
