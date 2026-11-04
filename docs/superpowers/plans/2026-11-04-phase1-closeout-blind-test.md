# Phase 1 Close-out — ACTIVEL layout, rule freeze, blind test Jul–Nov 2026 · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the run-14 engine, frozen, on ELRs Jul–Nov 2026 straight from Oracle ACTL + NAS. Report Coverage, Hold Rate and Oracle agreement separately. Add ACTIVEL cell positions (`MARK_ID_LAYOUT`) as a warning. Load the result as a new DB run that the Phase 2 web pages can read.

**Architecture:** Nothing changes in the engine core. New IO sits in `mark_engine/adapters/`:
- `env` / Oracle client
- an Oracle snapshot fetch
- an inference cache in the same file formats R0 used for May–Jun (`images_index.csv`, `det_rec.json`, `detections.json`, `reocr.csv`)

ACTIVEL positions live in the compare stage (`mark_engine/compare/layout_position.py`), never in generate (D-10). OCR and YOLO run as batch jobs on the AI server with the same models as R1. The blind runner reads only their cache.

**Tech Stack:**
- Python 3.12, pytest 8, pymupdf, psycopg2
- python-oracledb 4.x in **thick mode**, because ACTL is Oracle 10g. Instant Client: `D:\CIM Project\Search_data\.tools\instantclient_21_13`
- On the AI server 10.151.28.9: PaddleOCR (PP-OCRv5_server_det + EXP09 rec), ultralytics YOLOv8 (`models/symdet/v2`)

**Spec:** `docs/superpowers/specs/2026-11-04-phase1-completion-and-phase2-design.md` (part A, answers §9). Main spec: `docs/superpowers/specs/2026-11-04-mark-automation-design.md`. Logic reference: `docs/implementation/10-r1-logic-review-and-next-phase.md`.

**Out of scope (separate plans):**
- Part B (Phase 2 system B1–B7). Plan B1–B2 comes after this one, because B2's first data is this blind run.
- Debug G1–G9 (A6, after the blind test, per user answer §9.2).
- A8 merge/push (user command only).

## Global Constraints

**Read-only sources and frozen data**
- Oracle is read only. Every Oracle statement goes through `mark_engine/adapters/oracle_guard.assert_select_only`, and every session starts with `SET TRANSACTION READ ONLY`.
- Do not modify anything in `D:\CIM Project\mark` (R0). Its scripts are read as references and ported, never run against new data.
- Never update DB runs 1–14 or `mark_logic.logic_rule`. Every load is a new `run_id`.

**Secrets and customer data**
- Secrets live only in `D:\CIM Project\mark-web\.env`, which is git-ignored. The variable names are in `.env.example`.
- Code reads secrets with `os.environ` after `load_env()`. Never print, log or commit a password.
- Customer data (PDF, PNG, CSV of results, Oracle snapshots) goes only under git-ignored `artifacts/`.
- The blind cache dir is `artifacts/blind-2026h2/`.

**Engine rules (unchanged from Phase 1)**
- `generate_expected()` never reads `OracleMark`, TOP/BACK_MARK, `MARK_ID_LAYOUT` or `MARK_ID_SYMBOL` (D-10). Independence must stay at 100%.
- Web scope is TOP only, but the engine still computes BOTTOM. Do not drop BOTTOM rows from artifacts.
- The blind test runs on the rules and code frozen in Task 5. No rule or engine edit between the freeze and the final blind report (spec §17).

**Blind scope**
- ELR prefixes `ADI2607` `ADI2608` `ADI2609` `ADI2610` `ADI2611`.
- NAS months `7_JUL` `8_AUG` `9_SEP` `10_OCT` `11_NOV` under `\\th1srnas03\ELR\ADI\ELR Online 2026`.

**Every task, per user rule**
- Each task's commit also updates `HANDOFF.md` §4 (newest on top) and `docs/qa/QA_LOG.md` (Context & Symptom / Root Cause / Resolution & Code Fix / Prevention).
- Commit on branch `phase1/mark-engine` only. No push.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- The test baseline before starting is 219 unit + 3 regression passing. Each task ends with `python -m pytest -q` all green.

## Review Focus

1. **NAS share not mounted, or a month folder missing.** The blind runner must stop with an error naming the path. It must not finish with every ELR in `HOLD:NO_FOLDER`. Test: Task 10 `test_blind_refuses_missing_nas_month`.
2. **Engine or rule file edited after the freeze.** The blind runner refuses to run (hash mismatch) unless given `--allow-unfrozen`, and an unfrozen run is labelled `UNFROZEN` in `metrics.json`. Test: Task 5 `test_freeze_detects_code_change`.
3. **ELR filed under a different month folder than its ELR number suggests** (e.g. ADI2607xxx under `8_AUG`). The runner passes all five months to the resolver. Test: Task 10 `test_blind_scans_all_months`.
4. **TOP_MARK_ID with no `MARK_ID_LAYOUT` rows, or a line longer than the free cells.**
   - No rows: no position warning and no crash.
   - Line longer than the free cells: warning `LAYOUT_OVERFLOW`.
   - The status never changes in either case.
   - Tests: Task 4 `test_no_template_no_warning`, `test_overflow_warns`.
5. **Oracle returns two revisions of one ELR** (ELR_REV changed during the period). The snapshot keeps only the highest `ELR_REV` per `ELR_NO`. Test: Task 6 `test_rows_to_meta_keeps_latest_rev`.

---

## File Structure

| File | New/Mod | Responsibility |
|---|---|---|
| `mark_engine/adapters/env.py` | new | `load_env()` — tiny `.env` reader, no dependency |
| `mark_engine/adapters/oracle_client.py` | new | thick-mode connect, read-only session, guarded `select()` |
| `mark_engine/adapters/oracle_snapshot.py` | new | Oracle rows → snapshot JSON (same shape as R0 `elr_meta_2026.json`) + layout JSON |
| `mark_engine/compare/layout_position.py` | new | ACTIVEL template parse, fill, position warning |
| `mark_engine/abs/auto_inference.py` | new | shared "auto layout" builder (det_rec items + YOLO + reocr → `InferenceResult`) |
| `mark_engine/adapters/snapshot.py` | mod | May–Jun branch calls `auto_inference.build_auto_inference` (behaviour identical) |
| `mark_engine/adapters/inference_cache.py` | new | `load_cached_inference(cache_dir, elr_no, abs_stem)` |
| `mark_engine/abs/brand_page.py` | new | Brand/Marking image extraction from ABS PDF (port of R0 `extract_marking_images.py`) |
| `mark_engine/freeze.py` | new | code + rule hash, freeze record check |
| `mark_engine/domain/models.py` | mod | `ElrMeta.top_mark_id: int \| None = None` |
| `mark_engine/pipeline.py` | mod | optional `templates` arg → position warnings after compare |
| `mark_engine/regression/artifacts.py` | new | `write_jobs_csv`, `write_lines_csv` moved out of `run_regression.py` |
| `migrations/0004_line_result_review_columns.sql` | new | nullable columns on `mark_logic.line_result` |
| `scripts/load_r1_to_pg.py` | mod | write new columns, months 07–11, `--period` |
| `scripts/fetch_oracle_snapshot.py` | new | CLI for the snapshot fetch |
| `scripts/check_layout_hypothesis.py` | new | verifies §2.1 assumption on run-14 ELRs |
| `scripts/freeze_rules.py` | new | writes `mark_engine/rules/data/FREEZE-R1.json` + git tag |
| `scripts/blind_extract_images.py` | new | resolve ABS on NAS → Brand PNG + `images_index.csv` |
| `infer/det_rec_batch.py`, `infer/yolo_batch.py`, `infer/reocr_batch.py`, `infer/README.md` | new | run on AI server; write cache files |
| `scripts/run_blind.py` | new | blind runner |
| `scripts/export_team_lists.py` | new | CSVs for Marking team (A7) and Mark Eng rule approval (A5) |
| `docs/implementation/11-blind-test-2026h2.md` | new | blind result report |

---

### Task 1: `.env` loader and read-only Oracle client

**Files:**
- Create: `mark_engine/adapters/env.py`
- Create: `mark_engine/adapters/oracle_client.py`
- Test: `tests/unit/test_env.py`
- Test: `tests/unit/test_oracle_client.py`

**Interfaces:**
- Produces:
  - `load_env(path: Path | None = None, override: bool = False) -> dict[str, str]`. Default path is the repo root `.env`. It sets `os.environ` only for keys not already set unless `override` is true, and returns the parsed dict. A missing file returns `{}`.
  - `connect_actl() -> oracledb.Connection`. It reads `ACTL_HOST`, `ACTL_PORT`, `ACTL_SERVICE`, `ACTL_USER`, `ACTL_PASSWORD` and `ORACLE_CLIENT_DIR`, calls `init_oracle_client(lib_dir=...)` once, and executes `READ_ONLY_TXN`.
  - `select(conn, sql: str, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]`. It calls `assert_select_only(sql)` first. Keys are upper-case column names.

- [ ] **Step 1: Write failing tests**

```python
def test_env_keeps_backslashes_and_at(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text('# c\nNAS_ROOT=\\\\th1srnas03\\ELR\\ADI\nNAS_USER=TH\\41451475\nX=a@b=c\n\n', encoding="utf-8")
    for k in ("NAS_ROOT", "NAS_USER", "X"): monkeypatch.delenv(k, raising=False)
    d = load_env(p)
    assert d["NAS_ROOT"] == r"\\th1srnas03\ELR\ADI" and d["NAS_USER"] == r"TH\41451475" and d["X"] == "a@b=c"

def test_env_does_not_override_shell(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("MARK_PG_PASSWORD=fromfile\n", encoding="utf-8")
    monkeypatch.setenv("MARK_PG_PASSWORD", "shell")
    load_env(tmp_path / ".env"); assert os.environ["MARK_PG_PASSWORD"] == "shell"

def test_select_rejects_write(fake_conn):
    with pytest.raises(PermissionError): select(fake_conn, "DELETE FROM ACTLDBA.ELR")

def test_select_returns_upper_dicts(fake_conn):   # fake cursor: description [("mark_id",),("mark_data",)], rows [(1,"^")]
    assert select(fake_conn, "SELECT mark_id, mark_data FROM x") == [{"MARK_ID": 1, "MARK_DATA": "^"}]
```

`fake_conn` is a fixture in the test file. It is a small class with `.cursor()` returning an object with `execute`, `description` and `fetchall`.

- [ ] **Step 2:** Run `python -m pytest tests/unit/test_env.py tests/unit/test_oracle_client.py -q`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement `load_env`, `connect_actl` and `select`**
  - Split each line on the first `=` only, strip whitespace, and skip blank lines and lines starting with `#`.
  - Keep quotes off: a value `"..."` loses its surrounding quotes.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5: Live smoke test (manual, not in CI)**
  - Run `python -c "from mark_engine.adapters.env import load_env; load_env(); from mark_engine.adapters.oracle_client import connect_actl, select; c=connect_actl(); print(len(select(c, 'SELECT * FROM ACTLDBA.MARK_ID_LAYOUT WHERE MARK_ID = :m', {'m': 21355})))"`.
  - Expected: a positive integer, with no password in the output.
- [ ] **Step 6: Commit** `feat(adapters): .env loader and read-only ACTL client (thick mode)`, together with the HANDOFF and QA_LOG entries.

---

### Task 2: Migration 0004 and loader columns (A4)

**Files:**
- Create: `migrations/0004_line_result_review_columns.sql`
- Modify: `migrations/README.md` (add a row)
- Modify: `scripts/load_r1_to_pg.py`
- Test: `tests/unit/test_load_rows.py`

**Interfaces:**
- Produces:
  - Columns on `mark_logic.line_result`, all `text null`: `system_status`, `final_status`, `review_detail`, `warning`, `hold_detail`, `layout_source`.
  - `load_r1_to_pg.line_row(run_id: int, r: dict[str, str]) -> tuple`, a pure function. It builds one insert tuple from a `lines.csv` row, in the column order of the insert.
  - `MONTH` gains `"07": "7_JUL"` through `"11": "11_NOV"`.
  - A new flag `--period TEXT`. The default is the old value.
- Consumes: the current `cause_detail` packing, which stays for compatibility. Old readers keep working.

- [ ] **Step 1: Write failing tests**
  - `test_line_row_fills_new_columns`: for a row with `status=MATCH`, `final_status=DB_WRONG` and `warning=COO_ABBREVIATED`, the tuple holds `"MATCH"` at the `system_status` position, `"DB_WRONG"` at the `status` and `final_status` positions, and the warning at the `warning` position.
  - `test_month_map_covers_jul_nov`: `MONTH["11"] == "11_NOV"`.
- [ ] **Step 2:** Run `python -m pytest tests/unit/test_load_rows.py -q`. Expected: FAIL.
- [ ] **Step 3: Write the SQL**
  - Write the SQL with `-- UP` (`alter table … add column if not exists …`, one transaction) and `-- DOWN` (`drop column if exists`).
  - Refactor the loader's inline tuple building into `line_row`.
  - `status` stays = final_status, as before since run 10.
- [ ] **Step 4:** Run the same command. Expected: PASS. Then run `python scripts/load_r1_to_pg.py artifacts/regression-r1 --note dryrun`, which rolls back. Expected: "rolled back", no error. **Run this only after Step 5.**
- [ ] **Step 5 [USER]: Apply the migration**
  - The user applies `0004` UP on `10.151.28.2/mark_web` with the DBA account. The `migrations/README.md` row says "applied <date>".
  - Until then, the dry-run in Step 4 fails on the missing column; that is expected and blocks Task 11 only.
- [ ] **Step 6: Commit** `feat(db): migration 0004 review columns; loader writes them`, with HANDOFF and QA_LOG.

---

### Task 3: ACTIVEL template module and hypothesis check (A2, part 1)

**Files:**
- Create: `mark_engine/compare/layout_position.py`
- Create: `scripts/check_layout_hypothesis.py`
- Modify: `mark_engine/domain/models.py` (`ElrMeta.top_mark_id`)
- Modify: `mark_engine/adapters/snapshot.py` (`load_elr_snapshot` reads `TOP_MARK_ID`)
- Test: `tests/unit/test_layout_position.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Template: mark_id: int; fixed: Mapping[tuple[int, int], str]`. Keys are (row 1–5, col 1–18). A cell absent from `fixed` is a free cell.
  - `parse_template(mark_id: int, rows: Iterable[Mapping[str, Any]]) -> Template`. Input rows have the keys `MARK_ROW`, `MARK_COLUMN`, `MARK_DATA`. `MARK_DATA` None counts as `" "`.
  - `oracle_cells(line: str) -> str`. It returns the 18 grid characters of a TOP_MARKn value, which are characters 4–21 (index 3:21), padded to 18. The first 3 characters are cells A B C and are not part of the template.
  - `fits_template(t: Template, row: int, oracle_line: str) -> bool`. It is True when every fixed cell's non-space data equals the Oracle character there, and every non-space Oracle character outside the fixed cells sits in a free cell.
  - `ElrMeta.top_mark_id: int | None = None`, read from snapshot key `TOP_MARK_ID`.

- [ ] **Step 1: Write failing tests** (values from MARK_ID 21355, design §2.1)

```python
T = parse_template(21355, [{"MARK_ROW": 1, "MARK_COLUMN": 1, "MARK_DATA": "^"}]
    + [{"MARK_ROW": 1, "MARK_COLUMN": c, "MARK_DATA": " "} for c in [2] + list(range(5, 19))]
    + [{"MARK_ROW": 2, "MARK_COLUMN": c, "MARK_DATA": " "} for c in [1, 2] + list(range(5, 19))])

def test_free_cells_are_missing_rows():
    assert (1, 3) not in T.fixed and (1, 4) not in T.fixed and T.fixed[(1, 1)] == "^"

def test_oracle_cells_skips_abc():
    assert oracle_cells("     Q1              ")[:4] == "  Q1"

def test_fits_template_real_elr():
    assert fits_template(T, 1, "   ^ Y               ") and fits_template(T, 2, "     Q1              ")

def test_char_in_fixed_blank_cell_does_not_fit():
    assert not fits_template(T, 2, "   Q1                ")   # Q at col 1, which is fixed blank
```

- [ ] **Step 2:** Run `python -m pytest tests/unit/test_layout_position.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement the template functions**
  - Implement `parse_template`, `oracle_cells` and `fits_template`.
  - Add `top_mark_id`, parsed with `int(float(v))` when present; R0 JSON stores numbers.
- [ ] **Step 4:** Run the same command. Expected: PASS. Then run the full suite. Expected: all pass, and `test_generator_independence` is unchanged.
- [ ] **Step 5: Write and run `scripts/check_layout_hypothesis.py`**
  - The script reads run-14 snapshot ELRs (Jan–Jun, `load_elr_snapshot` on the R0 meta JSON), collects the distinct `TOP_MARK_ID`s and fetches their `MARK_ID_LAYOUT` rows in chunks of 500 via `select`.
  - For every TOP line 1–5 with non-blank Oracle text, it runs `fits_template`.
  - It prints the fit %, the number of MARK_IDs without rows, and up to 20 non-fitting examples to `artifacts/layout_check/report.txt`.
  - It also writes every fetched template to `artifacts/layout_check/layouts_r1.json` in the Task 4 layouts format, so Task 4 can rerun run 14 with positions.
  - **Gate:** a fit of 95% or more continues to Task 4. Below 95%, stop and show the user the examples. The §2.1 interpretation is wrong, and Task 4 must not start.
- [ ] **Step 6: Commit** `feat(layout): ACTIVEL template parse + hypothesis check (fit X%)`. Put the fit % in HANDOFF and QA_LOG, and in spec §2.1, replacing "[สันนิษฐาน]" with the result.

---

### Task 4: Position warning in compare (A2, part 2)

**Files:**
- Modify: `mark_engine/compare/layout_position.py`
- Modify: `mark_engine/pipeline.py`
- Modify: `scripts/run_regression.py` (`--layouts PATH`, optional)
- Test: `tests/unit/test_layout_position.py`
- Test: `tests/unit/test_pipeline.py`

**Interfaces:**
- Consumes: `Template`, `oracle_cells` (Task 3); `LineComparison.warning` (existing, joined with `;`).
- Produces:
  - `fill_line(t: Template, row: int, expected: str) -> str | None`. It returns the 18-cell string, or `None` on overflow.
  - `position_warning(t: Template | None, row: int, expected: str | None, oracle_line: str) -> str`. It returns `""`, `"LAYOUT_POSITION"` or `"LAYOUT_OVERFLOW"`.
  - `process_elr(..., templates: Mapping[int, Template] | None = None)`. The new keyword-only argument defaults to `None`, so existing callers are unchanged.
  - The layouts JSON file format is `{"<mark_id>": [[row, col, data], ...]}`. Task 6 writes it.

**Fill algorithm** (the signature does not determine it):
1. Start from the row's fixed cells.
2. Remove from `expected` (whitespace-stripped) the leading run of the row's fixed non-space characters in column order. For example, `^` is removed from `^ Y`, leaving `Y`.
3. Put the remaining non-space tokens left to right into the free cells, in column order. One space between tokens in `expected` skips one free cell.
4. Characters left over mean overflow.

- [ ] **Step 1: Write failing tests**
  - `test_fill_matches_activel`: `fill_line(T, 1, "^ Y")[:4] == "^ Y "` and `fill_line(T, 2, "Q1")[:4] == "  Q1"`.
  - `test_position_warning_none_when_same`: `position_warning(T, 2, "Q1", "     Q1") == ""`.
  - `test_overflow_warns`: `position_warning(T, 2, "Q1XYZ", "     Q1") == "LAYOUT_OVERFLOW"`.
  - `test_no_template_no_warning`: `position_warning(None, 1, "ABC", "   ABC") == ""`.
  - In `test_pipeline.py`, `test_templates_add_warning_not_status`: a fixture ELR whose Oracle puts `Q1` at col 1 gets status `MATCH` with `"LAYOUT_POSITION"` in `warning`.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3: Wire up the warning**
  - Implement it. Apply only to `Side.TOP`, only to statuses that count as match (`MATCH`, `MATCH_SLR`, `MATCH_SHIFT`, `MATCH_LOT`), and only when `templates` holds `meta.top_mark_id`.
  - Append to `warning` with `;`.
  - Use `dataclasses.replace` on the frozen comparison. Never touch `ExpectedMark`.
- [ ] **Step 4: Verify parity and record the count**
  - Run the full suite. Expected: all pass.
  - Then run `python scripts/run_regression.py --layouts artifacts/layout_check/layouts_r1.json --out artifacts/regression-r1-layout`. Task 3's script also writes that layouts file.
  - Expected: `parity_summary.json` has the same per-class counts as run 14 (BUG 0), and statuses are unchanged.
  - Record the `LAYOUT_POSITION` count.
- [ ] **Step 5: Commit** `feat(compare): ACTIVEL position warning (TOP, warning only)`, with HANDOFF and QA_LOG (count of position warnings on run-14 data).

---

### Task 5: Rule and engine freeze (A1)

**Files:**
- Create: `mark_engine/freeze.py`
- Create: `scripts/freeze_rules.py`
- Create: `mark_engine/rules/data/FREEZE-R1.json` (generated, committed)
- Modify: `mark_engine/version.py` (`ENGINE_VERSION = "0.2.0"`)
- Test: `tests/unit/test_freeze.py`

**Interfaces:**
- Produces:
  - `code_hash(pkg_dir: Path) -> str`. It is the sha256 over sorted `(relative posix path, file bytes)` of every `*.py`, `*.json` and `*.csv` under `mark_engine/`, excluding `FREEZE-*.json` and `__pycache__`.
  - `write_freeze(path: Path, rule_version: str) -> dict`. It writes `{freeze_id: "FREEZE-R1", created_at, git_commit, engine_version, rule_version, code_sha256}`.
  - `check_freeze(path: Path) -> None`. It raises `RuntimeError("engine changed since FREEZE-R1 ...")` on mismatch.
  - The git tag is `rules-r1-freeze-2026-11-04`, created by the script.

- [ ] **Step 1: Write failing tests**
  - `test_freeze_detects_code_change`: copy a tiny fake package into `tmp_path`, write the freeze, edit one file, and `check_freeze` raises.
  - `test_freeze_ignores_pycache`: adding `__pycache__/x.pyc` does not change `code_hash`.
- [ ] **Step 2:** Run `python -m pytest tests/unit/test_freeze.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement the freeze**
  - Implement `freeze.py`. The script refuses when `git status --porcelain mark_engine` is not empty.
  - `rule_version` = `RV-2026-11-04-R0`, which is the version run 14 used.
- [ ] **Step 4: Run the freeze**
  - Run the tests. Expected: PASS.
  - Run `python scripts/freeze_rules.py`, which writes the JSON. Commit it. Then run `git tag rules-r1-freeze-2026-11-04` on that commit.
  - After that, `python -c "from mark_engine.freeze import check_freeze; from pathlib import Path; check_freeze(Path('mark_engine/rules/data/FREEZE-R1.json'))"` must run without error.
- [ ] **Step 5: Commit** `chore(rules): FREEZE-R1 for blind test`, with HANDOFF (the freeze commit hash) and QA_LOG. **From here until Task 11 Step 5, no edits under `mark_engine/`.** Tasks 6–10 put their code under `scripts/`, `infer/` and new adapter files.

> The freeze hashes all of `mark_engine/`. New adapter files would break the hash, so Tasks 6–8 must add their `mark_engine` files **before** this task. **Run order: 1 → 2 → 3 → 4 → 6 → 7 → 8 → 10 (writers `mark_engine/regression/artifacts.py` only) → 5 → 9 → 10 (rest) → 11.** The numbering keeps the spec labels. Tasks 9–11 touch only `scripts/`, `infer/` and `docs/`.

---

### Task 6: Oracle snapshot fetch Jul–Nov

**Files:**
- Create: `mark_engine/adapters/oracle_snapshot.py`
- Create: `scripts/fetch_oracle_snapshot.py`
- Test: `tests/unit/test_oracle_snapshot.py`

**Interfaces:**
- Consumes: `select`, `connect_actl` (Task 1).
- Produces:
  - `rows_to_meta(rows: list[dict]) -> list[dict]`. Output is in the same key set as R0 `elr_meta_2026.json` (fields listed in `docs/implementation/02-oracle-field-mapping.md`), with only the highest `ELR_REV` kept per `ELR_NO`.
  - `layout_json(rows: list[dict]) -> dict[str, list[list]]`, in the format Task 4 reads.
  - CLI: `python scripts/fetch_oracle_snapshot.py --elr-prefix ADI2607 ADI2608 ADI2609 ADI2610 ADI2611 --out artifacts/blind-2026h2/oracle`. It writes `elr_meta.json`, `mark_layout.json`, and `fetch_info.json` (`fetched_at`, row counts, SQL text with no credentials).
- SQL: port the SELECT and joins from R0 `D:\CIM Project\mark\ActiveL_Mark V2.sql` and `fetch-elr-mark-meta-2026.mjs`. Read them; do not run them.
  - Filter `CUST_CODE = 'ADI'` and `ELR_NO LIKE :p || '%'`.
  - Do **not** filter `CURRENT_STEP` or `STATUS`; the engine's eligibility gate decides, as in run 14.

- [ ] **Step 1: Write failing tests**
  - `test_rows_to_meta_keeps_latest_rev`: two rows of `ADI2607001` with `ELR_REV` 0 and 1 give one row with rev 1.
  - `test_meta_shape_matches_r0`: the keys of a converted row are a superset of the keys of `tests/fixtures/elr_meta_sample.json[0]`.
  - `test_layout_json_groups_by_mark_id`.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the functions and the CLI. Fetch the layouts for the distinct `TOP_MARK_ID` set in chunks of 500.
- [ ] **Step 4: Fetch the data**
  - Run the tests. Expected: PASS.
  - Run the CLI. Expected: `fetch_info.json` with more than 0 ELRs per prefix. Spec §19 counted 402 ELRs Jul–Nov in Oracle; note the actual number.
- [ ] **Step 5: Commit** `feat(adapters): Oracle snapshot fetch (ELR meta + MARK_ID_LAYOUT)`, with HANDOFF and QA_LOG.

---

### Task 7: Shared auto-inference builder and inference cache adapter

**Files:**
- Create: `mark_engine/abs/auto_inference.py`
- Create: `mark_engine/adapters/inference_cache.py`
- Modify: `mark_engine/adapters/snapshot.py` (May–Jun branch only)
- Test: `tests/unit/test_inference_cache.py`

**Interfaces:**
- Produces:
  - `build_auto_inference(elr_no: str, img_stem: str, items: list, detections: list, reocr: Mapping[str, tuple[str, str]]) -> InferenceResult`. This is the body currently inline in `snapshot.load_inference` (the `layout_lines`, `assign_graphics`, `_reread` and `LayoutLine` assembly), moved verbatim. `layout_source="auto"`.
  - `load_cached_inference(cache_dir: Path, elr_no: str, abs_stem: str) -> InferenceResult`. It reads `cache_dir/images_index.csv` (columns `elr,abs_file,image`), `det_rec.json`, `detections.json` and `reocr.csv`. The formats are exactly R0's: `det_rec.json` is `{image_name: [[x0,y0,x1,y1,text,score],...]}`, `detections.json` is `{stem: [[cls,conf,x0,y0,x1,y1],...]}`, and `reocr.csv` has the columns `key,old,new,score,method`.
  - The re-OCR selection rule stays `_load_reocr`'s rule (score ≥ `REOCR_MIN_SCORE` 0.9, new ≠ old). Import it; do not duplicate it.
  - No match returns `InferenceResult(elr_no, (), "none")`.
- Pipeline use: `inference_loader=functools.partial(load_cached_inference, cache_dir)` (2-arg form).

- [ ] **Step 1: Write failing tests**
  - `test_cache_roundtrip`: write a 1-image cache with two det_rec boxes `LINE 1: ABC` / `LINE 2: XYZ` into `tmp_path`. `load_cached_inference` returns TOP lines 1–2 with `layout_source == "auto"`.
  - `test_cache_no_image_is_none`.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3: Move and add the code**
  - Move the code into `build_auto_inference` and make the snapshot branch call it.
  - Write `load_cached_inference` using the same functions.
- [ ] **Step 4: Prove the move changed nothing**
  - Run the full suite, then `python -m pytest tests/regression -q`, which needs MARK_R0_ROOT. Expected: all pass.
  - Run `python scripts/run_regression.py --out artifacts/regression-r1-refactor`. Its `parity_summary.json` must equal run 14's.
- [ ] **Step 5: Commit** `refactor(abs): shared auto-inference builder; inference cache adapter`, with HANDOFF and QA_LOG.

---

### Task 8: Brand page extraction from NAS ABS

**Files:**
- Create: `mark_engine/abs/brand_page.py`
- Create: `scripts/blind_extract_images.py`
- Test: `tests/unit/test_brand_page.py` (uses `tests/fixtures/make_pdfs.py`)

**Interfaces:**
- Produces:
  - `extract_brand_image(pdf: Path) -> tuple[bytes, str]`. It returns PNG bytes and the method, `"raster"` or `"render200"`. The rule is copied from the R0 `extract_marking_images.py` docstring: the Brand page is the last page whose text contains `Brand/Marking` (else the last page). The image is the largest embedded raster on that page with aspect ≤ 2.5, extracted losslessly. If there is none, the page is rendered at 200 dpi.
  - CLI: `python scripts/blind_extract_images.py --snapshot artifacts/blind-2026h2/oracle/elr_meta.json --nas-root "%NAS_ROOT%\ELR Online 2026" --months 7_JUL 8_AUG 9_SEP 10_OCT 11_NOV --out artifacts/blind-2026h2/cache`.
  - For each ELR, the CLI runs `resolve_documents(meta, nas_root, months, work_dir)` (the **same resolver** the runner uses) and extracts the chosen ABS only.
  - It writes `cache/images/<image>.png` (name `<ELR>__<abs_stem>`, md5 dedup: one image per unique ABS) and `cache/images_index.csv` (`elr,abs_file,image,method,md5`).
  - HOLD ELRs are skipped and listed in `cache/extract_skipped.csv`.
- Consumes: `load_env` (NAS path from `NAS_ROOT`), `load_elr_snapshot`, `resolve_documents`.

- [ ] **Step 1: Write failing tests**
  - `test_brand_page_prefers_brand_text`: a 3-page fixture PDF where page 2 has "Brand/Marking" and a raster, and the result comes from page 2.
  - `test_banner_raster_ignored`: a raster with aspect 4 is skipped, giving `render200`.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3: Implement** `extract_brand_image` and the CLI.
- [ ] **Step 4: Run on real data**
  - Run the tests. Expected: PASS.
  - Run the CLI once Task 6 has produced the snapshot and the NAS is mounted (`net use` per `infer/README.md`).
  - Expected: `images_index.csv` rows ≈ the number of non-HOLD ELRs. Note the counts in HANDOFF.
- [ ] **Step 5: Commit** `feat(abs): Brand page extraction; blind image extract CLI`, with HANDOFF and QA_LOG.

---

### Task 9: Batch inference on the AI server

**Files:**
- Create: `infer/det_rec_batch.py`
- Create: `infer/yolo_batch.py`
- Create: `infer/reocr_batch.py`
- Create: `infer/README.md`

**Interfaces:**
- Consumes: `cache/images/*.png` (Task 8).
- Produces: `cache/det_rec.json`, `cache/detections.json`, `cache/reocr.csv` in Task 7's formats, plus `cache/models.json`. The last file holds the model name, version and sha256 from `models/REGISTRY.json` and the det model name `PP-OCRv5_server_det`.
- Script behaviour, copied from R0 and run in a container or venv on 10.151.28.9:
  - `det_rec_batch.py SRC OUT` matches R0 `experiments/abs_vs_db/det_rec_server.py`: det `PP-OCRv5_server_det` on `device='cpu'` with `enable_mkldnn=False`; each box gets a 0.15×height pad and an axis-aligned crop, and is recognised by EXP09 (`models/ocr-rec-exp09/ep40`).
  - `yolo_batch.py WEIGHTS SRC OUT` matches R0 `symbol_det/predict_server.py`: `imgsz=1024`, `conf=0.25`, output `[cls, conf(3dp), x0,y0,x1,y1 (1dp)]`.
  - `reocr_batch.py` matches R0 `reocr.py`, both `legend_value` and `trim_logo`, against the EXP09 `/ocr` service (`http://10.151.28.9:8095`). It writes **every** candidate with its score; the GT-free selection happens in `_load_reocr`.

- [ ] **Step 1: Determinism check** (this is the test for this task)
  - Copy R0 `dataset/eval_h1/full_images/*.png` (read-only copy) to the server and run `det_rec_batch.py` and `yolo_batch.py` on it.
  - Compare against R0 `experiments/abs_vs_db/out/h1_det_rec.json` and `experiments/symbol_det/detections_h1.json` with a small diff script in `infer/README.md`.
  - Expected: identical texts, with box coordinates within 1 px. If they differ, stop. The blind run would not be "same models as R1".
- [ ] **Step 2 [USER/ops]: Run on the blind images**
  - Copy `artifacts/blind-2026h2/cache/images/` to the server, run the three scripts, and copy the outputs back into `artifacts/blind-2026h2/cache/`.
  - The user provides server access (SSH or shell on 10.151.28.9). Docker image `ic-marking-ocr:exp09` per the R0 `deploy/README.md`.
- [ ] **Step 3: Check the cache**
  - Run `python -c "from mark_engine.adapters.inference_cache import load_cached_inference as f; from pathlib import Path; import csv; c=Path('artifacts/blind-2026h2/cache'); r=list(csv.DictReader(open(c/'images_index.csv',encoding='utf-8'))); print(sum(1 for x in r if f(c,x['elr'],x['abs_file']).lines))"`.
  - Expected: close to `len(r)`.
- [ ] **Step 4: Commit** `feat(infer): AI-server batch scripts (det/rec, YOLO, re-OCR) + determinism check`, with HANDOFF (determinism result) and QA_LOG.

---

### Task 10: Blind runner

**Files:**
- Create: `mark_engine/regression/artifacts.py`. **Do this before Task 5**, together with Task 7, because it lives under `mark_engine/`.
- Modify: `scripts/run_regression.py` (use `artifacts.py` writers; output unchanged)
- Create: `scripts/run_blind.py`
- Test: `tests/unit/test_run_blind.py`

**Interfaces:**
- Consumes: `check_freeze` (Task 5), `load_elr_snapshot`, `load_cached_inference` (Task 7), the layouts JSON (Task 6) → `parse_template`, `process_elr(..., templates=...)`, `regression.metrics`.
- Produces:
  - `write_lines_csv(path, results: Sequence[JobResult], extra: Callable[[JobResult, LineComparison], dict] | None) -> int` and `write_jobs_csv(path, results) -> int`. The column sets are exactly the current `run_regression.py` `lines_fieldnames` and `jobs_fieldnames`.
  - CLI: `python scripts/run_blind.py --oracle artifacts/blind-2026h2/oracle --cache artifacts/blind-2026h2/cache --months 7_JUL 8_AUG 9_SEP 10_OCT 11_NOV --out artifacts/blind-2026h2/run [--allow-unfrozen] [--workers 8]`. It writes `jobs.csv`, `lines.csv` and `metrics.json`.
  - `metrics.json` carries the Coverage ELR, Coverage line, Hold Rate and Oracle agreement (auto / human split), plus `freeze_id`, `code_sha256` and the contents of `models.json`. When run with `--allow-unfrozen`, `freeze_id` = `"UNFROZEN"`.
  - No parity file, because there is no R0 for these months, and no review verdicts. `final_status` = system status.
  - The runner also runs the independence check, as in `tests/unit/test_generator_independence.py`: for every ELR, `generate_expected` with Oracle blanked equals the normal run. It writes `independence` (%) to `metrics.json`; the gate is 100%.

- [ ] **Step 1: Write failing tests**
  - `test_blind_refuses_missing_nas_month`: when `NAS_ROOT` points to a `tmp_path` without `9_SEP`, `main([...])` raises `SystemExit` with a message containing `9_SEP`.
  - `test_blind_scans_all_months`: a fixture ELR `ADI2607001` placed under `tmp/8_AUG/ADI2607001/` with ABS and SLR fixture PDFs is found (not `HOLD:NO_FOLDER`).
  - `test_blind_refuses_unfrozen`: if `check_freeze` raises, the runner exits non-zero unless `--allow-unfrozen` is given.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3: Implement**
  - Move the writers into `artifacts.py` and keep `run_regression.py` output byte-identical. Check this with run 14: `diff` the old and new `lines.csv`, which must be empty.
  - Then write `run_blind.py`. `main(argv)` is testable, and it calls `load_env()` first.
- [ ] **Step 4: Run the blind test**
  - Run the full suite. Expected: all pass.
  - Run the blind CLI. Expected: `metrics.json` exists, `independence == 100.0`, and `freeze_id == "FREEZE-R1"`.
- [ ] **Step 5: Commit** `feat(regression): blind runner Jul–Nov (frozen, independence-checked)`, with HANDOFF (headline metrics) and QA_LOG.

---

### Task 11: DB load, review page, team lists, blind report (A3 report, A5, A7)

**Files:**
- Create: `scripts/export_team_lists.py`
- Modify: `scripts/make_review_page.py` (`--in DIR --title TEXT`; defaults keep run-14 behaviour)
- Create: `docs/implementation/11-blind-test-2026h2.md`
- Modify: `docs/implementation/00-*.md` (doc index), `06` (metrics, blind section)
- Test: `tests/unit/test_export_team_lists.py`

**Interfaces:**
- Consumes: `artifacts/blind-2026h2/run/*`, `load_r1_to_pg.py` (Task 2), `reviews/r1_run14_review_export.csv`.
- Produces:
  - `marking_team_rows(lines: Iterable[dict]) -> list[dict]`. Rows are `final_status == "DB_WRONG"` or `review_detail` starting with `REVISION_MISMATCH` / `PRODUCT_NO_ABS_MISMATCH`. The columns are `elr_no, side, line_no, oracle_mark, expected_mark, issue, detail`.
  - `rule_approval_rows() -> list[dict]`. There is one row per decision D-22…D-29, taken from `docs/implementation/07-open-decisions.md`, with the columns `decision, title, rule_stage, example_elr, effect_lines_run14, approval (blank)`.
  - Outputs: `reviews/marking_team_2026-11.csv` and `reviews/mark_eng_rule_approval_2026-11.csv`, both utf-8-sig.

- [ ] **Step 1: Write failing tests**
  - `test_marking_rows_db_wrong_and_alerts`: of three input rows (DB_WRONG, REVISION_MISMATCH alert, plain MATCH), the first two are returned.
  - `test_rule_rows_cover_d22_d29`: the decisions are exactly `D-22`…`D-29`.
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3: Implement**
  - Implement and run it on run-14 `lines.csv` for the Marking list (G7–G8: expect about 17 DB_WRONG plus the config-alert lines), and on the blind run as a second file `marking_team_blind_2026h2.csv`.
- [ ] **Step 4: Load the blind run into the DB**
  - Run `python scripts/load_r1_to_pg.py artifacts/blind-2026h2/run --period "2026-07..2026-11 blind" --note "blind FREEZE-R1" --commit`. This needs Task 2 Step 5 to be done.
  - Expected: a new `run_id` (15 or later) is printed. Update memory `mark-web-db-r1-run4.md`: blind = run N.
- [ ] **Step 5: Build the review page and write the report**
  - Run `python scripts/make_review_page.py --in artifacts/blind-2026h2/run --title "Blind Jul–Nov 2026"` and write the local HTML only (customer images stay local).
  - Write doc 11 with the metrics table in the spec §18 format, the error/hold breakdown, the `LAYOUT_POSITION` count, and a comparison with run 14. It must say plainly that run 14 is not blind and the blind run is.
- [ ] **Step 6: Commit** `docs: blind test Jul–Nov report; Marking + rule approval lists`, with HANDOFF and QA_LOG. The freeze window ends here, and A6 debug may start (separate plan).

---

## Self-review notes

- **Spec coverage:** every Part A item has a task.

  | Spec item | Task |
  |---|---|
  | A1 | Task 5 |
  | A2 | Tasks 3–4 |
  | A3 | Tasks 6–10 + report in Task 11 |
  | A4 | Task 2 |
  | A5 | Task 11 (list) |
  | A7 | Task 11 |

  A6 and A8 are excluded on purpose; see the header. Credentials follow §9.3, and Task 1 handles them.
- **Freeze ordering** (spec §17: no edits during the blind run) forces every `mark_engine/` change before Task 5. The run order is stated in Task 5 and repeated in Task 10.
- **User-dependent steps** are marked `[USER]`:
  - Task 2 Step 5: DBA applies the migration.
  - Task 9 Step 2: AI-server access.
