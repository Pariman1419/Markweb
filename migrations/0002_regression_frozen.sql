-- 0002_regression_frozen — copy baseline R0 (run 3) and R0-legacy (run 2) into a locked schema (DRAFT, not applied)
-- Copies only. No row in mark_logic is changed or deleted.

-- UP ---------------------------------------------------------------------------------------------------------
begin;
set transaction isolation level repeatable read;

create schema mark_regression authorization mark_owner;

-- R0 = run 3 (code: repo mark tag regression-r0-2026-11-04, commit d7d788e)
create table mark_regression.r0_run            as select * from mark_logic.run            where run_id = 3;
create table mark_regression.r0_line_result    as select * from mark_logic.line_result    where run_id = 3;
create table mark_regression.r0_stage_accuracy as select * from mark_logic.stage_accuracy where run_id = 3;
create table mark_regression.r0_logic_rule           as select * from mark_logic.logic_rule;
create table mark_regression.r0_symbol_profile       as select * from mark_logic.symbol_profile;
create table mark_regression.r0_encoder_alias        as select * from mark_logic.encoder_alias;
create table mark_regression.r0_adi1039_token        as select * from mark_logic.adi1039_token;
create table mark_regression.r0_remark_profile       as select * from mark_logic.remark_profile;
create table mark_regression.r0_slr_instruction      as select * from mark_logic.slr_instruction;
create table mark_regression.r0_slr_line_instruction as select * from mark_logic.slr_line_instruction;
create table mark_regression.r0_elr_document         as select * from mark_logic.elr_document;
create table mark_regression.r0_review_verdict       as select * from mark_logic.review_verdict;
create table mark_regression.r0_status_dictionary    as select * from mark_logic.status_dictionary;

-- R0-legacy = run 2 (the 529-ELR result; its reference tables were overwritten by run 3 — see artifacts JSON)
create table mark_regression.r0legacy_run         as select * from mark_logic.run         where run_id = 2;
create table mark_regression.r0legacy_line_result as select * from mark_logic.line_result where run_id = 2;

create table mark_regression.baseline_manifest (
  table_name text primary key, source_filter text, row_count bigint not null, content_md5 text not null,
  frozen_at timestamptz not null default now(), note text);

insert into mark_regression.baseline_manifest (table_name, source_filter, row_count, content_md5)
select c.relname, null, c.n, c.h from (
  select 'r0_line_result' relname, count(*) n, md5(string_agg(t::text, '|' order by t::text)) h from mark_regression.r0_line_result t
  union all select 'r0_logic_rule', count(*), md5(string_agg(t::text, '|' order by t::text)) from mark_regression.r0_logic_rule t
  union all select 'r0legacy_line_result', count(*), md5(string_agg(t::text, '|' order by t::text)) from mark_regression.r0legacy_line_result t
) c;

-- guard: abort if the expected row counts are not there
do $$ begin
  if (select count(*) from mark_regression.r0_line_result) <> 2381
     or (select count(*) from mark_regression.r0legacy_line_result) <> 2381
     or (select count(*) from mark_regression.r0_logic_rule) <> 44 then
    raise exception 'baseline row counts differ from Phase 0 audit (2381 / 2381 / 44)';
  end if;
end $$;

grant usage on schema mark_regression to mark_app, mark_rules_admin, mark_readonly;
grant select on all tables in schema mark_regression to mark_app, mark_rules_admin, mark_readonly;
revoke insert, update, delete, truncate on all tables in schema mark_regression from public, mark_app, mark_rules_admin, mark_readonly;

commit;

-- DOWN -------------------------------------------------------------------------------------------------------
-- begin; drop schema mark_regression cascade; commit;
