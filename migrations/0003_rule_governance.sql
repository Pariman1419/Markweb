-- 0003_rule_governance — versioned rules with provenance class and approvals (DRAFT, not applied)
-- Seeds RV-2026-11-04-R0 as a COPY of mark_logic.logic_rule. mark_logic.logic_rule itself is not changed.

-- UP ---------------------------------------------------------------------------------------------------------
begin;

create schema mark_rules authorization mark_owner;

create table mark_rules.rule_version (
  rule_version_id text primary key,
  created_at timestamptz not null default now(),
  created_by text not null,
  frozen boolean not null default false,
  content_md5 text,
  note text);

create table mark_rules.rule (
  rule_version_id text not null references mark_rules.rule_version,
  rule_id text not null,
  step_no text, step_name text, rule_type text, title text, pattern text, replacement text, description text,
  source text, evidence text, status text, lines_decided int, implemented_in text, sort_order int,
  rule_stage text not null check (rule_stage in ('generate','compare','gate','process')),
  document_scope text, priority int, rule_origin text, effective_revision text,
  provenance_class text not null check (provenance_class in ('SPEC_DERIVED','ORACLE_DERIVED','EXPERIMENTAL','PENDING_VERIFICATION')),
  provenance_evidence text,
  oracle_influence text,              -- how the legacy code used TOP/BACK_MARK (docs/implementation/01 §3)
  primary key (rule_version_id, rule_id));

create table mark_rules.rule_approval (
  rule_version_id text not null, rule_id text not null,
  decision text not null check (decision in ('APPROVED','APPROVED_COMPARE_ONLY','APPROVED_WITH_CONDITION','REJECTED','PENDING')),
  condition text,
  approver text not null, approved_at timestamptz not null default now(), note text,
  foreign key (rule_version_id, rule_id) references mark_rules.rule);

-- frozen versions are read-only
create function mark_rules.block_frozen() returns trigger language plpgsql as $$
begin
  if exists (select 1 from mark_rules.rule_version v where v.rule_version_id = coalesce(old.rule_version_id, new.rule_version_id) and v.frozen) then
    raise exception 'rule_version % is frozen', coalesce(old.rule_version_id, new.rule_version_id);
  end if;
  return coalesce(new, old);
end $$;
create trigger rule_frozen before update or delete on mark_rules.rule for each row execute function mark_rules.block_frozen();

-- seed: copy of the production rules at R0 + provenance class from the Phase 0 audit (01-rule-provenance-audit.md)
insert into mark_rules.rule_version (rule_version_id, created_by, note)
values ('RV-2026-11-04-R0', 'phase0-migration', 'copy of mark_logic.logic_rule at R0 (run 3)');

insert into mark_rules.rule
select 'RV-2026-11-04-R0', r.rule_id, r.step_no, r.step_name, r.rule_type, r.title, r.pattern, r.replacement, r.description,
       r.source, r.evidence, r.status, r.lines_decided, r.implemented_in, r.sort_order,
       r.rule_stage, r.document_scope, r.priority, r.rule_origin, r.effective_revision,
       p.cls, 'docs/implementation/01-rule-provenance-audit.md', p.infl
from mark_logic.logic_rule r
join (values
  ('R01-ORACLE','SPEC_DERIVED','read only'),
  ('R02-NAS-PATH','PENDING_VERIFICATION',null),
  ('R03-ABS-SLR-GATE','PENDING_VERIFICATION',null),
  ('R03-NO-LINE-LABEL','EXPERIMENTAL',null),
  ('R03-ONE-ABS','ORACLE_DERIVED','selects the ABS by Oracle match count'),
  ('R04-ABS-PAGE','EXPERIMENTAL',null),
  ('R04-OCR','EXPERIMENTAL',null),
  ('R04-REOCR-LEGEND','EXPERIMENTAL',null),
  ('R04-REOCR-LOGO','PENDING_VERIFICATION','re-read kept only when equal to human GT'),
  ('R04-SLR-LINE','SPEC_DERIVED','candidate chosen by Oracle match; applied only on DIFF lines'),
  ('R04-SLR-LITERAL','ORACLE_DERIVED','writes the Oracle value into fused'),
  ('R04-SLR-LOT','SPEC_DERIVED','compare'),
  ('R04-SLR-QUAL','PENDING_VERIFICATION','consistency check against SLR line value'),
  ('R04-SLR-SECTION','SPEC_DERIVED',null),
  ('R04-SLR-TOKENS','SPEC_DERIVED','regex matched against Oracle, no placeholder generated'),
  ('R04-YOLO','EXPERIMENTAL',null),
  ('R05-BOM','SPEC_DERIVED','reads CUST_BOM_NO (metadata)'),
  ('R06-GRAPHIC-LINE','EXPERIMENTAL',null),
  ('R06-LEGEND','EXPERIMENTAL',null),
  ('R06-LINE-LABEL','EXPERIMENTAL',null),
  ('R06-MAX-LINES','PENDING_VERIFICATION',null),
  ('R06-RIGHT-LABEL','EXPERIMENTAL',null),
  ('R06-SHIFT','ORACLE_DERIVED','compare'),
  ('R06-TYPE-LAYOUT','PENDING_VERIFICATION','reads MARK_ID.TYPE_CODE (metadata)'),
  ('R07-ADI1039-COO','SPEC_DERIVED',null),
  ('R07-ADI1039-LOT','SPEC_DERIVED',null),
  ('R07-DB-PACKAGE','ORACLE_DERIVED','compare'),
  ('R07-GRAPHIC-BLANK','SPEC_DERIVED','graphics dropped before compare'),
  ('R07-OCRFIX-1','EXPERIMENTAL',null), ('R07-OCRFIX-2','EXPERIMENTAL',null), ('R07-OCRFIX-3','EXPERIMENTAL',null),
  ('R07-OCRFIX-4','EXPERIMENTAL',null), ('R07-OCRFIX-5','EXPERIMENTAL',null), ('R07-OCRFIX-6','EXPERIMENTAL',null),
  ('R07-OCRFIX-7','EXPERIMENTAL',null), ('R07-OCRFIX-8','PENDING_VERIFICATION',null),
  ('R07-PIN-NOTE','ORACLE_DERIVED','removes @ from the Oracle value'),
  ('R07-PLACEHOLDER','ORACLE_DERIVED','compare; MATCH_LOT set before SLR lot check'),
  ('R07-REMARK-CARET','ORACLE_DERIVED','fitted on Oracle history'),
  ('R07-REMARK-LOGO','ORACLE_DERIVED','fitted on Oracle history'),
  ('R07-REMARK-PIN','ORACLE_DERIVED','fitted on Oracle history'),
  ('R07-SKIP-MARK','SPEC_DERIVED','applied only when Oracle line is empty'),
  ('R07-SYMBOL-ADI','SPEC_DERIVED',null),
  ('R08-REVIEW','SPEC_DERIVED','compare')
) as p(rule_id, cls, infl) on p.rule_id = r.rule_id;

do $$ begin
  if (select count(*) from mark_rules.rule where rule_version_id = 'RV-2026-11-04-R0') <> (select count(*) from mark_logic.logic_rule) then
    raise exception 'not every mark_logic.logic_rule row has a provenance class — update the VALUES list';
  end if;
end $$;

-- owner-delegated decisions 2026-11-04 (docs/implementation/07-open-decisions.md, D-06)
insert into mark_rules.rule_approval (rule_version_id, rule_id, decision, condition, approver, note) values
 ('RV-2026-11-04-R0','R07-REMARK-CARET','APPROVED_WITH_CONDITION','generate; conflict with YOLO graphic -> NEEDS_REVIEW','owner-delegated (Kam) 2026-11-04','MARK_REMARK is an allowed input'),
 ('RV-2026-11-04-R0','R07-REMARK-LOGO','APPROVED_WITH_CONDITION','generate; conflict with YOLO graphic -> NEEDS_REVIEW','owner-delegated (Kam) 2026-11-04',null),
 ('RV-2026-11-04-R0','R07-REMARK-PIN','APPROVED_WITH_CONDITION','generate; YOLO sees pin dot but remark omits @ -> NEEDS_REVIEW','owner-delegated (Kam) 2026-11-04','absence rule'),
 ('RV-2026-11-04-R0','R07-PIN-NOTE','REJECTED',null,'owner-delegated (Kam) 2026-11-04','re-implement as ABS drawing-note rule, no Oracle input'),
 ('RV-2026-11-04-R0','R04-SLR-LITERAL','REJECTED',null,'owner-delegated (Kam) 2026-11-04','compare may flag ORACLE_VALUE_IN_SLR -> NEEDS_REVIEW, never MATCH'),
 ('RV-2026-11-04-R0','R06-SHIFT','APPROVED_COMPARE_ONLY',null,'owner-delegated (Kam) 2026-11-04',null),
 ('RV-2026-11-04-R0','R07-PLACEHOLDER','APPROVED_WITH_CONDITION','compare only; lot digits must equal ADI1039 lot_slice of SLR Scheduled Lot ID; date code must be a valid YYWW, else NEEDS_REVIEW','owner-delegated (Kam) 2026-11-04',null),
 ('RV-2026-11-04-R0','R07-DB-PACKAGE','APPROVED_COMPARE_ONLY',null,'owner-delegated (Kam) 2026-11-04',null),
 ('RV-2026-11-04-R0','R03-ONE-ABS','REJECTED',null,'owner-delegated (Kam) 2026-11-04','replaced by Document Resolver'),
 ('RV-2026-11-04-R0','R04-SLR-QUAL','APPROVED_WITH_CONDITION','consistency check only; never generates','owner-delegated (Kam) 2026-11-04',null),
 ('RV-2026-11-04-R0','R07-OCRFIX-8','APPROVED_WITH_CONDITION','X*n placeholder; real digits in Oracle -> NEEDS_REVIEW','owner-delegated (Kam) 2026-11-04','serial is not verifiable from SLR');

update mark_rules.rule_version
   set frozen = true,
       content_md5 = (select md5(string_agg(t::text, '|' order by t.rule_id)) from mark_rules.rule t where t.rule_version_id = 'RV-2026-11-04-R0')
 where rule_version_id = 'RV-2026-11-04-R0';

grant usage on schema mark_rules to mark_app, mark_rules_admin, mark_readonly;
grant select on all tables in schema mark_rules to mark_app, mark_readonly;
grant select, insert on mark_rules.rule_version, mark_rules.rule, mark_rules.rule_approval to mark_rules_admin;

commit;

-- DOWN -------------------------------------------------------------------------------------------------------
-- begin; drop schema mark_rules cascade; commit;
