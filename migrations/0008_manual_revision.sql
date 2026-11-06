-- 0008_manual_revision.sql — Allow manual rechecks without fingerprint uniqueness conflict and deduplicate unread notifications
-- UP: apply with DBA / postgres privileges on mark_web (transaction managed by apply script)

-- 1. Replace unique constraint on (elr_no, oracle_fp, docs_fp) with partial unique index excluding manual runs
alter table mark_app.elr_revision drop constraint if exists elr_revision_fp_unique;

create unique index if not exists elr_revision_fp_auto_unique
  on mark_app.elr_revision (elr_no, oracle_fp, docs_fp)
  where changed <> 'manual';

-- 2. Deduplicate unread notifications per ELR, kind, revision
create unique index if not exists notification_unread_unique
  on mark_app.notification (elr_no, kind, coalesce(revision, 0))
  where read_at is null;
