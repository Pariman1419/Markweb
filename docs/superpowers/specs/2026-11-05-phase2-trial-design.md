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
| ตาราง `mark_app` | 17 ตารางตาม spec หลัก §13 | เฉพาะที่หน้าเว็บใช้ตอนนี้ 7 ตาราง (ข้อ 4, PK/FK/index ข้อ 14) — ที่เหลือมากับ B3–B6 |
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

## 4. Database — `mark_app` (ชุดย่อยของ spec หลัก §13 · คีย์และ index ดูข้อ 14)

| ตาราง | เก็บ | หมายเหตุ |
|---|---|---|
| `app_user` | username, display_name, role (`engineer`/`mark_eng_approver`/`admin`), password_hash (argon2), active, failed_count, locked_until | ผู้ใช้คนแรกสร้างด้วย script (ไม่มีหน้าสมัคร) |
| `user_session` | token hash, user_id, csrf hash, expires_at, last_seen_at | ข้อ 11 |
| `api_token` | name, token_hash, scopes, expires_at, last_used_at, created_by | สำหรับ Airflow / monitor (ข้อ 11) |
| `elr_snapshot` | (run_id, elr_no) PK, top_mark_id, layout_code, mark_remark, mark_require, top_template_remark, oracle_top_raw (TOP_MARK1–5 ดิบ 21 ช่อง), layout_cells (jsonb 5×18), abs_file, abs_sha256, image_path, slr_files, slr_instructions (jsonb: line, value, quote), import_date | ค่า Oracle ณ เวลารัน — หน้าเว็บไม่ดึง Oracle สด **[ผู้ใช้]** |
| `line_review` | id, run_id, elr_no, abs_no, side, line_no, reason (DB wrong · OCR wrong · Symbol wrong · SLR / ECN change · Rule missing · Layout wrong · Other), note, corrected_mark, reviewer_id, created_at, is_draft | เก็บทุกครั้ง (ไม่ทับ) — แถวล่าสุดคือค่าปัจจุบัน |
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
holdout ใหม่ (รอข้อมูล พ.ย. ครบเดือน / ธ.ค.), Kong, Redis, WebSocket (B3), gRPC (B4), การจัดการ user ผ่านหน้าเว็บ

## 10. ให้ผู้สร้างตัดสินเอง

ไลบรารีกราฟ / UI kit, โครงไฟล์ใน `services/api` และ `web`, รูปแบบ session (cookie HttpOnly หรือ bearer), วิธีคัดลอกภาพ,
พอร์ต, ชื่อ run note

---

## 11. Token และ Auth **[Claude — ผู้ใช้ตรวจ]**

| ใช้กับ | แบบ | รายละเอียด |
|---|---|---|
| Web → API (คน) | **Session cookie แบบ opaque** (ไม่ใช้ JWT) | `mark_session` = random 32 byte (base64url) · `HttpOnly; SameSite=Strict; Path=/api` · ใส่ `Secure` เมื่อขึ้น HTTPS · DB เก็บเฉพาะ sha256 · หมดอายุ 8 ชม. นับจาก login หรือเมื่อไม่ใช้งานเกิน 60 นาที (`last_seen_at`) · logout = ลบแถว |
| กัน CSRF | Double-submit | login แล้ว set cookie `mark_csrf` (JS อ่านได้) · ทุก POST/PUT/DELETE ต้องส่ง header `X-CSRF-Token` ตรงกับ cookie · `Origin` ต้องเป็น host ของเว็บ |
| ระบบ → API (Airflow, health DAG, B3+) | **API token** (Bearer) | `Authorization: Bearer mk_<random>` · ตาราง `api_token` เก็บ sha256 + scopes (`metrics:read`, `jobs:write`) + วันหมดอายุ · สร้าง/ยกเลิกด้วย script · ไม่ใช้ session cookie |

ทำไมไม่ใช้ JWT: มี API ตัวเดียว และต้องยกเลิก session ได้ทันที (ล็อกบัญชี / logout) · opaque token + DB ง่ายกว่าและยกเลิกได้จริง

**Auth**
- รหัสผ่าน argon2id (ค่า default ของ `argon2-cffi`) ยาวอย่างน้อย 12 ตัว · ไม่มีหน้าสมัครหรือลืมรหัส · สร้างและ reset ด้วย script (admin)
- ใส่ผิด 5 ครั้งติดกันจะล็อก 15 นาที (`failed_count`, `locked_until`) · ตอบ 401 แบบเดียวกันทั้งกรณี "ไม่มี user" และ "รหัสผิด" · ตอบ 423 เมื่อถูกล็อก
- สิทธิ์ต่อ endpoint:

| role | อ่าน Dashboard / Preview | บันทึก review | Approve / Reject | `/api/metrics` |
|---|---|---|---|---|
| `engineer` | ✓ | ✓ | ✓ | |
| `mark_eng_approver` | ✓ | ✓ | ✓ | |
| `admin` | ✓ | | | ✓ |
| API token `metrics:read` | | | | ✓ |

## 12. Rate limit **[Claude]**

ทำที่ NGINX ด้วย `limit_req_zone` ต่อ IP (ไม่ต้องมี Redis) · เกินแล้วตอบ **429** และ log `rate_limited`

| Zone | Path | อัตรา | burst |
|---|---|---|---|
| `login` | `POST /api/auth/login` | 5 ครั้ง/นาที | 5 |
| `files` | `/api/files/` | 10 ครั้ง/วินาที | 20 |
| `api` | `/api/` อื่น ๆ | 20 ครั้ง/วินาที | 40 |

ชั้นที่ 2 ในแอป: ล็อกบัญชีตามข้อ 11 (กันการเดารหัสจากหลาย IP) · request body ใหญ่สุด 1 MB (`client_max_body_size`)

## 13. gRPC และ WebSocket **[ผู้ใช้ 2026-11-05: ทำรอบต่อไป]** (ออกแบบโดย Claude)

| | ใช้ที่ไหน | เมื่อไร |
|---|---|---|
| **REST/JSON** | Browser ↔ API ทั้งหมด (ข้อ 5) | รอบนี้ |
| **WebSocket** | `GET /api/ws`: server push event ให้หน้าเว็บ ได้แก่ `job.updated` (ELR ใหม่ / ประมวลผลเสร็จ / HOLD), `review.saved`, `approval.saved`, `notification.new` | **B3** (เมื่อ polling สร้าง job อัตโนมัติ) · รอบทดลองข้อมูลนิ่ง จึงยังไม่ทำ |
| **gRPC** | ใช้ภายในเท่านั้น: Mark API ↔ Inference Service บน AI Server (10.151.28.9) | **B4** · browser ไม่ใช้ gRPC |

**WebSocket (B3)**
- ยืนยันตัวตนด้วย session cookie ตอน handshake และตรวจ `Origin` · ไม่ใส่ token ใน URL
- ข้อความเป็น JSON `{type, run_id, elr_no, at, data}` · ส่งแค่ว่า "มีอะไรเปลี่ยน" แล้วหน้าเว็บดึงรายละเอียดผ่าน REST (ไม่ส่งข้อมูลลูกค้าทาง WS)
- แหล่ง event: PostgreSQL `LISTEN/NOTIFY` channel `mark_events` (ไม่ต้องมี Redis) · server ping ทุก 30 วินาที · client reconnect แบบ backoff
- จำกัด 3 connection ต่อ user

**gRPC (B4)**
- เหตุผลที่ใช้: ส่งภาพเป็น bytes ได้ตรง ๆ (ไม่ต้อง base64), stream ทีละภาพใน batch ใหญ่ได้ และสัญญา (proto) ตรวจชนิดข้อมูลทั้งสองฝั่ง
- ไฟล์ `proto/mark/inference/v1/inference.proto`:
  `service Inference { rpc Page(PageRequest) returns (PageResult); rpc Rec(stream RecRequest) returns (stream RecResult); rpc Symbols(SymbolsRequest) returns (SymbolsResult); }` พร้อม gRPC health checking มาตรฐาน
- ทุกผลตอบต้องมี `model_version` (ต้องบันทึกตามกฎ freeze)
- ความปลอดภัย: mTLS ระหว่างเครื่อง หรืออย่างน้อย API key ใน metadata `x-api-key` และเปิดพอร์ตให้เฉพาะ IP 10.153.90.17
- vLLM / LiteLLM ยังใช้ HTTP (OpenAI-compatible) ตามเดิม ไม่ห่อเป็น gRPC

## 14. Database: PK / FK / Index

ทุกตารางอยู่ใน schema `mark_app` · คอลัมน์เวลาใช้ `timestamptz` · ทำ FK ไป `mark_logic` ได้ เพราะ run และผลที่โหลดแล้วจะไม่ถูกลบ (ห้ามทับ run เดิม)

| ตาราง | PK | FK | Unique / Check | Index |
|---|---|---|---|---|
| `app_user` | `user_id bigint identity` | — | `unique(lower(username))` · check role ∈ 3 ค่า | (ใช้ unique) |
| `user_session` | `token_hash text` | `user_id → app_user on delete cascade` | — | `(user_id)`, `(expires_at)` สำหรับลบตัวที่หมดอายุ |
| `api_token` | `token_id bigint identity` | `created_by → app_user` | `unique(token_hash)` · `scopes text[]` | — |
| `elr_snapshot` | `(run_id, elr_no)` | `(run_id, elr_no) → mark_logic.job_result` | — | `(run_id, abs_file)` สำหรับค้นหา ABS · GIN trigram บน `elr_no`/`abs_file` เพิ่มเมื่อค้นหาช้า (ยังไม่ทำ) |
| `line_review` | `review_id bigint identity` | `(run_id, elr_no, abs_no, side, line_no) → mark_logic.line_result` · `reviewer_id → app_user` | check reason ∈ 7 ค่า · `side = 'TOP'` | `(run_id, elr_no, line_no, created_at desc)` สำหรับหาค่าล่าสุด |
| `approval` | `approval_id bigint identity` | `(run_id, elr_no) → mark_logic.job_result` · `user_id → app_user` | check decision ∈ 2 ค่า | `(run_id, elr_no, created_at desc)` |
| `audit_log` | `audit_id bigint identity` | `user_id → app_user` (null ได้ กรณี login ผิดด้วย user ที่ไม่มีอยู่) | — | `(created_at)`, `(run_id, elr_no)`, `(user_id, created_at)` |

- `line_review` อ้างคีย์เต็มของ `line_result` (รวม `abs_no`, `side`) เพราะ PK จริงคือ `(run_id, elr_no, abs_no, side, line_no)` (ตรวจจาก DB 2026-11-05)
- PK ของ `mark_logic.line_result` / `job_result` ขึ้นต้นด้วย `(run_id, elr_no)` อยู่แล้ว query ของ Dashboard / Preview จึงใช้ index นี้ได้ ไม่ต้องเพิ่ม index ใน `mark_logic`
- สถานะบรรทัดอ่านจาก `final_status` (ใช้ตั้งแต่ run 10) ไม่ใช่ `status`
- `audit_log`, `line_review`, `approval` เป็น append-only: role `mark_app` ได้แค่ `select, insert` (ไม่มี update/delete) · ส่วน `app_user`, `user_session`, `api_token` ได้ `update/delete`

## 15. Log และ Monitor **[Claude]**

แยกเป็น 2 อย่าง:
- `audit_log` (DB): หลักฐานทางธุรกิจ เก็บถาวร
- application log (ไฟล์): ใช้ monitor / debug เก็บ 14 วัน

**Application log**: JSON หนึ่งบรรทัดต่อ event ออก stdout แล้วเก็บด้วย Docker `json-file` (หมุนไฟล์ 20 MB × 10)

| field | ตัวอย่าง / หมายเหตุ |
|---|---|
| `ts`, `level`, `service` | `2026-11-05T10:00:01.234+07:00`, `INFO`, `mark-api` |
| `request_id` | รับจาก NGINX `X-Request-ID` (`$request_id`) ใช้โยง log ของ NGINX กับ API |
| `event` | `http.request`, `auth.login_ok`, `auth.login_failed`, `auth.locked`, `rate_limited`, `review.saved`, `approval.saved`, `db.error`, `db.slow_query` |
| `user_id`, `role` | ไม่ใส่ username / รหัสผ่าน / token |
| `method`, `route` (template เช่น `/api/elrs/{elr}`), `status`, `duration_ms`, `client_ip` | |
| `run_id`, `elr_no` | ใส่เมื่อเกี่ยวข้อง · **ไม่ log ค่า mark, ข้อความ SLR หรือ path ภาพ** |

NGINX access log ใช้ `log_format json` ด้วยฟิลด์ชุดเดียวกัน (`request_id`, `status`, `request_time`, `upstream_response_time`, zone ที่โดน limit)

**Endpoint สำหรับ monitor**
- `GET /api/health` → `{"status":"ok"}` (บอกว่า process ยังทำงาน ไม่ต้อง login)
- `GET /api/ready` → ตรวจ DB (`select 1`, timeout 2 วินาที) และ `MARK_FILES_ROOT` ว่าอ่านได้ → ตอบ 200 หรือ 503
- `GET /api/metrics` (admin หรือ token `metrics:read`) → JSON ตัวนับตั้งแต่ start: request แยกตาม status class, p50/p95 `duration_ms` ต่อ route, login สำเร็จ/ผิด/ล็อก, จำนวน 429, `db.error`, session ที่ active

**เกณฑ์เตือน** (B6 / `mark_daily_health_check` อ่านจาก `/api/ready` และ `/api/metrics` · รอบทดลองผู้ใช้ดูเองจาก log)

| เรื่อง | เกณฑ์ |
|---|---|
| ระบบล่ม | `/api/ready` ไม่ตอบ 200 |
| Error | 5xx เกิน 1% ของ request ใน 15 นาที |
| ช้า | p95 เกิน 1,000 ms (ไม่นับ `/api/files`) · query เกิน 500 ms → log `db.slow_query` |
| ความปลอดภัย | `auth.login_failed` เกิน 10 ครั้งต่อชั่วโมง · มี `auth.locked` · มี 429 บน zone `login` |

## 16. CORS และ security header **[Claude]**

**หลักคือ same-origin และไม่เปิด CORS**
- Production: หน้าเว็บกับ `/api` อยู่ origin เดียวกัน (NGINX เสิร์ฟ `dist/` และ proxy `/api` → `api:8000`)
- Dev: Vite proxy `/api` → `localhost:8000` ทำให้ browser เห็นเป็น origin เดียวกัน
- API จึง **ไม่ติดตั้ง `CORSMiddleware`** และไม่ส่ง header `Access-Control-Allow-*` เลย request จาก origin อื่นจึงถูก browser บล็อก
- ถ้าวันหน้าต้องให้ origin อื่นเรียก (เช่น dashboard ของทีมอื่น) ให้เปิดผ่าน env `MARK_CORS_ORIGINS` เป็นรายชื่อ origin แบบตรงตัว
  - ค่าเริ่มต้นว่าง = ปิด
  - ห้ามใช้ `*` ร่วมกับ `allow_credentials`
  - method ที่อนุญาต: `GET, POST`
  - header ที่อนุญาต: `Content-Type, X-CSRF-Token, X-Request-ID`
  - `max_age` 600
- CORS ไม่ได้กัน CSRF: การกันยังเป็น SameSite cookie + `X-CSRF-Token` + ตรวจ `Origin` ตามข้อ 11
- API token (Bearer) ใช้จากเครื่องต่อเครื่อง ไม่เกี่ยวกับ CORS
- WebSocket (B3): browser ไม่ใช้ CORS กับ WebSocket จึงต้องตรวจ `Origin` เองตอน handshake (ข้อ 13)

**Security header** (ตั้งที่ NGINX)

| Header | ค่า |
|---|---|
| `Content-Security-Policy` | `default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `same-origin` |
| `X-Frame-Options` | `DENY` |
| `Strict-Transport-Security` | ใส่เมื่อขึ้น HTTPS แล้วเท่านั้น (`max-age=31536000`) |
| `Cache-Control` | `no-store` สำหรับ `/api/` (ข้อมูลลูกค้า) · ยกเว้น `/api/files/` = `private, max-age=86400` + `ETag` = sha256 ของภาพ (ข้อ 18) · ไฟล์ static ที่มี hash ในชื่อ cache ได้ 1 ปี |

## 17. Cookie **[Claude]**

ระบบมี cookie แค่ 2 ตัว · ไม่มี cookie ติดตาม / analytics / third-party · ค่าที่เป็นความชอบส่วนตัวของหน้าเว็บ (filter, run ที่เลือก) เก็บใน `localStorage` ไม่ใช่ cookie

| Cookie | ค่า | HttpOnly | Secure | SameSite | Path | Domain | อายุ |
|---|---|---|---|---|---|---|---|
| `mark_session` | random 32 byte (base64url) · DB เก็บ sha256 | ✓ | เมื่อ HTTPS | `Strict` | `/api` | ไม่ใส่ (host-only) | `Max-Age=28800` (8 ชม.) |
| `mark_csrf` | random 32 byte · DB เก็บ sha256 ใน `user_session.csrf_hash` | ✗ (JS ต้องอ่านเพื่อใส่ header) | เมื่อ HTTPS | `Strict` | `/` (หน้าเว็บอยู่ที่ `/` จึงต้องอ่านได้) | ไม่ใส่ | `Max-Age=28800` |

**วงจรชีวิต**
- **Login สำเร็จ:**
  - ออก `mark_session` และ `mark_csrf` ใหม่ทุกครั้ง (กัน session fixation)
  - ถ้ามี session เดิมที่ browser ส่งมา ให้ลบแถวนั้นก่อน
- **ทุก request:**
  - หา session จาก sha256 แล้วตรวจ `session_valid` (8 ชม. / idle 60 นาที)
  - อัปเดต `last_seen_at` ไม่เกิน 1 ครั้งต่อนาที (ลดการเขียน DB)
  - ไม่ต่ออายุ cookie
- **Logout / หมดอายุ / ไม่ผ่าน:**
  - ลบแถวใน DB
  - ส่ง `Set-Cookie` ทั้ง 2 ตัวด้วย `Max-Age=0` (path เดิม)
  - ตอบ 401 แล้วหน้าเว็บพาไป `/login`
- **บัญชีถูกล็อก, reset รหัส หรือ `active=false`:** ลบ session ทั้งหมดของ user นั้น
- **CSRF:** cookie `mark_csrf` ต้องตรงกับ header `X-CSRF-Token` และ sha256 ของมันต้องตรงกับ `csrf_hash` ของ session เดียวกัน (ใช้ cookie ของ session อื่นไม่ได้)

**เมื่อขึ้น HTTPS**
- ใส่ `Secure` ให้ cookie ทั้ง 2 ตัว
- เปลี่ยนชื่อเป็น `__Host-mark_csrf` (บังคับ Secure, Path=/, ไม่มี Domain)
- `mark_session` คง `Path=/api` จึงใช้ prefix `__Secure-mark_session`
- ควบคุมด้วย env `MARK_COOKIE_SECURE=true`; ค่าเริ่มต้น false เพราะรอบทดลองเป็น HTTP ภายใน

**ห้าม:** ใส่ข้อมูลผู้ใช้ / role / ELR ใน cookie, ใช้ cookie แทน API token, ตั้ง `Domain=` ให้ใช้ร่วมกับ subdomain อื่น, log ค่า cookie

## 18. Performance และ Big-O **[Claude]**

**ขนาดข้อมูลที่ออกแบบไว้** (วัดจาก DB 2026-11-05)

| | ตอนนี้ | ออกแบบให้รับได้ |
|---|---|---|
| ELR ต่อ run (`J`) | 402 (ก.ค.–พ.ย.) ≈ 80 / เดือน | 10,000 (หลายปี) |
| บรรทัด TOP ต่อ run (`L`) | ~1,100–2,000 | 50,000 |
| `line_result` ทั้งตาราง (`N`) | 33,365 (17 run) | 5 ล้าน |
| บรรทัดต่อ ELR (`k`) | ≤ 5 ต่อ side (ค่าคงที่) | — |
| ผู้ใช้พร้อมกัน | 1 | 20 |

**ความซับซ้อนต่อ endpoint** (ทุก query ใช้ PK ที่ขึ้นต้นด้วย `(run_id, elr_no)` จึงไม่สแกนทั้งตาราง `N`)

| Endpoint | Query | เวลา | หน่วยความจำ | หมายเหตุ |
|---|---|---|---|---|
| `GET /dashboard` | 2 query: range scan ของ run เดียว | O(log N + L + J) ครั้งแรก · **O(1)** ครั้งต่อไป | O(L) ชั่วคราว | จัดกลุ่มใน Python ด้วย `classify_line` (ที่เดียว) · cache ผลต่อ `run_id` (LRU 8) เพราะผล run ที่โหลดแล้วไม่เปลี่ยน และ review ไม่เปลี่ยนการ์ด |
| `GET /elrs` | 2 query เดียวกับ dashboard (ใช้ cache แถวรวม) | O(J) กรอง + O(J log J) เรียง · **ส่งทีละหน้า 50 แถว** | O(J) | `q` ค้นหาแบบ substring O(J·m) ในหน่วยความจำ · ถ้า J > 50,000 ค่อยย้ายเป็น `ILIKE` + GIN trigram (ข้อ 14) |
| `GET /elrs/{elr}` | **4 query คงที่**: snapshot, job, lines, review ล่าสุด (`DISTINCT ON (line_no)` ใช้ index) | O(log N + k) | O(k) | ห้ามมี N+1 (ห้าม query ต่อบรรทัด) |
| `GET /files/abs/...` | 1 query snapshot | O(log N) + O(ขนาดภาพ) | O(1) — stream จากดิสก์ | `FileResponse` ไม่โหลดทั้งไฟล์เข้าหน่วยความจำ · `ETag` ทำให้เปิดซ้ำได้ 304 |
| `POST /reviews` | 1 insert + 1 audit | O(log N) | O(1) | |
| `POST /approvals` | 2 query (lines + latest reviews) + 2 insert | O(log N + k) | O(k) | `approve_blockers` O(k) |
| `POST /auth/login` | 1 select + update + insert | O(log U) + **argon2 ~50–150 ms (ตั้งใจให้ช้า)** | ~64 MB ต่อการ hash | เป็นเหตุผลหนึ่งที่จำกัด login 5/นาที (ข้อ 12) |
| ทุก request (session) | 1 select ตาม PK hash | O(log S) | O(1) | update `last_seen_at` ไม่เกินนาทีละครั้ง |
| `GET /metrics` | ไม่มี query | O(R · B log B) | O(R · B) | ring buffer เวลา 1,000 ค่าล่าสุดต่อ route (R ≈ 12) · คำนวณ p95 ตอนเรียกเท่านั้น |

**Snapshot loader (T2)**: O(J + I) แถว · insert ทีละ batch 500 (`execute_values`) · คัดลอกภาพ O(ขนาดรวม) และข้ามไฟล์ที่มี sha256 เดิมอยู่แล้ว (รันซ้ำแล้วไม่คัดลอกซ้ำ)

**ฝั่ง server**
- Connection pool `psycopg2.pool.ThreadedConnectionPool(min=1, max=10)` (ไม่เปิด connection ใหม่ทุก request)
- uvicorn 2 worker · cache dashboard แยกในแต่ละ worker ได้ (ข้อมูลไม่เปลี่ยน จึงไม่ต้อง sync)
- `statement_timeout = 5s` ต่อ connection · query เกิน 500 ms log `db.slow_query` (ข้อ 15)
- response ใหญ่ (dashboard, elrs) บีบอัดด้วย gzip ที่ NGINX (`gzip on`, ≥ 1 KB)

**ฝั่งหน้าเว็บ**
- JS ตอนเปิดครั้งแรก ≤ 300 KB (gzip) · หน้า Preview โหลดแบบ lazy (`React.lazy`)
- ตาราง ELR แสดงทีละหน้า 50 แถว (ไม่ต้องทำ virtual list)
- ตาราง ACTIVEL คงที่ 5 × 21 ช่อง: O(1) ต่อ ELR · สี diff ต่อช่อง O(5·21)
- ภาพ ABS ใช้ `loading="lazy"` และแสดงขนาดย่อด้วย CSS · กดขยายแล้วค่อยแสดงเต็มขนาด
- ค้นหาแบบ debounce 300 ms ก่อนยิง API

**เป้าหมายเวลา** (p95 บน LAN, run ขนาด ≤ 5,000 บรรทัด, วัดจาก `duration_ms` ใน log)

| Endpoint | เป้า |
|---|---|
| `/dashboard` | ≤ 300 ms ครั้งแรก · ≤ 50 ms เมื่อมี cache |
| `/elrs` | ≤ 200 ms |
| `/elrs/{elr}` | ≤ 150 ms |
| `POST /reviews`, `/approvals` | ≤ 150 ms |
| `/auth/login` | ≤ 500 ms |
| หน้าเว็บเปิดครั้งแรกจนเห็น Dashboard | ≤ 2 วินาที |

**เมื่อไรต้องออกแบบใหม่**:
- L > 50,000 ต่อ run หรือมีผู้ใช้พร้อมกันเกิน 20 คน → ย้ายการนับไปทำใน SQL (`GROUP BY`) หรือตาราง `metric_snapshot` (spec หลัก §13)
- เริ่มมี job ใหม่เข้าตลอดเวลา (B3) → cache dashboard ต้องล้างเมื่อได้ event (`mark_events` ข้อ 13)

