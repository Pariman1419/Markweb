# 05 — PostgreSQL Migration Plan (`mark_web`)

วันที่: 2026-11-04 · สถานะ: **แผนเท่านั้น — Phase 0 ไม่ได้รัน DDL/DML ใด ๆ** · ป้าย **[ยืนยัน]** / **[เสนอ]**

## 1. สภาพปัจจุบัน **[ยืนยัน]**

- PostgreSQL 13.6 (`10.151.28.2`), DB `mark_web`; schema `public` ว่าง; มีแค่ schema `mark_logic` (14 ตาราง)
- การเชื่อมต่อทั้งหมดใช้ user `postgres` (superuser) — รวมสคริปต์ export (`rule_scope_pg.py:99-101` default user `postgres`)
- `export_logic_pg.py` "Reference tables are replaced on every run" (`export_logic_pg.py:18`) → `logic_rule` ถูก insert ใหม่ทั้งตาราง
  (pg_stat: `logic_rule` ins 88 / upd 88; `elr_document` ins 1,204 สำหรับ 602 แถว)
- `run` มี 2 แถว: run 1 (15:07:57) และ run 2 (15:52:36) ทั้งคู่ `git_commit = d425dc8`, 2,381 บรรทัด, match 98.69%
  — run 2 ถูกเขียน**ระหว่างการตรวจ Phase 0**
- ไม่มีตาราง migration/version; ไม่มี constraint ป้องกันการแก้ run เก่า

## 2. หลักการ

1. Migration ผ่านเครื่องมือมีเวอร์ชัน (เสนอ **Alembic** ใน repo `mark-web`, ไฟล์ SQL ล้วนต่อ revision) — ไม่ใช้สคริปต์ export เขียน schema
2. **ไม่แก้ไข/ลบแถวเดิมใน `mark_logic`** ทั้ง run 1/2, `line_result`, `logic_rule` — การ freeze ทำด้วยการ *คัดลอก* และ *ล็อกสิทธิ์*
3. ทุก migration มี down-migration และรันบน DB สำเนาก่อนเสมอ
4. แยก role: `mark_owner` (DDL, ใช้ตอน migrate เท่านั้น), `mark_app` (RW `mark_app`, RO `mark_logic`), `mark_rules_admin` (เขียน `mark_rules` ผ่านขั้นอนุมัติ), `mark_readonly`

## 3. ลำดับ migration [เสนอ]

| # | ชื่อ | ทำอะไร | เขียนข้อมูลเดิม? | ต้องอนุมัติโดย |
|---|---|---|---|---|
| M0 | `0000_baseline_snapshot` | `pg_dump -n mark_logic` (ไฟล์ + sha256) ก่อนทุกอย่าง | ไม่ | เจ้าของโปรเจกต์ |
| M1 | `0001_roles` | สร้าง role 4 ตัวข้างบน; `REVOKE` เขียนบน `mark_logic` จาก role ที่ไม่ใช่ owner | ไม่ | เจ้าของ + DBA |
| M2 | `0002_regression_frozen` | schema `mark_regression`: `CREATE TABLE … AS SELECT` จาก `mark_logic.run/line_result/stage_accuracy/review_verdict/logic_rule/symbol_profile/encoder_alias/adi1039_token/remark_profile/slr_instruction/slr_line_instruction/elr_document` สำหรับ `run_id = 2` → ตาราง `baseline_r0_*` + `baseline_manifest(table, row_count, content_sha256, frozen_at, source_run_id)`; หลังสร้าง `REVOKE INSERT, UPDATE, DELETE, TRUNCATE` จากทุก role | ไม่ (คัดลอก) | เจ้าของ |
| M3 | `0003_rule_governance` | schema `mark_rules`: `rule_version(rule_version_id, created_at, created_by, frozen bool, content_sha256, note)`, `rule(rule_version_id, rule_id, …ทุกคอลัมน์ของ logic_rule…, provenance_class, provenance_evidence, oracle_influence text)`, `rule_approval(rule_version_id, rule_id, decision, approver, approved_at, note)`; seed version `RV-2026-11-04-R0` = สำเนา `mark_logic.logic_rule` ปัจจุบัน + `provenance_class` จากเอกสาร 01 ในสถานะ `proposed` (ไม่ใช่ approved) | ไม่ | Mark Eng อนุมัติ `provenance_class` |
| M4 | `0004_mark_app_core` | schema `mark_app`: `job`, `job_revision`, `elr_snapshot`, `document`, `document_resolution`, `inference_cache`, `model_version` | ไม่ | เจ้าของ |
| M5 | `0005_mark_values` | `draft_line`, `line_review`, `line_verification`, `approval`, `audit_log` (ตาราง 4 ค่า — ด้านล่าง) | ไม่ | เจ้าของ |
| M6 | `0006_slr_llm` | `slr_sentence`, `slr_line_instruction_v2`, `llm_call` | ไม่ | Phase 3 |
| M7 | `0007_metrics_notify` | `metric_snapshot`, `notification` | ไม่ | Phase 4 |

M0–M3 เป็นเงื่อนไขก่อน Phase 1 (ดู 00) · M4–M5 ต้องมีก่อนเก็บผลจาก `mark_engine` ลง DB (Phase 1 ช่วงท้าย / Phase 4)

## 4. ตาราง 4 ค่า (M5) [เสนอ]

```sql
create table mark_app.draft_line (
  job_revision_id   bigint references mark_app.job_revision on delete restrict,
  side              text check (side in ('TOP','BOTTOM')),
  line_no           smallint check (line_no between 1 and 5),
  expected_mark     text,                 -- สร้างโดย generator; NULL = generate ไม่ได้
  expected_tokens   jsonb not null,       -- [{text, rule_id, source:'ABS|SLR|REMARK|ADI1039|OCR_FIX|LLM', evidence}]
  generate_flags    text[] not null default '{}',  -- ORACLE_DERIVED_UNAPPROVED, LLM_PROPOSED, RULE_CONFLICT ...
  oracle_mark       text,                 -- snapshot จาก elr_snapshot (คัดลอกเพื่อความสะดวก)
  line_status       text not null,        -- ผล compare (spec §10)
  compare_rules     text[] not null default '{}',
  primary key (job_revision_id, side, line_no)
);
-- expected_mark ห้ามเปลี่ยนหลัง insert
create trigger draft_line_expected_immutable before update of expected_mark, expected_tokens
  on mark_app.draft_line for each row execute function mark_app.raise_immutable();

create table mark_app.line_review (            -- append-only
  review_id bigserial primary key,
  job_revision_id bigint, side text, line_no smallint,
  reason_code text check (reason_code in ('DB_WRONG','OCR_WRONG','SYMBOL_WRONG','SLR_ECN_CHANGE','RULE_MISSING','LAYOUT_WRONG','OTHER')),
  note text,
  engineer_corrected_mark text,
  reviewer text not null, reviewed_at timestamptz not null default now(),
  foreign key (job_revision_id, side, line_no) references mark_app.draft_line
);

create table mark_app.line_verification (      -- เขียนได้เฉพาะ transaction ของ Approve
  approval_id bigint references mark_app.approval,
  job_revision_id bigint, side text, line_no smallint,
  engineer_verified_mark text not null,
  verified_from text check (verified_from in ('EXPECTED_CONFIRMED','ENGINEER_CORRECTED')),
  primary key (approval_id, side, line_no)
);
```

- ไม่มีคอลัมน์ใดที่ตั้ง `engineer_verified_mark` จาก `oracle_mark` (CHECK `verified_from` บังคับ)
- `approval.status = 'STALE'` → view `mark_app.ground_truth` กรองออก

## 5. ข้อห้ามที่ migration ต้องบังคับ

- `mark_app` role ไม่มีสิทธิ์เขียน `mark_logic`, `mark_regression`, `mark_rules`
- `mark_rules.rule` ของ version ที่ `frozen = true` ห้าม UPDATE (trigger)
- สคริปต์ `export_logic_pg.py` / `rule_scope_pg.py` ต้องถูกเปลี่ยนให้เขียนเฉพาะ `mark_logic` ด้วย role ที่จำกัด หรือหยุดใช้ — **ไม่ทำใน Phase 0** (repo อื่น, ต้องตกลงกับเจ้าของ)

## 6. Rollback

ทุก revision M1–M7 มี `downgrade()`; M2/M3 rollback = drop schema ใหม่ (ไม่กระทบ `mark_logic`) · M1 rollback = คืนสิทธิ์เดิม
