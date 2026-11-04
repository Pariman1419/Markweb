# Phase 1 — `mark_engine` (offline) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python package `mark_engine` that, for one ELR, resolves the ABS/SLR documents, builds `expected_mark` without ever seeing Oracle TOP/BACK_MARK, compares it with `oracle_mark` in a separate engine, and a regression runner that produces baseline **R1** on Jan–Jun 2026 with a line-by-line parity report against **R0**.

**Architecture:** Pure core (`documents`, `slr`, `encode`, `abs`, `generate`, `compare`) working on frozen dataclasses; IO only in `adapters/` (snapshot files, a SELECT-only Oracle guard). Rules come from a checked-in rule-version file `RV-2026-11-04-R0` (same content as `migrations/0003_rule_governance.sql`). No live Oracle, NAS, A100 or PostgreSQL calls in Phase 1 — inputs are the R0 snapshot in `D:\CIM Project\mark` (tag `regression-r0-2026-11-04`).

**Tech Stack:** Python 3.12, pytest 8, hypothesis 6, pymupdf 1.24+, openpyxl 3.1. No ORM, no web framework.

**Spec:** `docs/superpowers/specs/2026-11-04-mark-automation-design.md` (Design Decisions v2) + `docs/implementation/00`–`07` (Phase 0 audit; decisions in `07-open-decisions.md`). Read `01` §4, `03` §3, `04` §2–§5 and `07` before starting.

## Global Constraints

- Repo: `D:\CIM Project\mark-web`, branch `phase1/mark-engine` cut from `phase0/readiness`. Package at `mark_engine/`, tests at `tests/`.
- `generate_expected()` must not take, import or read `OracleMark`, TOP_MARK*/BACK_MARK*, `MARK_ID_LAYOUT`, `MARK_ID_SYMBOL` (spec §1, D-10).
- Comparison never mutates `ExpectedMark` (all domain dataclasses `frozen=True`).
- MATCH_SHIFT and MATCH_LOT exist only in `mark_engine/compare/`.
- Rules with `provenance_class = ORACLE_DERIVED` are used for generate only if `rule_approval.decision` starts with `APPROVED`; `REJECTED` rules are never executed (D-06: R07-PIN-NOTE, R04-SLR-LITERAL, R03-ONE-ABS rejected).
- ADI1039 tokens apply to `DocType.ABS` and `DocType.SLR` only; `DocType.TRS` → `HOLD:TRS_OUT_OF_SCOPE` and ADI1039 code raises `ValueError` (D-05).
- Gates (spec v2 + D-19 call): no SLR → `HOLD:SLR_NOT_FOUND` **even when `CUST_REQ_NO` is empty**; `STATUS = 'C'`, `TOP_TYPE_CODE != 'E'` or `TOP_LAYOUT_CODE = 'ZY'` → `NOT_ELIGIBLE`; `Skip Mark` in MARK_REMARK → every line `NOT_MARKED` (regardless of Oracle).
- Generate priority (lower wins): SLR 10 > MARK_REMARK 20 > Symbol ADI 30 > ADI1039 40 > OCR fix 50.
- Never write to Oracle/NAS/PostgreSQL. The only Oracle code is the SELECT-only guard (D-11).
- No secret in the repo; customer data (PDFs, images, CSV outputs) only under git-ignored `artifacts/`.
- Do not modify anything in `D:\CIM Project\mark` (R0 root is read-only input).
- No word "PASS" in any status enum or output column (spec §6.1).

## Review Focus

1. ELR stored in a range folder (`3_MAR\ADI2603011-14`) or an annotated folder (`5_MAY\ADI2605073 Cancle`) → resolver finds it (Task 4 `test_range_folder_found`, `test_annotated_folder_flagged`).
2. SLR delivered only as `SLR*.zip` (354 zips in Jan–Jun) → extracted and used (Task 4 `test_slr_inside_zip`).
3. Oracle holds real lot digits that are **not** the SLR Scheduled Lot ID slice → `NEEDS_REVIEW`, never `MATCH_LOT` (Task 10 `test_lot_digits_not_in_slr_needs_review`).
4. SLR gives two different values for the same line → `SLR_AMBIGUOUS` → line `NEEDS_REVIEW` (Task 6 `test_conflicting_line_values_ambiguous`).
5. Oracle metadata with `None`/`'N/A'` (`CUST_BOM_NO='N/A'`, `CUST_REQ_NO=None`, `MARK_REMARK=None`) → deterministic HOLD/flag, no exception (Task 5 `test_bom_na_holds`, Task 7 `test_remark_none`).

---

## File Structure

```
pyproject.toml                         # package + pytest config, markers: regression
mark_engine/
  __init__.py  version.py              # ENGINE_VERSION = "0.1.0"
  domain/models.py                     # all dataclasses + enums (Task 1)
  rules/ruleset.py                     # RuleSet (Task 2)
  rules/data/RV-2026-11-04-R0.json     # rule version file (Task 2)
  adapters/oracle_guard.py             # SELECT-only guard (Task 3)
  adapters/snapshot.py                 # R0 snapshot readers (Task 3, 8)
  documents/locate.py fingerprint.py classify.py resolve.py   (Tasks 4–5)
  slr/parse.py                         # sections, line instructions, lots, coverage (Task 6)
  encode/ocr_fix.py symbol_adi.py adi1039.py remark.py        (Task 7)
  encode/data/adi1039_tokens.csv symbol_adi_r0.json           (Task 7)
  abs/layout.py symbols_to_lines.py    # (Task 8)
  generate/generator.py                # (Task 9)
  compare/engine.py lot.py shift.py    # (Task 10)
  pipeline.py                          # (Task 11)
scripts/build_rule_version.py          # (Task 2)
scripts/build_encoder_data.py          # (Task 7)
scripts/run_regression.py              # (Task 12)
mark_engine/regression/parity.py metrics.py                   (Task 12)
tests/unit/...  tests/regression/...   tests/fixtures/...
```

---

### Task 1: Project scaffold + domain model

**Files:**
- Create: `pyproject.toml`, `mark_engine/__init__.py`, `mark_engine/version.py`, `mark_engine/domain/models.py`
- Test: `tests/unit/test_models.py`

**Interfaces:**
- Produces (all `@dataclass(frozen=True, slots=True)`; tuples not lists):
  - enums (`StrEnum`): `Side{TOP,BOTTOM}`, `DocType{ABS,SLR,TRS,OTHER}`, `LineStatus{MATCH,MATCH_SLR,MATCH_SHIFT,MATCH_LOT,DIFF,NEEDS_REVIEW,DB_EMPTY,NOT_MARKED,NOT_COMPARABLE,NOT_MEASURABLE,NOT_ELIGIBLE}`, `ProcessingStatus{PENDING,RUNNING,DONE,FAILED,HOLD}`, `VerificationStatus{MATCH_ALL,HAS_DIFF,NEEDS_REVIEW,NOT_VERIFIABLE}`, `ApprovalStatus{NOT_REVIEWED,APPROVED,REJECTED,STALE}`, `Flag{ORACLE_DERIVED_UNAPPROVED,RULE_CONFLICT,SLR_AMBIGUOUS,SLR_UNRESOLVED,GRAPHIC_REMARK_CONFLICT,UNMAPPED_TOKEN,SLR_OVERRIDE}`
  - `ElrMeta(elr_no, import_date: str|None, status, current_step, cust_bom_no, cust_bom_revision, cust_req_no, cust_assy_lot, product_no, package_code, mark_remark, mark_require, top_type_code, top_layout_code)` — all `str|None` except `elr_no: str`
  - `OracleMark(elr_no: str, lines: tuple[tuple[Side,int,str],...])` with method `get(side, n) -> str` (`''` when absent)
  - `DocumentRef(path: str, sha256: str, doc_type: DocType, number: str|None, revision: str|None, revision_source: str|None)`
  - `DocumentResolution(elr_no, decision: Literal["RESOLVED","HOLD"], hold_reason: str|None, abs: DocumentRef|None, slr: tuple[DocumentRef,...], rejected: tuple[tuple[DocumentRef,str],...], steps: tuple[str,...])`
  - `LayoutLine(side: Side, line_no: int, text: str, graphics: str, score: float|None)` — `graphics` = left-to-right YOLO tokens using `@` pin dot, `%` partial logo, `{` full logo
  - `InferenceResult(elr_no, lines: tuple[LayoutLine,...], layout_source: Literal["auto","human_crop","none"])`
  - `SlrInstruction(side: Side, line_no: int, value: str|None, quote: str, alternatives: tuple[str,...])`
  - `SlrFacts(text: str, instructions: tuple[SlrInstruction,...], scheduled_lots: tuple[str,...], qual_lot: tuple[int,int]|None, unresolved: tuple[str,...])`
  - `ExpectedToken(text: str, rule_id: str, source: Literal["ABS","SLR","REMARK","ADI1039","SYMBOL_ADI","OCR_FIX","YOLO"], lot_slice: str|None = None)`
  - `ExpectedLine(side, line_no, text: str|None, tokens: tuple[ExpectedToken,...], flags: frozenset[Flag])`
  - `ExpectedMark(elr_no, lines: tuple[ExpectedLine,...], rule_version: str, engine_version: str)`; method `line(side,n) -> ExpectedLine|None`
  - `LineComparison(side, line_no, expected: str|None, oracle: str, status: LineStatus, compare_rules: tuple[str,...], detail: str)`
  - `JobResult(elr_no, processing_status, hold_reason: str|None, verification_status: VerificationStatus|None, approval_status: ApprovalStatus, resolution: DocumentResolution|None, expected: ExpectedMark|None, comparisons: tuple[LineComparison,...])`

- [ ] **Step 1: Create branch and write failing tests**

```bash
git -C "D:/CIM Project/mark-web" switch -c phase1/mark-engine phase0/readiness
```

```python
def test_expected_mark_is_frozen():
    em = ExpectedMark("ADI2601001", (), "RV-2026-11-04-R0", "0.1.0")
    with pytest.raises(dataclasses.FrozenInstanceError):
        em.elr_no = "x"

def test_oracle_mark_get_absent_is_empty():
    om = OracleMark("ADI2601001", ((Side.TOP, 1, "@%"),))
    assert om.get(Side.TOP, 1) == "@%" and om.get(Side.BOTTOM, 2) == ""

def test_no_pass_in_status_names():
    for e in (LineStatus, ProcessingStatus, VerificationStatus, ApprovalStatus):
        assert not any("PASS" in m.name for m in e)
```

- [ ] **Step 2: Run** `python -m pytest tests/unit/test_models.py -v` → FAIL (import error)
- [ ] **Step 3: Implement** `pyproject.toml` (deps above, `[tool.pytest.ini_options] markers = ["regression: needs MARK_R0_ROOT"]`), `version.py` (`ENGINE_VERSION = "0.1.0"`), `domain/models.py` per Interfaces. Add `artifacts/` already in `.gitignore`; add `.venv/`, `__pycache__/`.
- [ ] **Step 4: Run** `python -m pytest tests/unit/test_models.py -v` → 3 passed
- [ ] **Step 5: Commit** `feat(domain): frozen domain model for mark_engine`

---

### Task 2: Rule version file + `RuleSet`

**Files:**
- Create: `scripts/build_rule_version.py`, `mark_engine/rules/ruleset.py`, `mark_engine/rules/data/RV-2026-11-04-R0.json`
- Test: `tests/unit/test_ruleset.py`

**Interfaces:**
- Consumes: `artifacts/regression-r0/mark_logic/logic_rule.csv` (build time only)
- Produces:
  - `RuleSet.load(version: str = "RV-2026-11-04-R0") -> RuleSet`; `.version: str`; `.rule(rule_id) -> dict`
  - `RuleSet.usable(rule_id: str) -> tuple[bool, frozenset[Flag]]` — `(False, ∅)` if REJECTED or stage ≠ generate/compare/gate; `(True, {ORACLE_DERIVED_UNAPPROVED})` if ORACLE_DERIVED without an `APPROVED*` decision; else `(True, ∅)`
  - `RuleSet.condition(rule_id) -> str|None`
- JSON shape: `{"rule_version": "...", "rules": [{...all logic_rule columns..., "provenance_class": "...", "oracle_influence": "..."}], "approvals": [{"rule_id","decision","condition","approver"}]}` — provenance and approvals copied **verbatim** from the VALUES lists in `migrations/0003_rule_governance.sql`.

- [ ] **Step 1: Write failing tests**

```python
def test_r0_has_44_rules_and_4_classes():
    rs = RuleSet.load()
    assert len(rs.rules) == 44
    assert {r["provenance_class"] for r in rs.rules} == {"SPEC_DERIVED","ORACLE_DERIVED","EXPERIMENTAL","PENDING_VERIFICATION"}

@pytest.mark.parametrize("rid", ["R07-PIN-NOTE", "R04-SLR-LITERAL", "R03-ONE-ABS"])
def test_rejected_rules_not_usable(rid):
    assert RuleSet.load().usable(rid) == (False, frozenset())

def test_remark_caret_usable_with_condition():
    rs = RuleSet.load()
    assert rs.usable("R07-REMARK-CARET") == (True, frozenset())
    assert "NEEDS_REVIEW" in rs.condition("R07-REMARK-CARET")

def test_unapproved_oracle_derived_flags(tmp_path):
    rs = RuleSet.from_dict({"rule_version":"T","rules":[{"rule_id":"X","rule_stage":"generate","provenance_class":"ORACLE_DERIVED"}],"approvals":[]})
    assert rs.usable("X") == (True, frozenset({Flag.ORACLE_DERIVED_UNAPPROVED}))
```

- [ ] **Step 2: Run** `python -m pytest tests/unit/test_ruleset.py -v` → FAIL
- [ ] **Step 3: Implement** `scripts/build_rule_version.py` (reads the CSV, joins the two tables from migration 0003, writes JSON sorted by `rule_id`, `ensure_ascii=False`, indent 1) and run it; implement `RuleSet` (`load` reads JSON via `importlib.resources`; `from_dict` for tests).
- [ ] **Step 4: Run** tests → 6 passed
- [ ] **Step 5: Commit** `feat(rules): RV-2026-11-04-R0 rule version and RuleSet`

---

### Task 3: Adapters — Oracle SELECT-only guard + R0 snapshot metadata

**Files:**
- Create: `mark_engine/adapters/oracle_guard.py`, `mark_engine/adapters/snapshot.py`
- Test: `tests/unit/test_oracle_guard.py`, `tests/unit/test_snapshot_meta.py`, fixture `tests/fixtures/elr_meta_sample.json` (3 hand-written rows, fake ELR numbers `ADI2699001..003`)

**Interfaces:**
- Produces:
  - `assert_select_only(sql: str) -> None` — raises `PermissionError` unless, after stripping comments/whitespace, the text starts with `SELECT` or `WITH`, contains no `;` except one trailing, and contains none of `INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|GRANT|TRUNCATE|EXECUTE|CALL|BEGIN|DECLARE|LOCK|COMMIT` as whole words; `READ_ONLY_TXN = "SET TRANSACTION READ ONLY"` constant (the only non-SELECT statement allowed, checked by identity)
  - `load_elr_snapshot(path: Path) -> dict[str, tuple[ElrMeta, OracleMark]]` — reads `elr_meta_2026.json` rows; maps `TOP_TYPE_CODE`, `TOP_LAYOUT_CODE`, `CUST_REQ_NO`, etc.; strips strings; `''`→`None` for meta; Oracle lines from `TOP_MARK1..5`/`BACK_MARK1..5` (BACK → `Side.BOTTOM`), stripped
  - `r0_root() -> Path` — from env `MARK_R0_ROOT`; `verify_r0_root(root) -> None` runs `git -C root diff --quiet regression-r0-2026-11-04 -- experiments` and raises `RuntimeError` if it fails

- [ ] **Step 1: Write failing tests** — `test_guard_allows_select`, `test_guard_allows_with`, and parametrized `test_guard_blocks` over `["UPDATE actldba.elr SET x=1", "select 1; delete from t", "/*x*/ insert into t values(1)", "SELECT * FROM t FOR UPDATE", "begin null; end;"]` (`FOR UPDATE` → blocked: add `FOR\s+UPDATE` to the deny list); `test_snapshot_splits_meta_and_oracle` asserting `ElrMeta` has no attribute containing `mark1` and `OracleMark.get(Side.BOTTOM,1)` equals fixture `BACK_MARK1`.
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** both modules.
- [ ] **Step 4: Run** `python -m pytest tests/unit/test_oracle_guard.py tests/unit/test_snapshot_meta.py -v` → all pass
- [ ] **Step 5: Commit** `feat(adapters): SELECT-only Oracle guard and R0 ELR snapshot loader`

---

### Task 4: Documents — locate, fingerprint, classify

**Files:**
- Create: `mark_engine/documents/locate.py`, `fingerprint.py`, `classify.py`
- Test: `tests/unit/test_documents.py`; fixtures built in `tests/fixtures/make_pdfs.py` (pymupdf writes tiny PDFs with given text; `conftest.py` fixture `month_tree(tmp_path)`)

**Interfaces:**
- Produces:
  - `find_elr_folders(root: Path, elr_no: str, months: Iterable[str]) -> list[tuple[Path, str]]` — returns `(folder, kind)` where kind ∈ `"exact"|"range"|"annotated"`; range pattern `^ADI(\d{4})(\d{3})-(\d{1,3})$` (end number replaces the last *n* digits, as `build_compare.parse_job`); annotated = name starts with `elr_no` + whitespace
  - `fingerprint_folder(folder: Path, extract_dir: Path) -> list[tuple[Path, str]]` — `(file, sha256)` for every `*.pdf`; `*.zip` extracted into `extract_dir/<zip sha256>/` (reject members with absolute paths or `..`; max 50 members, 100 MB) and their PDFs included; duplicates by sha256 dropped
  - `classify(pdf: Path) -> tuple[DocType, str|None]` — text of pages 1–2 (pymupdf); `ABS` if `ABS\d{6}` and any page contains `Brand/Marking`; `SLR` if `SPECIAL INSTRUCTIONS` or `Scheduled Lot ID`; `TRS` if `Test Requirement` or `\bTRS\d+`; both ABS and SLR markers → `OTHER` with reason `"AMBIGUOUS"`; returns the document number (`ABS\d{6}` / `SLR\d{6}`) found first in text, else from file name

- [ ] **Step 1: Write failing tests** — `test_exact_folder_found`, `test_range_folder_found` (`ADI2603011-14` contains `ADI2603012`, not `ADI2603015`), `test_annotated_folder_flagged` (`ADI2605073 Cancle` → kind `annotated`), `test_slr_inside_zip`, `test_zip_slip_rejected`, `test_duplicate_sha_dropped`, `test_classify_abs_slr_trs`, `test_trs_named_abs_is_trs` (file `ABS999999.pdf` whose text says `Test Requirement Specification` → `DocType.TRS`).
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** the three modules.
- [ ] **Step 4: Run** `python -m pytest tests/unit/test_documents.py -v` → all pass
- [ ] **Step 5: Commit** `feat(documents): folder locator, zip-aware fingerprint, content classifier`

---

### Task 5: Document resolver

**Files:**
- Create: `mark_engine/documents/resolve.py`
- Test: `tests/unit/test_resolve.py`

**Interfaces:**
- Consumes: Task 4 functions, `ElrMeta`
- Produces: `resolve_documents(meta: ElrMeta, root: Path, months: Sequence[str], work_dir: Path) -> DocumentResolution`
- Hold reasons (exact strings): `NO_FOLDER`, `ARCHIVE_ERROR`, `DOC_TYPE_AMBIGUOUS`, `TRS_OUT_OF_SCOPE`, `BOM_MISSING_IN_ORACLE` (`cust_bom_no` None/`N/A`), `BOM_NOT_FOUND`, `SLR_NOT_FOUND`, `REVISION_UNREADABLE`, `SAME_REV_DIFFERENT_CONTENT`, `SLR_CONFLICT`
- Revision (D-08): file-name revision = suffix after the 6-digit ABS number (`A`, `E`, `-ENG-2` → `ENG-2`); pick the ABS whose revision equals `cust_bom_revision`; if none equals and exactly one ABS matches BOM → use it with step note `REVISION_NAME_MISMATCH` (pipeline turns this into flag `RULE_CONFLICT`); if none equals and >1 → `REVISION_UNREADABLE`
- SLR: if `cust_req_no` set → only SLRs whose number equals it; else all SLRs in the folder; >1 SLR with different `instructions` (Task 6 `parse_slr`) → `SLR_CONFLICT`; identical → keep all, step `MERGED_IDENTICAL`
- Never reads `OracleMark`; ordering/mtime independent

- [ ] **Step 1: Write failing tests** — `test_happy_path_resolved`, `test_bom_na_holds` (`cust_bom_no="N/A"` → `HOLD`, `BOM_MISSING_IN_ORACLE`), `test_missing_slr_holds_even_without_cust_req_no`, `test_trs_holds`, `test_picks_revision_matching_oracle` (`ABS066854A` vs `ABS066854B`, `cust_bom_revision="B"`), `test_two_abs_no_revision_match_holds`, `test_slr_conflict_holds`, `test_order_and_mtime_independent` (hypothesis: shuffle file creation order + random `os.utime` → identical `DocumentResolution`).
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** `resolve_documents` (Task 6's `parse_slr` is needed for conflict check — implement Task 6 first if executing out of order; the test for conflict can use two SLR fixtures with `Line 2: AAA` vs `Line 2: BBB`).
- [ ] **Step 4: Run** `python -m pytest tests/unit/test_resolve.py -v` → all pass
- [ ] **Step 5: Commit** `feat(documents): resolver with BOM/SLR matching, revision and conflict holds`

---

### Task 6: SLR parser (regex) with coverage

**Files:**
- Create: `mark_engine/slr/parse.py`
- Test: `tests/unit/test_slr_parse.py`

**Interfaces:**
- Produces: `parse_slr(text: str) -> SlrFacts`
- Rules:
  - section = `SPECIAL INSTRUCTIONS\n(.*?)(?:\nANALOG\nDEVICES|\nASSEMBLY LOT )` (R04-SLR-SECTION); normalise `‐`→`-`, whitespace→single space
  - scheduled lots: after `Scheduled Lot ID`, lines matching `^(\d{6,8})\.\d+$` → keep the part before the dot
  - line instructions: forms in `R04-SLR-LINE.pattern` (`TOP Line 1 Y Line 2 Q1`, `Line Mark 2 - Q1`, `Line 3 - ENGG`, `Line 3: QDOSVD`, `line 3 to ENGE`, `change line 2 to 8892W-U2C`, `brand line 1 as follows: Line 1 EB{1-DC}`, `BOTTOM Line 1 {Pb-Free}{DC-3}`); value ends at next `Line n`, a stop word (list `SLR_STOP` from legacy `mapping_gap_analysis.py:291-292`) or a lowercase word
  - **one value per (side,line)**: the value is the full token run up to the terminator (no 1–3 token candidates); same (side,line) given twice with different values → `value=None`, `alternatives=(v1, v2)`
  - qual lot: `Qual lot (\d+) of (\d+)` → `qual_lot` (consistency only, never an instruction)
  - coverage: split the section into sentences (`(?<=[.;])\s+`); a sentence is marking-related if it matches `\b(line|brand|mark|top|bottom|logo|lot|date code|symbol|laser|attachment)\b` (case-insensitive); marking-related sentences that produced no instruction and are not only a qual-lot sentence → `unresolved`

- [ ] **Step 1: Write failing tests** — one parametrized test per form above asserting `(side, line_no, value)` (e.g. `"Line Mark 2 - Q1"` → `(TOP, 2, "Q1")`, `"BOTTOM Line 1 {Pb-Free}{DC-3} Line 2 {Lot-4}"` → `(BOTTOM,1,"{Pb-Free}{DC-3}")`, `(BOTTOM,2,"{Lot-4}")`); `test_conflicting_line_values_ambiguous`; `test_scheduled_lots` (`"Scheduled Lot ID\n7346019.1\n7346020.2\n"` → `("7346019","7346020")`); `test_follow_attachment_unresolved` (`"Please brand per attachment."` → in `unresolved`); `test_unicode_hyphen` (`"Line 3 ‐ ENGG"` → `"ENGG"`); `test_qual_lot_is_not_instruction`.
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** `parse_slr`.
- [ ] **Step 4: Run** `python -m pytest tests/unit/test_slr_parse.py -v` → all pass
- [ ] **Step 5: Commit** `feat(slr): single-value regex parser with ambiguity and coverage`

---

### Task 7: Encoders — OCR fix, Symbol ADI, ADI1039, MARK_REMARK

**Files:**
- Create: `scripts/build_encoder_data.py`, `mark_engine/encode/data/adi1039_tokens.csv` (copy of R0 `experiments/abs_vs_db/adi1039_tokens.csv`, 42 rows), `mark_engine/encode/data/symbol_adi_r0.json`, `mark_engine/encode/ocr_fix.py`, `symbol_adi.py`, `adi1039.py`, `remark.py`
- Test: `tests/unit/test_encode.py`

**Interfaces:**
- Produces:
  - `ocr_fix(text: str) -> tuple[str, tuple[str,...]]` — applies R07-OCRFIX-1..8 patterns from the rule file in order, case-insensitive; returns applied rule_ids. OCRFIX-8 → `X*n` (D-09)
  - `encode_symbol_adi(text: str) -> tuple[str, tuple[str,...]]` — `{token}` → comp symbol via `symbol_adi_r0.json` (built from `Symbol ADI.xlsx` sheet `Summary`, rows where col B = `ADI`, key = normalised col D, value = col E minus ` (UTL)`; aliases from legacy `build_compare.py:26-31`); `{y+w+|x+}` kept upper-case; **`{CCCCC}` is not mapped** (legacy assumption dropped) → left as-is; any remaining `{...}` → reported in unmapped list. Returns `(text, unmapped_tokens)`
  - `apply_adi1039(text: str, doc_type: DocType) -> tuple[str, tuple[ExpectedToken,...]]` — raises `ValueError` for `DocType.TRS`/`OTHER`; replaces abbreviations from the CSV (`db_placeholder`, `lot_slice` copied onto the token), plus `ASSEMBLY LOT NUMBER`→`XXXXXXXXX` (R07-ADI1039-LOT), `COUNTRY OF ORIGIN`/`\bTHAI(L)?\b`→`THAILAND` (R07-ADI1039-COO), `_`/`␣`/`{SPACE}`→space (§5.1.6)
  - `remark_graphics(remark: str|None, require: str|None) -> dict[str, str]` — the mapping of YOLO token → DB code from legacy `remark_tokens()` (`mapping_gap_analysis.py:201-218`) incl. `caret_logo`; `None`/empty remark → `{'@':'@','%':'%','{':'{'}`
  - `is_skip_mark(remark, require) -> bool` — `skip\s*mark`, case-insensitive
- `build_encoder_data.py` asserts `sha256(Symbol ADI.xlsx) == 7858dc405a90b6600389accf32fa257ad23580cd532cda078da2f02cfe74ccb6` before reading.

- [ ] **Step 1: Write failing tests** — `test_ocrfix_examples` (`"{SPACEE}"`→`" "`, `"{YYWWE}"`→`"YYWW"`, `"5 DIGIT SERIAL NUMBER"`→`"XXXXX"`), `test_symbol_adi_logo` (`"{LOGO}"`→`"*"`), `test_unmapped_token_reported` (`"{CCCCC}"` in unmapped), `test_adi1039_lot_slice` (`"{Lot-5}"` → token text `"XXXXX"`, `lot_slice == "last-5"`), `test_adi1039_rejects_trs` (`pytest.raises(ValueError)`), `test_remark_caret` (`"^ = ADI logo"` → `{'@':'','%':'^','{':'^'}`), `test_remark_none` (`None` → default mapping), `test_skip_mark`.
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** script (run once, commit its outputs) and the four modules.
- [ ] **Step 4: Run** `python -m pytest tests/unit/test_encode.py -v` → all pass
- [ ] **Step 5: Commit** `feat(encode): OCR fix, Symbol ADI, ADI1039 (ABS/SLR only), remark graphics`

---

### Task 8: ABS layout + symbols to lines, and cached inference loader

**Files:**
- Create: `mark_engine/abs/layout.py`, `mark_engine/abs/symbols_to_lines.py`; Modify: `mark_engine/adapters/snapshot.py`
- Test: `tests/unit/test_layout.py`, `tests/regression/test_layout_parity.py`

**Interfaces:**
- Produces:
  - `layout_lines(items: Sequence[tuple[float,float,float,float,str,float]]) -> list[tuple[Side,int,str,float|None,tuple[float,float,float,float]|None]]` — port of legacy `build_h1.py` (`LABEL`, `HEAD`, `SKIP`, `LEGEND` regexes and thresholds `-0.6..+0.35` gap, chain `6*gap`, right-label mode, legend mode ≥2 rows) **without** the `REOCR`/`LEGACY` branches
  - `assign_graphics(lines, detections: Sequence[tuple[str,float,float,float,float,float]], conf_min: float = 0.5) -> dict[tuple[Side,int], str]` — port of `graphics_to_lines.py` non-LEGACY branch (line 0 = side-level, not returned)
  - `load_inference(root: Path, elr_no: str, abs_file_stem: str) -> InferenceResult`:
    - May–Jun: find image in `dataset/eval_h1/images_index.csv` by `(elr, abs_file)`; items from `experiments/abs_vs_db/out/h1_det_rec.json`; detections from `experiments/symbol_det/detections_h1.json`; run `layout_lines` + `assign_graphics`; `layout_source="auto"`
    - Jan–Apr: lines from `dataset/annotation.csv` + `dataset/eval_4_apr/annotation_v1.1.csv` (`image_id`, `side`, `line_index`) for the image mapped from the ABS file (`dataset/full_images/images_index.csv`, `dataset/eval_4_apr/images_index.csv`); text = `experiments/abs_vs_db/out/ocr_preds.csv` `ocr_text` by `sample_id` (**no `ocr_reocr.csv` overrides** — those were GT-gated); graphics from `experiments/symbol_det/graphics_by_line.csv`; `layout_source="human_crop"`
    - nothing found → `InferenceResult(elr_no, (), "none")`

- [ ] **Step 1: Write failing tests** — unit: `test_label_rows` (synthetic items `L1`,`L2` with text right of them → 2 TOP lines), `test_second_l1_is_bottom`, `test_legend_mode` (`"LINE 1: ABC"`, `"LINE 2: DEF"` → values `ABC`,`DEF`), `test_pin_dot_above_first_row_goes_to_line1`, `test_graphic_below_last_row_ignored`; regression (`@pytest.mark.regression`): `test_layout_matches_legacy_h1_lines` — for every image in `h1_det_rec.json`, `layout_lines` text equals `experiments/abs_vs_db/out/h1_lines.csv` `ocr_text` per `(image, side, line)` except rows whose key is in `ocr_reocr.csv` with `method == legend_value`.
- [ ] **Step 2: Run** `python -m pytest tests/unit/test_layout.py -v` → FAIL
- [ ] **Step 3: Implement** the ports and `load_inference`.
- [ ] **Step 4: Run** unit tests → pass; `MARK_R0_ROOT="D:/CIM Project/mark" python -m pytest -m regression tests/regression/test_layout_parity.py -v` → pass
- [ ] **Step 5: Commit** `feat(abs): auto layout and graphics-to-lines ported from R0; cached inference loader`

---

### Task 9: Expected-mark generator

**Files:**
- Create: `mark_engine/generate/generator.py`
- Test: `tests/unit/test_generator.py`, `tests/unit/test_generator_independence.py`

**Interfaces:**
- Consumes: Tasks 2, 6, 7, 8
- Produces: `generate_expected(meta: ElrMeta, docs: DocumentResolution, slr: SlrFacts, inference: InferenceResult, rules: RuleSet) -> ExpectedMark`
- Per line, in this order (each step records `ExpectedToken`s with its rule_id):
  1. ABS text from `inference` → `ocr_fix` (P50) → `encode_symbol_adi` (P30) → `apply_adi1039(…, DocType.ABS)` (P40)
  2. graphics: `inference` line graphics mapped with `remark_graphics` (P20, R07-REMARK-*), prefixed left of the text (`"@% TEXT"` → stored as `"@%"` + `" "` + text, spaces are insignificant downstream)
  3. SLR (P10): instruction for this (side,line) → value through `apply_adi1039(…, DocType.SLR)` replaces the text part (graphics kept), add `Flag.SLR_OVERRIDE`; `value is None` → `Flag.SLR_AMBIGUOUS`; SLR lines with no ABS line create a new `ExpectedLine`
  4. flags: any `slr.unresolved` → every line gets `SLR_UNRESOLVED`; unmapped tokens → `UNMAPPED_TOKEN`; REMARK-CARET/LOGO/PIN conditions (D-06): YOLO saw a pin dot but mapping drops `@`, or remark declares a logo YOLO did not see on that side → `GRAPHIC_REMARK_CONFLICT`; `rules.usable()` flags merged
- Signature contains no `OracleMark`; module must not import `adapters.snapshot`.

- [ ] **Step 1: Write failing tests** — `test_abs_only_line` (inference `L1 "{LOGO} ADW"` graphics `""` → text `"* ADW"`), `test_graphics_prefixed` (graphics `"@%"`, default remark → `"@%"` prefix), `test_caret_remark_no_pin` (`"^ = ADI logo"`, graphics `"@%"` → prefix `"^"`, flag `GRAPHIC_REMARK_CONFLICT` because pin dot seen but dropped), `test_slr_overrides_text` (SLR `Line 2: Q1` → line 2 text `Q1`, `SLR_OVERRIDE`), `test_slr_tokens_render_placeholders` (`{Lot-4}` → `XXXX` with `lot_slice="last-4"`), `test_unresolved_sentence_flags_all_lines`, `test_signature_has_no_oracle` (`inspect.signature(generate_expected)` has no parameter annotated `OracleMark`; `ast` scan of `generator.py` finds no `TOP_MARK`/`BACK_MARK`/`OracleMark`).
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** `generate_expected`.
- [ ] **Step 4: Run** `python -m pytest tests/unit/test_generator*.py -v` → all pass
- [ ] **Step 5: Commit** `feat(generate): expected_mark generator with priority and review flags`

---

### Task 10: Comparison engine

**Files:**
- Create: `mark_engine/compare/engine.py`, `lot.py`, `shift.py`
- Test: `tests/unit/test_compare.py`

**Interfaces:**
- Consumes: `ExpectedMark`, `OracleMark`, `SlrFacts`, `RuleSet`, `ElrMeta.import_date`
- Produces: `compare(expected: ExpectedMark, oracle: OracleMark, slr: SlrFacts, meta: ElrMeta, rules: RuleSet) -> tuple[LineComparison,...]`
- Decision order per (side,line) over the union of expected and oracle lines 1–5 (skip when both empty):
  1. expected line has any flag other than `SLR_OVERRIDE` → `NEEDS_REVIEW` (detail = flags)
  2. oracle empty → `DB_EMPTY`
  3. `nospace(expected) == nospace(oracle)` (graphics **included**) → `MATCH_SLR` if line has `SLR_OVERRIDE` else `MATCH`
  4. `lot.match_lot(expected_line, oracle_text, slr.scheduled_lots, meta.import_date)` → `MATCH_LOT` (R07-PLACEHOLDER + R04-SLR-LOT condition): every X-run digit group must equal the `lot_slice` of at least one scheduled lot (`1-9` full 9 chars with the dot removed, `last-n`, `3-7`, `first-half` = first 4, `last-half` = last 5); every `YYWW` digit group must have WW in 01–53 and YY within ±1 of the import year; any group failing → not MATCH_LOT
  5. side-level `shift.match_shift(...)` (R06-SHIFT): oracle line 1 of the side is graphics-only, every expected text line n equals oracle text line n+1, side graphic multisets equal → all lines of the side `MATCH_SHIFT`
  6. oracle text (no spaces, ≥6 chars, has a letter and a digit) occurs as a word in `slr.text` → `NEEDS_REVIEW`, detail `ORACLE_VALUE_IN_SLR` (replaces rejected R04-SLR-LITERAL)
  7. oracle has digits where expected has `X×n` from OCRFIX-8 → `NEEDS_REVIEW`, detail `SERIAL_NOT_VERIFIABLE`
  8. else `DIFF`
- `R07-DB-PACKAGE`: if `DIFF` and expected has an X-run and oracle matches `T?SSOP` → detail `DB_LOT_IS_PACKAGE` (status stays `DIFF`)

- [ ] **Step 1: Write failing tests** — `test_exact_match`, `test_graphics_count` (expected `"@% ADW"`, oracle `"% ADW"` → `DIFF`), `test_match_slr`, `test_lot_digits_in_slr_match_lot` (expected `"BXXXXX"`, oracle `"B28558"`, lots `("7228558",)`, slice `last-5` → `MATCH_LOT`), `test_lot_digits_not_in_slr_needs_review` → expected status **not** `MATCH_LOT` (it is `DIFF`), `test_bad_week_not_match_lot` (`YYWW` vs `2660`), `test_shift_side`, `test_oracle_value_in_slr_needs_review`, `test_flagged_line_needs_review_even_if_equal`, `test_compare_does_not_mutate_expected` (hash of `expected` before == after).
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** the three modules.
- [ ] **Step 4: Run** `python -m pytest tests/unit/test_compare.py -v` → all pass
- [ ] **Step 5: Commit** `feat(compare): comparison engine with verified MATCH_LOT and MATCH_SHIFT`

---

### Task 11: Pipeline `process_elr` + three status axes

**Files:**
- Create: `mark_engine/pipeline.py`
- Test: `tests/unit/test_pipeline.py`

**Interfaces:**
- Produces: `process_elr(meta: ElrMeta, oracle: OracleMark, root: Path, months: Sequence[str], work_dir: Path, rules: RuleSet, inference_loader: Callable[[str, str], InferenceResult]) -> JobResult`
- Flow: eligibility gate (`status == 'C'` or `top_type_code != 'E'` or `top_layout_code == 'ZY'` → DONE, all oracle lines `NOT_ELIGIBLE`, verification `NOT_VERIFIABLE`) → `resolve_documents` (HOLD → `ProcessingStatus.HOLD`, `hold_reason`, lines `NOT_MEASURABLE`, verification `None`) → skip mark (`is_skip_mark` → lines `NOT_MARKED`, `NOT_VERIFIABLE`) → `parse_slr` of resolved SLRs (joined text) → `inference_loader(elr_no, abs stem)`; `layout_source == "none"` → lines `NOT_COMPARABLE` → `generate_expected` → `compare`
- verification: any `NEEDS_REVIEW` → `NEEDS_REVIEW`; else any `DIFF` → `HAS_DIFF`; else all compared lines `MATCH*` → `MATCH_ALL`; nothing compared → `NOT_VERIFIABLE`. `approval_status` always `NOT_REVIEWED`.
- `generate_expected` is called **before** `oracle` is touched (assert by passing a sentinel object whose attribute access raises until `compare` — see test).

- [ ] **Step 1: Write failing tests** — `test_cancelled_not_eligible`, `test_type_code_p_not_eligible`, `test_missing_slr_hold`, `test_skip_mark_not_marked`, `test_match_all_still_not_reviewed`, `test_oracle_untouched_before_compare` (wrap `OracleMark` in a proxy that records first access; assert generate finished first via call-order list).
- [ ] **Step 2: Run** → FAIL
- [ ] **Step 3: Implement** `process_elr`.
- [ ] **Step 4: Run** `python -m pytest tests/unit/test_pipeline.py -v` → all pass
- [ ] **Step 5: Commit** `feat(pipeline): process_elr with eligibility, hold, and three status axes`

---

### Task 12: Regression runner R1, independence check, parity vs R0

**Files:**
- Create: `scripts/run_regression.py`, `mark_engine/regression/metrics.py`, `mark_engine/regression/parity.py`
- Test: `tests/unit/test_metrics.py`, `tests/unit/test_parity.py`, `tests/regression/test_r1.py`

**Interfaces:**
- Produces:
  - CLI: `python scripts/run_regression.py --r0-root "D:/CIM Project/mark" --months 1_JAN 2_FEB 3_MAR 4_APR 5_MAY 6_JUN --elr-prefix ADI2601 ADI2602 ADI2603 ADI2604 ADI2605 ADI2606 --out artifacts/regression-r1` → writes `lines.csv` (elr_no, side, line_no, layout_source, expected_mark, oracle_mark, status, flags, compare_rules, detail, processing_status, hold_reason), `jobs.csv`, `metrics.json`, `parity.csv`, `parity_summary.json`
  - `metrics.compute(jobs: Sequence[JobResult]) -> dict` — keys: `coverage_elr`, `coverage_line`, `hold_rate`, `oracle_agreement` (+ per-status counts `MATCH`, `MATCH_SLR`, `MATCH_SHIFT`, `MATCH_LOT`), `needs_review_lines`, `independence` (fraction of jobs whose `ExpectedMark` is byte-identical when re-generated with a blank `OracleMark`), each also split by `layout_source`; denominator for coverage_elr = ELRs in `elr_meta_2026.json` with the given prefixes (Oracle, not NAS — `06` §5)
  - `parity.classify(r1_row: dict, r0_row: dict|None, r0legacy_row: dict|None) -> str` — reason codes: `SAME`, `ORACLE_INFLUENCE_REMOVED` (R0 cause `SLR_OVERRIDE`/`GRAPHIC_ONLY_LINE`/`NO_BRAND_LINE`/`LINE_SHIFT` text match, or R0 `MATCH_SLR`), `GRAPHIC_NOW_COUNTED` (R0 cause `GRAPHIC_SYMBOL`), `LOT_NOW_VERIFIED` (R0 `MATCH_LOT`), `RESOLVER_CHANGED` (ELR measurable status differs or different ABS), `GATE_SPEC_V2` (R0 measurable via `CUST_REQ_NO` relaxation, R1 `SLR_NOT_FOUND`), `REVIEW_FLAG` (R1 `NEEDS_REVIEW`), `OCR_SOURCE_CHANGED` (Jan–Apr row whose R0 OCR came from `ocr_reocr.csv`), `BUG` (anything else)
  - R0 inputs: `artifacts/regression-r0/mark_logic/line_result.csv` (run 3) and `artifacts/regression-r0/line_result_run2_529elr.csv`
- Phase 1 acceptance (D-03): `metrics.independence == 1.0`; `parity_summary["BUG"] == 0` after triage (each BUG either fixed in the owning task or given a new reason code added to `parity.py` with a one-line justification in the commit message); `metrics.json` committed as R1 is **not** done — R1 outputs stay in `artifacts/`; a summary table is added to `docs/implementation/06-regression-and-blind-test-plan.md` §5 column "R1 Jan–Jun".

- [ ] **Step 1: Write failing tests** — unit: `test_metrics_counts` (3 hand-made `JobResult`s), `test_independence_detects_leak` (a fake generator that reads a global oracle → `independence < 1`), parametrized `test_parity_codes` (one row per reason code); regression: `test_r1_independence_is_one`, `test_r1_no_bug_parity` (reads `parity_summary.json`).
- [ ] **Step 2: Run** unit tests → FAIL
- [ ] **Step 3: Implement** `metrics.py`, `parity.py`, `run_regression.py` (calls `verify_r0_root` first; work dir `artifacts/regression-r1/work`).
- [ ] **Step 4: Run** `python -m pytest tests/unit -v` → all pass; then `python scripts/run_regression.py …` (command above) → prints metrics; then `MARK_R0_ROOT="D:/CIM Project/mark" python -m pytest -m regression -v` → `test_r1_independence_is_one` passes; triage `BUG` rows until `test_r1_no_bug_parity` passes
- [ ] **Step 5: Update** `docs/implementation/06-regression-and-blind-test-plan.md` §5 with R1 numbers (coverage, hold rate, oracle agreement split by status and by layout_source, independence, BUG = 0) and commit `feat(regression): R1 runner, independence metric and parity vs R0`

---

## Out of scope (later phases)

LLM SLR parsing and LLM encoder assist, FastAPI, Dramatiq, React, Airflow DAGs, PostgreSQL `mark_app` writes (migrations 0004+), A100 calls and deployment, live Oracle/NAS access, the Jul–Nov blind test (needs a copy of the NAS folders and OCR/YOLO inference for them — plan it after R1 is accepted).
