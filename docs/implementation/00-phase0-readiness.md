# 00 — Phase 0 Implementation Readiness

วันที่: 2026-11-04 · อ้างอิง: Architecture V2026-11-04 / Design Decisions v2 (`docs/superpowers/specs/2026-11-04-mark-automation-design.md`)
ผู้ตรวจ: Claude · โหมด: อ่านอย่างเดียวทั้งหมด (PostgreSQL read-only session, Oracle `SET TRANSACTION READ ONLY` + SELECT, ไม่แตะ A100/NAS write)

## คำตัดสิน (อัปเดตรอบ 2 — 2026-11-04 หลังเจ้าของตอบ/มอบหมาย ดู 07)

> ## GO — Phase 1 แบบ offline (`mark_engine` บน R0 ที่ freeze แล้ว)
> ## CONDITIONAL GO — เตรียมชุด blind test Jul–Nov (NAS เข้าได้แล้ว; ตัดชุด 2026-11-30)
> ## NO-GO — production integration จนกว่า D-15/D-19 จะตัดสิน และ migration 0001–0003 ถูกรัน

| เงื่อนไขเดิม | สถานะ |
|---|---|
| C1 commit + tag โค้ด | ✔ `mark` branch `phase0/regression-r0`, commit `d7d788e`, tag `regression-r0-2026-11-04` (local, ไม่ push) |
| C2 freeze baseline | ✔ แบบไฟล์: R0 = run 3 → `artifacts/regression-r0/` (CSV + MANIFEST, git-ignored); R0-legacy = run 2 `line_result`. ใน DB: `migrations/0002` เขียนแล้ว ยังไม่รัน |
| C3 เกณฑ์ผ่าน Phase 1 | ✔ ตัดสินแล้ว (D-03) |
| C4 Phase 1 ใช้ snapshot เท่านั้น | ✔ คงไว้ |
| B1 Oracle เขียนได้ | ยอมรับความเสี่ยง (D-11): บังคับ read-only ในโค้ด |
| B5 NAS | ✔ ปิดแล้ว (D-12) |
| B6 trigger | ✔ ปิดแล้ว `CURRENT_STEP = '6'` (D-01) |
| B7 credential | ยอมรับความเสี่ยง (D-13) |
| **ใหม่ — D-15/D-19** | session อื่นยังเขียน `mark_logic` และแก้โค้ด (run 3 16:05 ผ่อน gate SLR, อนุมัติ REMARK-*/PIN-NOTE เอง) — **ไม่บล็อก Phase 1** เพราะ R0 ล็อกด้วย tag+CSV แล้ว แต่ต้องตัดสินก่อน production |

ส่วนด้านล่างคือผลการตรวจรอบแรก (คงไว้เป็นหลักฐาน)

## คำตัดสินรอบแรก (ก่อนเจ้าของตอบ)

> CONDITIONAL GO — Phase 1 offline · NO-GO — Oracle สด, blind test, production จนกว่าจะปิด B1, B5, B6

## สรุปข้อค้นพบสำคัญ

| # | ข้อค้นพบ | ป้าย | รายละเอียด |
|---|---|---|---|
| 1 | **ระบบปัจจุบันไม่มี `expected_mark` ที่สร้างอิสระ** — ค่าที่สร้างถูกแก้/เลือกด้วยค่า Oracle ใน ≥ 3 จุด (SLR-LITERAL เขียนค่า Oracle ทับ, SLR candidate เลือกตาม Oracle, ABS เลือกตาม Oracle) | ยืนยัน | 01 §4 |
| 2 | 98.7% คือ "อธิบายค่า Oracle ได้" ไม่ใช่ความถูกต้อง; ส่วนที่ได้โดยไม่พึ่ง Oracle ≥ 72.3% | ยืนยัน / สันนิษฐาน | 01 §4 |
| 3 | จัดประเภท 44 กฎ: SPEC_DERIVED 12 · ORACLE_DERIVED 9 · EXPERIMENTAL 16 · PENDING_VERIFICATION 7; metadata ใน DB ไม่ตรงโค้ด 5 ข้อ (สำคัญสุด R03-ONE-ABS) + กฎ spec อีก 3 ข้อที่ implement โดยใช้ Oracle | ยืนยัน | 01 §3 |
| 4 | MATCH_SHIFT / MATCH_LOT อยู่ฝั่ง compare แล้ว ✔ แต่ MATCH_LOT ไม่ตรวจว่าเลขตรง SLR lot → ความเสี่ยง False PASS | ยืนยัน | 01 #38, 04 §5 |
| 5 | ADI1039 ไม่ถูกใช้กับ TRS **เพราะยังไม่มี TRS ในข้อมูล** ไม่ใช่เพราะมีการป้องกัน; ADI1039 ถูกใช้กับ SLR (ขัดกับ spec §9) | ยืนยัน | 01 §5 |
| 6 | `ACTLUSR` มี INSERT/UPDATE/DELETE บน `ACTLDBA.ELR`; Oracle เป็น 10g (ต้องใช้ thick client) | ยืนยัน | 02 §1 |
| 7 | ไม่มีค่าใน Oracle ที่บอก "Mark Eng Review" โดยตรง; `ELR_REV` = `'00'` เสมอ; `CUST_REQ_NO` = เลข SLR, `CUST_BOM_REVISION` = revision ABS (ช่วย resolver มาก); `TYPE_CODE` อยู่ใน `MARK_ID` | ยืนยัน | 02 §3 |
| 8 | Resolver เดิม: range folder ผิด, SLR.zip 354 ไฟล์ถูกละ, SLR หลายฉบับถูกต่อกัน, ไม่มี revision | ยืนยัน | 03 §2 |
| 9 | โค้ด pipeline ทั้งหมด **ไม่อยู่ใน git**; `run.git_commit d425dc8` ไม่มีโค้ดที่สร้างผล | ยืนยัน | 04 §1 |
| 10 | **`mark_logic` ถูกเขียนทับระหว่างการตรวจ** (run 2 เวลา 15:52, `logic_rule` 44 แถวเขียนใหม่, R04-SLR-QUAL เปลี่ยนเป็น spec/approved โดยไม่มีบันทึกอนุมัติ) | ยืนยัน | 01 §1, 05 §1 |
| 11 | Jan–Apr ใช้ครอปของคน + OCR อ่านซ้ำถูกคัดด้วย GT → ไม่ใช่ pipeline อัตโนมัติ | ยืนยัน | 06 §1 |
| 12 | ชุด blind Jul–Nov: 402 ELR ใน Oracle, 347 approved, ตัด 21 ELR ที่เคยถูกดูแล้ว; **NAS เข้าไม่ได้** | ยืนยัน | 06 §4 |

## Blockers

| ID | Blocker | บล็อกอะไร | ปิดเมื่อ | อ้าง |
|---|---|---|---|---|
| **B1** | Oracle credential เขียนได้ (`ACTLUSR` INSERT/UPDATE/DELETE) | ต่อ Oracle สดจาก `mark_engine` / Airflow | มี user SELECT-only หรือ DBA ยืนยัน revoke | D-11 |
| **B2** | โค้ดที่สร้าง baseline ไม่อยู่ใน git และยังถูกแก้อยู่ | Phase 1 (legacy-parity ต้องมีโค้ดอ้างอิงที่คงที่) | commit + tag ใน repo `mark` | D-14 |
| **B3** | `mark_logic` ไม่ถูก freeze และมีผู้เขียนอื่นอยู่ | Phase 1 (rule version ต้องคงที่) | M0+M2+M3 (05) + หยุด export | D-04, D-15 |
| **B4** | เกณฑ์ผ่าน Phase 1 ใน spec ("regression ได้ผลเท่าเดิม") ใช้ไม่ได้กับผลที่ Oracle-conditioned | Phase 1 acceptance | เจ้าของรับเกณฑ์ legacy-parity + R1 | D-03 |
| **B5** | NAS เข้าไม่ได้ | Blind test, resolver บนข้อมูลจริง | มีสิทธิ์อ่านหรือสำเนา ก.ค.–พ.ย. | D-12 |
| **B6** | ไม่มีนิยาม trigger "Mark Eng Review" ใน Oracle | Airflow polling (Phase 5) | ทีม ACTL ยืนยัน | D-01 |
| B7 | credential `postgres`/`<redacted>` อยู่ในแชท | production | rotate | D-13 |

## เงื่อนไขก่อนเริ่ม Phase 1 (CONDITIONAL GO)

| ID | เงื่อนไข | ปิด blocker |
|---|---|---|
| **C1** | Commit + tag โค้ด `experiments/abs_vs_db`, `experiments/symbol_det`, `deploy` ใน repo `mark`; hash `Symbol ADI.xlsx` หลังปิดไฟล์ | B2 |
| **C2** | Freeze R0: run M0 (pg_dump) + M2 (คัดลอก run 2 → `mark_regression`) + หยุด `export_logic_pg.py` บน `mark_web` | B3 |
| **C3** | เจ้าของรับเกณฑ์ Phase 1 ใหม่: (ก) invariant "expected ไม่ขึ้นกับ oracle_mark" 100% (ข) legacy-parity: ทุกบรรทัดที่ต่างจาก R0 มี reason code และไม่มี `BUG` (ค) R1 บันทึกเป็น baseline ใหม่ | B4 |
| **C4** | Phase 1 ไม่ต่อ Oracle/NAS/A100 สด — ใช้ snapshot JSON/CSV ใน manifest (06 §3) เท่านั้น จนกว่า B1/B5 ปิด | B1, B5 (กันไว้ ไม่ใช่ปิด) |

ตัดสินใจที่ควรได้ก่อนเริ่ม แต่ไม่บล็อก: D-02 (ค่าที่ 4 — ใช้ค่าเริ่มต้นได้), D-05 (ADI1039 กับ SLR), D-06 (เริ่มด้วย "ทั้งหมดยังไม่อนุมัติ")

## ขอบเขต Phase 1 ที่แนะนำ (หลัง C1–C4)

1. แพ็กเกจ `mark_engine` ตาม 04 §3: `domain`, `rules` (อ่าน `mark_rules` version ที่ freeze), `documents` (resolver บนสำเนา), `abs`, `slr` (regex), `encode`, `generate`, `compare`, `adapters/snapshot_source.py`
2. Migration M1, M3 (governance) — M4/M5 ตามมาเมื่อพร้อมเก็บผล
3. Test: unit ต่อกฎ, invariant 4 ข้อ, resolver fixtures, legacy-parity บน Jan–Jun
4. ผลลัพธ์: รายงาน R1 บน Jan–Jun ตามตัวชี้วัด 06 §5

**ไม่อยู่ใน Phase 1:** LLM, FastAPI, Airflow, React, deploy A100, การต่อ Oracle/NAS สด, blind test

## ข้อจำกัดด้านความปลอดภัย — สถานะใน Phase 0

| ข้อจำกัด | ปฏิบัติ |
|---|---|
| Oracle read-only | ✔ SELECT ภายใน `SET TRANSACTION READ ONLY` เท่านั้น; ไม่สร้าง/แก้ ELR |
| ไม่แก้ dataset 529 ELR | ✔ อ่านอย่างเดียว; hash เท่านั้น |
| ไม่แก้ production rules | ✔ PostgreSQL session read-only; ไม่รัน DDL/DML |
| ไม่ deploy/restart A100/vLLM | ✔ ไม่เชื่อมต่อ A100 |
| ไม่ใช้ TOP/BACK_MARK สร้าง expected | ✔ ออกแบบบังคับระดับ type (04 §2) |
| MATCH_SHIFT/MATCH_LOT อยู่ใน Comparison Engine | ✔ (04 §5) |
| ไม่ใช้ ORACLE_DERIVED ที่ไม่อนุมัติ | ✔ ออกแบบให้เป็น NEEDS_REVIEW (04 §2 ข้อ 3) |
| ไม่เทรนโมเดล | ✔ |

## ดัชนีเอกสาร

| ไฟล์ | เนื้อหา |
|---|---|
| `01-rule-provenance-audit.md` | 44 กฎ, การจัดประเภท, Oracle influence, ADI1039/TRS |
| `02-oracle-field-mapping.md` | ฟิลด์ Oracle, บทบาท GEN/META/ORACLE_MARK, ความปลอดภัย |
| `03-document-resolver-design.md` | audit การหาเอกสาร + ออกแบบ resolver |
| `04-mark-engine-architecture.md` | แพ็กเกจ, 4 ค่า, compare, API, test |
| `05-database-migration-plan.md` | M0–M7, freeze, roles |
| `06-regression-and-blind-test-plan.md` | manifest R0, ชุด blind, ตัวชี้วัด |
| `07-open-decisions.md` | D-01 – D-29 |
| `08-database-tables.md` | ตาราง `mark_web.mark_logic`, ประวัติ run 1–14 |
| `09-mark-eng-confirmation.md` | คำถาม/คำตอบ Mark Eng (Q1 COO, Q2 revision) |
| `10-r1-logic-review-and-next-phase.md` | **logic R1 ปัจจุบันทั้งหมด, True/Warning/Error, งาน debug ค้าง, เตรียม phase ถัดไป** |

## Phase 1 closeout update (2026-11-05)

See [11-blind-test-2026h2.md](11-blind-test-2026h2.md) for the frozen holdout, run 17, its coverage and limitations. This later result supersedes the prospective Phase 0 plan above.
