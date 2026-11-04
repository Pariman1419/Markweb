# Engine worker deployment

Run this unit on the application host with read-only Oracle and NAS access. Deploy the frozen source tree with `mark_engine/`, `scripts/`, `services/inference/`, `models/REGISTRY.json`, and `pyproject.toml` under the same release root; freeze verification hashes those source files at that location. Install dependencies into an isolated environment and execute commands from that root. A wheel alone is insufficient for the current freeze verifier. Model weights stay on the AI host. Set environment values on this host; do not copy the local `.env` into an image or source bundle.

1. Take a read-only Oracle snapshot with `python -m scripts.fetch_oracle_snapshot --elr-prefix ADI2607 ADI2608 ADI2609 ADI2610 ADI2611 --out <private-oracle-dir>`.
2. Extract images with `python -m scripts.blind_extract_images --snapshot <private-oracle-dir>/elr_meta.json --months 7_JUL 8_AUG 9_SEP 10_OCT 11_NOV --out <private-cache-dir>`.
3. Transfer only the extracted image batch to the AI worker. Return its OCR/YOLO output and model provenance to the private cache. Run re-OCR using the recognizer endpoint and validate the complete cache.
4. Only after review and freeze, run `python -m scripts.run_blind --oracle <private-oracle-dir> --cache <private-cache-dir> --months 7_JUL 8_AUG 9_SEP 10_OCT 11_NOV --out <private-run-dir>`.

`run_blind` checks the freeze, month paths, image hashes, cache completeness and inference-output provenance. `--allow-unfrozen` is for diagnostics and labels its results UNFROZEN. The batch is not yet ready for an official run until the remaining freeze, model and historical-review gates are complete.

Oracle client: install `python-oracledb` and an Oracle Instant Client compatible with the source server. The PostgreSQL loader additionally requires `psycopg2`; DBA applies migration 0004 before the loader is run. `MARK_PG_PASSWORD` belongs only on the authorized DB-loading host.
