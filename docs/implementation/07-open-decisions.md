# 07 — Decisions Log

อัปเดต 2026-11-04 (รอบ 2): เจ้าของโปรเจกต์ (Kam) ตอบเองบางข้อ และมอบให้ Claude ตัดสินข้อ 1–12 แทน
ป้ายผู้ตัดสิน: **[เจ้าของ]** = Kam ตอบเอง · **[มอบหมาย]** = Claude ตัดสินแทนตามที่เจ้าของมอบ (แก้ได้ทุกเมื่อ) · **[เปิด]** = ยังไม่ตัดสิน

## ตัดสินแล้ว

| ID | เรื่อง | คำตัดสิน | ผู้ตัดสิน | เหตุผล / หลักฐาน |
|---|---|---|---|---|
| D-01 | trigger "Mark Eng Review" | `ACTLDBA.ELR.CURRENT_STEP = '6'` (step code: 1 CS Review, A QA Review, 2 Engineering Review, 3 MC review, 4 Engineering lot Center, 5 PC Reserve, **6 Mark Eng review**, 7 Generate Order) | [เจ้าของ] | `mark/ActiveL_Mark V2.sql:28-38`. **[ยืนยัน]** ตอนตรวจไม่มี ELR ของ ADI อยู่ step 6 เลย (ทุกปี: step 1 = 1,112, 4 = 4, 5 = 2, 7 = 8,280) → เป็นสถานะชั่วคราว poller ต้องถี่ และต้องมีรอบเก็บตกจาก step 7 ที่ `MARK_DATE` ใหม่ (shadow) |
| D-02 | `engineer_verified_mark` | ค่าที่ Engineer รับรองตอน Approve: corrected ถ้ามี ไม่งั้น expected; ห้ามตั้งจาก oracle | [มอบหมาย] | ทำให้มี ground truth ครบทุกบรรทัดสำหรับ False PASS |
| D-03 | เกณฑ์ผ่าน Phase 1 | (ก) expected ไม่ขึ้นกับ oracle_mark 100% (ข) legacy-parity: ทุกบรรทัดที่ต่างจาก R0 มี reason code และไม่มี `BUG` (ค) บันทึก R1 เป็น baseline ใหม่ | [มอบหมาย] | ผลเดิม Oracle-conditioned (01 §4) |
| D-04 | Baseline R0 | **R0 = `mark_logic` run 3** (16:05:12) + โค้ด tag `regression-r0-2026-11-04` (commit `d7d788e`) · **R0-legacy = run 2** (`line_result` 2,381 บรรทัด, 529 ELR) เก็บเป็น CSV | [มอบหมาย] | เดิมตั้งใจใช้ run 2 แต่ session อื่นแก้โค้ดและกฎ (run 3) ก่อน commit → run 3 เป็นชุดเดียวที่โค้ด/กฎ/ผลตรงกันครบ; ตารางอ้างอิงของ run 2 มีแค่ snapshot JSON 15:54 |
| D-05 | ADI1039 กับ SLR | ใช้ตีความ placeholder ใน **ABS และ SLR** ได้ (`{Lot-n}`, `{DC-n}`, `{Pb-Free}` คือ abbreviation ใน ADI1039 Table 1–2) · **ห้ามใช้กับ TRS** (TRS → HOLD) | [มอบหมาย] | แก้ประโยค spec §9 "ABS เท่านั้น" เป็น "ABS/SLR ไม่ใช่ TRS" |
| D-06 | กฎ ORACLE_DERIVED + SLR-QUAL | ดูตาราง D-06 ด้านล่าง — บันทึกใน `migrations/0003_rule_governance.sql` (ยังไม่รัน, ไม่แก้ `mark_logic`) | [มอบหมาย] | หลัก: ยอมรับเฉพาะที่ไม่เอาค่า Oracle เข้า expected; ที่เหลือเป็น compare-only หรือปฏิเสธ |
| D-08 | revision ของ ABS | ตัวหลัก `CUST_BOM_REVISION` (Oracle) → หา ABS ที่ revision ตรง; หลักฐานรอง: ชื่อไฟล์ (`A`, `-ENG-n`); เนื้อหาเมื่ออ่านได้; ขัดกัน → REVIEW; Oracle `N/A` และมี ABS > 1 → HOLD | [มอบหมาย] | 40 ABS ตัวอย่างไม่มี REV ใน text หน้า 1 (03 §2) |
| D-09 | `n DIGIT SERIAL NUMBER` | คง `X×n` เป็น placeholder ของ field ที่เปลี่ยนต่อ unit; ถ้า Oracle ใส่ตัวเลขจริง → NEEDS_REVIEW (ไม่มีแหล่งให้ตรวจ serial) | [มอบหมาย] | ไม่ขัด ADI1039 Table 12 เพราะ Table 12 นิยามค่าจริงตอนผลิต ไม่ใช่ค่าที่ต้องคีย์ |
| D-10 | `MARK_ID_LAYOUT` / `MARK_ID_SYMBOL` | ค่าฝั่ง Oracle — **ห้ามเป็นอินพุตของ expected_mark**; ใช้ได้แค่แสดงผล/เทียบ | [มอบหมาย] | เป็นแม่แบบที่ระบบ ACTL เก็บ ไม่ใช่เอกสาร ADI |
| D-11 | Oracle read-only account | **ไม่ขอ user ใหม่** — เว็บ/engine บังคับเองว่าไม่ทำอะไรกับ Oracle นอกจาก SELECT (`SET TRANSACTION READ ONLY` + allow-list statement + test) | [เจ้าของ] | ความเสี่ยงที่ยอมรับ: `ACTLUSR` ยังมีสิทธิ์ INSERT/UPDATE/DELETE ในระดับ DB |
| D-12 | NAS | ใช้ account `TH\41451475` — **[ยืนยัน]** เข้า `ELR Online 2026` ได้: 1_JAN 131 · 2_FEB 138 · 3_MAR 89 · 4_APR 82 · 5_MAY 89 · 6_JUN 106 · 7_JUL 67 · 8_AUG 103 · 9_SEP 89 · 10_OCT 81 · 11_NOV 14 โฟลเดอร์ | [เจ้าของ] | รหัสต้องอยู่ใน secret store/env เท่านั้น ห้ามอยู่ใน repo |
| D-13 | rotate รหัส `postgres` / `actlusr` | **ไม่ทำตอนนี้** | [เจ้าของ] | ความเสี่ยงที่ยอมรับ; migration 0001 ยังแยก role ให้แอปไม่ใช้ superuser |
| D-14 | commit โค้ด repo `mark` | ทำแล้ว: branch local `phase0/regression-r0`, commit `d7d788e`, tag `regression-r0-2026-11-04`, **ไม่ push** (remote GitHub, มีภาพ ABS ของลูกค้าใน `experiments/symbol_det/preview/`) | [มอบหมาย] | ไฟล์ที่คุณ stage ลบไว้ก่อน (`CLAUDE_WORK_LOG.md`, `EXPERIMENT_PLAN.md`) ไม่ถูก commit และยังอยู่ในสถานะเดิม |
| D-17 | ตัวอย่างวัด False PASS | stratified ตามเดือน 60 ELR (ทุกบรรทัด) + ทุกบรรทัดที่ไม่ใช่ MATCH + **ทุกบรรทัด MATCH_SLR / MATCH_SHIFT / MATCH_LOT** | [มอบหมาย] | บรรทัด MATCH แบบมีเงื่อนไขเสี่ยง False PASS สูงสุด |
| D-18 | migration M0–M3 | เขียนไฟล์แล้วใน `migrations/` — **ยังไม่รัน** | [มอบหมาย] | ให้ DBA รันบนสำเนาก่อน |

### D-06 — คำตัดสินรายกฎ

| rule_id | คำตัดสิน | เงื่อนไข |
|---|---|---|
| R07-REMARK-CARET | อนุมัติ (generate) มีเงื่อนไข | ขัดกับกราฟิกที่ YOLO เห็น → NEEDS_REVIEW |
| R07-REMARK-LOGO | อนุมัติ (generate) มีเงื่อนไข | เช่นเดียวกัน |
| R07-REMARK-PIN | อนุมัติ (generate) มีเงื่อนไข | YOLO เห็น pin dot แต่ remark ไม่ประกาศ `@` → NEEDS_REVIEW |
| R07-PIN-NOTE | **ปฏิเสธ** | เขียนใหม่เป็นกฎจากโน้ตในแบบ ABS ("Mark Pin 1 Dot if not Molded") + remark ประกาศ `@` → ใส่ `@` ใน expected โดยไม่ดู Oracle |
| R04-SLR-LITERAL | **ปฏิเสธ** | compare แจ้งได้แค่ `ORACLE_VALUE_IN_SLR` → NEEDS_REVIEW ไม่ใช่ MATCH |
| R06-SHIFT | อนุมัติ compare-only | — |
| R07-PLACEHOLDER | อนุมัติ compare-only มีเงื่อนไข | lot ต้องตรง `lot_slice` ของ Scheduled Lot ID; date code ต้องเป็น YYWW ที่ถูกรูปแบบ; ไม่งั้น NEEDS_REVIEW |
| R07-DB-PACKAGE | อนุมัติ compare-only | — |
| R03-ONE-ABS | **ปฏิเสธ** | แทนด้วย Document Resolver (03) |
| R04-SLR-QUAL | อนุมัติเป็น consistency check | ไม่สร้างค่า; แค่ทำให้เข้มขึ้น |

ผู้อนุมัติที่บันทึก: `owner-delegated (Kam) 2026-11-04` — แนะนำให้ Mark Eng ทบทวนตารางนี้อีกครั้งในช่วง shadow mode

## ยังเปิด

| ID | เรื่อง | ทำไมสำคัญ | เจ้าของ |
|---|---|---|---|
| D-07 | คำตอบที่ถูกของ 20 โฟลเดอร์ multi-ABS / 41 multi-SLR | golden test ของ resolver | Mark Eng |
| D-16 | ELR measurable: 531 (`elr_document`) vs 529 (run 2) vs 470 (run 3) | ตัวหาร regression — Phase 1 ใช้ตัวหารจาก Oracle (plan Task 12) | ผู้พัฒนา (Phase 1) |

### ปิดแล้วรอบ 3 (2026-11-04)

| ID | ตัดสิน |
|---|---|
| D-15 | ✔ เจ้าของปิด session อื่นแล้ว; R0 ยังยึด run 3 + commit `d7d788e` |
| D-19 | ✔ (ผู้พัฒนาตัดสินตาม delegation) `mark_engine` ใช้ spec v2: ขาด SLR → `HOLD:SLR_NOT_FOUND` แม้ `CUST_REQ_NO` ว่าง; PIN-NOTE คง REJECTED (D-06). ส่วนต่างจาก run 3 ติด reason code `GATE_SPEC_V2` ใน parity report |
| D-20 | ✔ repo `mark-web` ใช้ remote `git@github.com:Pariman1419/Markweb.git` (branch `phase0/readiness` push แล้ว); repo `mark` branch `phase0/regression-r0` **ไม่ push** (มีภาพแบบลูกค้า) |
| D-21 | ✔ `Symbol ADI.xlsx` sha256 `7858dc405a90b6600389accf32fa257ad23580cd532cda078da2f02cfe74ccb6` — ใช้เป็นค่าตรวจใน plan Task 7 |

## Open — R1 Jan–Jun (2026-11-04)

ไม่มีข้อค้าง — D-22, D-23 ปิดแล้วด้านล่าง

### ปิดแล้วรอบ 4 (2026-11-04, Mark Eng ตอบ [09](09-mark-eng-confirmation.md))
| ID | คำตัดสิน |
|---|---|
| D-22 | ✔ ชื่อประเทศแบบย่อใน Oracle ที่ยังอ่านเป็น THAILAND (`TH`, `THA`, `THAI`, `THAIL`, …) = **MATCH แต่มี warning** ให้ผู้ใช้เห็นว่าต่างจากชื่อเต็ม (`LineComparison.warning = "COO_ABBREVIATED: Oracle THAIL, expected THAILAND"`, metrics `warning_lines`) — R1: 13 บรรทัด |
| D-27 | ✔ (ผู้ใช้ 2026-11-04) HUMAN_FIXED ที่เป็น OCR อ่านผิด → แก้ที่ OCR: ใช้ re-OCR ครอปแคบ (legend value / ตัดโลโก้) แบบไม่ใช้ GT; ADI2602089 TOP 5 (`0.0` vs Oracle `O.0`) แก้ด้วย OCR ไม่ได้ — ในภาพเป็นตัวเดียวกัน |
| D-25 | ✔ (ผู้ใช้ 2026-11-04) concept งาน = ตรวจจับแล้วแจ้งให้ user แก้: revision ไม่ตรง (`REVISION_MISMATCH`) และ PRODUCT_NO ชี้ ABS คนละเลข (`PRODUCT_NO_ABS_MISMATCH`) → NEEDS_REVIEW พร้อมสาเหตุใน `review_detail` (ไม่นับเป็น MATCH) |
| D-26 | ✔ (ผู้ใช้ 2026-11-04) บรรทัดที่มีรีวิวเก่า (`mark/experiments/abs_vs_db/review/diff_review_*.csv`) → ใช้คำตัดสินนั้นเป็น `final_status` (DB_WRONG / HUMAN_FIXED / MATCH) หลัง compare; `status` ของระบบไม่เปลี่ยน (agreement, independence, parity ใช้ค่าระบบ) |
| D-24 | ✔ (ผู้ใช้ 2026-11-04) revision ใน Oracle อาจแยกเก็บ: ตัวอักษรท้าย `CUST_BOM_NO` + `CUST_BOM_REVISION` (`ABS034529D` + `ENG-1`) = ไฟล์ `ABS034529D-ENG-1` → นับว่าตรงกัน |
| D-23 | ✔ `CUST_BOM_REVISION` ขัดกับ revision ใน `PRODUCT_NO` → **`HOLD:REVISION_CONFLICT`** ให้คนตรวจ พร้อมสาเหตุใน `hold_detail` (ไม่เดาว่า rev ไหนถูก); ใช้เมื่อทั้งสองค่าเป็น revision ตัวอักษร (`ENG-1` vs `B-ENG-1` ไม่นับ) — R1: ADI2606077/078. Oracle ที่ผิดให้รายงานเป็น error พร้อมสาเหตุ (ระบบไม่แก้ Oracle เอง) |
