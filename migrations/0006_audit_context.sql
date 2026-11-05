-- 0006_audit_context.sql — Add client_ip and request_id to mark_app.audit_log
-- UP: run with DBA privileges or mark_app owner on mark_web
begin;

alter table mark_app.audit_log add column if not exists client_ip inet;
alter table mark_app.audit_log add column if not exists request_id text;
create index if not exists audit_log_action_created_idx on mark_app.audit_log (action, created_at);

commit;
