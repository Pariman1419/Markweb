# mark_web migrations

Status: migration 0004 UP was applied on 2026-11-05 to `10.151.28.2/mark_web`. The earlier Phase 0 drafts 0001–0003 have not been applied as part of this work.
Plan and rationale: `docs/implementation/05-database-migration-plan.md`.

| File | Purpose | Writes existing data? |
|---|---|---|
| `M0_baseline_snapshot.md` | how R0 was frozen (git tag + read-only CSV export) and the `pg_dump` command to run before M1 | no |
| `0001_roles.sql` | roles `mark_owner`, `mark_app`, `mark_rules_admin`, `mark_readonly`; revoke writes on `mark_logic` | privileges only |
| `0002_regression_frozen.sql` | schema `mark_regression`: copy of R0 (run 3) and R0-legacy (run 2 `line_result`), then revoke writes | no (copies) |
| `0003_rule_governance.sql` | schema `mark_rules`: versioned rules, provenance class, approvals; seeds `RV-2026-11-04-R0` | no (copies) |
| `0004_line_result_review_columns.sql` | adds nullable review fields to `mark_logic.line_result` and a per-run `job_result` table so failed jobs are retained | schema only; applied 2026-11-05 |
| `0005_mark_app_trial.sql` | creates `mark_app` schema (app_user, user_session, api_token, elr_snapshot, line_review, approval, audit_log) and grants | schema only |

Each `.sql` file has an `-- UP` section and a `-- DOWN` section. Run order: M0 → 0001 → 0002 → 0003, each in one transaction,
first on a copy of `mark_web`, by a person with the DBA password (not by an app account).

Secrets: passwords for the new roles are set with `\password <role>` in psql — never written in these files.
