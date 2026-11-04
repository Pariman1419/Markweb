# 03 — NAS Document Resolver: Audit + Design

วันที่: 2026-11-04 · ป้าย **[ยืนยัน]** / **[สันนิษฐาน]**

## 1. การเข้าถึง NAS

**[ยืนยัน] เครื่อง/บัญชีที่ใช้ตรวจเข้า `\\th1srnas03\ELR\ADI\ELR Online 2026` ไม่ได้** (`Access is denied` ทั้งใน sandbox
และนอก sandbox) — การตรวจทั้งหมดในเอกสารนี้ทำบน**สำเนา** `D:\CIM Project\mark\1_JAN … 6_JUN` (602 โฟลเดอร์) เท่านั้น
ข้อสรุปเกี่ยวกับโครงสร้าง NAS เดือน ก.ค.–พ.ย. จึงเป็น **[สันนิษฐาน]** ทั้งหมด

## 2. Audit การหาเอกสารในโค้ดปัจจุบัน

| เรื่อง | โค้ดทำอย่างไร | ปัญหา | หลักฐาน |
|---|---|---|---|
| หาโฟลเดอร์ ELR | `glob('[1-6]_*', 'ADI*')`, ELR_NO = `basename(folder)` | Range folder `ADI2603011-14`, `ADI2603055-56` ถูกนับเป็น ELR ชื่อแปลก; ELR จริง ADI2603011–014, 055–056 ได้ "no ELR folder" → NOT_MEASURABLE; โฟลเดอร์ `ADI2605073 Cancle` ก็เช่นกัน | `mapping_gap_analysis.py:450-453`; `elr_document` มีแถว `ADI2603011-14 (has_abs, no slr)` |
| ช่วง Jan–Apr | `build_compare.py:74-86 parse_job()` รองรับ range `ADI2603011-14` และ `\` | ใช้คนละตรรกะกับ gate → ผลไม่สอดคล้องกัน | `build_compare.py:74` |
| ชนิดเอกสาร | prefix ชื่อไฟล์ `ABS*` / `SLR*` + `.PDF` | ไม่แยกจากเนื้อหา; `SLR*.zip` 354 ไฟล์ถูกละ; TRS ที่ชื่อ ABS* จะถูกใช้ | `mapping_gap_analysis.py:451-452` |
| หลาย ABS | เลือกไฟล์ที่ "match Oracle มากสุด" | **Oracle เลือกเอกสาร** (R03-ONE-ABS) | `mapping_gap_analysis.py:33-36` |
| หลาย SLR | ต่อข้อความ special instructions ทุกไฟล์เข้าด้วยกัน | SLR เก่า/ใหม่ปนกัน; คำสั่งขัดกันไม่ถูกตรวจ | `mapping_gap_analysis.py:56` `slr[elr] = slr.get(elr,'') + ' ' + s` |
| BOM | `CUST_BOM_NO.startswith(abs_no[:9])` | ใช้เป็นป้ายสาเหตุ ไม่ใช่ gate; โฟลเดอร์ ABS เดียว + BOM ไม่ตรง ยังใช้ต่อ | `build_compare.py:160-161` |
| Revision | ไม่มี | ไม่มีการอ่าน revision | — |

### สถิติจากสำเนา ม.ค.–มิ.ย. **[ยืนยัน]**

| รายการ | ค่า |
|---|---|
| โฟลเดอร์ | 602 |
| โฟลเดอร์ที่มี ABS > 1 ไฟล์ | 20 |
| โฟลเดอร์ที่มี SLR > 1 ไฟล์ | 41 |
| ไฟล์ตามชนิด (prefix) | ABS*.pdf 626 · SLR*.pdf 577 · SLR*.zip 354 · E-MAIL*.pdf 442 · ADI*.pdf 105 · ASSY 29 · MOM 18 · อื่น ๆ |
| รูปแบบชื่อ ABS | `ABS066854A.pdf` (ตัวอักษร rev), `ABS065710-ENG-2.pdf` (ENG-n) |
| Revision ในเนื้อหา ABS หน้า 1 | ตัวอย่าง 40 ไฟล์: **ไม่พบ** pattern `REV/REVISION/ECN` ใน text layer — ตำแหน่ง revision ในเนื้อหายังไม่ทราบ (spec §19) |
| SLR หน้า 1 | มีป้าย `Request Date` (ตัวอย่าง SLR230684–686) |

### ข้อมูลจาก Oracle ที่ช่วย resolver **[ยืนยัน]** (ดู 02)

- `CUST_BOM_NO` + `CUST_BOM_REVISION` (เช่น `ABS071457` / `ENG-1`) — รูปแบบ revision ตรงกับชื่อไฟล์ `-ENG-n`
- `CUST_REQ_NO` = เลข SLR (เช่น `SLR246826`) — ใช้เลือก SLR ได้ตรงตัว แทนการเดา

## 3. ออกแบบ Document Resolver (สำหรับ `mark_engine.documents`)

หลักการ: **ไม่มีขั้นใดใช้ TOP/BACK_MARK** · ไม่ใช้ mtime/ชื่อไฟล์ "ล่าสุด" · ทุกการตัดสินบันทึก reason code ·
ตัดสินไม่ได้ → `HOLD` (ไม่เดา)

```
ElrMeta ─┐
NAS scan ─┼─> 1 Locate ─> 2 Fingerprint ─> 3 Classify ─> 4 Match ─> 5 Revision ─> 6 Conflict ─> Resolution
          │   (folders)    (sha256,unzip)   (content)     (BOM/SLR)  (select)     (HOLD?)
```

| ขั้น | อินพุต | กติกา | ผลเมื่อไม่ผ่าน |
|---|---|---|---|
| 1 Locate | ELR_NO, `IMPORT_DATE` | ค้นใน `ELR Online <yyyy>\<n>_<MON>\` ของเดือน import และเดือนข้างเคียง ±1; โฟลเดอร์ที่ตรงเมื่อ (ก) ชื่อ = ELR_NO (ข) ชื่อเป็น range `ADIyymmNNN-MM[M]` ที่ครอบ ELR_NO (ค) ชื่อขึ้นต้น ELR_NO + ข้อความ (เช่น `Cancle`) → ติดธง `FOLDER_ANNOTATED` | ไม่พบ → `HOLD:NO_FOLDER` |
| 2 Fingerprint | ไฟล์ในโฟลเดอร์ | sha256 ต่อไฟล์; แตก `.zip` (จำกัดขนาด/จำนวน, ไม่ follow path นอกโฟลเดอร์) แล้ว fingerprint ไฟล์ข้างใน; sha256 ซ้ำ = ไฟล์เดียว | zip เสีย → `HOLD:ARCHIVE_ERROR` |
| 3 Classify | text layer หน้า 1–2 (OCR ถ้าไม่มี text) | ABS: มีเลข `ABS\d{6}` + หน้า "Brand/Marking"; SLR: มี `SPECIAL INSTRUCTIONS` และ/หรือ `Scheduled Lot ID`; TRS: rule ที่ต้องได้ตัวอย่างจริงก่อน **[สันนิษฐาน]**; อื่น ๆ = `OTHER` | ชนิดไม่ชัด (เข้าเกณฑ์ >1 ชนิด) → `HOLD:DOC_TYPE_AMBIGUOUS`; พบ TRS → `HOLD:TRS_OUT_OF_SCOPE` |
| 4 Match | `CUST_BOM_NO`, `CUST_REQ_NO` | ABS: เลข ABS ในเนื้อหา = `CUST_BOM_NO` (6 หลักแรก); SLR: เลข SLR ในเนื้อหา/ชื่อ = `CUST_REQ_NO` เมื่อ Oracle มีค่า; ถ้า `CUST_REQ_NO` ว่าง → SLR ที่อ้าง ELR_NO หรือ Cust Assy lot ในเนื้อหา | ไม่มี ABS ที่ตรง → `HOLD:BOM_NOT_FOUND`; `CUST_BOM_NO = 'N/A'` → `HOLD:BOM_MISSING_IN_ORACLE`; ไม่มี SLR → `HOLD:SLR_NOT_FOUND` (= R03 gate) |
| 5 Revision | ABS ที่ผ่านข้อ 4 | อ่าน revision จาก**เนื้อหา** (ตำแหน่งรอยืนยัน); เทียบกับ `CUST_BOM_REVISION` ใน Oracle; เลือก revision ที่ = `CUST_BOM_REVISION` ถ้ามี ไม่งั้นสูงสุดที่ effective ≤ วันประมวลผล; ชื่อไฟล์ใช้เป็นหลักฐานรองเท่านั้น | อ่าน revision ไม่ได้ และมี >1 ABS → `HOLD:REVISION_UNREADABLE`; revision เนื้อหา ≠ ชื่อไฟล์ → `REVIEW:REVISION_NAME_MISMATCH`; revision Oracle = ตัวอักษรท้าย `CUST_BOM_NO` + `-` + `CUST_BOM_REVISION` (D-24); `CUST_BOM_REVISION` ≠ revision ใน `PRODUCT_NO` → `HOLD:REVISION_CONFLICT` + `hold_detail` (D-23) |
| 6 Conflict | ABS/SLR ที่เหลือ | revision เท่ากันแต่ sha256 ต่าง → `HOLD:SAME_REV_DIFFERENT_CONTENT`; SLR >1 ฉบับที่คำสั่ง marking ต่างกัน → `HOLD:SLR_CONFLICT`; SLR >1 ฉบับคำสั่งเหมือนกัน → ใช้ทั้งหมด บันทึกเป็น `MERGED_IDENTICAL` | — |

### Output (`DocumentResolution`)

```json
{
  "elr_no": "ADI2610001",
  "decision": "RESOLVED | HOLD",
  "hold_reason": null,
  "abs": {"sha256": "…", "nas_path": "…", "abs_no": "ABS071457", "revision": "ENG-1", "revision_source": "content|filename"},
  "slr": [{"sha256": "…", "slr_no": "SLR246826", "request_date": "…"}],
  "rejected": [{"sha256": "…", "path": "…", "doc_type": "ABS", "reason": "REVISION_SUPERSEDED"}],
  "steps": [{"step": "match", "rule": "ABS_NO_EQ_CUST_BOM_NO", "result": "pass", "evidence": "…"}],
  "resolver_version": "0.1.0"
}
```

เก็บใน `mark_app.document_resolution` (05) — ทั้งไฟล์ที่ถูกเลือก ถูกตัด และเหตุผลทุกขั้น

## 4. ผลต่อ regression Jan–Jun **[สันนิษฐาน]**

Resolver ใหม่จะเปลี่ยนชุด ELR ที่ measurable (range folder ได้รับการนับ, SLR.zip ถูกอ่าน, ABS เลือกด้วย BOM/revision
แทน Oracle) → **ตัวเลข regression จะไม่เท่าเดิม และไม่ควรเท่าเดิม** — ใช้เป็นเหตุผลให้แยก baseline เป็น
"legacy parity" กับ "corrected" (06)

## 5. Test strategy ของ resolver

- Fixture เป็นโฟลเดอร์จำลอง (ไฟล์ PDF ขนาดเล็ก + zip) ครอบ: ELR ปกติ, range folder, `Cancle`, ABS 2 revision, ABS rev เดียว
  เนื้อหาต่าง, SLR 2 ฉบับขัดกัน, SLR ใน zip, ไม่มี SLR, TRS ปลอมที่ชื่อ `ABS*.pdf`, `CUST_BOM_NO = N/A`
- Property: ผล resolver ไม่ขึ้นกับลำดับไฟล์และ mtime (สลับ/แก้ mtime แล้วผลต้องเท่าเดิม)
- Golden test: 20 โฟลเดอร์ multi-ABS + 41 multi-SLR ใน ม.ค.–มิ.ย. → ให้ Mark Eng ตัดสินคำตอบที่ถูก (07 · D-07)
