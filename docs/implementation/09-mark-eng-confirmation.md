# 09 — คำถามให้ Mark Engineer ยืนยัน (จาก R1 Jan–Jun)

> สถานะ: **รอคำตอบ** · สร้าง 2026-11-04 จาก R1 `cb9b74e` (DB `mark_web.mark_logic` run 5) · ผลรายบรรทัด: `artifacts/regression-r1/lines.csv`
> คำตอบที่ได้ให้บันทึกใน `07-open-decisions.md` แล้วแก้โค้ด/กฎตามนั้น

---

## Q1. ชื่อประเทศแบบย่อใน Oracle (`THAIL`) ให้นับเป็น MATCH ได้หรือไม่

**สิ่งที่ระบบทำตอนนี้** (กฎ `R07-ADI1039-COO`, ขั้น compare — `mark_engine/compare/engine.py` step 3b)
- expected สร้างเป็นชื่อเต็ม `THAILAND` เสมอ ตาม ADI1039 §5.5.3 "full name when space allows"
- ถ้า Oracle เก็บเป็นตัวย่อที่ขึ้นต้นด้วย `THAILAND` ยาว ≥ 4 ตัว (`THAI`, `THAIL`, …, `THAILAN`) → **MATCH** โดยมี `compare_rules = R07-ADI1039-COO`, `detail = COO_ABBREVIATED`
- `THA`, `THAIX` หรือข้อความอื่น → DIFF
- R0 (legacy) ก็นับเป็น MATCH เช่นกัน (cause `MAPPING_RULE`)

**ข้อมูล**: 13 บรรทัด / 13 ELR — ทุกบรรทัดเป็น expected `THAILAND#` vs Oracle `THAIL#` (TOP 4)

| ELR | |
|---|---|
| ADI2601001 – ADI2601006 | 6 ELR, ABS066854 |
| ADI2604008 – ADI2604013 | 6 ELR |
| ADI2606038 | 1 ELR |

**คำถาม**
1. ตัวย่อ `THAIL` ใน Oracle ถูกต้องตามที่พิมพ์จริงบนชิ้นงานหรือไม่ (พื้นที่บรรทัดไม่พอสำหรับ `THAILAND#`)
2. เลือกการทำงาน:
   - **(a)** คงไว้: ตัวย่อ ≥ 4 ตัว = MATCH เสมอ (ปัจจุบัน)
   - **(b)** MATCH เฉพาะเมื่อ ABS/drawing ระบุตัวย่อหรือจำนวนตัวอักษร (เช่น `{CCCCC}`), นอกนั้น → NEEDS_REVIEW
   - **(c)** ไม่ยอมรับตัวย่อ → DIFF ทุกกรณี (แจ้งทีม Marking ให้แก้ Oracle)
3. ตัวย่อที่ยอมรับมีแบบอื่นอีกหรือไม่ (เช่น `THA`, `TH`)

---

## Q2. ADI2606077 / ADI2606078: Oracle ระบุ ABS rev B แต่ mark ที่บันทึกเป็นของ rev C

**สิ่งที่พบ**
- โฟลเดอร์ ELR มี ABS068387 สองฉบับ: **ABS068387B** และ **ABS068387C**
- Oracle `CUST_BOM_NO = ABS068387`, `CUST_BOM_REVISION = B` → ระบบเลือก **rev B** ตามกฎ revision (D-08)
- แต่ Oracle `PRODUCT_NO = ADMFS7201-ABS068387C-A` (ชี้ไปที่ **rev C**) และ TOP_MARK ที่บันทึกตรงกับ drawing rev C

| line | expected จาก rev B (R1) | Oracle TOP_MARK | ผล |
|---|---|---|---|
| 1 | `@% ADM` | `@% ADMF` | DIFF |
| 2 | `FS7201` | `S7201BCP` | DIFF |
| 3 | `BCPZA` | `ZA#YYWW` | DIFF |
| 4 | `#YYWW` | `XXXXXXXX` | DIFF |
| 5 | `XXXXXXXX` | `THAILAND` | DIFF |

- เทียบ: ADI2606035–037 (`CUST_BOM_REVISION = B`, `PRODUCT_NO = …-ABS068387B-A`) ใช้ภาพ rev B เดียวกัน → **MATCH ครบ 5 บรรทัด** — แปลว่าการอ่าน rev B ถูกต้อง
- R0 ได้ MATCH เพราะเลือก ABS ฉบับที่ตรงกับ Oracle มากที่สุด (`R03-ONE-ABS`, ถูก reject ใน D-06 เพราะใช้ Oracle เลือกเอกสาร)

| ELR | CUST_BOM_REVISION | PRODUCT_NO | IMPORT_DATE |
|---|---|---|---|
| ADI2606035 | B | ADMFS7201-ABS068387**B**-A | 2026-06-10 |
| ADI2606077 | B | ADMFS7201-ABS068387**C**-A | 2026-06-23 |
| ADI2606078 | B | ADMFS7201-ABS068387**C**-A | 2026-06-23 |

**คำถาม**
1. ADI2606077/078 ควรใช้ ABS068387 rev **C** ใช่หรือไม่ (`CUST_BOM_REVISION = B` ใน Oracle ผิด)
2. ถ้าใช่ — ให้ระบบทำอย่างไรเมื่อ `CUST_BOM_REVISION` ขัดกับ revision ใน `PRODUCT_NO`:
   - **(a)** HOLD ใหม่ `REVISION_CONFLICT` ให้คนเลือก (แนะนำ — ไม่เดา)
   - **(b)** เชื่อ revision ใน `PRODUCT_NO` ก่อน
   - **(c)** คงเดิม (เชื่อ `CUST_BOM_REVISION`) และรายงาน DIFF ให้ทีม Marking แก้ Oracle
3. ต้องแจ้งทีม Marking ให้แก้ `CUST_BOM_REVISION` ของ 2 ELR นี้ใน Oracle หรือไม่

---

## ช่องบันทึกคำตอบ

| Q | คำตอบ | ผู้ตอบ | วันที่ | Action |
|---|---|---|---|---|
| Q1 | | | | |
| Q2 | | | | |
