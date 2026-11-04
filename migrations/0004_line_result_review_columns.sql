-- UP: run this section only, with DBA privileges.
begin;
alter table mark_logic.line_result
  add column if not exists system_status text,
  add column if not exists final_status text,
  add column if not exists review_detail text,
  add column if not exists warning text,
  add column if not exists hold_detail text,
  add column if not exists layout_source text;
create table if not exists mark_logic.job_result (
  run_id bigint not null references mark_logic.run(run_id),
  elr_no text not null,
  processing_status text not null,
  hold_reason text,
  hold_detail text,
  review_detail text,
  verification_status text,
  approval_status text,
  layout_source text,
  abs_no text,
  primary key (run_id, elr_no)
);
commit;

-- DOWN (manual, destructive to these columns; do not run with UP):
-- begin;
-- drop table if exists mark_logic.job_result;
-- alter table mark_logic.line_result drop column if exists system_status,
--   drop column if exists final_status, drop column if exists review_detail,
--   drop column if exists warning, drop column if exists hold_detail,
--   drop column if exists layout_source;
-- commit;
