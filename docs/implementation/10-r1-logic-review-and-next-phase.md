# 10 — R1 Logic ปัจจุบัน, ผลรีวิว และการเตรียม Phase ถัดไป

วันที่: 2026-11-04 · branch `phase1/mark-engine` (ยังไม่ push) · DB `mark_web.mark_logic` **run 14** (commit `4cf36da`)
เอกสารนี้รวม logic ทั้งหมดที่เพิ่มระหว่าง R1 triage (D-22 – D-29) ไว้ที่เดียว; รายละเอียดแต่ละกฎอยู่ใน `01` §7, resolver ใน `03`, การตัดสินใน `07`

---

## 1. ภาพรวม pipeline (หลังแก้ทั้งหมด)

```
ElrMeta (Oracle meta, ไม่มี TOP/BACK_MARK)
  └─ resolve_documents ──> DocumentResolution (decision, hold_reason, hold_detail, review_detail, steps)
        └─ parse_slr ──> SlrFacts (instructions, scheduled_lots, unresolved)
        └─ load_inference ──> LayoutLine (OCR + re-OCR cache + YOLO graphics)
              └─ generate_expected ──> ExpectedMark (flags ต่อบรรทัด)      ← ไม่เห็น Oracle mark
                    └─ compare(expected, OracleMark) ──> LineComparison.status (+ warning)
                          └─ review_overlay ──> final_status (คำตัดสินของคน, แยกจาก status)
                                └─ page class: True / Warning / Error
```

หลักเดิมยังคงอยู่ทุกข้อ: independence 100% (รันซ้ำด้วย Oracle ว่าง), parity BUG 0, ไม่แก้ run 1–3 ใน DB

## 2. Logic ที่เพิ่มรอบนี้ (D-22 – D-29)

| D | ขั้น | Logic | ไฟล์ | ผล |
|---|---|---|---|---|
| D-22 | compare | Oracle ย่อ `THAILAND` เหลือ prefix ≥ 2 ตัว (`THAIL`, `TH`) → `MATCH` + `warning = COO_ABBREVIATED` | `compare/engine.py` `_coo_abbreviation` | 13 บรรทัด MATCH+warning |
| D-23 | resolver | revision ตัวอักษรใน `PRODUCT_NO` ≠ `CUST_BOM_REVISION` → `HOLD:REVISION_CONFLICT` + `hold_detail` | `documents/resolve.py` | 2 ELR |
| D-24 | resolver | revision Oracle = ตัวอักษรท้าย `CUST_BOM_NO` + `-` + `CUST_BOM_REVISION` (`ABS034529D`+`ENG-1` = `D-ENG-1`) | `resolve.py` `_oracle_revision` | 11 ELR → MATCH |
| D-25 | resolver → generate | แจ้งเตือนจริงพร้อมสาเหตุใน `review_detail`: `REVISION_MISMATCH` (Oracle rev ≠ ABS ฉบับเดียวในโฟลเดอร์), `PRODUCT_NO_ABS_MISMATCH` (PRODUCT_NO ชี้ ABS คนละเลข) → flag `RULE_CONFLICT` → NEEDS_REVIEW | `resolve.py`, `generate/generator.py` | user เห็นว่าต้องแก้อะไรใน Oracle |
| D-26 | หลัง compare | คำตัดสินของคน → `final_status` (DB_WRONG / HUMAN_FIXED / MATCH); `status` ของระบบไม่เปลี่ยน; ใช้เฉพาะบรรทัดที่เทียบจริง และเมื่อค่ายังเท่าตอนรีวิว | `regression/review_overlay.py` | แหล่ง: R0 `diff_review_*.csv` แล้ว `reviews/r1_review_*.csv` (ใหม่กว่าชนะ) |
| D-27 | inference | ใช้ re-OCR cache (`ocr_reocr.csv`) เมื่อค่าใหม่ ≠ เดิม และ score ≥ 0.9 (ไม่ดู GT/`kept`): legend อ่านเฉพาะค่าหลัง `LINE n:`, ตัดโลโก้ออกจาก crop | `adapters/snapshot.py` `_load_reocr` | `LHYBN`→`LHYB`, `UJHN`→`UJH`, `SAD`→`ADW` |
| D-28 | resolver | (1) ABS ที่ text layer อ่านไม่ได้ → ใช้เลขจากชื่อไฟล์ `ABS######` เฉพาะเมื่อไม่มี ABS เลขเดียวกันที่อ่านเนื้อหาได้ (step `ABS_BY_FILENAME`); (2) `CUST_BOM_NO` ไม่มีในโฟลเดอร์ แต่มี ABS ที่ `PRODUCT_NO` ระบุ → สร้างจากฉบับนั้น + แจ้ง `PRODUCT_NO_ABS_MISMATCH`; (3) `BOM_NOT_FOUND` มี `hold_detail` ว่าโฟลเดอร์มี ABS อะไร | `resolve.py` | 17 ELR / 69 บรรทัดได้เทียบ (Template C ม.ค.–เม.ย.), hold 103 → 85 |
| D-29 | SLR | ประโยค `Same date code with/as SLR######…` ไม่นับเป็น `SLR_UNRESOLVED` (ผูกค่าวันที่ ไม่เปลี่ยนรูปแบบ mark) | `slr/parse.py` `SAME_DATE_CODE_NOTE_RE` | 12 ELR / 48 บรรทัด → MATCH (BOTTOM 2 `{Lot-4}` = MATCH_LOT) |

ก่อนหน้านี้ในรอบเดียวกัน (`01` §7 ข้อ 1–9): `{Lot-n}`/"n DIGIT LOT NUMBER", COO suffix `ENGn`, SLR coverage, โฟลเดอร์ย่อยของ ELR อื่น,
`GRAPHIC_REMARK_CONFLICT` ระดับ ELR, `e3` ตาม remark, `R07-OCRFIX-6` ตัดเฉพาะ `U\d`

### 2.1 Layout แบบ Template C (legend `LINE n:` ใต้รูปตัวอย่าง)
- ABS บางฉบับมีรูปตัวอย่าง (`<YWW / LABC / Q456`) และค่าจริงเป็นข้อความ `LINE 1: {<}{YWW}`, `LINE 2: LHYB` ข้างล่าง
- พ.ค.–มิ.ย. (auto layout): `abs/layout.py` — มีแถว `LINE n:` ≥ 2 แถว → ใช้ legend แทนรูป
- ม.ค.–เม.ย. (human crop): annotation กติกา D7 crop ข้อความ `LINE n:` อยู่แล้ว
- ปัญหาที่เจอไม่ใช่ layout แต่ resolver HOLD ก่อน (D-28)
- ยังไม่ใช้: คำอธิบายตัวย่อใต้ภาพ (`{YWW} = 3 Digit Date Code`, `{<} = Pin1 <`)

## 3. การแบ่งผลบนหน้ารีวิว (True / Warning / Error)

นิยามตามผู้ใช้ 2026-11-04 (`scripts/make_review_page.py` `classify`) — ใช้กับบรรทัดที่ระบบเทียบได้ (`MATCH*`, `DIFF`, `NEEDS_REVIEW`)

| class | เงื่อนไข | run 14 |
|---|---|---:|
| **True** | expected ของระบบ = Oracle (ไม่นับช่องว่าง) รวม MATCH_LOT/SLR/SHIFT และบรรทัดที่ค่าตรงแต่ติดแจ้งเตือน config | **1,508** (93.7%) |
| **Warning** | ใกล้เคียง: Oracle ย่อชื่อประเทศ (กฎเดียวกับ D-22) — รวมบรรทัดที่ status เป็น NEEDS_REVIEW เพราะ alert ด้วย จึงมากกว่า `warning_lines` ใน metrics (13) | **25** (1.6%) |
| **Error** | ไม่ตรง; cause = Oracle ผิด (รีวิวยืนยัน) / ยังไม่รีวิว · DIFF / ยังไม่รีวิว · flag | **77** (4.8%) |
| ไม่ได้เทียบ | นอกขอบเขต 375 · HOLD 311 · เทียบไม่ได้ 22 | 708 |

Error 77 = Oracle ผิด (รีวิวยืนยัน) 17 + ยังไม่รีวิว 60

## 4. ตัวเลข run 14 (Jan–Jun, 668 ELR)

| ตัวชี้วัด | ค่า |
|---|---|
| Coverage ELR | 57.0% (381/668) |
| Coverage line | 69.5% (1,610/2,316) |
| Hold rate | 12.7% (85/668) |
| Oracle agreement (system status) | **85.34%** (1,374/1,610) — MATCH 1,205 · MATCH_SLR 114 · MATCH_SHIFT 15 · MATCH_LOT 40 · DIFF 49 · NEEDS_REVIEW 187 |
| แยก layout | auto 93.2% (477/512) · human crop 81.7% (897/1,098) |
| หลังรีวิว (`final_status`) | DB_WRONG 17 · HUMAN_FIXED 0 · ยังเปิด (NEEDS_REVIEW+DIFF) 213 |
| Independence | 100% (668/668) |
| Parity vs R0 | SAME 1,732 · RESOLVER_CHANGED 253 · REVIEW_FLAG 187 · GATE_SPEC_V2 77 · ORACLE_INFLUENCE_REMOVED 68 · GRAPHIC_NOW_COUNTED 1 · **BUG 0** |
| Tests | 219 unit + 3 regression |

## 5. ผลรีวิวที่บันทึกไว้

| ไฟล์ | เนื้อหา |
|---|---|
| `reviews/r1_review_2026-11-04.csv` | คำตัดสินรอบ 1 จากหน้ารีวิว (12 บรรทัด: DB_WRONG 8, SYSTEM_OK 6 — รวม ADI2602089 T5 `0.0` = DB_WRONG) — runner อ่านไฟล์นี้ |
| `reviews/r1_run14_review_export.csv` | export ทุกบรรทัดของ run 14 (2,318) + class/cause + คำตัดสิน/หมายเหตุบนหน้า (13 รายการ) — สร้างด้วย `scripts/export_review_csv.py` |
| หน้ารีวิว | https://claude.ai/artifact/8EdxZNgy6P6bZPfCwXxSnZ (เก็บคำตัดสินใน db `verdicts/<line id>`) · ไฟล์มีภาพ (ห้ามเผยแพร่) `artifacts/review/r1_review_local.html` |

Export ใหม่: ดึง `verdicts` ด้วย ArtifactData `list` (`out_dir`) แล้ว
`python scripts/export_review_csv.py --verdicts <out_dir> --out reviews/<name>.csv`
ถ้ามีคำตัดสินใหม่ให้ runner ใช้ ให้เพิ่มเป็น `reviews/r1_review_<date>.csv` (คอลัมน์ `id, expected, verdict, note`)

## 6. งาน Debug ค้าง (ทำรอบหน้า)

| # | เรื่อง | บรรทัด | สิ่งที่รู้ | ต้องการ |
|---|---|---|---|---|
| G1 | `Q` ใน Oracle ตรงตำแหน่ง date code 1 หลัก | 8 (ADI2602005, 101, 119–122, 124, 126) | template Oracle `MARK_NAME 41477448`; SLR `{DC-1} for 1-digit date code`; ABS `{1-DC}`; ระบบให้ `Y` / ไม่รู้จัก `{1-DC}` | ยืนยันว่า `Q` = placeholder date code 1 หลัก แล้วเพิ่ม `{1-DC}`/`{DC-1}` ↔ `Q` |
| G2 | หมายเหตุบนหน้ารีวิว ADI2601052 TOP 1 | 1 (ปัจจุบัน True) | note "rev ENG-1 ไม่นับเอาแค่ Digi BOM 10"; resolver เลือก `ABS065954B-ENG-1` ตาม D-24 | ถามความหมาย — อาจเป็นกติกาเลือก revision แบบใหม่ |
| G3 | DIFF ยังไม่รีวิว | 45 | เช่น expected ว่าง vs Oracle `?` (ADI2601052–054 T5), token `{1-DC}` | รีวิวบนหน้า แท็บ Error |
| G4 | SLR_OVERRIDE / unresolved ที่เหลือ | 7 | เช่น ADI2601066 T3 `ENGBU1Q 7ADC44285.012 -` vs `ENGBU1Q` (SLR ปนข้อความอื่น) | ตรวจ parser ตัดค่าเกิน |
| G5 | `FS91004B` vs `ADW91004B` | 4 (ADI2605053/054, ADI2606014/015) | SLR "Branding: FS for Fast-Slow…" (legend อธิบาย) | ตัดสินว่า SLR หรือ Oracle ถูก |
| G6 | MPW powerpoint | 12 ELR | SLR อ้าง "Multi Project Wafer build instructions powerpoint" — ไฟล์ไม่ได้อ่าน | คงแจ้งเตือนไว้ หรือรองรับ pptx |
| G7 | แจ้งเตือน config (ค่าตรงแต่ต้องแก้ Oracle) | 183 (True) | RC2 revision 60, RC3 PRODUCT_NO 77 + อื่น ๆ | ส่งรายการให้ทีม Marking แก้ Oracle |
| G8 | DB_WRONG ต้องแจ้งทีม Marking | 17 | `LSNv00–11`, `9x9`, `0.0`, ADI2602050 SLR/ECN | ส่งรายการ |
| G9 | ABS อ่านได้แต่ไม่มี SLR | ADI2601082–084, ADI2602001 ฯลฯ | `HOLD:SLR_NOT_FOUND` (ถูกต้องตาม gate) | ขอ SLR หรือยืนยันว่า hold |

คำสั่งเช็คเร็ว: `python -u scripts/run_regression.py --r0-root "D:/CIM Project/mark" --out artifacts/regression-r1` แล้ว
`MARK_R0_ROOT="D:/CIM Project/mark" python -m pytest -m regression -q` · โหลด DB: `scripts/load_r1_to_pg.py artifacts/regression-r1 --note "…" --commit` (env `MARK_PG_PASSWORD`)

## 7. เตรียม Phase ถัดไป

สถานะ: Phase 1 (`mark_engine` offline) ครบ 12 task และผ่านเกณฑ์ D-03 (BUG 0, independence 100%) — debug ข้อ 6 ไม่บล็อก Phase ถัดไป
แต่ต้องปิดก่อน blind test (ตัวเลข agreement จะขยับเมื่อแก้ G1, G3)

| ลำดับ | งาน | อ้างอิง | สถานะ |
|---|---|---|---|
| N1 | Merge `phase1/mark-engine` → base (`phase0/readiness`) แล้ว push (ต้องให้ผู้ใช้สั่ง) | HANDOFF §1 | รอ |
| N2 | Apply migrations `0001_roles` (role แยกแทน `postgres`), `0002_regression_frozen`, `0003_rule_governance`; เพิ่มคอลัมน์ `final_status`, `system_status`, `review_detail`, `warning` แทนการยัดใน `cause_detail` | `05`, `08` §4 | ยังไม่ apply |
| N3 | ส่งกฎใหม่ (D-22 – D-29) เข้า `logic_rule` ผ่าน migration 0003 + การอนุมัติ Mark Eng (ตอนนี้เป็นโค้ด + เอกสาร ยังไม่อยู่ใน `RV-2026-11-04-R0.json`) | `01` §7, `07` | รอ |
| N4 | Blind test Jul–Nov: ต้องเข้า NAS `\\th1srnas03\ELR\ADI\ELR Online 2026` ได้ (ตอนนี้ Access denied), ต้องมี inference ใหม่ (A100) แทน cache R0 | `06` §4.3 | blocker |
| N5 | Inference ออนไลน์: OCR det+rec + YOLO ผ่าน `deploy/infer/` — re-OCR legend/logo (D-27) ต้องเป็นขั้นจริง ไม่ใช่ cache | `04` §6.3 | ออกแบบแล้ว |
| N6 | หน้ารีวิวจริงในระบบ (แทน artifact): True/Warning/Error, alert, คำตัดสินลง `review_verdict` | spec, ข้อ 3 ของเอกสารนี้ | ต้นแบบ = artifact |
| N7 | PPTX/attachment ใน SLR (G6) และ OCR สำหรับ PDF ที่ text layer เสีย (แทน `ABS_BY_FILENAME`) | `03` ขั้น 3 | เสนอ |
