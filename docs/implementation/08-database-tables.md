# 08 — ตาราง Database `mark_web` (schema `mark_logic`)

> อ่านจาก DB จริงแบบ read-only เมื่อ 2026-11-04 (host `10.151.28.2:5432`, DB `mark_web`). ไม่มีรหัสผ่านในไฟล์นี้ — ใช้ env `MARK_PG_PASSWORD`

## 1. ภาพรวม

- มี schema เดียวคือ `mark_logic` (15 ตาราง, ไม่มี view) — เป็น **schema legacy ของ R0** เขียนโดยสคริปต์ใน repo `D:\CIM Project\mark`
  (`experiments/abs_vs_db/export_logic_pg.py`, `export_adi1039_pg.py`, `rule_scope_pg.py`, `mapping_gap_analysis.py`)
- **ยังไม่ได้ apply** `migrations/0001_roles.sql`, `0002_regression_frozen.sql` (`mark_regression.r0_*`), `0003_rule_governance.sql` (`mark_rules.*`) — ดูแผนใน [05](05-database-migration-plan.md)
- `mark_engine` Phase 1 **ไม่อ่าน DB ตอนรัน** — ใช้ snapshot ที่ commit ไว้ในแพ็กเกจ (ดูคอลัมน์ "ใน mark_engine")
- Run ที่มีอยู่: 1–3 = R0 (legacy, Oracle-conditioned; **run 3 = baseline ที่ freeze**), 4–5 = R1 (`mark_engine`; **run 5 = ปัจจุบัน**, run 4 ถูกแทนที่)

## 2. สรุปตาราง

| กลุ่ม | ตาราง | แถว | PK | หน้าที่ | ใน mark_engine |
|---|---|---:|---|---|---|
| ผลการรัน | [`run`](#run) | 5 | `run_id` | หัวของแต่ละ regression run + ตัวเลขสรุป | R1 เขียนเป็น run ใหม่ (`scripts/load_r1_to_pg.py`) |
| ผลการรัน | [`line_result`](#line_result) | 11,780 | `(run_id, elr_no, abs_no, side, line_no)` | ผลรายบรรทัด expected vs Oracle ของทุก run | R1 เขียน 2,318 แถว (run 5) |
| ผลการรัน | [`stage_accuracy`](#stage_accuracy) | 90 | `(run_id, stage_order, stage_no, period)` | ความแม่นยำสะสมทีละขั้น pipeline ของ R0 | ไม่ใช้ (R1 ไม่ได้เขียน) |
| ผลการรัน | [`elr_document`](#elr_document) | 602 | `elr_no` | ELR มี ABS / SLR / วัดได้หรือไม่ (R0) | ไม่ใช้ — R1 ใช้ `resolve_documents` |
| ผลการรัน | [`review_verdict`](#review_verdict) | 146 | `(review_file, line_id)` | คำตัดสินของคนจากไฟล์ diff review | ไม่ใช้ |
| พจนานุกรม | [`status_dictionary`](#status_dictionary) | 12 | `status` | ความหมาย/สี/การนับของแต่ละสถานะ | R1 เพิ่ม `NEEDS_REVIEW` |
| กฎ | [`logic_rule`](#logic_rule) | 44 | `rule_id` | แคตตาล็อกกฎ 44 ข้อ (ขั้น, pattern, origin, approval) | snapshot → `mark_engine/rules/data/RV-2026-11-04-R0.json` |
| Encoder | [`symbol_profile`](#symbol_profile) | 29 | `(cust_code, package_code, cust_symbol)` | Symbol ADI.xlsx: สัญลักษณ์ลูกค้า → สัญลักษณ์ Oracle | snapshot → `mark_engine/encode/data/symbol_adi_r0.json` |
| Encoder | [`encoder_alias`](#encoder_alias) | 17 | `abs_token` | alias ของ token ที่ OCR/ABS พิมพ์ → ชื่อ Symbol ADI | snapshot (รวมใน `symbol_adi_r0.json`) |
| Encoder | [`adi1039_token`](#adi1039_token) | 42 | `token_id` | ADI1039 Rev AE: placeholder → ค่าใน Oracle, lot slice | snapshot → `mark_engine/encode/data/adi1039_tokens.csv` |
| Encoder | [`adi1039_code`](#adi1039_code) | 1,506 | `(table_no, key)` | ตาราง lookup ADI1039 (wafer ID, date code, SOT66 month, die position) | ยังไม่ใช้ |
| Encoder | [`token_stat`](#token_stat) | 31 | `token` | สถิติ token ที่พบใน ABS ของ R0 และอัตรา match | ไม่ใช้ (วิเคราะห์อย่างเดียว) |
| ข้อมูล ELR | [`remark_profile`](#remark_profile) | 598 | `elr_no` | MARK_REMARK ที่ parse แล้ว (สัญลักษณ์ที่ประกาศ, logo, Skip Mark) | ไม่ใช้ — R1 parse `MARK_REMARK` เอง (`encode/remark.py`) |
| ข้อมูล ELR | [`slr_instruction`](#slr_instruction) | 533 | `elr_no` | SPECIAL INSTRUCTIONS + Scheduled Lot ID + qual lot จาก SLR | ไม่ใช้ — R1 ใช้ `slr/parse.py` |
| ข้อมูล ELR | [`slr_line_instruction`](#slr_line_instruction) | 209 | `(elr_no, side, line_no)` | คำสั่ง SLR รายบรรทัด (candidate หลายค่า) | ไม่ใช้ — ของ R0 เป็น candidate ที่ใช้ match กับ Oracle |

**ข้อควรระวังเมื่ออ่านค่า**
- `line_result` ของ run 1–3 กับ run 4–5 **เทียบกันตรง ๆ ไม่ได้**: R0 ปรับ `final_mark` ตาม Oracle (`docs/implementation/01` §4), R1 สร้าง expected โดยไม่เห็น Oracle
- ตาราง ELR/encoder ด้านล่างเป็น **ผลของ R0** ไม่ใช่ข้อมูลต้นทาง — แหล่งจริงคือ Oracle `ACTLDBA.ELR`, ไฟล์ใน NAS, `Symbol ADI.xlsx`, ADI1039 Rev AE

## 3. รายละเอียดแต่ละตาราง

### run
หัวของ regression run หนึ่งครั้ง (`run_id` serial)

| คอลัมน์ | ความหมาย |
|---|---|
| `run_id`, `run_at` | เลข run และเวลาที่บันทึก |
| `period` | ช่วง ELR เช่น `2026-01..2026-06` |
| `git_commit` | commit ของโค้ดที่ใช้ (R0 = repo `mark` `d425dc8`; R1 = `mark-web <sha> (branch)`) |
| `ocr_model`, `symbol_model` | โมเดล OCR / YOLO (R1 ใช้ cached inference ของ R0) |
| `elr_total`, `elr_measurable` | ELR ทั้งหมด / ที่วัดได้ (R1 = DONE และมีบรรทัดที่เทียบได้) |
| `lines_total`, `lines_measured`, `lines_match`, `match_pct` | บรรทัดทั้งหมด / ที่เทียบได้ / MATCH* / เปอร์เซ็นต์ |
| `lines_db_wrong`, `lines_diff` | DB_WRONG (มีคำตัดสินว่า DB ผิด) / DIFF |
| `pipeline_right_pct` | R0: % ที่ pipeline ถูกหลังนับ DB_WRONG — R1 ไม่ใส่ (NULL) |
| `note` | คำอธิบาย run |

| run | ที่มา | ตัวเลขหลัก |
|---|---|---|
| 1, 2 | R0 export แรก / หลังปรับ Qual lot | 1,956/1,982 = 98.69% |
| 3 | R0 v3 gates (**baseline freeze**, tag `regression-r0-2026-11-04`) | 1,747/1,773 = 98.53% |
| 4 | R1 `9dce03e` — ถูกแทนด้วย run 5 | 1,015/1,554 = 65.32% |
| 5 | R1 `cb9b74e` — **ปัจจุบัน**, parity BUG 0 | 1,014/1,550 = 65.42% |

### line_result
ผลรายบรรทัด — ลบอัตโนมัติเมื่อลบ `run` (FK `ON DELETE CASCADE`)

| คอลัมน์ | R0 (run 1–3) | R1 (run 4–5) |
|---|---|---|
| `elr_no`, `abs_no`, `side`, `line_no`, `month` | ตามชื่อ | `abs_no` = `ABS\d{6}` (ว่างถ้า HOLD); `month` จาก `ADI26MM` |
| `ocr_text`, `encoded`, `encoded_after_rules`, `yolo` | ผลแต่ละขั้น (OCR → Symbol ADI → กฎ → กราฟิก YOLO) | ว่าง |
| `final_mark` | ค่าที่ระบบสร้าง (**ถูกปรับตาม Oracle**) | `ExpectedMark` (ไม่เห็น Oracle) |
| `db_mark` | Oracle TOP/BACK_MARK | Oracle TOP/BACK_MARK |
| `status` | ดู `status_dictionary` | + `NEEDS_REVIEW` |
| `cause` | สาเหตุหลัก เช่น `OK`, `MAPPING_RULE`, `GRAPHIC_SYMBOL` | `hold_reason` / `detail` / compare rule (เช่น `COO_ABBREVIATED`, `SLR_UNRESOLVED`, `EXACT`) |
| `cause_detail` | ข้อความอธิบาย | `rules=…; flags=…; detail=…; layout_source=…; parity_vs_r0=…` |
| `graphic_check`, `slr_line`, `db_mark_remark` | ผลตรวจกราฟิก / ค่าจาก SLR / MARK_REMARK | ว่าง |
| `review_verdict`, `review_note` | คำตัดสินของคน | ว่าง (สำหรับ Mark Eng ในอนาคต) |

### stage_accuracy
ความแม่นยำสะสมทีละขั้นของ R0 (`stage_order` เช่น `ocr_first`, `stage` เช่น `1 OCR only`) แยก `period` (Jan-Apr / May-Jun) — `matched/total = pct`

### elr_document
ผลการหาเอกสารของ R0 ต่อ ELR: `has_abs`, `has_slr`, `measurable` — 602 แถว (รวม ELR ปลอมจาก range folder เช่น `ADI2603011-14`, ดู `01` #3)

### review_verdict
คำตัดสินจากไฟล์ review (`review_file` เช่น `diff_review_2026-11-04.csv`, `line_id` = `ELR_T4`) — `verdict`, `note`, `final_mark`, `db_mark` ณ เวลาตรวจ

### status_dictionary
| status | counts_as_match | in_denominator | ความหมายย่อ |
|---|:-:|:-:|---|
| MATCH, MATCH_SLR, MATCH_SHIFT, MATCH_LOT | ✓ | ✓ | ตรง (ตรง / ตาม SLR / เลื่อนบรรทัด pin dot / lot จริงที่ยืนยันกับ SLR) |
| DB_WRONG | | ✓ | ตรวจแล้ว DB ผิด |
| DIFF | | ✓ | ไม่ตรง ยังไม่มีคำตัดสิน |
| **NEEDS_REVIEW** (เพิ่มโดย R1) | | ✓ | expected มี review flag หรือ Oracle digits ยืนยันไม่ได้ → Mark Eng ตรวจ |
| DB_EMPTY, NOT_COMPARABLE, NOT_MARKED, NOT_MEASURABLE, NOT_ELIGIBLE | | | ไม่นับคะแนน |

### logic_rule
แคตตาล็อกกฎ 44 ข้อ: `step_no/step_name`, `rule_type`, `pattern/replacement`, `source/evidence`, `status`,
`rule_stage` (`generate` สร้าง expected / `compare` ใช้เทียบเท่านั้น / `gate` / `process`), `document_scope`,
`priority` (SLR 10 < ELR_REMARK 20 < Symbol ADI 30 < ADI1039 40 < OCR fix 50), `rule_origin`, `approval_status`
- **ไม่มี `provenance_class`** — การจัดประเภทของผู้ตรวจอยู่ใน `01` §3 และ `RV-2026-11-04-R0.json`
- R1 **ไม่ได้แก้ตารางนี้** (ยังเท่ากับ RV-2026-11-04-R0); การเปลี่ยน implementation ดู `01` §7

### symbol_profile
จาก `Symbol ADI.xlsx (Summary)`: `cust_symbol` (เช่น `{1 Digit Date Code - LTC format}`) → `comp_symbol` (ค่าใน Oracle), `utl_symbol`, `comments`,
สถิติ R0 `abs_lines/abs_elrs/abs_lines_match` — snapshot ถูกตรวจ SHA256 ของ xlsx (`7858dc40…`)

### encoder_alias
`abs_token` (เช่น `•`) → `symbol_adi_name` (`pin1 dot`) → `comp_symbol` (`@`), `kind`, `source` (`build_compare.py ALIAS`)

### adi1039_token
ADI1039 Rev AE §5: `dropdown` / `preview_text` (ข้อความที่พิมพ์ใน ABS เช่น "7 Digit Lot Number") / `abbreviation` (`{Lot-7}`) → `db_placeholder` (`XXXXXXX`),
`lot_slice` (ส่วนของ Scheduled Lot ID ที่ lot จริงต้องเท่ากับ), `implemented`, `document_scope = ABS`, `priority = 40`

### adi1039_code
ตาราง lookup ADI1039: 4a/4b wafer ID, 9/10 date code 2 หลัก, 11 เดือน SOT66, 15 die position (`table_no`, `key` → `code`) — สร้างด้วยสูตรและสุ่มตรวจกับ PDF

### token_stat
token ที่ R0 พบใน ABS (`kind`, `encoded_as`), จำนวน `lines/elrs`, `lines_match`, `match_pct`, `months`, `example_elr` — ใช้วิเคราะห์ coverage ของ encoder

### remark_profile
MARK_REMARK ต่อ ELR ที่ R0 parse: `declared_symbols` (array), `pin_dot_code`, `adi_logo_code`, `full_logo_code`, `caret_is_adi_logo`, `skip_mark`

### slr_instruction
ต่อ ELR: `special_instructions` (ข้อความ), `scheduled_lot_ids` (array), `qual_lot_n/qual_lot_total`, `brand_override` (SLR สั่งเปลี่ยน brand)

### slr_line_instruction
คำสั่ง SLR รายบรรทัด `(elr_no, side, line_no)` → `candidates` (array) — **R0 เลือก candidate ที่ตรง Oracle** (R04-SLR-LINE, `01` #10); R1 ใช้ค่าเดียวต่อบรรทัด, ถ้าขัดกัน → `SLR_AMBIGUOUS`

## 4. การเขียน R1 ลง DB

- สคริปต์: `scripts/load_r1_to_pg.py` (อ่าน `artifacts/regression-r1/{lines,jobs,parity}.csv` + `metrics.json`) — insert `run` ใหม่ + `line_result`, transaction เดียว, ตรวจว่า run เดิมไม่เปลี่ยน
- กติกา: rerun = **run_id ใหม่เสมอ**; ห้ามแก้/ลบ run 1–3; ห้ามแก้ `logic_rule` จนกว่าจะมี migration 0003 + การอนุมัติของ Mark Eng
- รหัสผ่านส่งทาง env `MARK_PG_PASSWORD` เท่านั้น; ควรสร้าง role แยก (migration 0001) แทน `postgres`
