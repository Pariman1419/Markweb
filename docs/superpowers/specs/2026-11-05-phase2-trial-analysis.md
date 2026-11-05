# Phase 2 Trial — วิเคราะห์ design และแผน

วันที่: 2026-11-05 · ตรวจ [`2026-11-05-phase2-trial-design.md`](2026-11-05-phase2-trial-design.md) (§1–18) และ
[`../plans/2026-11-05-phase2-trial.md`](../plans/2026-11-05-phase2-trial.md) (Task 1–6) โดยเทียบกับโค้ด, artifact และ DB จริง

ป้าย: **แก้แล้ว** = แก้ใน spec/plan แล้ว · **รอผู้ใช้** = ต้องให้ผู้ใช้ตัดสิน

---

## 1. สรุป

- **โครงโดยรวมใช้ได้** ลำดับ T0→T5 ต่อกันได้จริง ขอบเขตแคบพอสำหรับผู้ใช้คนเดียว และกฎหลักไม่ขัดกัน: ไม่เขียน Oracle/`mark_logic`, ไม่ทับ run เดิม, independence
- **ถ้าทำตามแผนเดิม จะติด 4 จุด (ข้อ 3)**:
  - ตัวโหลด DB ปฏิเสธ run ที่ไม่ freeze
  - ข้อมูลบางคอลัมน์ไม่มีใน DB
  - ชื่อคอลัมน์ไม่ตรง
  - test ของ engine จะพัง 1 ตัวเมื่อเปลี่ยนเวอร์ชัน
- **ไม่สอดคล้องกันเอง 9 จุด (ข้อ 4)**: rate limit, cache header, metrics หลาย worker, เกณฑ์รับงาน, คีย์ของ review, สิทธิ์ DB ฯลฯ
- ทั้ง 13 จุดแก้ใน spec/plan แล้ว
- **รอผู้ใช้ตัดสิน 3 เรื่อง (ข้อ 6)** เพราะคำตอบเปลี่ยนสิ่งที่จะสร้าง

## 2. ข้อเท็จจริงที่ตรวจแล้ว (จาก `artifacts/blind-2026h2/run-overflowfix`, DB 2026-11-05)

| เรื่อง | ค่าจริง | ผลต่อแผน |
|---|---|---|
| Jobs | 402: DONE 368, HOLD 34 (BOM_NOT_FOUND 22, SLR_NOT_FOUND 8, NO_FOLDER 2, REVISION_CONFLICT 1, SLR_CONFLICT 1), FAILED 0 | การ์ด HOLD = 34 |
| บรรทัด TOP | 1,304: MATCH 909, MATCH_SLR 69, MATCH_LOT 2, NEEDS_REVIEW 100, DB_EMPTY 37, DIFF 4, NOT_MEASURABLE 107, NOT_ELIGIBLE 76 | ได้ค่าคาดหวังของการ์ด (ข้อ 4 M4) |
| Warning | MATCH 99, MATCH_SLR 15, NEEDS_REVIEW 63 บรรทัดมี warning | |
| ภาพ ABS | 287 / 402 ELR มีภาพ (1 ภาพต่อ ELR), รวม 13 MB | 115 ELR ต้องแสดง "ไม่มีภาพ ABS" |
| ABS ต่อ ELR | 1 (`jobs.csv.abs_no`) | review หา `abs_no` จาก job ได้ |
| SLR | 271 ไฟล์ที่ `work/<elr>/extracted/<sha>/SLR*.pdf` · `work/` รวม 995 MB | loader อ่านได้ตาม glob ในแผน |
| `elr_meta.json` | `TOP_MARK1–5` ยาว 21 ตัวอักษร (A B C + 1–18) · `TOP_MARK_ID` เป็น float (`25077.0`) · `TOP_LAYOUT_CODE` | ต้องแปลงเป็น int |
| `mark_logic.line_result` | PK `(run_id, elr_no, abs_no, side, line_no)` · ค่าคาดหวัง = `final_mark`, Oracle = `db_mark`, สถานะ = `final_status` · **ไม่มีคอลัมน์ `compare_rules` / `flags` / `detail`**: loader รวมไว้ใน `cause_detail` เป็นข้อความ `rules=…; flags=…; detail=…` | ข้อ 3 B2, B3 |
| `scripts/load_r1_to_pg.py` | `is_blind = 'blind' in period or 'freeze' in metrics` แล้วตอน `--commit` บังคับ `FREEZE-R1` · `metrics.json` ของ run unfrozen มี `freeze: {freeze_id: 'UNFROZEN'}` | ข้อ 3 B1 |
| `tests/unit/test_generator.py:255` | `assert expected.engine_version == "0.2.0"` | ข้อ 3 B4 |

## 3. จุดที่ทำให้แผนเดิมติด **[แก้แล้ว]**

| # | ปัญหา | ผลถ้าไม่แก้ | แก้อย่างไร |
|---|---|---|---|
| B1 | Loader มองว่า run ที่มี key `freeze` เป็น blind ทุกครั้ง แม้ค่าเป็น `UNFROZEN` | Task 1 Step 3 `--commit` จะ error "Blind commit requires an official frozen run" | Task 1 แก้ loader ให้ `is_blind = freeze_id == 'FREEZE-R1' or 'blind' in period` + test 1 ตัว · run ใหม่จะได้ note แบบไม่ใช่ blind |
| B2 | `compare_rules` / `flags` / `detail` ไม่มีใน DB เป็นคอลัมน์ | Preview แสดง "ที่มา / กฎ" ต่อบรรทัดไม่ได้ ถ้าแยกจาก `cause_detail` ก็เปราะ | snapshot loader เก็บ `line_extra` jsonb `{line_no: {compare_rules, flags, detail}}` จาก `lines.csv` ลงใน `elr_snapshot` |
| B3 | แผนใช้ชื่อ `expected` / `oracle` / `status` | SQL ผิด | Repo map `final_mark → expected`, `db_mark → oracle`, `final_status → status` |
| B4 | เปลี่ยนเวอร์ชันเป็น 0.3.0 แล้ว test เดิมพัง | Task 1 Step 1 ได้ 305/306 ไม่ใช่ 306 | แก้ test ให้อ่านจาก `ENGINE_VERSION` |

## 4. ความไม่สอดคล้องใน design / แผน **[แก้แล้ว]**

| # | ปัญหา | แก้ |
|---|---|---|
| M1 | Rate limit `login` burst 5 ถ้าไม่ใส่ `nodelay` NGINX จะ **หน่วง** request ไม่ใช่ปฏิเสธ · ขั้นตรวจ "ครั้งที่ 6 ได้ 429" ผิด | ใส่ `nodelay` ทุก zone · ขั้นตรวจเป็น "ยิงติดกัน 7 ครั้ง ครั้งที่ 7 ได้ 429" (1 + burst 5 ผ่าน) |
| M2 | NGINX ใส่ `Cache-Control: no-store` ที่ `/api/` จะทับ header cache ของภาพ (§18) · และ `add_header` ใน `location` ย่อยจะไม่สืบทอด header ความปลอดภัยจากชั้นบน | แยก `location /api/files/` (zone `files`, ไม่ใส่ no-store) · ใส่ security header ผ่าน `include security_headers.conf` ในทุก location |
| M3 | §18 ใช้ uvicorn 2 worker แต่ `/api/metrics` เป็นตัวนับในหน่วยความจำ จึงเห็นแค่ worker เดียว | รอบทดลองใช้ **1 worker** (ผู้ใช้คนเดียว และยังอยู่ในเป้าเวลา) · ขยาย worker เมื่อย้าย metrics ไปเก็บร่วมกัน (B6) |
| M4 | เกณฑ์รับงานบอกว่า "การ์ดตรงกับ `metrics.json`" แต่ `metrics.json` นับทั้ง TOP+BOTTOM และไม่มีกลุ่ม Warning | เทียบกับ TOP ใน `lines.csv` ที่จัดกลุ่มด้วย `classify_line` · ค่าคาดหวัง (ถ้า engine 0.3.0 ให้ผลเท่า `run-overflowfix`): **True 866 · Warning 214 · Error 41 · HOLD 34 ELR · ไม่ได้เทียบ 183** |
| M5 | `POST /reviews` ไม่ส่ง `abs_no` / `side` แต่ FK ของ `line_review` ต้องใช้ | server ใส่ `side='TOP'` และ `abs_no` จาก `job_result` เอง (ข้อมูลจริงมี 1 ABS ต่อ ELR) |
| M6 | `TOP_MARK_ID` เป็น float | Task 2 แปลงเป็น int · test มี `25077.0 → 25077` |
| M7 | API ต่อ DB ด้วย user ไหนไม่ได้ระบุ (loader ใช้ `postgres`) | API ใช้ role `mark_app` (มีจาก 0001) · DBA ตั้งรหัสใน Task 1 Step 6 · `.env` มี `MARK_PG_USER=mark_app` · script admin (loader, create user) ใช้ user แยก |
| M8 | Approve ELR ที่เป็น HOLD ได้ ทั้งที่ไม่มีค่าคาดหวัง **[Claude]** | `POST /approvals` APPROVED กับ HOLD ตอบ 409 `{reason:'HOLD'}` · Reject ได้ (บันทึกว่าตรวจแล้ว) |
| M9 | Review Focus บอกว่า "ผิด 5 ครั้งล็อก" ทดสอบใน Task 3 แต่ test นั้นตรวจแค่สถานะ ไม่ได้ตรวจการนับ (การนับอยู่ใน Repo) | เพิ่ม route test `test_five_failures_lock`: ผิด 5 ครั้ง แล้วครั้งที่ 6 ใส่รหัสถูกยังได้ 423 |

## 5. ที่ตรวจแล้วไม่มีปัญหา

- ลำดับงานและ dependency: Task 2 ต้องมี run_id จาก Task 1 · Task 3 เป็น pure function ไม่ต้องมี DB · Task 4 ใช้ repo ปลอม · Task 5 ใช้แค่ endpoint
- Independence: `elr_snapshot` เก็บ `TOP_MARK1–5` ไว้แสดงอย่างเดียว ไม่ป้อนเข้า engine
- Big-O: ข้อมูลจริง (1,304 บรรทัด, 402 ELR) ต่ำกว่าขนาดที่ออกแบบไว้ (50k / 10k) มาก · query ทุกตัวใช้ PK ที่ขึ้นต้นด้วย `(run_id, elr_no)`
- Auth / cookie / CSRF / CORS ไม่ขัดกัน: `mark_csrf` Path=/ อ่านได้จากหน้าเว็บ, `mark_session` Path=/api, same-origin จึงไม่ต้องมี CORS
- Test ไม่ซ้ำกับ engine: test ใหม่ทุกตัวตรวจโค้ดใหม่เท่านั้น (รวม 29 ตัว: core 9, snapshot 3, routes 16, loader 1)

## 6. การตัดสินใจ

- **ข้อ 1 [ผู้ใช้ 2026-11-05]: รีวิวใหม่ทุก run** — review / approve ผูกกับ `run_id` ไม่ตามไป run ใหม่ (ทางเลือก ก)
- **ข้อ 2 [Claude — ค่าเริ่มต้น ผู้ใช้ยังไม่ตอบ]:** DB_EMPTY คงเป็น Error ตาม spec §5 · ถ้าเปลี่ยนแก้ที่ `classify_line` จุดเดียว
- **ข้อ 3 [Claude — ค่าเริ่มต้น ผู้ใช้ยังไม่ตอบ]:** รอบทดลองใช้ HTTP ภายใน (`MARK_COOKIE_SECURE=false`) · ใส่ HTTPS ได้ทีหลังโดยไม่ต้องแก้โค้ด

คำถามเดิม:

1. **Review จะตามไปที่ run ใหม่ไหม** — engine ยังเปลี่ยนอยู่ ถ้าโหลด replay ครั้งถัดไปเป็น run ใหม่ review / approve ที่ทำไว้ผูกกับ `run_id` เดิม จะไม่ขึ้นใน run ใหม่
   ทางเลือก: (ก) ผูกกับ run ตามเดิม · (ข) ถ้า ELR + บรรทัดเดียวกันและ `expected` / `oracle` ไม่เปลี่ยน ให้แสดง review เดิมใน run ใหม่ (เปลี่ยนแล้วขึ้นว่า "ต้องรีวิวใหม่")
2. **DB_EMPTY (37 บรรทัด: Oracle ว่าง แต่ระบบสร้างค่าได้) นับเป็น Error หรือ Warning**
3. **มี certificate สำหรับ HTTPS ภายในไหม** — ถ้าไม่มี รอบทดลองจะส่งรหัสผ่านผ่าน HTTP ในเครือข่ายภายใน และ cookie ไม่มี `Secure`

## 7. ความเสี่ยงที่เหลือ

| ความเสี่ยง | ป้องกัน |
|---|---|
| Replay ด้วย 0.3.0 ได้ผลไม่เท่า `run-overflowfix` | Task 1 Step 2 เทียบ `lines.csv` สองชุด ต้องเหมือนกัน (เปลี่ยนแค่เวอร์ชัน) |
| เครื่อง 10.153.90.17 ไม่มี Docker หรือต่อ 10.151.28.2:5432 ไม่ได้ | Task 6 เพิ่มขั้นตรวจก่อนเริ่ม (`docker compose version`, `pg_isready`) |
| `work/` ใหญ่ 995 MB | loader อ่านเฉพาะ `SLR*.pdf` และไม่คัดลอก `work/` ขึ้นเซิร์ฟเวอร์ (คัดลอกแค่ภาพ 13 MB) |
