-- R1 review checks — คิวรี่ตรวจหัวข้อในหน้า "R1 Line Review"
-- ส่วน A: PostgreSQL mark_web (schema mark_logic) — ผล R1 ที่โหลดไว้ (run ล่าสุด = run 8)
-- ส่วน B: Oracle ACTLDBA.ELR (read-only) — ดูค่าต้นทาง revision / PRODUCT_NO / TOP_MARK
-- cause_detail ของ R1 = "rules=…; flags=A;B (หลาย flag คั่นด้วย ; ไม่มีเว้นวรรค); detail=…; warning=…; hold_detail=…; layout_source=…; parity_vs_r0=…"

-- =====================================================================
-- ส่วน A — PostgreSQL mark_web
-- =====================================================================

-- A0. run ทั้งหมด และ run ล่าสุด
SELECT run_id, run_at, git_commit, lines_measured, lines_match, match_pct, lines_diff, left(note, 120) AS note
FROM mark_logic.run ORDER BY run_id;

-- A1. สรุปสถานะของ run ล่าสุด
SELECT status, count(*) AS lines
FROM mark_logic.line_result
WHERE run_id = (SELECT max(run_id) FROM mark_logic.run)
GROUP BY status ORDER BY lines DESC;

-- A2. NEEDS_REVIEW แยกตามสาเหตุ (flag)
--     บรรทัดหนึ่งมีได้หลาย flag; SLR_OVERRIDE เป็น flag ประกอบ (บรรทัดนี้ใช้ค่าจาก SLR) ไม่ใช่สาเหตุที่ต้องรีวิว
SELECT f.flag, count(*) AS lines, count(DISTINCT l.elr_no) AS elrs,
       sum((replace(coalesce(final_mark,''),' ','') = replace(coalesce(db_mark,''),' ',''))::int) AS exp_eq_oracle
FROM mark_logic.line_result l
CROSS JOIN LATERAL regexp_split_to_table(substring(l.cause_detail FROM 'flags=(.*?)(?:; [a-z_0-9]+=|$)'), ';') AS f(flag)
WHERE l.run_id = (SELECT max(run_id) FROM mark_logic.run) AND l.status = 'NEEDS_REVIEW'
GROUP BY f.flag ORDER BY lines DESC;

-- A3. RULE_CONFLICT ราย ELR (เทียบ revision ใน ส่วน B3)
SELECT elr_no, abs_no, count(*) AS lines,
       sum((replace(coalesce(final_mark,''),' ','') = replace(coalesce(db_mark,''),' ',''))::int) AS exp_eq_oracle
FROM mark_logic.line_result
WHERE run_id = (SELECT max(run_id) FROM mark_logic.run) AND cause_detail LIKE '%RULE_CONFLICT%'
GROUP BY elr_no, abs_no ORDER BY elr_no;

-- A4. รายบรรทัดของหัวข้อใดหัวข้อหนึ่ง (เปลี่ยนรายชื่อ ELR ตามแท็บ)
--     RC1 ชื่อ ENG-n | RC2 rev B แต่มีแค่ rev C | RC3 PRODUCT_NO คนละ ABS
SELECT elr_no, side, line_no, final_mark AS expected_r1, db_mark AS oracle, status, cause_detail
FROM mark_logic.line_result
WHERE run_id = (SELECT max(run_id) FROM mark_logic.run)
  AND elr_no IN ('ADI2603024','ADI2603025','ADI2603026','ADI2603027','ADI2603028','ADI2603029','ADI2603030',
                 'ADI2603072','ADI2603073','ADI2603074','ADI2603075','ADI2603076')   -- RC2
ORDER BY elr_no, side DESC, line_no;

-- A5. DIFF ทั้งหมดของ run ล่าสุด
SELECT elr_no, side, line_no, final_mark AS expected_r1, db_mark AS oracle,
       substring(cause_detail FROM 'layout_source=([^;]*)') AS layout_source
FROM mark_logic.line_result
WHERE run_id = (SELECT max(run_id) FROM mark_logic.run) AND status = 'DIFF'
ORDER BY elr_no, side DESC, line_no;

-- A6. HOLD แยกตามสาเหตุ (1 แถวต่อ ELR) + สาเหตุละเอียด (hold_detail)
--     นับเฉพาะ ELR ที่มีบรรทัดใน Oracle — ELR ที่ Oracle ไม่มี mark เลยจะไม่มีแถว (jobs.csv นับได้มากกว่า 1–2 ELR)
SELECT cause AS hold_reason, count(DISTINCT elr_no) AS elrs,
       string_agg(DISTINCT substring(cause_detail FROM 'hold_detail=([^;]*)'), ' | ') AS hold_detail
FROM mark_logic.line_result
WHERE run_id = (SELECT max(run_id) FROM mark_logic.run) AND status = 'NOT_MEASURABLE'
GROUP BY cause ORDER BY elrs DESC;

-- A7. MATCH ที่มี warning (ชื่อประเทศแบบย่อ, D-22)
SELECT elr_no, side, line_no, final_mark AS expected_r1, db_mark AS oracle,
       substring(cause_detail FROM 'warning=([^;]*)') AS warning
FROM mark_logic.line_result
WHERE run_id = (SELECT max(run_id) FROM mark_logic.run) AND cause_detail LIKE '%warning=%'
ORDER BY elr_no;

-- A8. เทียบสองรอบ: บรรทัดที่สถานะเปลี่ยนระหว่าง run 7 กับ run 8
SELECT a.elr_no, a.side, a.line_no, a.status AS run7, b.status AS run8, a.final_mark AS exp7, b.final_mark AS exp8, b.db_mark AS oracle
FROM mark_logic.line_result a
JOIN mark_logic.line_result b USING (elr_no, abs_no, side, line_no)
WHERE a.run_id = 7 AND b.run_id = 8 AND (a.status <> b.status OR coalesce(a.final_mark,'') <> coalesce(b.final_mark,''))
ORDER BY a.elr_no, a.side DESC, a.line_no;

-- A9. เทียบกับ R0 baseline (run 3) ราย ELR ที่สนใจ
SELECT r.run_id, r.elr_no, r.abs_no, r.side, r.line_no, r.final_mark, r.db_mark, r.status, r.cause
FROM mark_logic.line_result r
WHERE r.run_id IN (3, (SELECT max(run_id) FROM mark_logic.run)) AND r.elr_no = 'ADI2603024'
ORDER BY r.side DESC, r.line_no, r.run_id;

-- A10. คำตัดสินคนจากรีวิวเก่า (R0) ที่โหลดไว้ใน review_verdict
SELECT * FROM mark_logic.review_verdict ORDER BY 1, 2 LIMIT 200;


-- =====================================================================
-- ส่วน B — Oracle ACTLDBA.ELR (read-only; ใช้ @actl ถ้ารันผ่าน DB link)
-- =====================================================================

-- B1. revision ใน Oracle ของทุกหัวข้อ RULE_CONFLICT + REVISION_CONFLICT
SELECT e.ELR_NO, e.CUST_BOM_NO, e.CUST_BOM_REVISION, e.PRODUCT_NO, e.CUST_REQ_NO, e.IMPORT_DATE, e.STATUS
FROM ACTLDBA.ELR e
WHERE e.ELR_NO IN (
  -- RC1 ชื่อ ENG-n
  'ADI2601052','ADI2601053','ADI2601054','ADI2601103','ADI2602033','ADI2602098','ADI2602100','ADI2602142','ADI2602161','ADI2603081','ADI2606066',
  -- RC2 Oracle rev B แต่มีแค่ rev C
  'ADI2603024','ADI2603025','ADI2603026','ADI2603027','ADI2603028','ADI2603029','ADI2603030','ADI2603072','ADI2603073','ADI2603074','ADI2603075','ADI2603076',
  -- RC3 PRODUCT_NO คนละ ABS
  'ADI2602126','ADI2606076',
  -- REVISION_CONFLICT (D-23)
  'ADI2606077','ADI2606078')
ORDER BY e.ELR_NO;

-- B2. ELR อื่นที่ใช้ BOM เดียวกัน — revision ที่ Oracle เคยบันทึก (ช่วยตัดสิน RC2)
SELECT e.CUST_BOM_NO, e.CUST_BOM_REVISION, count(*) AS elrs, min(e.ELR_NO) AS first_elr, max(e.ELR_NO) AS last_elr,
       min(e.IMPORT_DATE) AS first_import, max(e.IMPORT_DATE) AS last_import
FROM ACTLDBA.ELR e
WHERE e.CUST_CODE = 'ADI' AND e.CUST_BOM_NO IN ('ABS065744','ABS065954','ABS033106','ABS034529','ABS064180','ABS068387')
GROUP BY e.CUST_BOM_NO, e.CUST_BOM_REVISION
ORDER BY e.CUST_BOM_NO, e.CUST_BOM_REVISION;

-- B3. ทั้งปี: CUST_BOM_REVISION ขัดกับ revision ใน PRODUCT_NO (ตรรกะเดียวกับ HOLD REVISION_CONFLICT)
SELECT e.ELR_NO, e.CUST_BOM_NO, e.CUST_BOM_REVISION, e.PRODUCT_NO,
       REGEXP_SUBSTR(e.PRODUCT_NO, 'ABS' || REGEXP_SUBSTR(e.CUST_BOM_NO, '\d{6}') || '([A-Z]{1,2})(-|$)', 1, 1, NULL, 1) AS pn_rev
FROM ACTLDBA.ELR e
WHERE e.CUST_CODE = 'ADI'
  AND e.ELR_NO LIKE 'ADI26%'
  AND REGEXP_LIKE(e.CUST_BOM_REVISION, '^[A-Z]{1,2}$')
  AND REGEXP_SUBSTR(e.PRODUCT_NO, 'ABS' || REGEXP_SUBSTR(e.CUST_BOM_NO, '\d{6}') || '([A-Z]{1,2})(-|$)', 1, 1, NULL, 1) IS NOT NULL
  AND REGEXP_SUBSTR(e.PRODUCT_NO, 'ABS' || REGEXP_SUBSTR(e.CUST_BOM_NO, '\d{6}') || '([A-Z]{1,2})(-|$)', 1, 1, NULL, 1) <> e.CUST_BOM_REVISION
ORDER BY e.ELR_NO;

-- B4. PRODUCT_NO ชี้ ABS คนละเลขกับ CUST_BOM_NO (หัวข้อ RC3)
SELECT e.ELR_NO, e.CUST_BOM_NO, e.CUST_BOM_REVISION, e.PRODUCT_NO
FROM ACTLDBA.ELR e
WHERE e.CUST_CODE = 'ADI' AND e.ELR_NO LIKE 'ADI26%'
  AND REGEXP_LIKE(e.PRODUCT_NO, 'ABS\d{6}')
  AND REGEXP_SUBSTR(e.PRODUCT_NO, 'ABS(\d{6})', 1, 1, NULL, 1) <> REGEXP_SUBSTR(e.CUST_BOM_NO, '\d{6}')
ORDER BY e.ELR_NO;

-- B5. mark ที่ Oracle บันทึกของ ELR ใดก็ได้ (ใส่ ELR ที่ต้องการ)
SELECT e.ELR_NO, e.CUST_BOM_NO, e.CUST_BOM_REVISION, e.PRODUCT_NO,
       e.TOP_MARK1, e.TOP_MARK2, e.TOP_MARK3, e.TOP_MARK4, e.TOP_MARK5,
       e.BACK_MARK1, e.BACK_MARK2, e.BACK_MARK3, e.BACK_MARK4, e.BACK_MARK5,
       e.MARK_REMARK, e.MARK_REQUIRE
FROM ACTLDBA.ELR e
WHERE e.ELR_NO IN ('ADI2605086','ADI2605087','ADI2605088','ADI2602044','ADI2602050');  -- รีวิวเก่า "Oracle ผิด"
