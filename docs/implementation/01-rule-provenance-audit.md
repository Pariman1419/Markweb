# 01 — Rule Provenance Audit (44 กฎใน `mark_web.mark_logic.logic_rule`)

วันที่ตรวจ: 2026-11-04 · ผู้ตรวจ: Claude (Phase 0) · โหมด: อ่านอย่างเดียว (PostgreSQL `set_session(readonly=True)`)

ป้าย: **[ยืนยัน]** = มีหลักฐานจากโค้ด/DB/เอกสาร · **[สันนิษฐาน]** = ข้อสรุปของผู้ตรวจที่ยังไม่ได้พิสูจน์

---

## 1. แหล่งหลักฐาน

| แหล่ง | รายละเอียด |
|---|---|
| DB snapshot A | `logic_rule` อ่านครั้งแรก (ก่อน 15:52) — 44 แถว, `run` มีแค่ run_id 1 |
| DB snapshot B | `logic_rule` อ่านซ้ำ 15:54 — 44 แถว, `run` มี run_id 1 และ 2 (run 2 สร้าง 2026-11-04 15:52:36) |
| โค้ด | repo `D:\CIM Project\mark` — `experiments/abs_vs_db/mapping_gap_analysis.py` (sha256 `d215f4b0…`, แก้ล่าสุด 15:51), `build_compare.py`, `build_h1.py`, `rule_scope_pg.py`, `export_adi1039_pg.py`, `experiments/symbol_det/graphics_to_lines.py` |
| Spec | `docs/superpowers/specs/2026-11-04-mark-automation-design.md` (Design Decisions v2) |

**[ยืนยัน] กฎถูกแก้ระหว่างตรวจ:** ระหว่าง snapshot A → B มีโปรเซสอื่นรัน `export_logic_pg.py` + `rule_scope_pg.py`
(ไฟล์ทั้งสองแก้ 15:51:57, `pg_stat_user_tables.logic_rule` n_tup_ins = 88, n_tup_upd = 88 = เขียนซ้ำทั้งตาราง 2 รอบ)
ความต่าง: `R04-SLR-LINE.pattern` เพิ่ม `Line Mark 2 - Q1` และ `R04-SLR-QUAL` เปลี่ยนจาก
`generate / oracle_derived / pending` → `gate / spec / approved` — รายงานนี้ใช้ **snapshot B** เป็นสถานะปัจจุบัน

## 2. เกณฑ์จัดประเภท (การตัดสินใจของผู้ตรวจ)

| ประเภท | เกณฑ์ |
|---|---|
| **SPEC_DERIVED** | เนื้อหากฎสืบย้อนได้ถึงเอกสารต้นทาง (ADI1039 Rev AE, Symbol ADI.xlsx, ข้อความ SLR/ABS, MARK_REMARK ที่เป็นคำสั่ง) **และ** ไม่ได้ถูกค้นพบโดยการ fit กับ TOP/BACK_MARK ของ Oracle |
| **ORACLE_DERIVED** | กฎถูกค้นพบ/ปรับจนตรงกับค่า TOP/BACK_MARK ในอดีต (หลักฐาน "n of n ELRs ตรง DB") หรือการตัดสินของกฎต้องใช้ค่า Oracle mark |
| **EXPERIMENTAL** | heuristic ที่ปรับจากเคสจำนวนน้อย/ภาพตัวอย่าง หรือโมเดล ML — ไม่ได้มาจาก spec และไม่ได้อ่าน Oracle mark |
| **PENDING_VERIFICATION** | ยังไม่ implement (`planned`), หรือ provenance/metadata ใน DB ขัดกับโค้ด, หรือ implementation มีข้อบกพร่องที่ยืนยันแล้ว จนบอกไม่ได้ว่ากฎทำงานตามที่บันทึกไว้ |

แยกเป็นอีกคอลัมน์: **Oracle-influence ในโค้ดปัจจุบัน** (คำถามข้อ 4) — กฎที่ provenance เป็น spec ก็อาจถูก implement โดยใช้ค่า Oracle เลือกคำตอบได้

## 3. ตารางกฎทั้ง 44 ข้อ

คอลัมน์ "DB" = `rule_stage / rule_origin / approval_status` จาก snapshot B · "Oracle?" = โค้ดใช้ `db_mark` (TOP/BACK_MARK) ในการตัดสินหรือไม่ — อ้างบรรทัดใน `mapping_gap_analysis.py` (MGA) ณ sha `d215f4b0`

| # | rule_id | DB | ประเภท (ผู้ตรวจ) | Oracle? | หลักฐาน / เหตุผล |
|---|---|---|---|---|---|
| 1 | R01-ORACLE | process/process/approved | SPEC_DERIVED (process) | อ่าน | ดึงข้อมูลอย่างเดียว; **แต่** user `actlusr` มีสิทธิ์ INSERT/UPDATE/DELETE บน `ACTLDBA.ELR` (ดู 02) และตัวดึงผูก `^ADI260[1-6]` (`fetch-elr-marks-2026-h1.mjs:9`) |
| 2 | R02-NAS-PATH | process/process/approved | PENDING_VERIFICATION | — | implementation ปัจจุบันคือสำเนาด้วยมือ `mark/[1-6]_*` (MGA:51, MGA:450); ไม่รองรับ Range Folder (ดู #3); เครื่องนี้เข้า NAS ไม่ได้ (Access denied) |
| 3 | R03-ABS-SLR-GATE | gate/user_confirmed/approved | PENDING_VERIFICATION | ไม่ | MGA:450-453 ใช้ `basename(folder)` เป็น ELR_NO → Range Folder `ADI2603011-14`, `ADI2603055-56` กลายเป็น ELR ปลอม (`elr_document` มีแถว `ADI2603011-14`) และ ELR จริงใน range ได้ `no ELR folder` → NOT_MEASURABLE; นับเฉพาะ `SLR*.pdf` ขณะที่มี `SLR*.zip` 354 ไฟล์ในสำเนา ม.ค.–มิ.ย. |
| 4 | R03-NO-LINE-LABEL | gate/user_confirmed/approved | EXPERIMENTAL | ไม่ (ผลเป็น NOT_COMPARABLE) | ABS hard-code `{'ABS053350','ABS057473'}` (MGA:109); ผลปลอดภัย (ไม่เกิด MATCH) |
| 5 | R03-ONE-ABS | gate/user_confirmed/approved | **ORACLE_DERIVED** | **ใช่ — เลือกเอกสาร** | MGA:33-36 เลือก ABS ที่ "match DB มากที่สุด" (`_score` นับ status MATCH vs db_mark) → Oracle เลือกเอกสารต้นทาง; DB บันทึกเป็น user_confirmed/approved = **จัดประเภทผิด** |
| 6 | R04-ABS-PAGE | process/process/approved | EXPERIMENTAL | ไม่ | `extract_marking_images.py` หน้าสุดท้ายที่มี "Brand/Marking", raster ใหญ่สุด |
| 7 | R04-OCR | process/process/approved | EXPERIMENTAL (model) | ไม่ | EXP09; ครอป ม.ค.–มี.ค. เป็นชุดเทรนของ EXP09 (`build_compare.py:254` note) |
| 8 | R04-REOCR-LEGEND | process/user_confirmed/approved | EXPERIMENTAL | ไม่ | `reocr.py` กรณี legend; ใช้ score ≥ 0.9 เมื่อไม่มี GT |
| 9 | R04-REOCR-LOGO | process/user_confirmed/approved | PENDING_VERIFICATION | ไม่ (แต่ใช้ human GT) | `reocr.py` docstring: "override is kept only when it equals GT" และ `build_compare.py:104-107` รับผลอ่านซ้ำเฉพาะแถว `kept == 'Y'` → ใช้ ground truth คัดผล OCR; ทำซ้ำใน production ไม่ได้ |
| 10 | R04-SLR-LINE | generate/spec/approved (P10) | SPEC_DERIVED | **ใช่** | MGA:342 ทำงานเฉพาะบรรทัดที่ `fused_status == 'DIFF'` (= ไม่ตรง Oracle) และ MGA:346 เลือก candidate ที่ `fullmatch` กับ `db_mark` → คำสั่ง SLR ถูกใช้ก็ต่อเมื่อ Oracle ไม่ตรง ABS และเลือกค่าโดยดู Oracle |
| 11 | R04-SLR-LITERAL | compare/oracle_derived/needs_approval | ORACLE_DERIVED | **ใช่ — เขียนทับค่าที่สร้าง** | MGA:352-354 `hit = dtext` (ค่า Oracle) แล้ว MGA:363 `o['fused'] = yolo + hit` → ค่าที่ระบบ "สร้าง" ถูกแทนด้วยค่า Oracle; ติดป้าย compare แต่แก้ fused จริง |
| 12 | R04-SLR-LOT | compare/spec/approved | SPEC_DERIVED | ใช่ (compare) | regex Scheduled Lot ID (MGA:57-59); ใช้ `endswith` เท่านั้น — ADI1039 Table 2 มี `{Lot-3-7}`, First/Last Half ที่ยังไม่รองรับ |
| 13 | R04-SLR-QUAL | gate/spec/approved | PENDING_VERIFICATION | ใช่ | เปลี่ยน provenance จาก oracle_derived → spec และ approval pending → approved **วันนี้ 15:52 โดยไม่มีบันทึกการอนุมัติของ Mark Eng**; คำอธิบายเองระบุว่าได้จากดูพฤติกรรม Oracle ("Feb-Mar keep ABS mark, Apr use Yn") — MGA:358-360 |
| 14 | R04-SLR-SECTION | process/spec/approved | SPEC_DERIVED | ไม่ | regex `SPECIAL INSTRUCTIONS` (MGA:53) |
| 15 | R04-SLR-TOKENS | generate/spec/approved (P10) | SPEC_DERIVED | **ใช่** | `slr_regex()` (MGA:321-335) ไม่ได้สร้างข้อความ แต่สร้าง regex แล้ว `fullmatch` กับค่า Oracle; `{Lot-n}` → `[0-9A-Z]{n}` ยอมรับอักขระใดก็ได้ → ไม่มี expected_mark ที่เป็น placeholder ให้เทียบ |
| 16 | R04-YOLO | process/process/approved | EXPERIMENTAL (model) | ไม่ | symdet_v2 val 10 ภาพ; `adi_full_logo` ไม่มีข้อมูลเทรน |
| 17 | R05-BOM | gate/spec/approved | SPEC_DERIVED | อ่าน CUST_BOM_NO | ไม่ได้บังคับเป็น gate: `build_compare.py:161` ถ้าโฟลเดอร์มี ABS ไฟล์เดียวยังใช้ ELR ต่อแม้ BOM_MISMATCH; MGA:145 ใช้เป็นแค่ป้ายสาเหตุ |
| 18 | R06-GRAPHIC-LINE | generate/user_confirmed/approved | EXPERIMENTAL | ไม่ | `graphics_to_lines.py` threshold ตาม IMG009 |
| 19 | R06-LEGEND | generate/user_confirmed/approved | EXPERIMENTAL | ไม่ | `build_h1.py:29-53` |
| 20 | R06-LINE-LABEL | generate/spec/approved | EXPERIMENTAL | ไม่ | ป้าย L/Line มาจาก ABS แต่ระยะ `-0.6..+0.35 row gap`, `6 row gaps` เป็นค่าที่ปรับเอง (`build_h1.py:101,120`) — DB บันทึกเป็น spec |
| 21 | R06-MAX-LINES | gate/spec/planned | PENDING_VERIFICATION | — | ยังไม่ implement (`implemented_in` ว่าง) |
| 22 | R06-RIGHT-LABEL | generate/user_confirmed/approved | EXPERIMENTAL | ไม่ | `build_h1.py:109-115` |
| 23 | R06-SHIFT | compare/oracle_derived/needs_approval | ORACLE_DERIVED | ใช่ (compare) | MGA:419-441 ตัดสินจาก DB line 1 ที่มีแต่กราฟิก; ไม่แก้ fused → สถานะอย่างเดียว ✔ |
| 24 | R06-TYPE-LAYOUT | gate/spec/planned | PENDING_VERIFICATION | — | ยังไม่ implement; **[ยืนยัน]** `TYPE_CODE` ไม่ได้อยู่ใน `ACTLDBA.ELR` แต่อยู่ใน `ACTLDBA.MARK_ID` (join ผ่าน `TOP_MARK_ID`) |
| 25 | R07-ADI1039-COO | generate/spec/approved (P40) | SPEC_DERIVED | ไม่ | `rule_text()` MGA:91-92, ADI1039 §5.5.3 |
| 26 | R07-ADI1039-LOT | generate/spec/approved (P40) | SPEC_DERIVED | ไม่ | MGA:90, ADI1039 Table 2 `{Lot-Full}` |
| 27 | R07-DB-PACKAGE | compare/oracle_derived/needs_approval | ORACLE_DERIVED | ใช่ (compare) | ป้ายคุณภาพข้อมูล ไม่เปลี่ยน status เป็น MATCH ✔ |
| 28 | R07-GRAPHIC-BLANK | generate/spec/approved (P30) | SPEC_DERIVED (แต่ stage ผิด) | ใช่ | ใช้ลบกราฟิกก่อนเทียบ (`norm()` MGA:96-100) → MGA:133-134 `GRAPHIC_SYMBOL` นับ MATCH แม้กราฟิกต่าง (143 บรรทัด/run) — เป็น compare-normalizer ไม่ใช่ generate |
| 29–36 | R07-OCRFIX-1…8 | generate/user_confirmed/approved (P50) | EXPERIMENTAL (1–7) · PENDING_VERIFICATION (8) | ไม่ | `OCR_FIX` MGA:70-79; #8 `n DIGIT SERIAL NUMBER → X×n` ขัดกับ ADI1039 §5.10 Table 12 (serial เติมศูนย์ เริ่ม 1 ต่อ lot) — ต้องให้ Mark Eng ยืนยัน |
| 37 | R07-PIN-NOTE | generate/oracle_derived/needs_approval (P20) | ORACLE_DERIVED | **ใช่** | MGA:376-378 ลบ `@` ออกจาก **ค่า Oracle** แล้วตัดสิน MATCH → เป็นการยอมรับค่า Oracle ไม่ใช่การสร้าง; stage `generate` ไม่ถูก |
| 38 | R07-PLACEHOLDER | compare/oracle_derived/needs_approval | ORACLE_DERIVED | ใช่ (compare) | MGA:395 ตั้ง `MATCH_LOT` เมื่อมีตัวเลขแทน X/YYWW **ก่อน**คำนวณ `ver` (MGA:399) → ไม่ว่าจะตรง SLR lot หรือไม่ (`ver` ใช้แค่ข้อความ cause); date code ไม่ตรวจเลย → ความเสี่ยง False PASS |
| 39 | R07-REMARK-CARET | generate/oracle_derived/needs_approval (P20) | ORACLE_DERIVED | ทางอ้อม | หลักฐาน "44 of 44 ELRs" = fit กับ Oracle; `caret_logo()` MGA:190 |
| 40 | R07-REMARK-LOGO | generate/oracle_derived/needs_approval (P20) | ORACLE_DERIVED | ทางอ้อม | "124 of 124 ELRs"; `remark_tokens()` MGA:201-218 |
| 41 | R07-REMARK-PIN | generate/oracle_derived/needs_approval (P20) | ORACLE_DERIVED | ทางอ้อม | "216 of 218 ELRs (exceptions ADI2603055/056)" |
| 42 | R07-SKIP-MARK | gate/spec/approved | SPEC_DERIVED | **ใช่** | MGA:121 ใช้ได้เฉพาะเมื่อ `norm(d) == ''` (Oracle ว่าง) → ถ้า Oracle มีค่า กฎ Skip Mark ไม่ทำงาน |
| 43 | R07-SYMBOL-ADI | generate/spec/approved (P30) | SPEC_DERIVED | ไม่ | `build_compare.py:17-65`; **ยกเว้น** `{CCCCC}` → `THAILAND[:n]` (`build_compare.py:45-47`) ซึ่งไม่อยู่ใน Symbol ADI ("assumption" ตามคอมเมนต์ตัวเอง) |
| 44 | R08-REVIEW | compare/user_confirmed/approved | SPEC_DERIVED (process) | ใช่ (compare) | MGA:463-476 คำตัดสินคนเปลี่ยน DIFF → DB_WRONG; ไม่แก้ fused ✔ |

### สรุปจำนวน (ผู้ตรวจ)

| ประเภท | จำนวน | rule_id |
|---|---|---|
| SPEC_DERIVED | 12 | R01-ORACLE, R04-SLR-LINE, R04-SLR-LOT, R04-SLR-SECTION, R04-SLR-TOKENS, R05-BOM, R07-ADI1039-COO, R07-ADI1039-LOT, R07-GRAPHIC-BLANK, R07-SKIP-MARK, R07-SYMBOL-ADI, R08-REVIEW |
| ORACLE_DERIVED | 9 | R03-ONE-ABS, R04-SLR-LITERAL, R06-SHIFT, R07-DB-PACKAGE, R07-PIN-NOTE, R07-PLACEHOLDER, R07-REMARK-CARET, R07-REMARK-LOGO, R07-REMARK-PIN |
| EXPERIMENTAL | 16 | R03-NO-LINE-LABEL, R04-ABS-PAGE, R04-OCR, R04-REOCR-LEGEND, R04-YOLO, R06-GRAPHIC-LINE, R06-LEGEND, R06-LINE-LABEL, R06-RIGHT-LABEL, R07-OCRFIX-1 … R07-OCRFIX-7 |
| PENDING_VERIFICATION | 7 | R02-NAS-PATH, R03-ABS-SLR-GATE, R04-REOCR-LOGO, R04-SLR-QUAL, R06-MAX-LINES, R06-TYPE-LAYOUT, R07-OCRFIX-8 |
| **รวม** | **44** | |

กฎ SPEC_DERIVED 4 ข้อ (R04-SLR-LINE, R04-SLR-TOKENS, R07-SKIP-MARK, R07-GRAPHIC-BLANK) แม้ provenance ถูก แต่ **implementation
ใช้ค่า Oracle** — ต้องเขียนใหม่ ไม่ใช่ย้ายโค้ด

### ความต่างกับ `rule_origin` ใน DB (ต้องแก้ก่อน Phase 1 ใช้ตาราง)

| rule_id | DB บอก | ผู้ตรวจพบ | ผลกระทบ |
|---|---|---|---|
| R03-ONE-ABS | user_confirmed / approved | ORACLE_DERIVED | Oracle เลือก ABS — ห้ามใช้ใน Document Resolver |
| R04-SLR-QUAL | spec / approved (ตั้งวันนี้) | PENDING_VERIFICATION | ไม่มีหลักฐานการอนุมัติ; เปลี่ยนระหว่างการตรวจ |
| R06-LINE-LABEL | spec | EXPERIMENTAL | threshold ปรับเอง |
| R07-GRAPHIC-BLANK | generate | ควรเป็น compare-normalizer | ทำให้ graphic ไม่ถูกนับใน MATCH |
| R07-PIN-NOTE | generate | compare (ยอมรับค่า Oracle) | ห้ามอยู่ในเส้นทางสร้าง expected_mark |
| R07-SKIP-MARK, R04-SLR-LINE, R04-SLR-TOKENS | spec / approved | spec แต่ implement แบบ Oracle-conditioned | ต้องเขียนใหม่ใน `mark_engine` |

## 4. กฎ/โค้ดที่ใช้ค่า Oracle มีผลต่อ Generated Mark (คำถามข้อ 4)

**[ยืนยัน] ข้อสรุปหลัก: โค้ดปัจจุบันไม่มี `expected_mark` ที่สร้างขึ้นอย่างอิสระ** — คอลัมน์ `final_mark` ใน `line_result`
มาจาก `o['fused']` ซึ่งถูกแก้ตามค่า Oracle ในหลายจุด และ `fused_status` ถูกตัดสินแบบ "ลองทุกทางจนตรง Oracle" (การเทียบเป็นลำดับ
`if … elif …` ที่แต่ละขั้นใช้ `db_mark` เป็นตัวตัดสิน) ไม่ใช่ "สร้างก่อน แล้วค่อยเทียบ"

| ระดับ | ตำแหน่ง | กลไก |
|---|---|---|
| **A — แก้ค่าที่สร้างด้วยค่า Oracle** | MGA:352-354, 363 (R04-SLR-LITERAL) | ถ้าค่า Oracle ปรากฏในข้อความ SLR → `fused` = ค่า Oracle |
| A | MGA:346, 349-351 (R04-SLR-LINE/TOKENS) | เลือก candidate SLR (1–3 token) หรือย้ายค่า SLR จาก**บรรทัดอื่น** มาใส่ ตามที่ตรง Oracle |
| A | MGA:33-36 (R03-ONE-ABS) | Oracle เลือก ABS ที่จะใช้สร้าง |
| **B — Oracle เป็นเงื่อนไขให้กฎทำงาน** | MGA:342, 374 | กฎ SLR / lot / pin-note ทำงานเฉพาะบรรทัดที่ `DIFF` กับ Oracle |
| B | MGA:121, 125, 129 | Skip Mark, GRAPHIC_ONLY_LINE, NO_BRAND_LINE ต้องการ `norm(db_mark) == ''` |
| B | MGA:281-282 | `fused_status = MATCH` ทั้งที่ `fused ≠ db_mark` ถ้าขั้น text-only ผ่าน — 81 บรรทัด/run ที่ MATCH แต่ `final_mark ≠ db_mark` (3,270/3,432 ของ 2 run) |
| **C — compare (ยอมรับได้ถ้าแยก)** | R06-SHIFT, R07-PLACEHOLDER, R07-DB-PACKAGE, R08-REVIEW | ให้สถานะเท่านั้น — ตรงกับข้อจำกัด "MATCH_SHIFT/MATCH_LOT อยู่ใน Comparison Engine" |
| **D — ใช้ human GT ในเส้นทาง OCR** | `build_compare.py:104-107`, `reocr.py` | ผลอ่านซ้ำถูกรับเฉพาะเมื่อเท่ากับ GT |

### ผลต่อตัวเลข 98.7% **[ยืนยันจาก `line_result` run 2 / สันนิษฐานในการตีความ]**

| สถานะ (run 2) | บรรทัด | ขึ้นกับ Oracle |
|---|---|---|
| MATCH — cause OK | 1,200 | ไม่ (ยกเว้น ABS ถูกเลือกด้วย R03-ONE-ABS) |
| MATCH — MAPPING_RULE (lot/COO) | 233 | ไม่ |
| MATCH — GRAPHIC_SYMBOL | 143 | กราฟิกถูกละในการเทียบ (มี YOLO check บางส่วน) |
| MATCH — GRAPHIC_ONLY_LINE / NO_BRAND_LINE | 117 / 23 | ใช่ (ต้องการ Oracle ว่าง) |
| MATCH_SLR | 132 | ใช่ (ระดับ A) |
| MATCH_SHIFT / MATCH_LOT | 61 / 47 | compare |
| ตัวหาร (comparable) | 1,982 | |

**[สันนิษฐาน]** สัดส่วนที่สร้างได้โดยไม่ใช้ Oracle เลย ≥ (1,200 + 233) / 1,982 = **72.3%** (ขอบล่าง) — ตัวเลข 98.7% วัด
"ความสามารถในการอธิบายค่า Oracle" ไม่ใช่ความถูกต้องของ expected_mark ต้องวัดใหม่หลังแยก generate/compare (ดู 06)

## 5. ADI1039 ใช้กับ ABS เท่านั้น ไม่ใช่ TRS (คำถามข้อ 6)

| ประเด็น | ผล | หลักฐาน |
|---|---|---|
| metadata กฎ ADI1039 | **[ยืนยัน]** `R07-ADI1039-COO/LOT`: `document_scope = ABS`; `adi1039_token` โหลดด้วย scope `ABS` | `export_adi1039_pg.py:20-23` ("ADI1039 applies to ABS brand content only (not TRS laser marks, 5.1.5)") |
| โค้ดใช้ ADI1039 กับ TRS หรือไม่ | **[ยืนยัน] ไม่** — ไม่มีโค้ดใดอ่าน TRS; ไม่มี TRS ในสำเนา ม.ค.–มิ.ย. (ไม่พบชื่อไฟล์ TRS และ ABS 625 ไฟล์ไม่มีข้อความ "TRS"/"Test Requirement") | grep `\bTRS\b` พบเฉพาะคอมเมนต์ `export_adi1039_pg.py:20` |
| ระบบ "ป้องกัน" TRS ได้หรือไม่ | **[ยืนยัน] ไม่มีกลไก** — แยกเอกสารด้วย prefix ชื่อไฟล์ `ABS*` / `SLR*` เท่านั้น (MGA:51, 451-453); ถ้า TRS ถูกตั้งชื่อ ABS* จะถูกประมวลผลเป็น ABS | spec §6.2 ข้อ 3 กำหนดให้แยกจากเนื้อหา — ยังไม่ทำ |
| ADI1039 ใช้กับ SLR | **[ยืนยัน] ใช่** — `R04-SLR-TOKENS` (`effective_revision = ADI1039 Rev AE`, scope SLR) ตีความ `{Lot-n}`, `{DC-n}`, `{Pb-Free}` ใน SLR ตาม ADI1039 | ขัดกับประโยค "ADI1039 = ABS เท่านั้น" ใน spec §9 — ต้องตัดสิน (07 · D-05) |

**สรุป:** "ADI1039 ไม่เคยถูกใช้กับ TRS" = จริงในปัจจุบันเพราะยังไม่มี TRS ในชุดข้อมูล ไม่ใช่เพราะมีการป้องกัน →
`mark_engine` ต้องมี doc-type classifier จากเนื้อหาและ unit test ที่ยืนยันว่า TRS → HOLD และ ADI1039 rule ไม่ถูกเรียก (ดู 03, 04)

## 6. สิ่งที่ต้องทำก่อนใช้ `logic_rule` ใน Phase 1

1. เพิ่มคอลัมน์ `provenance_class` (4 ค่าข้างต้น) แยกจาก `rule_origin` เดิม — **ผ่าน migration ที่ Mark Eng อนุมัติ ห้ามแก้แถวเดิมอัตโนมัติ** (05)
2. Mark Eng ทบทวน 9 ORACLE_DERIVED + R04-SLR-QUAL — จนกว่าจะอนุมัติ กฎ generate ที่เป็น ORACLE_DERIVED ทำให้บรรทัดเป็น NEEDS_REVIEW
3. R03-ONE-ABS ต้องถูกแทนด้วย Document Resolver (03) — ห้ามย้ายเข้า `mark_engine`
4. R04-SLR-LITERAL ย้ายเป็น compare-only และห้ามแก้ `expected_mark`

## 7. การเปลี่ยน implementation ของกฎจาก R1 triage (2026-11-04, branch `phase1/r1-fixes`)

ไม่มี rule_id ใหม่ และไม่เปลี่ยน `provenance_class`/approval ใน `RV-2026-11-04-R0` — ทุกข้อเป็นการทำให้โค้ดตรงกับเนื้อหากฎที่อนุมัติแล้ว
หลักฐานทุกข้อมาจาก parity R1 vs R0 (ไม่ได้ fit กับ TOP/BACK_MARK: ข้อ 1–3 เป็น generate และพิสูจน์ด้วย independence 668/668)

| # | rule_id | stage | เดิม (Phase 1 code) | ใหม่ | เหตุผล / หลักฐาน | ไฟล์ |
|---|---|---|---|---|---|---|
| 1 | R07-ADI1039-LOT | generate (P40) | รองรับเฉพาะ `{Lot-n}`, `{Lot-Full}`, `ASSEMBLY LOT NUMBER` | รูป preview text `n DIGIT LOT NUMBER` / `LAST n DIGIT LOT NUMBER` → `X`×n, `lot_slice = last-n` (ไม่ต้องมี `\b` หน้า/หลัง เพราะ OCR ติดกับฟิลด์ข้างเคียง: `YW6 DIGIT LOT NUMBER`, `3 DIGIT LOT NUMBERYWW`) | ADI1039 Table 2 (`adi1039_tokens.csv` คอลัมน์ preview_text "7 Digit Lot Number" = `{Lot-7}`); R0 `build_compare.py:53-54`; 87 บรรทัด BUG ใน R1 | `mark_engine/encode/adi1039.py` |
| 2 | R07-OCRFIX-7 | generate (P50) | `COUNTRY OF ORIGINENGn` → `""` (ลบทั้งช่อง) | ตัดเฉพาะ suffix `ENGn` → `COUNTRY OF ORIGIN` แล้ว R07-ADI1039-COO แปลงเป็น `THAILAND` | คำอธิบายกฎ: "drafting suffixes (NUMBERU1, ORIGINENG2)" = ตัด suffix ไม่ใช่ลบฟิลด์; 7 บรรทัด (ADI2605079–090 TOP 5) | `mark_engine/encode/ocr_fix.py` |
| 3 | R04-SLR-LINE (coverage) | generate (P10) | ประโยคที่มีคำ `line/brand/mark/top/bottom/logo/lot/date code/symbol/laser/attachment` แต่ไม่ได้ instruction → `SLR_UNRESOLVED` ทั้ง ELR | นับเฉพาะคำที่พูดถึงตัว mark: `brand*`, `mark(ing)`, `logo`, `symbol`, `laser`, `date code`, `line N`, `first…fifth line`, `top/bottom side`, `attachment for (further) instructions` | ประโยคที่โดน flag 191 ELR เกือบทั้งหมดเป็นเรื่อง wafer / fab lot / ขนส่ง (header "SPECIAL LOT REQUEST" 63, "IB Lot" 19, "Fab Lot ID" …); 689/803 บรรทัดเท่า Oracle อยู่แล้ว → 86 บรรทัด | `mark_engine/slr/parse.py` |
| 4 | R07-ADI1039-COO | **compare** | expected `THAILAND` vs Oracle `THAIL` → DIFF | Oracle = expected ที่ย่อ `THAILAND` เหลือ prefix ≥ 2 ตัว (`TH`…`THAILAN`, D-22) → `MATCH` + `warning`, `compare_rules = (R07-ADI1039-COO,)`, `detail = COO_ABBREVIATED`; `T`, `THAIX` ยังเป็น DIFF | ADI1039 5.5.3 "full name when space allows" (ย่อได้เมื่อพื้นที่ไม่พอ); Symbol ADI `{Country of Origin}` → THAI; R0 นับเป็น MATCH (MAPPING_RULE); 13 บรรทัด (`THAILAND#` vs `THAIL#`, 13 ELR) — แยกนับได้จาก `detail` | `mark_engine/compare/engine.py` |
| 5 | R03-ABS-SLR-GATE / R05-BOM (resolver) | gate | สแกนทุกไฟล์ใต้โฟลเดอร์ ELR แบบ recursive | ข้ามโฟลเดอร์ย่อยที่ชื่อเป็น ELR อื่น (ไม่อยู่ใน ELR/range ของโฟลเดอร์ที่สแกน) | `2_FEB/ADI2602092/ADI2602095/` มี ABS+SLR ของ ADI2602095 → R1 ใช้ SLR231729 ของสินค้าอื่น (3 บรรทัด BUG) | `mark_engine/documents/fingerprint.py` |
| 6 | R07-REMARK-LOGO (review flag `GRAPHIC_REMARK_CONFLICT`) | generate | remark ประกาศโลโก้ แต่ YOLO ไม่เห็น `%`/`{` **บนด้านนั้น** → flag ทุกบรรทัดของด้าน | ตรวจระดับ ELR จากข้อความ expected ที่สร้างเสร็จ (`% { * ^` ไม่ว่ามาจาก YOLO หรือจากข้อความ drawing เช่น `{LTC-PARTIAL-LOGO}` → `*`); flag เมื่อไม่มีโลโก้เลยทั้ง ELR | MARK_REMARK ประกาศสัญลักษณ์ระดับชิ้นงาน ไม่ใช่รายด้าน (BOTTOM ไม่มีโลโก้); `*`/`^` เป็นโลโก้ตาม remark; 303 บรรทัด (259 เท่า Oracle) → 4 บรรทัด / 1 ELR | `mark_engine/generate/generator.py` |
| 7 | R07-OCRFIX-5 + priority MARK_REMARK (P20) > OCR fix (P50) | generate | `{e3}` → `<` เสมอ | ถ้า remark ประกาศ `e3 =` และไม่ประกาศ `< =` → `e3` | remark เป็นคำสั่ง (เช่น ADI2603063 "e3 = Pb- free identification"); ตรวจกับข้อมูล: remark ประกาศ `e3` 42 ELR — Oracle ไม่มี `<` เลย; ประกาศ `<` 94 ELR — Oracle ใช้ `<` | `mark_engine/generate/generator.py` |
| 8 | R05-BOM / revision (resolver, D-23) | gate | เลือก ABS ตาม `CUST_BOM_REVISION` เสมอ | ถ้า `PRODUCT_NO` มี revision ตัวอักษรหลังเลข ABS (`…-ABS068387C-A`) ที่ต่างจาก `CUST_BOM_REVISION` → `HOLD:REVISION_CONFLICT` + `hold_detail` | Mark Eng 09 Q2; ADI2606077/078 (Oracle rev B, mark ตรงกับ rev C); ทั้งปีขัดกัน 6 ELR — 3 เป็นแค่รูปแบบ `ENG-1` vs `B-ENG-1` จึงไม่นับ | `mark_engine/documents/resolve.py` |
| 9 | R07-OCRFIX-6 | generate (P50) | `(LOT) NUMBERU\d` → `""` (ลบทั้งช่อง) | ตัดเฉพาะ suffix `U\d` (`XXU1` → `XX`, `LOT NUMBERU1` → `LOT NUMBER` แล้ว R07-ADI1039-LOT → `XX`) | catalog pattern `(X+)U\d` → `` (ตัด suffix เท่านั้น); รีวิวเก่า `diff_review_2026-11-04.csv` note "ตีความผิดปะ"; 5 บรรทัด DIFF → MATCH_LOT (ADI2604002/026, ADI2605003/007/008 BOTTOM 2) | `mark_engine/encode/ocr_fix.py` |
| 10 | R05-BOM / revision (resolver, D-24) | gate | เทียบ revision ไฟล์กับ `CUST_BOM_REVISION` อย่างเดียว | revision ของ Oracle = ตัวอักษรท้าย `CUST_BOM_NO` + `-` + `CUST_BOM_REVISION` เมื่อ BOM มีตัวอักษรต่อท้าย (`ABS034529D` + `ENG-1` = `D-ENG-1`) | ผู้ใช้ยืนยัน 2026-11-04: Oracle แยก revision เก็บสองช่อง; 11 ELR (46 บรรทัด) RULE_CONFLICT → MATCH | `mark_engine/documents/resolve.py` `_oracle_revision` |
| 11 | R04-REOCR-LEGEND / R04-REOCR-LOGO (re-OCR, D-27) | process | ไม่ใช้ re-OCR (R0 เลือกแถว trim_logo ด้วย human GT) | ใช้ผล re-OCR ที่ cache ไว้ (`ocr_reocr.csv`) เมื่อค่าใหม่ต่างจากเดิมและ score ≥ 0.9 — ไม่ดู `kept`/`gt` | `legend_value`: อ่านเฉพาะค่าหลัง `LINE n:` (`LHYBN`→`LHYB`, `UJHN`→`UJH`); `trim_logo`: ตัดโลโก้ออกก่อนอ่าน (`SAD`→`ADW`); ตรวจกับภาพจริงแล้ว 5 บรรทัด → MATCH | `mark_engine/adapters/snapshot.py` `_load_reocr` |

ข้อ 4 อยู่ใน Comparison Engine เท่านั้น (ไม่แก้ `ExpectedMark`) — expected ยังเป็น `THAILAND` ตาม ADI1039
Mark Eng ยืนยันแล้ว (D-22): ยอมรับเป็น MATCH แต่ต้องแสดง warning
