# 04 — `mark_engine` Architecture, API Contracts, Test Strategy

วันที่: 2026-11-04 · อิงสถาปัตยกรรมใน `docs/superpowers/specs/2026-11-04-mark-automation-design.md` §5–§11 ·
ป้าย **[ยืนยัน]** = audit โค้ดปัจจุบัน · **[เสนอ]** = การออกแบบของผู้ตรวจ รอรีวิว

---

## 1. Audit โค้ดที่จะย้าย (สรุป)

| ส่วน | ไฟล์ (repo `mark`) | สภาพ | ย้ายอย่างไร |
|---|---|---|---|
| ดึงหน้า Brand | `experiments/abs_vs_db/extract_marking_images.py` | batch ตามเดือน, md5 dedupe | ย้ายเป็นฟังก์ชันต่อ 1 PDF |
| OCR det+rec | `det_rec_server.py`, `deploy/app.py`, `deploy/infer/ocr_app.py` (ร่าง) | `/ocr` อยู่บน A100 port 8095; `/v1/page`, `/v1/rec` ยังไม่ deploy | Phase 1 ใช้ผล OCR ที่ cache แล้ว (`out/h1_det_rec.json`, `ocr_preds.csv`) ไม่เรียก A100 |
| YOLO | `experiments/symbol_det/predict_server.py`, `deploy/infer/symbols_app.py` (ร่าง) | conf ≥ 0.5 ที่กฎ | เช่นเดียวกัน ใช้ `detections*.json` |
| จัดบรรทัด | `build_h1.py` (พ.ค.–มิ.ย. auto), Jan–Apr ใช้ **ครอปของคน** (`dataset/annotation.csv`) | **[ยืนยัน]** ม.ค.–เม.ย. ไม่ได้ผ่าน layout อัตโนมัติ | ย้ายเฉพาะ auto layout; รัน auto layout กับ ม.ค.–เม.ย. ใหม่เพื่อวัดจริง |
| วาง symbol | `graphics_to_lines.py` | ใช้ได้ | ย้าย |
| Encoder | `build_compare.py:17-65` (`SYM`, `ALIAS`, `DESC`, `encode`) | อ่าน `Symbol ADI.xlsx` ตรง; `{CCCCC}` → `THAILAND[:n]` เป็น assumption | ย้าย + อ่านจาก `mark_logic.symbol_profile` |
| กฎ + เทียบ | `mapping_gap_analysis.py` | **[ยืนยัน]** generate/compare ผสมกัน, ใช้ Oracle ตัดสินลำดับขั้น (01 §4); ใช้ `exec()` ดึงโค้ดข้ามไฟล์ (`build_h1.py:19`) | **ไม่ย้ายตรง — เขียนใหม่**แยก generate/compare; ใช้ไฟล์เดิมเป็น oracle สำหรับ legacy-parity test |
| SLR parser | `mapping_gap_analysis.py:51-63, 295-335` | parser ให้ candidate หลายค่า แล้วให้ Oracle เลือก | เขียนใหม่ให้ได้ค่าเดียวต่อบรรทัด หรือ NEEDS_REVIEW |
| Export | `export_logic_pg.py`, `rule_scope_pg.py`, `export_adi1039_pg.py` | **เขียนทับ `logic_rule` ทุกครั้งที่รัน** (n_tup_ins 88 = 2 รอบ) | หยุดใช้กับ production rules หลัง freeze (05) |

**[ยืนยัน] ไฟล์ทั้งหมดในตารางนี้ยังไม่ได้ commit** — `git status` ของ repo `mark`: `?? experiments/abs_vs_db/`,
`?? experiments/symbol_det/`, `?? deploy/` ขณะที่ `mark_logic.run.git_commit = d425dc8` → commit ที่อ้างไม่มีโค้ดที่สร้างผล

## 2. หลักการออกแบบ [เสนอ]

1. **Generate ไม่เห็น Oracle mark ตั้งแต่ระดับ type** — `ExpectedMarkGenerator.generate()` ไม่มีพารามิเตอร์ที่เป็น `OracleMark`
2. **Compare ไม่แก้ expected** — `ComparisonEngine` รับ `ExpectedMark` แบบ immutable (`frozen=True`) คืน `LineComparison`
3. **กฎเป็นข้อมูล** — โหลดจาก `mark_logic` ตาม `rule_version` ที่ freeze แล้ว; กฎ `provenance_class = ORACLE_DERIVED` ที่ยังไม่อนุมัติ → ทำงานได้แต่บังคับ `NEEDS_REVIEW`
4. **Pure core / IO shell** — แกนกลาง (resolve, layout, encode, generate, compare) เป็นฟังก์ชันบริสุทธิ์รับ dataclass; IO (Oracle, NAS, A100, PostgreSQL, MinIO) อยู่ใน `adapters/`
5. **ทุกค่ามีหลักฐาน** — ทุก token ใน expected_mark อ้าง `rule_id` + `source` (ABS bbox / SLR quote / remark)

## 3. โครงสร้างแพ็กเกจ [เสนอ]

```
mark_engine/
  __init__.py
  version.py                 # ENGINE_VERSION, ใส่ใน job_revision
  domain/
    models.py                # ElrMeta, OracleMark, DocumentRef, BrandPage, OcrItem, SymbolBox,
                             # LayoutLine, SlrInstruction, ExpectedLine, ExpectedMark, LineComparison,
                             # MarkValues (4 ค่า), enums: Side, ProcessingStatus, VerificationStatus,
                             # ApprovalStatus, LineStatus, ProvenanceClass, RuleStage
    errors.py                # HoldError(reason_code), RetryableError
  rules/
    repository.py            # RuleSet.load(rule_version) จาก mark_logic (read-only), RuleSet.from_json() สำหรับ test
    registry.py              # rule_id -> implementation; ตรวจว่าทุกกฎ approved/generate มี implementation
  documents/
    locator.py               # หาโฟลเดอร์ (range folder, annotated folder)
    fingerprint.py           # sha256, zip extract
    classifier.py            # ABS / SLR / TRS / OTHER จากเนื้อหา
    resolver.py              # 03-document-resolver-design.md
  abs/
    brand_page.py            # จาก extract_marking_images.py
    layout.py                # จาก build_h1.py (label, legend, right-label)
    symbols_to_lines.py      # จาก graphics_to_lines.py
  slr/
    sections.py              # SPECIAL INSTRUCTIONS, Scheduled Lot ID
    regex_parser.py          # คำสั่งบรรทัด -> SlrInstruction (ค่าเดียว หรือ ambiguous)
    coverage.py              # ประโยค -> instruction / unresolved / not_marking
    llm_parser.py            # Phase 3 (stub ใน Phase 1)
  encode/
    ocr_fix.py               # R07-OCRFIX-*
    symbol_adi.py            # R07-SYMBOL-ADI
    adi1039.py               # adi1039_token; รับเฉพาะ DocumentRef.doc_type == ABS (หรือ SLR ตาม D-05) — TRS -> ValueError
    remark.py                # R07-REMARK-* (ORACLE_DERIVED -> flag needs_review)
  generate/
    generator.py             # ExpectedMarkGenerator: SLR 10 > REMARK 20 > Symbol ADI 30 > ADI1039 40 > OCR fix 50
    conflicts.py             # กฎต่าง priority ให้ค่าต่างกัน -> NEEDS_REVIEW (ไม่ทับเงียบ)
  compare/
    engine.py                # ComparisonEngine: MATCH / MATCH_SLR / MATCH_SHIFT / MATCH_LOT / DIFF / ...
    lot.py                   # R07-PLACEHOLDER + R04-SLR-LOT (ADI1039 Table 2 lot_slice) — ต้องตรง SLR lot จึง MATCH_LOT
    shift.py                 # R06-SHIFT
    normalize.py             # whitespace/graphic normalisation สำหรับเทียบเท่านั้น
  pipeline.py                # process_elr(meta, oracle_mark, docs, inference) -> JobResult
  adapters/
    oracle_ro.py             # SELECT-only, SET TRANSACTION READ ONLY, คืน (ElrMeta, OracleMark)
    nas.py                   # list/read เท่านั้น
    inference_client.py      # A100 /v1/page /v1/rec /v1/symbols + cache key (sha256 ภาพ, model version)
    pg_repository.py         # เขียน mark_app.* เท่านั้น
    snapshot_source.py       # อ่าน JSON/CSV เก่า (elr_db_2026_h1.json, h1_det_rec.json ...) สำหรับ regression
  legacy/
    parity.py                # รัน mapping_gap_analysis เดิมแบบ subprocess บนสำเนา เพื่อเทียบ (ไม่ import)
tests/
  unit/ … property/ … regression/ … contract/
```

## 4. แยก 4 ค่า (คำถามข้อ 5) [เสนอ]

| ค่า | ใครตั้ง | อินพุตที่อนุญาต | ห้าม | เก็บที่ | เปลี่ยนได้เมื่อ |
|---|---|---|---|---|---|
| `expected_mark` | `ExpectedMarkGenerator` (Worker) | ABS (OCR/YOLO/layout), SLR, ADI1039, Symbol ADI, `MARK_REMARK`/`MARK_REQUIRE`, Scheduled Lot ID | TOP/BACK_MARK, `MARK_ID_LAYOUT`, `MARK_ID_SYMBOL`, ค่าของคน | `mark_app.draft_line.expected_mark` (+ `expected_tokens` JSON พร้อม rule_id/source) | ทุก `job_revision` ใหม่เท่านั้น (immutable ต่อ revision) |
| `oracle_mark` | Oracle adapter | `TOP_MARK1..5`, `BACK_MARK1..5` ณ เวลา snapshot | ห้ามป้อนให้ generator / LLM | `mark_app.elr_snapshot` + `draft_line.oracle_mark` | snapshot ใหม่ (ELR เปลี่ยน) |
| `engineer_corrected_mark` | Engineer ในหน้า Review | ข้อความที่ Engineer พิมพ์ เมื่อบรรทัด HAS_DIFF / NEEDS_REVIEW / ไม่เห็นด้วย | ระบบห้ามเติมเอง | `mark_app.line_review.engineer_corrected_mark` (append-only, มีผู้รีวิว/เวลา) | ทุกครั้งที่ Engineer แก้ (เก็บประวัติ) |
| `engineer_verified_mark` | ระบบคำนวณ ณ ตอน Engineer กด Approve | = `engineer_corrected_mark` ถ้ามี ไม่งั้น = `expected_mark` ที่ Engineer ยืนยันว่าถูก | ห้ามตั้งจาก `oracle_mark` แม้ตรงกัน; ห้ามมีค่าก่อน Approve | `mark_app.line_verification` (1 แถว/บรรทัด/approval) | Approve ใหม่เท่านั้น; STALE ทำให้ไม่ใช้เป็น ground truth |

**[การตัดสินใจของผู้ตรวจ — D-02]** `engineer_verified_mark` คือ "ค่าที่ถูกต้องที่ Engineer รับรองแล้ว" ของทุกบรรทัด
(รวมบรรทัดที่ไม่ได้แก้) และเป็น ground truth เพียงค่าเดียวที่ใช้วัด Correctness / False PASS:

- Correctness = `expected_mark == engineer_verified_mark` / บรรทัดที่มี verified
- False PASS = บรรทัดที่ `line_status ∈ MATCH*` **และ** `engineer_verified_mark ≠ expected_mark`
- ตัวชี้วัด Oracle agreement ใช้ `expected_mark` vs `oracle_mark` เท่านั้น — ห้ามใช้ `oracle_mark` เป็น ground truth

Invariant ที่ต้องมี test:
1. `generate(meta, docs, rules)` ไม่ขึ้นกับ `oracle_mark` (ลบ/สุ่ม oracle_mark → expected เท่าเดิมทุกไบต์)
2. `compare()` ไม่เปลี่ยน `expected_mark` (frozen dataclass + hash ก่อน/หลัง)
3. `engineer_verified_mark` มีค่าได้เฉพาะเมื่อ `approval_status = APPROVED`
4. `engineer_corrected_mark` บังคับเมื่อ line_status ∈ {DIFF, NEEDS_REVIEW, LLM_PROPOSED} ก่อน Approve

## 5. Comparison Engine — สถานะที่อนุญาต [เสนอ]

| สถานะ | เงื่อนไข (ต้องผ่านทั้งหมด) | ต่างจากโค้ดเดิม |
|---|---|---|
| MATCH | `norm(expected) == norm(oracle)` โดย **ไม่ลบกราฟิก** | เดิม GRAPHIC_SYMBOL ลบกราฟิกแล้ว MATCH (143 บรรทัด/run) |
| MATCH_SLR | expected บรรทัดนั้นมาจาก SLR instruction (source=SLR) และเท่ากับ oracle | เดิมเลือก candidate ตาม oracle |
| MATCH_SHIFT | R06-SHIFT (compare-only, ORACLE_DERIVED → แสดงป้าย "รออนุมัติ") | เหมือนเดิม |
| MATCH_LOT | ตัวเลขใน oracle อยู่ตำแหน่ง X/YYWW **และ** lot ตรง `lot_slice` ของ Scheduled Lot ID (ADI1039 Table 2); date code ต้องเป็น YYWW ที่ถูกต้องตามรูปแบบ | เดิมยอมรับตัวเลขใดก็ได้ |
| DIFF / NEEDS_REVIEW / NOT_COMPARABLE / NOT_MARKED / DB_EMPTY | ตาม spec §10 | Skip Mark ไม่ขึ้นกับ oracle ว่าง |

### 5.1 ชั้นรีวิวและการแสดงผล (R1, 2026-11-04) **[ยืนยัน]**

- `LineComparison.warning` — MATCH ที่ต้องให้ผู้ใช้เห็นความต่าง (`COO_ABBREVIATED`, D-22)
- `DocumentResolution.review_detail` → แจ้งเตือนพร้อมสาเหตุ (D-25/D-28); บรรทัดเป็น NEEDS_REVIEW (`RULE_CONFLICT`)
- `final_status` (D-26) — คำตัดสินของคนทับบน `status`: `DB_WRONG` (ระบบถูก Oracle ผิด), `HUMAN_FIXED` (ระบบผิด คนให้ค่า), `MATCH`; `status` ยังเป็นผลของระบบล้วน (ใช้วัด agreement/independence/parity)
- หน้ารีวิว: True (= Oracle) / Warning (ใกล้เคียง: COO ย่อ) / Error (ไม่ตรง + cause) — `scripts/make_review_page.py` `classify`, รายละเอียด `10` §3

## 6. API Contracts [เสนอ]

### 6.1 Library API (Phase 1 — ใช้ใน worker และ regression)

```python
def resolve_documents(meta: ElrMeta, listing: NasListing) -> DocumentResolution: ...
def generate_expected(meta: ElrMeta, docs: ResolvedDocuments, inference: InferenceResult,
                      rules: RuleSet) -> ExpectedMark: ...          # ไม่มี OracleMark
def compare(expected: ExpectedMark, oracle: OracleMark, slr: SlrFacts, rules: RuleSet) -> list[LineComparison]: ...
def process_elr(...) -> JobResult                                   # รวม 3 ขั้น + status 3 แกน
```

### 6.2 Internal REST (FastAPI, Phase 4) — schema v1

| Method | Path | ผู้เรียก | หมายเหตุ |
|---|---|---|---|
| POST | `/internal/v1/jobs` | Airflow | `{elr_no, trigger: poll|nas|manual, snapshot_hash}` → idempotent ตาม key spec §15 |
| GET | `/api/v1/jobs?processing_status=&verification_status=&approval_status=` | Web | ไม่มีคำว่า PASS |
| GET | `/api/v1/jobs/{elr_no}` | Web | job + revision ล่าสุด + document_resolution |
| GET | `/api/v1/jobs/{elr_no}/revisions/{rev}/lines` | Web | `[{side, line_no, expected_mark, oracle_mark, line_status, rules[], evidence, engineer_corrected_mark}]` |
| PUT | `/api/v1/jobs/{elr_no}/revisions/{rev}/lines/{side}/{line_no}/review` | Engineer | `{reason_code, note, engineer_corrected_mark}` |
| POST | `/api/v1/jobs/{elr_no}/revisions/{rev}/approve` / `reject` | Engineer | ปฏิเสธถ้า STALE หรือยังขาดเหตุผล/ค่าที่ถูกต้อง |
| POST | `/internal/v1/jobs/{elr_no}/reprocess` | Engineer/Admin | สร้าง revision ใหม่ |

- ไม่มี endpoint ใดเขียน Oracle; ไม่มี endpoint ใดคืน `oracle_mark` ให้บริการ LLM
- ทุก response มี `engine_version`, `rule_version`, `model_versions`

### 6.3 A100 inference (มีร่างใน `deploy/infer/`) — ยืนยันตามโค้ดร่าง **[ยืนยัน]**

`GET /health`, `POST /v1/page`, `POST /v1/rec`, `POST /v1/symbols`, `POST /ocr` (legacy), header `X-API-Key`, `LOCK` 1 request,
`FLAGS_allocator_strategy=auto_growth` (`deploy/infer/ocr_app.py:17,47`; `symbols_app.py:27,41`) — **Phase 0/1 ไม่ deploy**

## 7. Test Strategy [เสนอ]

| ชั้น | ทดสอบอะไร | ข้อมูล |
|---|---|---|
| Unit | กฎแต่ละข้อ (1 test ต่อ rule_id ขั้นต่ำ), parser SLR ทุกรูปแบบใน `R04-SLR-LINE.pattern`, ADI1039 28 token, resolver ทุก reason code | fixture เล็ก |
| Invariant/property | ข้อ 4 invariant 1–4; resolver ไม่ขึ้นกับลำดับ/mtime; ADI1039 ไม่ถูกเรียกเมื่อ doc_type = TRS | hypothesis |
| Contract | Oracle adapter ปฏิเสธ statement ที่ไม่ใช่ SELECT; inference client ตรง schema ของ `deploy/infer` | mock |
| Legacy parity | รันโค้ดเดิม (subprocess บนสำเนา frozen) กับ `mark_engine` แล้ว **อธิบายทุกบรรทัดที่ต่าง** ด้วยรหัสเหตุผล (`ORACLE_INFLUENCE_REMOVED`, `RESOLVER_CHANGED`, `GRAPHIC_NOW_COUNTED`, `LOT_NOW_VERIFIED`, `BUG`) — ผ่านเมื่อไม่มี `BUG` | baseline run 2 (06) |
| Regression (corrected) | ตัวชี้วัด spec §18 บน Jan–Jun ด้วย engine ใหม่ — ตั้งเป็น baseline ใหม่ "R1" | 06 |
| Blind | Jul–Nov ด้วย rule_version ที่ freeze | 06 |

ไม่มี test ใดเรียก Oracle/NAS/A100 จริงใน CI — ใช้ snapshot ที่ freeze แล้ว
