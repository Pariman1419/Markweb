# Mark Automation — Phase 2 Trial (ผู้ใช้ทดลองใช้คนเดียว) · Design

วันที่: 2026-11-05 · ปรับจาก [`2026-11-04-phase1-completion-and-phase2-design.md`](2026-11-04-phase1-completion-and-phase2-design.md) §4 (B1–B7)
และ schema ใน [`2026-11-04-mark-automation-design.md`](2026-11-04-mark-automation-design.md) §13

ป้าย: **[ผู้ใช้]** = ผู้ใช้ตัดสิน · **[Claude]** = Claude ตัดสินเอง ผู้ใช้ตรวจได้

---

## 1. ทำเพื่ออะไร

ผู้ใช้ (Mark Engineer) เปิดหน้าเว็บทดลองใช้เองก่อนคนอื่น **[ผู้ใช้]** โดยใช้ผลรันชุด ก.ค.–พ.ย. หลังแก้ overflow
(commit `dd57846`, coverage 254/402, agreement 1,019/1,127) แทนหน้า HTML local ที่ใช้รีวิวอยู่ตอนนี้
คือ Dashboard → ค้นหา ELR → ELR Preview → บันทึกเหตุผล / ค่าที่ถูกต้อง → Approve

นี่คือ B1 + B2 ของแผนเดิม ย่อให้พอสำหรับผู้ใช้คนเดียว ส่วน B3–B7 (polling อัตโนมัติ, inference API, LLM, notification, shadow mode)
ยังเป็นแผนเดิม ไม่ทำในรอบนี้

## 2. สิ่งที่เปลี่ยนจากแผนเดิม

| เรื่อง | แผนเดิม (B1–B2) | รอบนี้ |
|---|---|---|
| ข้อมูลที่แสดง | ผล blind test (run 17) | ผลหลังแก้ overflow โหลดเป็น **run ใหม่** (ข้อ 3 T0) — run 17 คงไว้เป็น baseline |
| ตาราง `mark_app` | 17 ตารางตาม spec หลัก §13 | เฉพาะที่หน้าเว็บใช้ตอนนี้ 6 ตาราง (ข้อ 4) — ที่เหลือมากับ B3–B6 |
| ผลรายบรรทัด | `mark_app.draft_line` | อ่านจาก `mark_logic.line_result` / `job_result` ของ run ที่เลือก (มีอยู่แล้ว, migration 0004) **[Claude]** |
| Service | 10 microservices | FastAPI app เดียว แยก router ตาม service (Mark / Validation / Workflow / Auth) เพื่อแยกเป็น service ได้ภายหลัง **[Claude]** |
| Gateway / Redis | Kong/NGINX + Redis | NGINX อย่างเดียว · ไม่ใช้ Redis (ไม่มี queue ในรอบนี้) **[Claude]** |

## 3. งาน

| # | งาน | เสร็จเมื่อ |
|---|---|---|
| T0 | **โหลด run สำหรับทดลองใช้**: engine `0.3.0`, รันชุด ก.ค.–พ.ย. ด้วยโค้ดหลัง `dd57846` แบบ `--allow-unfrozen` แล้วโหลดเป็น run ใหม่ (note ระบุ commit และว่า "debug replay หลังรีวิว overflow ไม่ใช่ holdout") · **ไม่ทำ FREEZE-R2 รอบนี้ [Claude]**: inference cache ผูกกับ freeze 0.2.0 (`run_blind` ปฏิเสธ freeze ใหม่) และ freeze มีไว้สำหรับ holdout ครั้งหน้า | run ใหม่ใน DB, run 1–17 ไม่ถูกแตะ |
| T1 | **Migration 0005 `mark_app`** (ข้อ 4) + สิทธิ์: role `mark_app` เขียนได้เฉพาะ `mark_app`, อ่าน `mark_logic` | migration ผ่านบน `mark_web`; DOWN แยกไว้ |
| T2 | **Snapshot loader**: จาก artifacts ของ run (`oracle/elr_meta.json`, `mark_layout.json`, `cache/images_index.csv` + ภาพ, SLR ที่ engine ใช้) → `mark_app.elr_snapshot` + คัดลอกภาพ ABS ไปที่เก็บไฟล์ของ app (`MARK_FILES_ROOT`) | ทุก ELR ของ run มี snapshot; ภาพเปิดได้ |
| T3 | **API (FastAPI)** `services/api/` (ข้อ 5) | endpoint ครบ, login ได้ |
| T4 | **Web (React + TS + Vite)** `web/`: Dashboard + ELR Preview + Review/Approve (ข้อ 6) | ผู้ใช้ใช้งานครบ flow บนเครื่อง dev |
| T5 | **Deploy** บน 10.153.90.17: Docker Compose (`api`, `web` = NGINX เสิร์ฟไฟล์ + proxy `/api`) อ่านค่าลับจาก `.env` | เปิดจากเครือข่ายภายในได้ |

ลำดับ: T0 → T1 → T2 → T3 → T4 → T5 (T3/T4 ทำคู่ได้หลัง T1)

## 4. Database — `mark_app` (ชุดย่อยของ spec หลัก §13)

| ตาราง | เก็บ | หมายเหตุ |
|---|---|---|
| `app_user` | username, display_name, role (`engineer`/`mark_eng_approver`/`admin`), password_hash (argon2), active, failed_count, locked_until | ผู้ใช้คนแรกสร้างด้วย script (ไม่มีหน้าสมัคร) |
| `user_session` | token hash, user_id, expires_at | อายุสั้น (8 ชม.) **[Claude]** |
| `elr_snapshot` | (run_id, elr_no) PK, top_mark_id, layout_code, mark_remark, mark_require, top_template_remark, oracle_top_raw (TOP_MARK1–5 ดิบ 21 ช่อง), layout_cells (jsonb 5×18), abs_file, abs_sha256, image_path, slr_files, slr_instructions (jsonb: line, value, quote), import_date | ค่า Oracle ณ เวลารัน — หน้าเว็บไม่ดึง Oracle สด **[ผู้ใช้]** |
| `line_review` | id, run_id, elr_no, line_no, reason (DB wrong · OCR wrong · Symbol wrong · SLR / ECN change · Rule missing · Layout wrong · Other), note, corrected_mark, reviewer_id, created_at, is_draft | เก็บทุกครั้ง (ไม่ทับ) — แถวล่าสุดคือค่าปัจจุบัน |
| `approval` | id, run_id, elr_no, decision (APPROVED / REJECTED), user_id, created_at | |
| `audit_log` | id, user_id, action, target (run_id/elr_no/line_no), detail jsonb, created_at | ทุก login / review / approve |

ไม่เขียน `mark_logic` และไม่เขียน Oracle **[ผู้ใช้]**

## 5. API (`services/api/`, FastAPI, REST, prefix `/api`)

| Router (= service ในแผนภาพ) | Endpoint |
|---|---|
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| Mark | `GET /runs` · `GET /elrs?run=&month=&result=&cause=&q=` (ตาราง + ค้นหา ELR/ABS/SLR) · `GET /elrs/{elr}?run=` (snapshot + lines + reviews) · `GET /files/abs/{run}/{elr}` (ภาพ) |
| Validation | `GET /dashboard?run=` (การ์ด 4 ใบ, รายเดือน, สาเหตุ Error / HOLD) |
| Workflow | `POST /reviews` (บันทึกร่าง/เหตุผล/ค่าที่ถูกต้อง) · `POST /approvals` |

กฎฝั่ง server **[ผู้ใช้ จาก spec เดิม §4.4]**: Approve ไม่ผ่านถ้ามีบรรทัด Error ที่ยังไม่มีเหตุผล + ค่าที่ถูกต้อง · ทุก endpoint ต้อง login
· ตรวจ path ของไฟล์ภาพให้อยู่ใต้ `MARK_FILES_ROOT` เท่านั้น

**การจัดกลุ่ม True / Warning / Error / HOLD [Claude — ผู้ใช้ตรวจ]** (ระดับบรรทัด TOP)

| กลุ่ม | สถานะใน `line_result` |
|---|---|
| True | MATCH, MATCH_SLR, MATCH_LOT ที่ไม่มี warning |
| Warning | MATCH* ที่มี warning (CASE_DIFF, COO_ABBREVIATED, LAYOUT_*), MATCH_SHIFT, NEEDS_REVIEW |
| Error | DIFF, DB_EMPTY, NOT_MARKED + job FAILED |
| HOLD | job HOLD (นับระดับ ELR) |

NOT_ELIGIBLE / NOT_MEASURABLE / NOT_COMPARABLE ไม่นับในการ์ด แสดงในตารางเป็น "ไม่ได้เทียบ"

## 6. หน้าเว็บ (ตาม mockup ร่าง 5–6 ใน spec เดิม §4.4 — TOP เท่านั้น)

- **Login**
- **Dashboard**: เลือก run · การ์ด True / Warning / Error / HOLD (จำนวน + % + สาเหตุหลัก) · กราฟแท่งรายเดือนซ้อนสี ·
  กราฟสาเหตุ Error / HOLD กดแล้วกรองตาราง · ค้นหา + ตาราง ELR → กดเข้า Preview
- **ELR Preview**: ซ้าย = ระบบสร้าง (ภาพ ABS กดขยาย, SLR ที่ใช้, ตาราง ACTIVEL 21 ช่อง × 5 บรรทัด, ที่มา/กฎ/warning ต่อบรรทัด)
  ขวา = Oracle (MARK_ID + layout code, MARK_REMARK, MARK_REQUIRE, TOP_TEMPLATE_REMARK, ตาราง 21 ช่องจาก TOP_MARK1–5)
  · สี: ขาว = มีตัวอักษร, ฟ้า = ช่องที่ layout สงวน/เว้น, แดง = ระบบกับ Oracle ต่างกัน
  · ฟอร์มต่อบรรทัด (เหตุผล, โน้ต, ค่าที่ถูกต้อง) · ปุ่ม บันทึกร่าง / Approve / Reject

## 7. Test **[ผู้ใช้: ไม่ test ซ้ำซ้อน]**

- ไม่เขียน test ซ้ำกับ `mark_engine` (มี 306 test แล้ว) — API แค่อ่านผลที่ engine เขียนไว้
- Test เฉพาะ logic ใหม่: การจัดกลุ่ม True/Warning/Error/HOLD, กฎ Approve, login/lock/session, path guard ของไฟล์ภาพ
- API: test ต่อ endpoint ด้วย repo ปลอมในหน่วยความจำ (ไม่ต้องมี DB ทดสอบ) **[Claude]** · Web: `tsc` + `vite build` ผ่าน ไม่ทำ unit test UI
- เกณฑ์รับจริง = ผู้ใช้ลองใช้ flow ครบบนข้อมูลจริง

## 8. เกณฑ์รับงาน

- ตัวเลขการ์ด Dashboard ตรงกับ `metrics.json` ของ run เดียวกัน
- ตาราง 21 ช่องของ Oracle ใน Preview ตรงกับ `TOP_MARK1–5` ดิบ; ฝั่งระบบตรงกับ `expected_mark`
- บันทึก review / approve แล้วอยู่ใน `mark_app` + `audit_log`; ไม่มีการเขียน `mark_logic` หรือ Oracle
- ภาพ ABS และข้อมูลลูกค้าเปิดได้เฉพาะในเครือข่ายภายใน, ไม่มีรหัสผ่านใน repo

## 9. ไม่ทำรอบนี้

Airflow DAG / polling (B3), inference API (B4), LLM / pgvector (B5), notification / config / audit viewer (B6), BOTTOM,
holdout ใหม่ (รอข้อมูล พ.ย. ครบเดือน / ธ.ค.), Kong, Redis, การจัดการ user ผ่านหน้าเว็บ

## 10. ให้ผู้สร้างตัดสินเอง

ไลบรารีกราฟ / UI kit, โครงไฟล์ใน `services/api` และ `web`, รูปแบบ session (cookie HttpOnly หรือ bearer), วิธีคัดลอกภาพ,
พอร์ต, ชื่อ run note
