-- 0005_mark_app_trial.sql — Trial schema for mark_app (Phase 2 Trial)
-- UP: run with DBA privileges on mark_web
begin;

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'mark_app') then
    create role mark_app login;
  end if;
end $$;

create schema if not exists mark_app;

-- 1. app_user
create table if not exists mark_app.app_user (
  user_id bigint generated always as identity primary key,
  username text not null,
  display_name text not null,
  role text not null check (role in ('engineer', 'mark_eng_approver', 'admin')),
  password_hash text not null,
  active boolean not null default true,
  failed_count int not null default 0,
  locked_until timestamptz,
  created_at timestamptz not null default now()
);

create unique index if not exists app_user_lower_username_idx on mark_app.app_user (lower(username));

-- 2. user_session
create table if not exists mark_app.user_session (
  token_hash text primary key,
  user_id bigint not null references mark_app.app_user(user_id) on delete cascade,
  csrf_hash text not null,
  expires_at timestamptz not null,
  last_seen_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create index if not exists user_session_user_id_idx on mark_app.user_session (user_id);
create index if not exists user_session_expires_at_idx on mark_app.user_session (expires_at);

-- 3. api_token
create table if not exists mark_app.api_token (
  token_id bigint generated always as identity primary key,
  name text not null,
  token_hash text not null unique,
  scopes text[] not null,
  created_by bigint not null references mark_app.app_user(user_id),
  created_at timestamptz not null default now(),
  expires_at timestamptz,
  last_used_at timestamptz
);

-- 4. elr_snapshot
create table if not exists mark_app.elr_snapshot (
  run_id bigint not null,
  elr_no text not null,
  top_mark_id bigint,
  layout_code text,
  line_extra jsonb,
  mark_remark text,
  mark_require text,
  top_template_remark text,
  oracle_top_raw jsonb,
  layout_cells jsonb,
  abs_file text,
  abs_sha256 text,
  image_path text,
  slr_files text[],
  slr_instructions jsonb,
  import_date timestamptz not null default now(),
  primary key (run_id, elr_no),
  foreign key (run_id, elr_no) references mark_logic.job_result(run_id, elr_no)
);

create index if not exists elr_snapshot_run_abs_file_idx on mark_app.elr_snapshot (run_id, abs_file);

-- 5. line_review
create table if not exists mark_app.line_review (
  review_id bigint generated always as identity primary key,
  run_id bigint not null,
  elr_no text not null,
  abs_no text not null,
  side text not null check (side = 'TOP'),
  line_no int not null,
  reason text check (reason in ('DB_WRONG','OCR_WRONG','SYMBOL_WRONG','SLR_ECN_CHANGE','RULE_MISSING','LAYOUT_WRONG','OTHER')),
  note text,
  corrected_mark text,
  reviewer_id bigint not null references mark_app.app_user(user_id),
  is_draft boolean not null default false,
  created_at timestamptz not null default now(),
  foreign key (run_id, elr_no, abs_no, side, line_no) references mark_logic.line_result(run_id, elr_no, abs_no, side, line_no)
);

create index if not exists line_review_lookup_idx on mark_app.line_review (run_id, elr_no, line_no, created_at desc);

-- 6. approval
create table if not exists mark_app.approval (
  approval_id bigint generated always as identity primary key,
  run_id bigint not null,
  elr_no text not null,
  decision text not null check (decision in ('APPROVED', 'REJECTED')),
  user_id bigint not null references mark_app.app_user(user_id),
  created_at timestamptz not null default now(),
  foreign key (run_id, elr_no) references mark_logic.job_result(run_id, elr_no)
);

create index if not exists approval_lookup_idx on mark_app.approval (run_id, elr_no, created_at desc);

-- 7. audit_log
create table if not exists mark_app.audit_log (
  audit_id bigint generated always as identity primary key,
  user_id bigint references mark_app.app_user(user_id),
  action text not null,
  run_id bigint,
  elr_no text,
  line_no int,
  detail jsonb,
  created_at timestamptz not null default now()
);

create index if not exists audit_log_created_at_idx on mark_app.audit_log (created_at);
create index if not exists audit_log_run_elr_idx on mark_app.audit_log (run_id, elr_no);
create index if not exists audit_log_user_created_idx on mark_app.audit_log (user_id, created_at);

-- Grants
grant usage on schema mark_app to mark_app;
grant select on all tables in schema mark_logic to mark_app;
grant select, insert on mark_app.line_review, mark_app.approval, mark_app.audit_log to mark_app;
grant select, insert, update, delete on mark_app.app_user, mark_app.user_session, mark_app.api_token, mark_app.elr_snapshot to mark_app;
grant usage, select on all sequences in schema mark_app to mark_app;

commit;

-- DOWN (destructive, manual only):
-- begin;
-- drop schema if exists mark_app cascade;
-- commit;
