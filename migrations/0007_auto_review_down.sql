-- 0007_auto_review_down.sql — Rollback for 0007_auto_review
-- DOWN: apply with DBA / postgres privileges on mark_web
begin;

-- Revoke permissions
revoke select on mark_app.latest_job_result from mark_app;
revoke select, insert on mark_app.scan, mark_app.work_item from mark_app;
revoke update (read_by, read_at) on mark_app.notification from mark_app;
revoke select on mark_app.elr_revision, mark_app.notification from mark_app;

revoke select, insert, update, delete on mark_app.work_item from mark_worker;
revoke select, insert on mark_app.scan, mark_app.elr_revision, mark_app.notification, mark_app.elr_snapshot from mark_worker;
revoke select, insert on mark_logic.run, mark_logic.job_result, mark_logic.line_result from mark_worker;
revoke select on all tables in schema mark_logic from mark_worker;
revoke usage on schema mark_app, mark_logic from mark_worker;

-- Drop view and tables in reverse dependency order
drop view if exists mark_app.latest_job_result;
drop table if exists mark_app.notification;
drop table if exists mark_app.work_item;
drop table if exists mark_app.elr_revision;
drop table if exists mark_app.scan;

-- Drop role mark_worker
drop role if exists mark_worker;

commit;
