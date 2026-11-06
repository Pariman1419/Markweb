-- 0008_manual_revision_down.sql — Rollback 0008
-- DOWN: apply with DBA / postgres privileges on mark_web (transaction managed by apply script)
-- NOTE: If multiple revisions with identical (elr_no, oracle_fp, docs_fp) exist where changed = 'manual',
-- re-adding the unique constraint elr_revision_fp_unique will fail until duplicate manual revisions are removed.

drop index if exists mark_app.notification_unread_unique;

drop index if exists mark_app.elr_revision_fp_auto_unique;

alter table mark_app.elr_revision
  add constraint elr_revision_fp_unique unique (elr_no, oracle_fp, docs_fp);
