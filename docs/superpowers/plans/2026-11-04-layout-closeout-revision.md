# Phase 1 Layout Closeout Revision Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. This revision supersedes conflicting instructions in the closeout plan, especially Tasks 3–5 and the D-10 prohibition on reading layouts.

**Goal:** Generate position-aware expected marks using ACTIVEL layout, then run the frozen July–November blind evaluation.

**Architecture:** Fetch layout by ELR mark ID; apply fixed cells and place generated values in cells absent from the layout before comparison. Oracle mark values remain excluded from expected generation. Preserve the existing pipeline's other eligibility and document gates.

**Tech Stack:** Python, pytest, Oracle, PostgreSQL, existing OCR and YOLO tooling.

**Spec:** `docs/superpowers/specs/2026-11-04-phase1-completion-and-phase2-design.md`; user decisions in this revision override conflicting text.

## Global Constraints

- Oracle and source snapshots are read-only. Secrets stay in ignored `.env`; customer artifacts remain ignored.
- A layout row reserves its 1-based grid cell: space means blank, non-space means fixed value. An absent cell accepts generated text. A–C precede the 18-cell grid.
- Fixed values win over generator values. Missing layout and overflow are errors, with ELR, mark ID and line where applicable. Continue other ELRs; never silently truncate or compare a partial result.
- Expected output may use layout, but never TOP_MARK/BACK_MARK or review verdicts. Report independence denominator and exclusions.
- Do not freeze until the algorithm and changed historical results have been validated. Do not modify old DB runs.

## Review Focus

- Missing mark ID or layout: per-ELR error, no false match (layout integration tests).
- Duplicate or invalid layout coordinates: reject rather than silently overwrite (parser tests).
- Fixed symbol already in generator output: match it once; ambiguous alignment must error rather than discard text (alignment tests).
- Overflow and fixed conflicts: no truncation; fixed value wins and conflict is visible (alignment tests).
- Missing inference outputs or NAS month: abort or report accurately, never report a successful blind run (blind runner tests).

## Tasks

1. **Oracle access and migration:** execute Tasks 1–2 of `2026-11-04-phase1-closeout-blind-test.md`; defer the DBA migration and DB load if credentials unavailable. Test read-only guards and loader. Do not print credentials.
2. **Empirical layout validation:** retrieve representative layouts and ELRs, including 20168 / ADI2601085. Record fixed positions, free positions, spaces, multiple fixed values and examples of generator output. Confirm how to resolve ambiguous fixed-symbol alignment; reject ambiguous cases until supported by evidence. Record observed facts without customer data in tracked files.
3. **Expected layout:** implement and test parsing and alignment before comparison. Validate 20168 rows `*  YYWW`, ` 1963`, `  EFE15`, `  BSSOP<`; ensure fixed cells take precedence and are not duplicated. Add missing layout, overflow, invalid coordinates, conflicts and ambiguity tests. Preserve bottom-side behavior and report per-ELR errors.
4. **Regression and independence:** rerun run 14 and document changed counts and examples, rather than require parity. For each eligible case mutate TOP/BACK marks without changing layout and assert expected unchanged; changing fixed layout must affect expected. Record numerator, denominator and excluded cases.
5. **Snapshots and inference:** execute Tasks 6–8 and the writer refactor in Task 10 of the original plan before freeze. Check historical output after refactor. Implement Task 9 and compare det/rec, YOLO and re-OCR outputs to historical references before blind inference.
6. **Freeze:** freeze engine, rules, inference scripts and model identities after code changes; record snapshot hashes separately. Verify each hash before an official run. Unfrozen results must never be labelled official.
7. **Blind run and reporting:** execute Tasks 10–11 with per-ELR layout errors and complete cache validation. Load a new run only when migration and credentials are available. Separate system-detected differences awaiting review from human-confirmed DB_WRONG. Produce metrics with denominators and error counts, review page and team lists.

## Validation

Run targeted tests for each task and the full Python suite; run historical comparison before freeze. Record failures and external blockers in HANDOFF and QA_LOG. AI-server access and PostgreSQL credentials are external prerequisites for the live inference and DB load.
