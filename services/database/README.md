# Database deployment

The DBA reviews and applies the **UP** section of `migrations/0004_line_result_review_columns.sql` on the target PostgreSQL database. It adds review columns and a per-ELR `job_result` table so jobs that fail before line comparison are not lost. It has already been applied to the `mark_web` target used for run 17; check target state before applying it elsewhere. The commented DOWN section removes data and is not part of normal deployment.

After the migration and a verified frozen run, the engine host runs `python -m scripts.load_r1_to_pg <private-run-dir> --period "2026-07..2026-11 holdout" --note "frozen FREEZE-R1"` as a rollback-only dry run, then uses `--commit` when ready. It creates a new run and leaves old runs intact. Run 17 has already been loaded; do not reload it. The database password is supplied through the environment on that host; it is never packaged with the migration or AI worker.
