# 02 — Oracle ELR Field Mapping (read-only)

วันที่ตรวจ: 2026-11-04 · ต้นทาง: `ACTL` (`10.151.26.3:1521`, service `ACTL`, user `ACTLUSR`) ·
Oracle Database **10g EE 10.2.0.4** · เชื่อมด้วย python-oracledb thick mode (`Search_data/.tools/instantclient_21_13`)
เพราะ thin mode ไม่รองรับ 10g (`DPY-3010`) · ทุก query อยู่ใน `SET TRANSACTION READ ONLY` และเป็น SELECT เท่านั้น
(สคริปต์: scratchpad `ora_probe.py`, `ora_q2.py` — ไม่ได้บันทึกรหัสผ่านลงไฟล์)

ป้าย: **[ยืนยัน]** / **[สันนิษฐาน]**

---

## 1. ข้อค้นพบด้านความปลอดภัย — ต้องแก้ก่อนต่อระบบจริง

| # | ข้อค้นพบ | หลักฐาน |
|---|---|---|
| S-1 | **[ยืนยัน] `ACTLUSR` มีสิทธิ์ `INSERT`, `UPDATE`, `DELETE`, `SELECT` บน `ACTLDBA.ELR`** และ sys privilege `CREATE DATABASE LINK`, `CREATE VIEW`, `CREATE SYNONYM`, `UNLIMITED TABLESPACE` | `user_tab_privs`, `user_sys_privs` |
| S-2 | ข้อกำหนด "Oracle อ่านอย่างเดียว" จึงบังคับได้แค่ด้วยโค้ด ไม่ใช่ด้วยสิทธิ์ — ขัดกับ spec §16 และเกณฑ์รับงาน §18 ("ตรวจจาก user สิทธิ์อ่านอย่างเดียว") | — |
| S-3 | ตัวดึงเดิม (`Search_data/scripts/fetch-elr-marks-2026-h1.mjs`) ใช้อีกเส้นทาง: user `BSMUSER4` บน BSM `10.151.25.145` ผ่าน DB link `ACTLDBA.ELR@actl` — สิทธิ์ของ link นี้ยังไม่ได้ตรวจ | `fetch-elr-marks-2026-h1.mjs:4-9` |
| S-4 | รหัส `postgres` superuser ของ `mark_web` และ `actlusr` ถูกส่งผ่านแชทอีกครั้งใน session นี้ | — |

**ข้อเสนอ:** ขอ DBA สร้าง user ใหม่ (เช่น `MARK_RO`) ที่มีเฉพาะ `SELECT` บน `ACTLDBA.ELR`, `ACTLDBA.MARK_ID`,
`ACTLDBA.MARK_ID_LAYOUT`, `ACTLDBA.MARK_ID_SYMBOL` · ระหว่างรอ: adapter ใน `mark_engine` ต้อง (1) เปิด
`SET TRANSACTION READ ONLY` ทุก session (2) อนุญาตเฉพาะ statement ที่ขึ้นต้นด้วย `SELECT`/`WITH` (3) มี unit test ยืนยัน

## 2. โครงสร้างที่เกี่ยวข้อง **[ยืนยัน]**

- `ACTLDBA.ELR` — TABLE, 280 คอลัมน์, 1 แถวต่อ ELR (`count(*) = count(distinct elr_no)` = 1,070 สำหรับ `ADI26%`)
- `ELR_REV` = `'00'` ทุกแถวของ ADI26* → **ใช้ตรวจจับการเปลี่ยนแปลงไม่ได้**
- `LAST_DATE > MARK_DATE` ใน 519 / 1,070 แถว → ELR ถูกแก้หลัง Mark approve บ่อย ต้องตรวจจับด้วย hash ของฟิลด์
- ตารางที่เกี่ยวกับ Mark profile: `MARK_ID`, `MARK_ID_LAYOUT`, `MARK_ID_SYMBOL`, `MARK_ID_INSTRUC`, `MARK_ID_LEVEL`,
  `MARK_ID_LEVELCODE`, `MARK_ID_SPACE`, `MARK_ID_TYPEGROUP`, `MARK_ID_2DSPECIAL`
- **ไม่พบ**ตาราง dictionary ของ step (ค้น `%STEP%`, `%WORKFLOW%`, `%FLOW%` ใน ACTLDBA — ได้แต่ตาราง flow การผลิต)

## 3. Mapping ฟิลด์ที่ TO-BE Workflow ต้องใช้

คอลัมน์ "บทบาท" กำหนดว่าฟิลด์ใช้ได้ที่ไหน:
**GEN** = ใช้สร้าง expected_mark ได้ · **META** = ใช้เลือกเอกสาร/gate/แสดงผล ห้ามใช้สร้างข้อความ mark ·
**ORACLE_MARK** = ค่าที่จะถูกเทียบ ห้ามเข้าเส้นทางสร้าง · **TRIGGER** = ใช้ตรวจจับงาน/การเปลี่ยนแปลง

ค่าการเติม (non-null) จาก query `populated` — H1 = ADI2601–ADI2606 (668 แถว), JUL_NOV = ADI2607–ADI2611 (402 แถว)

| Workflow | ความหมาย | คอลัมน์ Oracle | บทบาท | non-null H1 / Jul–Nov | สถานะ |
|---|---|---|---|---|---|
| 01 | เลข ELR | `ELR.ELR_NO` | META | 668 / 402 | **[ยืนยัน]** |
| 01 | ขั้น Mark Eng Review | **`CURRENT_STEP = '6'`** (+ `STATUS`, `MARK_APPROVE`, `MARK_DATE`, `MARK_NAME`) | TRIGGER | 668 / 402 (step) · 611 / 348 (MARK_APPROVE) | **[ยืนยัน — เจ้าของ + `mark/ActiveL_Mark V2.sql:28-38`]** step: 1 CS Review · A QA Review · 2 Engineering Review · 3 MC review · 4 Engineering lot Center · 5 PC Reserve · 6 Mark Eng review · 7 Generate Order. ตอนตรวจไม่มี ADI อยู่ step 6 (สถานะชั่วคราว) → poll ถี่ + รอบเก็บตกจาก step 7 ตาม `MARK_DATE` |
| 01 | ตรวจการเปลี่ยนแปลง | `LAST_DATE`, `LAST_USER` + hash ฟิลด์ที่ใช้ | TRIGGER | 668 / 402 | **[ยืนยัน]** `ELR_REV` ใช้ไม่ได้ |
| 01 | Mark ที่ Engineer คีย์ | `TOP_MARK1..5`, `BACK_MARK1..5` | **ORACLE_MARK** | TOP_MARK1 607 / 334 · BACK_MARK1 77 / 28 | **[ยืนยัน]** |
| 01 | หมายเหตุ Mark | `MARK_REMARK`, `MARK_REQUIRE` | GEN (เฉพาะที่เป็นคำสั่ง/การประกาศสัญลักษณ์) | 605 / 323 · 368 / 180 | **[ยืนยัน]**; spec §1 อนุญาต; แต่กฎที่แปลง remark → รหัส เป็น ORACLE_DERIVED (01 §3) |
| 02 | Cust Assy | `CUST_ASSY_LOT` | META (+ GEN สำหรับ lot ถ้า ADI1039 กำหนด) | 661 / 399 | **[ยืนยัน]** ตัวอย่าง `7548478.1`, `WBDOE` |
| 02 | Cust Eng Req. / เลข SLR | `CUST_REQ_NO` | META → **กุญแจหา SLR** | 573 / 357 | **[ยืนยัน]** ค่าเป็นเลข SLR เช่น `SLR246826` (ADI2610001/003) |
| 03 | ABS / BOM | `CUST_BOM_NO`, `CUST_BOM_REVISION` | META → **กุญแจหา ABS + revision** | 663 / 399 | **[ยืนยัน]** เช่น `ABS071457` + `ENG-1`; มีค่า `N/A` (ADI2610002/004/005) |
| 05 | Product No. | `PRODUCT_NO` | META | 660 / 399 | **[ยืนยัน]** |
| 05 | Package | `PACKAGE_CODE` | META | 646 / 381 | **[ยืนยัน]** |
| 06 | Mark ID | `TOP_MARK_ID`, `BACK_MARK_ID` | META | 607 / 334 · 77 / 28 | **[ยืนยัน]** |
| 06 | Layout Code | `TOP_LAYOUT_CODE`, `BACK_LAYOUT_CODE` | META (gate `≠ ZY`) | 603 / 333 | **[ยืนยัน]** Jul–Nov: ZA 65, ZI 57, ZB 50, ZE 33, ZF 27, A 24, **ZY 23**, ZD 21, null 69 |
| 06 | Type Code | `MARK_ID.TYPE_CODE` (join `MARK_ID.MARK_ID = ELR.TOP_MARK_ID`) | META (gate `= 'E'`) | Jul–Nov: E 311 · P 23 · null 68 | **[ยืนยัน]** คอลัมน์อยู่ใน `MARK_ID` ไม่ใช่ `ELR` (join เดียวกับ `ActiveL_Mark V2.sql:55-57`) |
| 06 | MARK_ID_LAYOUT | `MARK_ID_LAYOUT(MARK_ID, MARK_ROW, MARK_COLUMN, MARK_DATA)` | **ORACLE_MARK-adjacent** | — | **[สันนิษฐาน]** เป็นแม่แบบ mark ฝั่ง Oracle → จัดเป็นค่าฝั่ง Oracle ห้ามเข้าเส้นทางสร้าง จนกว่า Mark Eng ยืนยันว่าเป็น spec |
| 07 | Symbol replace ของ Oracle | `MARK_ID_SYMBOL(MARK_ID, LINE_NO, SEARCH_SYMBOL, REPLACE_SYMBOL)` | ORACLE_MARK-adjacent | — | **[สันนิษฐาน]** เช่นเดียวกัน |
| — | ไม่มีข้อมูล | `MARK_SPEC`, `MARK_REV`, `CUST_TOP_MARK`, `CUST_BACK_MARK`, `SPECIAL_INSTRUCT_1`, `TOPMARK_IMAGE_PATH`, `DATE_CODE`, `CUST_DATE_CODE`, `PB_FREE`, `LOGO` | — | 0 / 0 | **[ยืนยัน]** ว่างทั้งหมดใน ADI26* — ห้ามออกแบบโดยพึ่งฟิลด์เหล่านี้ |
| — | ไฟล์นำเข้า | `IMPORT_FILE1` | META (อาจช่วยหาเอกสาร) | 401 / 242 | ค่ายังไม่ได้ตรวจ |

## 4. กติกาการใช้ฟิลด์ใน `mark_engine` (เสนอ)

1. Adapter Oracle คืนค่าเป็น 2 object แยกกัน: `ElrMeta` (META + GEN + TRIGGER) และ `OracleMark` (TOP/BACK_MARK1–5)
   — `ExpectedMarkGenerator` รับได้แค่ `ElrMeta` (บังคับด้วย type signature + test "ลบ oracle_mark แล้ว expected เท่าเดิม" spec §18)
2. `MARK_REMARK` / `MARK_REQUIRE` เข้า generate ได้ แต่กฎที่ map remark → รหัส (R07-REMARK-*) ยังเป็น ORACLE_DERIVED → ผลเป็น NEEDS_REVIEW จนอนุมัติ
3. `MARK_ID_LAYOUT` / `MARK_ID_SYMBOL` ไม่ถูกอ่านใน Phase 1
4. Snapshot ที่เก็บใน `mark_app.elr_snapshot` = ทุกคอลัมน์ในตารางข้อ 3 + `LAST_DATE` + sha256 ของ JSON ที่ normalize แล้ว

## 5. ช่องว่างระหว่าง Jan–Jun dataset กับ Oracle

| ตัวเลข | ค่า | ที่มา |
|---|---|---|
| ELR ADI2601–ADI2606 ใน Oracle (ณ วันนี้) | 668 | query `months` |
| ELR ใน JSON dump ที่ pipeline ใช้ | 598 | `mark_logic.run.elr_total` |
| โฟลเดอร์ NAS ที่สำเนา | 602 (รวม range folder/โฟลเดอร์ "Cancle") | `elr_document` |
| ELR ที่ `measurable` | 531 ใน `elr_document` vs 529 ใน `run.elr_measurable` | ความต่าง 2 ยังไม่ทราบสาเหตุ **[ต้องตรวจ]** |

70 ELR ใน Oracle ไม่อยู่ใน dump (ส่วนหนึ่งยังเป็น `CURRENT_STEP = '1'` ที่ยังไม่มี mark) — ตัวหาร Coverage ใน spec §18
(529/602) จึงไม่ใช่ "ELR ทั้งหมดใน Oracle" ต้องนิยามตัวหารใหม่ (06)
