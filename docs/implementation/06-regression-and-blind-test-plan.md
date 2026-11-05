# 06 — Regression Freeze (Jan–Jun 2026) และ Blind Test (Jul–Nov 2026)

วันที่: 2026-11-04 · ป้าย **[ยืนยัน]** / **[สันนิษฐาน]** / **[เสนอ]**

## 1. ชุด Jan–Jun ที่มีอยู่ **[ยืนยัน]**

| รายการ | ค่า | ที่มา |
|---|---|---|
| run ใน DB | run 1 (2026-11-04 15:07:57), run 2 (15:52:36) — `period 2026-01..2026-06`, `git_commit d425dc8` | `mark_logic.run` |
| บรรทัด | 2,381 ต่อ run (สถานะทั้งสอง run เท่ากันทุกหมวด) | `line_result` |
| สถานะ (ต่อ run) | MATCH 1,716 · NOT_MEASURABLE 270 · MATCH_SLR 132 · DB_EMPTY 105 · MATCH_SHIFT 61 · MATCH_LOT 47 · NOT_COMPARABLE 19 · DB_WRONG 18 · DIFF 8 · NOT_MARKED 5 | `line_result` |
| ตัวเลขหลัก | 1,956 / 1,982 = 98.69%; ELR 529 measurable / 598 | `run` |
| เดือน | 1_JAN 131 ELR · 2_FEB 141 · 3_MAR 90 · 4_APR 52 · 5_MAY 81 · 6_JUN 103 | `line_result.month` |

### ข้อจำกัดของชุดนี้ในฐานะ baseline

1. **Oracle-conditioned** — ผลไม่ได้มาจาก expected_mark ที่สร้างอิสระ (01 §4); ขอบล่างของส่วนที่ไม่ใช้ Oracle ≈ 72.3% **[สันนิษฐาน]**
2. **ม.ค.–เม.ย. ใช้ครอปบรรทัดของคน** (`dataset/annotation.csv` crop_bbox, `build_compare.py:108-114`) และครอป ม.ค.–มี.ค. เป็นชุดเทรน EXP09 (`build_compare.py:254`)
3. **ผล OCR อ่านซ้ำถูกเลือกด้วย GT** (`build_compare.py:104-107`, `reocr.py`)
4. **กฎถูกปรับบนชุดนี้เอง** (ทุกกฎ user_confirmed อ้าง "user review 2026-11-04" บนเคสในชุดนี้)
5. **โค้ดที่สร้างผลไม่อยู่ใน git** และไฟล์ถูกแก้ระหว่างตรวจ (15:51) → ทำซ้ำไม่ได้หากไม่ freeze ตอนนี้
6. ความต่าง measurable 531 (`elr_document`) vs 529 (`run`) ยังไม่ได้อธิบาย

## 1b. สถานะ freeze จริง (อัปเดตรอบ 2) **[ยืนยัน]**

- ระหว่างตรวจ session อื่นสร้าง **run 3** (16:05:12, "v3 gates: SLR required only when CUST_REQ_NO set; TYPE_CODE E only;
  cancelled ELRs excluded") — run 3: ELR measurable 470/598, 1,747/1,773 = 98.53%; สถานะ MATCH 1,555 · NOT_ELIGIBLE 482 ·
  MATCH_SLR 123 · MATCH_SHIFT 57 · NOT_MARKED 53 · NOT_COMPARABLE 33 · NOT_MEASURABLE 28 · DB_WRONG 20 · MATCH_LOT 12 · DB_EMPTY 12 · DIFF 6
- **R0 = run 3** (D-04): โค้ด commit `d7d788e` / tag `regression-r0-2026-11-04` (repo `mark`, local) = ไฟล์บนดิสก์ตอน 16:21 ตรงกับ run 3;
  DB export `artifacts/regression-r0/mark_logic/` + `MANIFEST.json` (line_result run 3 sha256 prefix `03c3b40e`)
- **R0-legacy = run 2** (529 ELR): `artifacts/regression-r0/line_result_run2_529elr.csv` sha256 `1e779c901b2b3369…`;
  ตารางอ้างอิงของ run 2 มีเฉพาะ `run2_reference_snapshot_1554.json` (ตารางใน DB ถูกแทนด้วยของ run 3 แล้ว)
- manifest ไฟล์ในข้อ 3 ด้านล่างถ่ายตอน ~15:55 (ยุค run 2) — ไฟล์ของ R0 จริงให้ยึด commit `d7d788e`
- NAS (D-12) มีโฟลเดอร์ ม.ค.–มิ.ย. 635 (สำเนาใน repo มี 602) และ ก.ค.–พ.ย. 354

## 2. Freeze plan (รอบแรก — F1, F3-ไฟล์ ทำแล้ว; F2, F3-DB รอ)

Phase 0 **ไม่ได้แก้ไขอะไรใน dataset** — บันทึกเฉพาะ manifest ด้านล่าง (อ่านอย่างเดียว) ขั้นที่ต้องทำต่อ:

| # | ขั้น | ผล |
|---|---|---|
| F1 | ใน repo `mark`: commit `experiments/abs_vs_db/`, `experiments/symbol_det/`, `deploy/` (ยกเว้นข้อมูลใหญ่/secret) แล้ว tag `regression-r0-2026-11-04` | โค้ดที่สร้าง baseline มี commit จริง |
| F2 | หยุดรัน `export_logic_pg.py` บน `mark_web` จนกว่า M1–M3 เสร็จ | baseline ไม่ถูกเขียนทับ |
| F3 | Migration M0 + M2 (05) — คัดลอก run 2 → `mark_regression.baseline_r0_*` + manifest | DB baseline ล็อก |
| F4 | คัดลอกไฟล์ใน manifest ข้อ 3 ไปที่เก็บแบบ read-only (MinIO bucket `regression/r0/` หรือ NAS share) พร้อม sha256 | ไฟล์ baseline ล็อก |
| F5 | ตั้งชื่อ baseline: **R0 = legacy (Oracle-conditioned)**; หลัง `mark_engine` เสร็จ จะมี **R1 = independent generate** บน Jan–Jun | แยกตัวเลขสองชุดชัดเจน |

## 3. Manifest ณ เวลาตรวจ **[ยืนยัน]** (repo `D:\CIM Project\mark`, sha256)

| ไฟล์ | sha256 | bytes | แก้ล่าสุด |
|---|---|---|---|
| `experiments/abs_vs_db/out/line_compare.csv` | `1fd708508eec04b363fd84ec2ace0c5c4ee10621e81d010257fdab952772bdd1` | 340549 | 2026-11-04 14:53 |
| `experiments/abs_vs_db/out/line_compare_h1.csv` | `74c3e37e608bb975718df131d8a9037d777bce1b3467a044f7cdb5d794e7de36` | 149582 | 2026-11-04 14:53 |
| `experiments/abs_vs_db/out/mapping_gap.csv` | `66e25cb18e60d8908a5b8b74154f00b8333011e5a88a1e8c6957a2f68bcdb1f7` | 655685 | 2026-11-04 15:52 |
| `experiments/abs_vs_db/out/summary_elr_abs_ocr_gt.csv` | `94e11b25d5f42538f833db34e7df7fb0e8c3824a797ab278e7abb3e05914d294` | 734680 | 2026-11-04 15:52 |
| `experiments/abs_vs_db/out/elr_db_2026.json` | `2b97fb6f761141fe14f45599ec8453599c7652bb6c431590c937c2192878f76c` | 301046 | 2026-11-03 15:24 |
| `experiments/abs_vs_db/out/elr_db_2026_h1.json` | `b284704efa6a3999e1e75c69a34267862d2a3c7d6b69c456dbbf56cc62016dd3` | 432828 | 2026-11-04 11:18 |
| `experiments/abs_vs_db/out/ocr_preds.csv` | `0a30c6f797dedf3115e9a7fccccd78b8b19d34ce42c9582f5782fbecb0aeb4de` | 48649 | 2026-11-03 15:44 |
| `experiments/abs_vs_db/out/ocr_reocr.csv` | `6980a89e3d50245c81020a63b30b1523999a81a3e4e6080336001070d5c91adc` | 903 | 2026-11-04 14:53 |
| `experiments/abs_vs_db/out/h1_det_rec.json` | `59ed4d14c034e59442912fc926d93690fa9991dd4b7713fec61ef09a56fcf6f4` | 118467 | 2026-11-04 11:45 |
| `experiments/abs_vs_db/out/logic_dump.json` | `938c74c3ffff036d19e4e145c52ce13473f184185497219dfb24e3efb39f3ec2` | 397934 | 2026-11-04 15:52 |
| `experiments/abs_vs_db/review/diff_review_2026-11-04.csv` | `6473a52ce72c9db5741bd9139a8158620c79bbdcfb749800b579f0847e80bdb6` | 20960 | 2026-11-04 14:43 |
| `experiments/abs_vs_db/review/diff_review_2026-11-04b.csv` | `e0020e07bdbc1a07d3e1842666ce1db51ddaddaed25fe878f308ef1f75fcecec` | 2449 | 2026-11-04 14:56 |
| `experiments/symbol_det/graphics_by_line.csv` | `cb57748ab99b6f56efb1ed5392a6718591ef279b8cfe663626cb30d73f406fef` | 3756 | 2026-11-04 13:44 |
| `experiments/symbol_det/graphics_by_line_h1.csv` | `cc6b8f2e8ac810b95060725137b6226d562b8be77159ceca5318a4d838920ba5` | 2499 | 2026-11-04 14:53 |
| `experiments/symbol_det/review_decisions.csv` | `385dfbbffb7e1db0e46f22d4966e6bccb16d86daa874f2b9de06980f958d6bb5` | 1913 | 2026-11-04 10:20 |
| `dataset/annotation_frozen_v1.0.csv` (= `dataset/annotation.csv`) | `4a40624885b3a1a7ea050093e5de576fbb8996ae4c54afcdc22ee99290ef7095` | 254770 | 2026-10-02 |
| `dataset/eval_4_apr/annotation_v1.1.csv` | `b9a178a1b9a0caf396d8e52a2f8b86e2bf3956ccb34783b694b31451c8eb3b0e` | 38175 | 2026-10-03 |
| `dataset/eval_h1/images_index.csv` | `a270ac93d69aa0afc27872a32cb011490240a0c7c43b1645c81fea32ca3faae3` | 20410 | 2026-11-04 11:35 |
| `ADI1039.pdf` | `f536ce17e19709e186b86e34d6dee89ad4b3050307fcd2be258cf6f215263f1b` | 3339256 | 2026-07-01 |
| `experiments/abs_vs_db/mapping_gap_analysis.py` | `d215f4b0f3e5d7705048bb850de89e14be230ac3e3e1f4c87da18c4b2931f16c` | 37320 | 2026-11-04 15:51 |
| `experiments/abs_vs_db/build_compare.py` | `a68d6eac41c1c90902788b4cd8bda5560c43c35a9ac96db4bedea8e08c40b96c` | 14212 | 2026-11-04 14:53 |
| `experiments/abs_vs_db/build_h1.py` | `8fc68a04a1fd42d72b5eb869465e6f9f54f4fbae8adb7b992a6f809ff0e6d7fd` | 11420 | 2026-11-04 14:53 |
| `experiments/symbol_det/graphics_to_lines.py` | `cb4ced1843f40909cfe27a1cbe1e601b14068eefb03328bda5dde8f46f2c05fa` | 6127 | 2026-11-04 13:44 |
| `experiments/abs_vs_db/export_logic_pg.py` | `9e3e63e4f8ab2d1cbd65c29a0b89f54c28ef0eb4ce5fae2ee9a00e30a54cda22` | 29267 | 2026-11-04 15:51 |
| `experiments/abs_vs_db/rule_scope_pg.py` | `7d674389856b958138f99a47de74b6b40f57a9b2feff4fc671865e9d5dd35d57` | 6901 | 2026-11-04 15:51 |
| `Symbol ADI.xlsx` | **อ่านไม่ได้ — ไฟล์เปิดค้างอยู่ใน Excel** (มี `~$Symbol ADI.xlsx`) | | ต้อง hash หลังปิด |

ถ้าไฟล์ใดถูกแก้หลังเวลานี้ ให้ถือว่า manifest R0 ต้องสร้างใหม่ตอน F1 (และบันทึกความต่าง)

## 4. Blind test dataset Jul–Nov 2026

### 4.1 จำนวนใน Oracle **[ยืนยัน]** (query 2026-11-04 ~15:55)

| prefix | ELR | IMPORT_DATE |
|---|---|---|
| ADI2607 | 77 | 2026-06-29 → 2026-07-31 |
| ADI2608 | 105 | 2026-07-26 → 2026-08-31 |
| ADI2609 | 107 | 2026-08-24 → 2026-09-30 |
| ADI2610 | 98 | 2026-09-28 → 2026-10-28 |
| ADI2611 | 15 | 2026-10-27 → 2026-11-04 11:55 (ยังเพิ่มอยู่) |
| **รวม** | **402** | |

- `MARK_APPROVE = 'A'` 347 · `TOP_MARK1` non-null 334 · `CURRENT_STEP = '7'` 347 / `'1'` 55
- `TOP_LAYOUT_CODE = 'ZY'` 23 (ถูกตัดตาม gate R06-TYPE-LAYOUT) · null 69

### 4.2 นิยามชุด blind [เสนอ]

- **กรอบ:** `ELR_NO` prefix `ADI2607`–`ADI2611` (ใช้เลข ELR ไม่ใช่ IMPORT_DATE เพราะช่วงทับกันข้ามเดือน) · ตัดชุดที่ **2026-11-30 23:59** แล้วล็อก snapshot
- **รวมเข้า:** `MARK_APPROVE = 'A'` และ `TOP_MARK1` หรือ `BACK_MARK1` ไม่ว่าง (มี oracle_mark ให้เทียบ)
- **ตัดออก — เคยถูกดูระหว่างพัฒนา (contamination) [ยืนยัน]:** 21 ELR
  - ปรากฏใน `Search_data/scripts/sample_2026_elrs.json` / `matched_2026_files.json` / `elr_abs_marking_pages_2026.json`:
    ADI2607014, ADI2607054, ADI2607056, ADI2607071, ADI2607074, ADI2608003, ADI2608039, ADI2608041, ADI2608061, ADI2608062,
    ADI2608075, ADI2608078, ADI2609002, ADI2609017, ADI2609061, ADI2609062, ADI2609104, ADI2609105, ADI2609106
  - ปรากฏใน `mark/ActiveL_Mark V2.sql`: ADI2610059, ADI2610075
  - (ไม่พบ ADI2607–2611 ในโค้ด/ข้อมูลอื่นของ repo `mark` นอกโฟลเดอร์เดือน)
- **รายงานแยก:** ELR ที่ HOLD (ไม่มี ABS/SLR ฯลฯ) ไม่ตัดออก แต่นับเข้า Hold Rate
- **ขนาดคาด [สันนิษฐาน]:** ~320–330 ELR (347 approved − 21 contamination − บางส่วนไม่มี mark) ~1,200–1,300 บรรทัด

### 4.3 สิ่งที่ขาด (blocker ของ blind test)

1. **NAS เข้าไม่ได้** จาก account นี้ → ยังไม่มี ABS/SLR ของ ก.ค.–พ.ย. (สำเนาใน repo มีแค่ `1_JAN`–`6_JUN`)
2. **ไม่มี OCR/YOLO cache** สำหรับ ก.ค.–พ.ย. — ต้องเรียก A100 (`/ocr` port 8095 ที่มีอยู่) แบบ batch ซึ่ง Phase 0 ห้ามแตะ service; ทำใน Phase 1 ด้วยการเรียก endpoint ที่มีอยู่ (ไม่ deploy/restart)
3. **Ground truth สำหรับ Correctness / False PASS** ยังไม่มี — Oracle agreement วัดได้ทันที, ส่วน False PASS ต้องให้ Mark Eng ยืนยันตัวอย่าง (เสนอ: ทุกบรรทัด MATCH* ใน 60 ELR สุ่มแบบ stratified ตามเดือน + ทุกบรรทัดที่ไม่ MATCH)

### 4.4 กติการะหว่างวัด

- ใช้ `rule_version` ที่ frozen (`mark_rules.rule_version.frozen = true`) + `engine_version` + model version คงที่ ตลอดการวัด
- ห้ามแก้กฎ/parser ระหว่างวัด; ข้อผิดพลาดที่พบ บันทึกใน `07` แล้วแก้ใน version ถัดไป
- ผู้พัฒนาไม่ดูผลรายบรรทัดจนกว่าการรันจะจบและ metric ถูกบันทึก

## 5. ตัวชี้วัดที่รายงาน (spec §18, ปรับนิยาม)

| ตัวชี้วัด | นิยาม | R0 (legacy) | R1 Jan–Jun | Blind Jul–Nov |
|---|---|---|---|---|
| Coverage ELR | ELR ที่ processing DONE และไม่ HOLD / ELR ในกรอบ (ตัวหาร = Oracle ไม่ใช่โฟลเดอร์ NAS) | 529/598 (88.5%) | **57.0%** (381/668) · auto 54.6% (112/205), human 58.1% (269/463) — run 14 | วัด |
| Coverage line | บรรทัดที่เทียบได้ / บรรทัดที่ oracle หรือ expected มีค่า | 1,982/2,381 (83.2%) | **69.5%** (1,610/2,316) · auto 72.1% (512/710), human 68.4% (1,098/1,606) | วัด |
| Hold Rate | HOLD + NOT_VERIFIABLE / ELR | 12.1% (ตัวหาร 602) | **12.7%** (85/668) · auto 10.7% (22/205), human 13.6% (63/463) | วัด |
| Oracle agreement | MATCH* / comparable — **แสดงแยก MATCH, MATCH_SLR, MATCH_SHIFT, MATCH_LOT** | 98.7% (conditioned) | **85.3%** (1,374/1,610) [MATCH 1,205 (ในนี้ COO ย่อ + warning 13), MATCH_SLR 114, MATCH_SHIFT 15, MATCH_LOT 40, DIFF 49, NEEDS_REVIEW 187]; auto 93.2%, human 81.7%; หลังรีวิว DB_WRONG 17 — run 14 | วัด |
| Independence | expected เท่าเดิมเมื่อลบ oracle_mark | ไม่ผ่าน (by design) | **100.0%** (668/668 — วัดจริง: รัน `process_elr` ซ้ำด้วย `OracleMark` ว่างแล้วเทียบ `ExpectedMark`) | ต้อง 100% |
| Parity vs R0 BUG | divergence จาก R0 ที่ไม่มีคำอธิบายทางสถาปัตยกรรม | — | **0 — ผ่าน** (run 14: SAME 1,732, RESOLVER_CHANGED 253, REVIEW_FLAG 187, GATE_SPEC_V2 77, ORACLE_INFLUENCE_REMOVED 68, GRAPHIC_NOW_COUNTED 1, BUG 0) | — |
| Correctness | expected == engineer_verified | — | ตัวอย่าง | ตัวอย่าง |
| False PASS | MATCH* และ engineer_verified ≠ expected | — | **ต้อง 0** | **ต้อง 0** |

| True / Warning / Error (หน้ารีวิว) | บรรทัดที่เทียบได้: = Oracle / COO ย่อ / ไม่ตรง (`10` §3) | — | 1,508 / 25 / 77 (93.7% / 1.6% / 4.8%) | วัด |

### 5.0 ประวัติ run R1 ใน DB (ล่าสุด run 14 — ดู `08`)
run 8 OCRFIX-6 · 9 D-24 · 10 D-25/26 · 11 D-27 · 12 D-28 · 13 รีวิวรอบ 1 · 14 D-29 — ตัวเลขข้างล่าง §5.1 เป็นของ run 7 (เก็บไว้เป็นประวัติ)

### 5.1 รายละเอียดผลลัพธ์ R1 Jan–Jun (branch `phase1/r1-fixes`, 2026-11-04)

ตัวเลขชุดก่อน (commit `d4fd534`: agreement 25.8%, BUG 0, independence 1.0) **ใช้ไม่ได้**:
independence เป็นค่า default (ไม่ได้ส่ง blank run), parity เทียบ `abs_no` คนละรูปแบบ
(`ABS066973-ENG-1` vs `ABS066973`) จน MATCH 327 บรรทัดถูกนับเป็น RESOLVER_CHANGED และซ่อน BUG ไว้

แก้ใน R1 รอบนี้ (รายละเอียดกฎ: `01` §7):
1. Independence วัดจริง — `run_regression.py` รัน blank-Oracle ซ้ำทุก ELR; `compute_independence` คืน `None` ถ้าไม่ได้วัด
2. Parity normalise `abs_no` เป็น `ABS\d{6}`; R0 cause `DB_LINE_EMPTY` → `ORACLE_INFLUENCE_REMOVED`
3. SLR coverage (`R04-SLR-LINE`) ไม่นับ `lot`/`attachment` ลอย ๆ — SLR_UNRESOLVED 803 → 86 บรรทัด
4. `R07-ADI1039-LOT` รับรูป preview text "n DIGIT LOT NUMBER" (ADI1039 Table 2)
5. `R07-OCRFIX-7` ไม่ลบทั้งช่อง COUNTRY OF ORIGIN เมื่อเจอ suffix `ENGn`
6. `R07-ADI1039-COO` ฝั่ง compare: Oracle `TH`…`THAILAN` = MATCH + warning, `detail = COO_ABBREVIATED` (ADI1039 5.5.3, D-22)
7. `HOLD:REVISION_CONFLICT` เมื่อ `CUST_BOM_REVISION` ขัดกับ `PRODUCT_NO` (D-23)

BUG 13 บรรทัดสุดท้าย — triage แล้ว (BUG = 0):
- `ADI2602092` TOP 2–4 → **แก้ resolver** (`fingerprint.py`): โฟลเดอร์ `2_FEB/ADI2602092/` มีโฟลเดอร์ย่อย `ADI2602095/` (ABS062830A + SLR231729 ของ ELR อื่น) ซึ่งถูกสแกนรวม → SLR ของสินค้าอื่นเขียนทับบรรทัด 2–5; ตอนนี้ข้ามโฟลเดอร์ย่อยที่ตั้งชื่อเป็น ELR อื่น (ยังเก็บโฟลเดอร์ย่อยของ ELR เดียวกัน/อยู่ใน range) → ELR นี้เหลือแต่อีเมล (OTHER) จึงเป็น `HOLD:SLR_NOT_FOUND` (`GATE_SPEC_V2`, CUST_REQ_NO ว่าง)
- `ADI2606077/078` TOP 2–5 → `RESOLVER_CHANGED` (ไม่ใช่บั๊ก): โฟลเดอร์มี ABS068387**B** และ **C**, Oracle `CUST_BOM_REVISION = B` → R1 ใช้ B ตาม D-08 (ภาพเดียวกัน MATCH ทั้งหมดใน ADI2606035–037) แต่ TOP_MARK ใน Oracle ตรงกับ rev C; R0 เลือก ABS ที่ตรง Oracle (R03-ONE-ABS, rejected D-06). **ข้อค้นพบสำหรับ Mark Eng: Oracle ระบุ rev B แต่ mark ที่บันทึกเป็นของ rev C** — parity ใช้ `abs_other_revisions` (REVISION_SUPERSEDED จาก resolver) เพราะ R0 ไม่เก็บ revision
- `ADI2605013`, `ADI2606019` TOP 2 → `OCR_SOURCE_CHANGED`: R0 ใช้ `ocr_reocr.csv` (`LHYBN` → `LHYB`, kept = Y คัดด้วย GT, R04-REOCR-*) ส่วน R1 ใช้ OCR ดิบ; parity อ่าน `ocr_reocr.csv` จริงแทน ELR ที่ hard-code ไว้ (5 บรรทัด kept = Y)

`GRAPHIC_REMARK_CONFLICT` (`01` §7 ข้อ 6–7): ตรวจโลโก้ระดับ ELR จากข้อความ expected → NEEDS_REVIEW 475 → **210**, agreement 65.4% → **82.1%**;
บรรทัดที่เคยถูกซ่อนด้วย flag เผย `{e3}` ที่ remark ประกาศเป็น `e3` (แก้ในข้อ 7) และ MATCH_LOT 23 บรรทัดที่ตรวจกับ SLR ได้จริง

ยังต้องดูต่อ: NEEDS_REVIEW 210 = `RULE_CONFLICT` 112 (`REVISION_NAME_MISMATCH` — ABS ฉบับเดียวแต่ชื่อ revision ไม่ตรง Oracle), `SLR_UNRESOLVED` 86, `ORACLE_VALUE_IN_SLR` 5, `GRAPHIC_REMARK_CONFLICT` 4; 179/210 มีค่าเท่า Oracle

## Frozen holdout result (2026-11-05)

See [11-blind-test-2026h2.md](11-blind-test-2026h2.md) for run 17, measured denominators, 141 layout overflows, snapshot cutoff and analyst-blindness limitation.
