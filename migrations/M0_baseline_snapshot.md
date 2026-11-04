# M0 — Baseline snapshot R0

## Already done (2026-11-04, read-only)

| Item | Value |
|---|---|
| Code | repo `D:\CIM Project\mark`, local branch `phase0/regression-r0`, commit `d7d788e6b9d3c8c975b94747e4be6af15021cb05`, annotated tag `regression-r0-2026-11-04` (not pushed — the remote is GitHub and the commit contains customer ABS preview images) |
| DB run | `mark_logic.run.run_id = 3` (2026-11-04 16:05:12, note "v3 gates …", 98.53% = 1,747/1,773, ELR measurable 470/598) |
| DB export | `artifacts/regression-r0/mark_logic/*.csv` + `MANIFEST.json` (run-scoped tables filtered to `run_id = 3`; reference tables = state at export) |
| R0-legacy | `artifacts/regression-r0/line_result_run2_529elr.csv` (run 2, 2,381 lines, 529 measurable ELR) sha256 `1e779c901b2b33690a8b224f6627e86b32990f100e7002cb71f3e3691c6e646a` |
| Run-2 reference tables | `artifacts/regression-r0/run2_reference_snapshot_1554.json` (logic_rule, adi1039_token, stage_accuracy … read at 15:54) |

`artifacts/` is git-ignored (customer data).

## To run before migration 0001 (DBA)

```
pg_dump -h 10.151.28.2 -U <dba> -d mark_web -n mark_logic -Fc -f mark_logic_2026-11-04_R0.dump
sha256sum mark_logic_2026-11-04_R0.dump > mark_logic_2026-11-04_R0.dump.sha256
```

Store both files next to `artifacts/regression-r0/`. If `mark_logic.run` has a row with `run_id > 3` by then, record it —
it is **not** part of R0.
