# Mark Automation — ปิด Phase 1 และ Phase 2 (ระบบใช้งานจริง) · Design

วันที่: 2026-11-04 · ต่อจาก [`2026-11-04-mark-automation-design.md`](2026-11-04-mark-automation-design.md) (spec หลัก) และ
[`docs/implementation/10-r1-logic-review-and-next-phase.md`](../../implementation/10-r1-logic-review-and-next-phase.md)

ป้าย: **[ผู้ใช้]** = ผู้ใช้ตัดสิน · **[Claude]** = Claude ตัดสินเอง ผู้ใช้ตรวจได้ · **[สันนิษฐาน]** = ยังไม่ยืนยัน

---

## 1. ทำเพื่ออะไร

User (Mark Engineer / Reviewer / Approver) เปิดระบบเพื่อดูว่า mark ที่คนกรอกมือลง Oracle / ACTIVEL ตรงกับที่ระบบสร้างจาก
ABS + SLR หรือไม่ ดูภาพรวมทั้งหมดใน Dashboard แล้วค้นหา ELR ที่จะรีวิว ดู preview ผลและสาเหตุ (root cause)
แก้ค่าที่ถูกต้องและ Approve ได้ในหน้าเดียว **[ผู้ใช้]**

Phase 1 (engine offline) ผ่านเกณฑ์แล้ว (parity BUG 0, independence 100%, run 14) แต่ยังวัดได้แค่ชุด ม.ค.–มิ.ย.
ที่ใช้ปรับกฎ และยังไม่มีระบบให้ user ใช้ เอกสารนี้วางแผน 2 ส่วนต่อกัน:

- **ส่วน A: ปิด Phase 1** — วัดความแม่นจริงด้วย blind test ก.ค.–พ.ย. และเก็บงานค้าง
- **ส่วน B: Phase 2** — ระบบใช้งานจริงตาม architecture ที่ผู้ใช้ออกแบบ (ข้อ 4)

## 2. สถานะที่เปลี่ยนวันนี้ (2026-11-04)

| เรื่อง | เดิม (spec หลัก §19) | ตอนนี้ |
|---|---|---|
| Oracle `ACTL` (10.151.26.3:1521, user ACTLUSR) | อ่าน `MARK_ID_LAYOUT` / `INSTRUC` / `SYMBOL` / `PROD_MARKLAYOUT` ผ่าน `@actl` ไม่ได้ (ORA-00942) | ต่อตรงด้วย python-oracledb **thick mode** (Oracle 10g, Instant Client `Search_data/.tools/instantclient_21_13`) อ่านได้ทั้ง 4 ตาราง |
| NAS `\\th1srnas03\ELR\ADI\ELR Online 2026` | Access denied | เปิดได้ด้วยบัญชีที่ผู้ใช้ให้ มีโฟลเดอร์ 1_JAN … 11_NOV |

รหัสผ่านอยู่ใน `.env` (ignored) และอ่านผ่าน env เท่านั้น (`ACTL_*`, `NAS_*`, `MARK_PG_PASSWORD`)
ไม่อยู่ใน git / memory / log **[ผู้ใช้ 9.3]** · รหัสถูกส่งผ่านแชท → ควรเปลี่ยนก่อนขึ้นระบบจริง (spec หลัก §16)

### 2.1 `MARK_ID_LAYOUT` คืออะไร

คอลัมน์: `MARK_ID, MARK_ROW, MARK_COLUMN, MARK_DATA` — 1 แถวต่อ 1 ช่องของตาราง ACTIVEL (ROW 1–5 × COLUMN 1–18)

ตัวอย่าง MARK_ID 21355 (ADI2601023 TOP, `TOP_MARK1='   ^ Y'`, `TOP_MARK2='     Q1'`):
- ROW 1: COL 1 = `^`, COL 2 = ช่องว่าง, **COL 3–4 ไม่มีแถว**, COL 5–18 = ช่องว่าง
- ROW 2: COL 1–2 = ช่องว่าง, **COL 3–4 ไม่มีแถว**, COL 5–18 = ช่องว่าง
- ROW 3: มีทุกช่อง (ว่าง)

**[สันนิษฐาน]** ช่องที่มีแถว = ค่าคงที่ของ template (ล็อกไว้, เช่นโลโก้ `^`); ช่องที่ไม่มีแถว = ช่องที่ต้องกรอกต่อ ELR
(`Y`, `Q1` ตรงกับ COL 3–4 พอดี) · TOP_MARKn ใน ELR มี 3 ตัวแรกเป็นช่อง A B C แล้วตามด้วย COLUMN 1–18
→ ต้องยืนยันกับ MARK_ID อื่นอีกอย่างน้อย 20 ตัวก่อนใช้ (งาน A2)

---

## 3. ส่วน A — ปิด Phase 1

| # | งาน | ทำไม | เสร็จเมื่อ |
|---|---|---|---|
| A1 | **Rule freeze** — ติด tag rule version (กฎ D-01…D-29 + `logic_rule` ปัจจุบัน) | blind test ห้ามแก้กฎระหว่างวัด (spec หลัก §17) | git tag + `rule_version` hash ใน DB run |
| A2 | **Layout จาก `MARK_ID_LAYOUT`** — อ่าน template ของ TOP_MARK_ID, วาง expected ลงช่องที่ต้องกรอก, ยืนยันข้อ 2.1 | preview ต้องบอกได้ว่าใส่ช่องไหนเว้นช่องไหนแบบ ACTIVEL **[ผู้ใช้]** และตอนนี้ระบบเทียบแบบไม่สนช่องว่าง | snapshot layout ใน DB, รายงานจำนวนบรรทัดที่ตำแหน่งต่าง (เป็น **Warning** ไม่เปลี่ยนสถานะเดิม **[Claude]**) |
| A3 | **Blind test ก.ค.–พ.ย. 2026** — ดึง ELR จาก Oracle + เอกสารจาก NAS, รัน OCR/YOLO (โมเดลเวอร์ชันเดียวกับ R1), รัน engine ด้วยกฎที่ freeze | วัดความแม่นบนข้อมูลที่ไม่เคยใช้ปรับกฎ | DB run ใหม่ (run_id ใหม่, ไม่ทับ run 1–14) + metrics ตาม spec หลัก §18 แยก Coverage / Hold / Agreement |
| A4 | **Migrations 0001–0003** + คอลัมน์จริง `final_status`, `review_detail`, `warning`, `system_status` แทนการยัดใน `cause_detail` | ให้ Phase 2 อ่านได้ตรง ๆ | migration รันบน DB dev, run 14 โหลดซ้ำได้ผลเดิม |
| A5 | **ส่งกฎ D-22…D-29 ให้ Mark Eng อนุมัติ** → `logic_rule` (`approval_status`) | กฎ oracle_derived ห้าม MATCH_ALL ถ้ายังไม่อนุมัติ (spec หลัก §18) | รายการกฎ + ผลอนุมัติใน DB |
| A6 | **Debug G1–G9** (doc 10 §6) | ผู้ใช้ให้เก็บไว้ทำทีหลัง | หลัง blind test (ข้อ 9.2) — แก้แล้วได้ rule version ใหม่ ไม่ทับผล blind test |
| A7 | **รายการส่งทีม Marking**: DB_WRONG 17 + config alert 183 บรรทัด (G7–G8) | ข้อมูล Oracle ผิดต้องให้ทีม Marking แก้เอง (ระบบไม่เขียน Oracle) | CSV ส่งได้ |
| A8 | **Merge / push branch `phase1/mark-engine`** | รอผู้ใช้สั่ง | ผู้ใช้สั่ง |

ลำดับ **[ผู้ใช้ 9.2]**: A4 → A2 → A1 → A3 → A7 → A6 (debug ทีหลัง); A5 เดินคู่กันได้ตลอด

---

## 4. ส่วน B — Phase 2 ตาม architecture ของผู้ใช้ **[ผู้ใช้: แผนภาพ "Mark Automation – Microservices Architecture (Updated)"]**

### 4.1 เครื่องและหน้าที่

| เครื่อง | IP | ส่วนประกอบ |
|---|---|---|
| Airflow (TH1SRAPPDEV5) | 10.151.28.3 | Apache Airflow (มีอยู่แล้ว) — DAG ของ Mark |
| Dev / App | 10.153.90.17 | React (TS + Vite), API Gateway Kong/NGINX, microservices FastAPI ใน Docker, Redis (cache/queue) |
| AI Server | 10.151.28.9 | vLLM (Qwen 3.5 27B), LiteLLM (gateway + monitoring), PaddleOCR, YOLO, Qwen Embedding |
| DB Server | 10.151.28.2 | PostgreSQL + pgvector (`mark_web`) |

แหล่งข้อมูล (อ่านอย่างเดียว): Oracle ELR, NAS (ABS/SLR), `Symbol ADI.xlsx` → transform → DB, Historical Mark Data (approved cases)

### 4.2 Microservices

| Service | หน้าที่ | ใช้โค้ดที่มี |
|---|---|---|
| ELR Service | อ่าน ELR / snapshot จาก Oracle, ตรวจเงื่อนไข (CUST_CODE ADI, CURRENT_STEP 6, STATUS ≠ C) | `adapters/` ของ mark_engine |
| Document Service | หา / ตรวจเวอร์ชัน ABS / SLR บน NAS, เก็บสำเนา | `documents/resolve.py` |
| Rule Engine | กฎ ADI1039, Type E, SLR > REMARK > Symbol ADI > ADI1039 | `mark_engine` generate |
| Mark Service | สร้าง Mark Result + evidence ต่อบรรทัด | `mark_engine` pipeline |
| Validation Service | เทียบ expected vs Oracle, ตรวจข้อขัดแย้ง (revision, BOM, rule conflict) | `compare`, `review_detail` |
| Knowledge Service | SLR clause, vector, rule catalog (pgvector) | ใหม่ |
| Workflow Service | สถานะงาน 3 แกน / approve | ใหม่ (spec หลัก §6.1) |
| Notification Service | แจ้ง HOLD ฯลฯ | ใหม่ — ดูคำถาม 9.1 |
| Audit Service | trace / provenance | ใหม่ |
| Config Service | ค่าตั้ง, model version, rule version | ใหม่ |

**[Claude]** ทุก service ใช้ `mark_engine` เป็นไลบรารีเดียวกัน (ไม่ copy logic) — engine ที่ผ่าน parity ใน Phase 1 คือตัวที่รันจริง

### 4.3 Flow (E2E) **[ผู้ใช้]**

1 Airflow เตรียมข้อมูล (เอกสาร, OCR, index) → 2 User เลือก ELR (Mark Eng Review) → 3 Microservices ประมวลผล (Rule + LLM + Validation)
→ 4 สร้าง Mark Result พร้อม evidence → 5 Review / Edit / Approve → 6 เก็บผลและ audit ใน PostgreSQL

DAG ตาม spec หลัก §14 (`mark_elr_polling` 5 นาที, `mark_nas_document_sync` 15 นาที, `mark_pending_job_retry` 10 นาที,
`mark_document_reconciliation` 1 ชม., `mark_historical_symbol_index` รายคืน, `mark_daily_health_check` รายวัน) ·
Airflow เรียก API ไม่เขียนตารางเอง · กันงานซ้ำด้วย idempotency key (spec หลัก §15)

### 4.4 หน้าเว็บ **[ผู้ใช้: ยืนยันจาก mockup ร่าง 5–6]**

**ขอบเขตตอนนี้: TOP MARK เท่านั้น** — BOTTOM / BACK_MARK ระบบยังคำนวณ แต่ไม่แสดงและไม่นับในหน้า **[ผู้ใช้]**

**หน้า 1 Dashboard**
- การ์ดแยก 4 ใบ: True / Warning / Error / HOLD (จำนวน + % + สาเหตุหลัก)
- กราฟแท่งรายเดือนซ้อนสี True / Warning / Error
- กราฟสาเหตุ Error (บรรทัด) และสาเหตุ HOLD (ELR) — กดแล้วกรองตาราง
- ค้นหา ELR / ABS / SLR + ตาราง ELR (เดือน, ผล TOP, True/บรรทัด, สาเหตุ) → กดเข้าหน้า 2

**หน้า 2 ELR Preview**
- ซ้าย **ระบบสร้าง**: ภาพหน้า Brand/Marking ของ ABS (กดขยาย, กรอบบรรทัด), รายละเอียด SLR ที่ใช้, ตาราง ACTIVEL 21 ช่อง (A B C + 1–18) × 5 บรรทัด, ที่มาของค่าแต่ละบรรทัด
- ขวา **Oracle / ACTIVEL**: MARK_ID + layout code, `MARK_REMARK`, `MARK_REQUIRE`, `TOP_TEMPLATE_REMARK`, ตาราง 21 ช่องจาก `TOP_MARK1–5`
- สี: ขาว = มีตัวอักษร, ฟ้า = เว้น/ไม่ใช้ (ตาม `MARK_ID_LAYOUT`), แดง = ระบบกับ Oracle ต่างกัน
- **แก้ไข / อนุมัติ [ผู้ใช้]**: ช่องค่าที่ถูกต้องต่อบรรทัด, เหตุผล (DB wrong · OCR wrong · Symbol wrong · SLR / ECN change · Rule missing · Layout wrong · Other) + โน้ต, ปุ่ม Approve / Reject / บันทึกร่าง · บรรทัด Error ต้องมีเหตุผล + ค่าที่ถูกต้องก่อน Approve · STALE ปิดปุ่ม Approve · บันทึกใน `mark_web` เท่านั้น ไม่เขียน Oracle

หน้าอื่นตามแผนภาพ (ELR Queue, Evidence Viewer) ใช้โครงเดียวกัน · ข้อมูลทุกหน้าอ่านจาก PostgreSQL ที่ระบบรันเก็บไว้ ไม่ดึง Oracle สดตอนเปิด **[ผู้ใช้: ETL ผ่าน Airflow]**

### 4.5 ลำดับสร้าง Phase 2 **[Claude]**

สร้างเป็นชิ้นที่ใช้งานได้จริงทีละชิ้น ไม่สร้างครบ 10 service ก่อนแล้วค่อยต่อ:

| ขั้น | สิ่งที่ได้ | ใช้ได้เมื่อ |
|---|---|---|
| B1 | `mark_app` schema (job, job_revision, elr_snapshot, document, draft_line, line_review, approval, audit_log, app_user) + Login | migration ผ่าน |
| B2 | Mark/Validation/Workflow API (FastAPI) อ่านผล run → **Dashboard + ELR Preview + Review/Approve** บนผล blind test (A3) | user ใช้รีวิวผล blind test ได้ — นี่คือ shadow mode ช่วงแรก |
| B3 | ELR Service + Document Service + DAG `mark_elr_polling` / `mark_nas_document_sync` → job อัตโนมัติ | ELR ใหม่ใน step 6 ขึ้นหน้าเว็บเองภายใน 15–20 นาที |
| B4 | Inference service บน AI Server (`/v1/page`, `/v1/rec`, `/v1/symbols`, `/health`) + retry / health DAG | ไม่ต้องรัน OCR offline |
| B5 | Knowledge Service (pgvector, SLR clause) + LLM ผ่าน LiteLLM สำหรับประโยค SLR ที่ regex ไม่รู้จัก | ข้อเสนอ LLM เป็น REVIEW เสมอ |
| B6 | Notification, Config, Audit viewer, reconciliation / historical DAG | — |
| B7 | Shadow mode 1–2 เดือน → ใช้เป็นหลัก | เกณฑ์ข้อ 6 ผ่าน |

---

## 5. ข้อจำกัด

- Oracle อ่านอย่างเดียว ทุก session `SET TRANSACTION READ ONLY`, SELECT เท่านั้น · Oracle 10g ต้อง thick mode
- ห้ามแก้ `D:\CIM Project\mark` (R0) · ห้ามทับ DB run 1–14 และ `logic_rule` เดิม — รันใหม่ได้ run_id ใหม่
- ไม่มีรหัสผ่านใน repo · ภาพ ABS ของลูกค้าไม่ publish ออกนอกเครือข่าย (หน้าเว็บอยู่บน 10.153.90.17 ภายใน)
- `expected_mark` สร้างโดยไม่อ่าน TOP_MARK (independence 100% ต้องคงอยู่)
- ทุกการแก้ไข → อัปเดต `HANDOFF.md` §4 และ `docs/qa/QA_LOG.md` **[ผู้ใช้]**
- commit บน branch ของงาน, ไม่ push จนกว่าผู้ใช้สั่ง

## 6. เกณฑ์รับงาน

- ส่วน A: blind test ก.ค.–พ.ย. รายงาน Coverage, Hold Rate, Oracle agreement แยกกัน; parity BUG 0; independence 100%
- ส่วน B: False PASS = 0 ช่วง shadow mode (Engineer ยืนยันทุกบรรทัด) · ทุกบรรทัดใน Preview ย้อนกลับไปหาภาพ / กฎ / SLR / เวอร์ชันได้ · ไม่มีการเขียน Oracle

## 7. ไม่ทำ / ห้ามเกิด

- ไม่ทำ: แสดง / นับ BOTTOM ในหน้าเว็บรอบนี้, เขียนกลับ Oracle, แก้กฎระหว่าง blind test
- ห้ามเกิด: MATCH ทั้งที่ engineer แก้ค่า (False PASS), ELR ขาด ABS/SLR แต่ขึ้น True, รหัสผ่านหลุดใน repo / log

## 8. ให้ผู้สร้างตัดสินเอง

ชื่อไฟล์ / โครงแพ็กเกจของ service, ไลบรารีกราฟใน React, รูปแบบ API (REST), รายละเอียด migration, วิธี batch OCR สำหรับ A3
(ต้องใช้โมเดลเวอร์ชันเดียวกับ R1 และบันทึกเวอร์ชัน)

## 9. คำตอบผู้ใช้ (2026-11-04)

1. **Notification [ผู้ใช้]:** ยังไม่ส่ง Email / Teams — แจ้งผ่านหน้าจอ UI เท่านั้น (badge / รายการ HOLD) ตาม spec หลัก §11 · Notification Service ใน B6 ทำแค่ตาราง `notification` สำหรับหน้าจอ
2. **Debug G1–G9 [ผู้ใช้]:** ทำทีหลัง — blind test (A3) รันด้วยกฎ run 14 ที่ freeze (A1) ตรง ๆ · ลำดับส่วน A จึงเป็น A4 → A2 → A1 → A3 → A7 แล้วค่อย A6
3. **Credentials [ผู้ใช้]:** เก็บใน `.env` ที่ root ของ repo (อยู่ใน `.gitignore`) · `.env.example` มีแต่ชื่อตัวแปร · โค้ดอ่านผ่าน env เท่านั้น
