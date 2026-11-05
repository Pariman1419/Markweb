-- 0007_auto_review.sql — Auto Review Flow: history, queue, worker, and notifications
-- UP: apply with DBA / postgres privileges on mark_web
begin;

-- 1. Role mark_worker
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'mark_worker') then
    create role mark_worker login;
  end if;
end $$;

-- Ensure mark_app schema exists
create schema if not exists mark_app;

-- 2. mark_app.scan
create table if not exists mark_app.scan (
  scan_id bigint generated always as identity primary key,
  source text not null check (source in ('airflow', 'initial', 'user')),
  requested_by text,
  from_ts timestamptz,
  to_ts timestamptz,
  elr_no text,
  counts jsonb,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  error text
);

create index if not exists scan_started_at_idx on mark_app.scan (started_at desc);
create index if not exists scan_elr_no_idx on mark_app.scan (elr_no) where elr_no is not null;

-- 3. mark_app.elr_revision
create table if not exists mark_app.elr_revision (
  elr_no text not null,
  revision int not null,
  oracle_fp text not null,
  docs_fp text not null,
  version_fp text not null,
  result_fp text not null,
  changed text not null check (changed in ('new', 'oracle', 'docs', 'both', 'manual')),
  changed_fields text[],
  result_unchanged boolean not null default false,
  run_id bigint not null references mark_logic.run(run_id),
  created_at timestamptz not null default now(),
  primary key (elr_no, revision),
  constraint elr_revision_fp_unique unique (elr_no, oracle_fp, docs_fp)
);

create index if not exists elr_revision_run_idx on mark_app.elr_revision (run_id);
create index if not exists elr_revision_created_at_idx on mark_app.elr_revision (created_at desc);

-- 4. mark_app.work_item
create table if not exists mark_app.work_item (
  item_id bigint generated always as identity primary key,
  scan_id bigint references mark_app.scan(scan_id),
  elr_no text not null,
  state text not null check (state in ('queued', 'running', 'done', 'retry', 'failed')),
  reason text not null check (reason in ('scan', 'user', 'recheck', 'retry_docs')),
  attempts int not null default 0,
  next_attempt_at timestamptz not null default now(),
  revision int,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Partial unique index: exactly one work_item active per ELR
create unique index if not exists work_item_active_elr_idx on mark_app.work_item (elr_no)
  where state in ('queued', 'running', 'retry');

create index if not exists work_item_state_next_idx on mark_app.work_item (state, next_attempt_at);
create index if not exists work_item_scan_id_idx on mark_app.work_item (scan_id);

-- 5. mark_app.notification
create table if not exists mark_app.notification (
  notification_id bigint generated always as identity primary key,
  elr_no text not null,
  run_id bigint references mark_logic.run(run_id),
  revision int,
  kind text not null check (kind in ('not_in_system', 'not_in_oracle', 'not_eligible', 'hold', 'failed', 'inference_failed', 'changed_after_approve', 'scan_failed')),
  message text not null,
  created_at timestamptz not null default now(),
  read_by text,
  read_at timestamptz,
  constraint notification_elr_kind_rev_unique unique (elr_no, kind, revision)
);

create index if not exists notification_created_at_idx on mark_app.notification (created_at desc);
create index if not exists notification_unread_idx on mark_app.notification (read_at) where read_at is null;

-- 6. View mark_app.latest_job_result
create or replace view mark_app.latest_job_result as
select distinct on (r.elr_no)
  r.elr_no,
  r.revision,
  r.run_id,
  r.created_at as revision_created_at,
  r.changed,
  r.result_unchanged,
  j.processing_status,
  j.hold_reason,
  j.hold_detail,
  j.review_detail,
  j.verification_status,
  j.approval_status,
  j.layout_source,
  j.abs_no
from mark_app.elr_revision r
join mark_logic.job_result j on j.run_id = r.run_id and j.elr_no = r.elr_no
order by r.elr_no, r.revision desc;

-- 7. Permissions and Grants
-- Worker role
grant usage on schema mark_app to mark_worker;
grant usage on schema mark_logic to mark_worker;

grant select, insert on mark_logic.run, mark_logic.job_result, mark_logic.line_result to mark_worker;
grant select on all tables in schema mark_logic to mark_worker;
revoke update, delete, truncate on all tables in schema mark_logic from mark_worker;

grant select, insert, update, delete on mark_app.work_item to mark_worker;
grant select, insert on mark_app.scan, mark_app.elr_revision, mark_app.notification, mark_app.elr_snapshot to mark_worker;
grant usage, select on all sequences in schema mark_app to mark_worker;
grant usage, select on all sequences in schema mark_logic to mark_worker;

-- API role (mark_app)
grant select on mark_app.scan, mark_app.elr_revision, mark_app.work_item, mark_app.notification to mark_app;
grant select on mark_app.latest_job_result to mark_app;
grant insert on mark_app.scan, mark_app.work_item to mark_app;
grant update (read_by, read_at) on mark_app.notification to mark_app;
grant usage, select on all sequences in schema mark_app to mark_app;

commit;
