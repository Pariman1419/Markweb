# B4 Inference Service on the A100 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. Steps marked **[USER]** wait for the user. Do not tick them yourself.

**Goal:** run OCR (PP-OCRv5 det + exp09 rec) and YOLO (symdet v2) as one gRPC service on the A100. The engine can call it in place of the batch cache, and it gives the same results as the run-19 cache.

**Architecture:**
- **Server:** one Python gRPC server in one Docker container on `10.151.28.9:50051`.
- **RPCs:** `Health`, `Page` (det + rec), `Symbols` (YOLO), `Rec` (recognise crops; used for legend re-reads).
- **Shared code:** the model code moves out of the batch scripts into one module, so batch and service run the same code.
- **Client:** a new `mark_engine` adapter. It builds the same `InferenceResult` as the cache loader, using `build_auto_inference`.
- **Selection:** `MARK_INFERENCE=cache|service` picks the source.

**Tech Stack:** grpcio / grpcio-tools / protobuf, PaddleOCR (same version as image `ic-marking-ocr:exp09`), Ultralytics 8.3.40 + torch 2.4.0+cu121, Docker with `--gpus`.

**Spec:** `docs/superpowers/specs/2026-11-05-auto-review-flow-design.md` §6 and §9 step 2 (gRPC per `2026-11-05-phase2-trial-design.md` §13). Also read `services/inference/README.md`, which describes how the cache was made.

## Global Constraints

- **The A100 is shared.** vLLM and about 40 other containers run on it.
  - **Never stop, restart, or change any container except `mark-inference` and `ic-marking-ocr`.**
  - **`ic-marking-ocr` is retired [user 2026-11-05].** Remove its container and image (`docker rm -f ic-marking-ocr; docker rmi ic-marking-ocr:exp09`) only in Task 4 Step 5. By then its package versions and det model have been copied, and `mark-inference` reports Health `ok`.
  - **Prune is allowed [user 2026-11-05]:** `docker image prune -a -f` and `docker builder prune -f`. Never `--volumes`, never `docker system prune --volumes`, and never `docker volume`/`docker network` removal. Record `docker system df` before and after in QA_LOG.
- **Device: GPU with CPU fallback [user 2026-11-05].** Only about 6–7 GB of VRAM is free (vLLM uses about 72 GB).
  - Never pre-allocate VRAM. Paddle uses `FLAGS_allocator_strategy=auto_growth`; torch's lazy allocator is fine.
  - At start, if free VRAM is below `MARK_INF_MIN_FREE_MB` (default 3000), load on CPU.
  - On a CUDA out-of-memory error during a request, rerun that request on CPU and report `device="cpu"`.
  - `MARK_INF_FORCE_DEVICE=cpu|gpu` overrides this, for tests and for comparison.
- **Disk:** the A100 has about 22 GB free (89% used). Check `df -h ~` before any build or copy. If less than 15 GB would be free afterwards, run the allowed prune first. If it is still short, stop and ask the user.
- **SSH:**
  - Use the key: `ssh 10.151.28.9` (user `cimadmin`, `~/.ssh/config`).
  - Never use the password in `.env` (`AI_SERVER_PASSWORD`) and never print it.
  - Use `sudo` on the A100 only in a step marked [USER].
- **Secrets:**
  - The API key comes from `python -c "import secrets;print(secrets.token_urlsafe(32))"`, written straight into two git-ignored files without being echoed:
    - local `.env` as `MARK_INFERENCE_API_KEY`;
    - A100 `~/mark_inference/.env` (chmod 600) as `MARK_INF_API_KEY`.
  - Never put the key in git, logs, docs or chat.
- **Customer data** (ABS images, OCR text): only under `artifacts/` and `reports/` (both git-ignored) and in `~/mark_inference/` on the A100. Reports in git hold counts and image hashes only, never text.
- **Read-only:** Oracle, NAS, and `artifacts/blind-2026h2/cache`. Never touch runs 1–19, R0 `D:\CIM Project\mark`, or `models/` (copy from it; never edit it).
- **Freeze:** model files are byte-identical to `models/REGISTRY.json` / `cache/models.json`. Check sha256 after every copy.
- **Process:**
  - Every commit updates HANDOFF §4 and `docs/qa/QA_LOG.md`.
  - Add no duplicate tests.
  - A task is done only after push and a green Jenkins build.
  - `git pull --rebase` before push.

## Review Focus

1. **GPU and CPU must give the same result as the cache.** The cache's det/rec ran on **CPU** (`det_rec_batch.py`, `device='cpu'`) and YOLO on GPU. GPU OCR can differ slightly. Task 5 measures both, and every difference must be explained before the service is used.
2. **Out of VRAM mid-request:** the request must still answer, via CPU, and must never crash the server or touch vLLM.
3. **Wrong or missing API key:** `UNAUTHENTICATED`, with nothing run.
4. **Large or broken image** (not a PNG, or 0 bytes): `INVALID_ARGUMENT`, and the server keeps running. Max message size is 32 MB.
5. **Server down while the engine runs:** the engine marks the job `INFERENCE_FAILED`. It must not fall back to the cache silently. Fallback happens only when the operator sets `MARK_INFERENCE=cache`. Once `ic-marking-ocr` is removed, there is no old OCR service on the A100 to fall back to.

## File Structure

| File | Role |
|---|---|
| `services/inference/proto/mark_inference.proto` | gRPC contract |
| `services/inference/mark_inference_pb2.py`, `_pb2_grpc.py` | generated; committed; regenerate with `scripts/gen_inference_proto.py` |
| `services/inference/engines.py` | `OcrEngine`, `SymbolEngine`: model code taken from `det_rec_batch.py` / `yolo_batch.py`, with the same rounding and settings |
| `services/inference/devices.py` | device choice and CPU fallback |
| `services/inference/server.py` | gRPC server, API-key interceptor, Health |
| `services/inference/Dockerfile` | the `mark-inference` image |
| `mark_engine/abs/reocr.py` | `legend_candidates`, `trim_logo` moved from `reocr_batch.py` (shared by batch and client) |
| `mark_engine/adapters/inference_service.py` | client and `load_service_inference` |
| `scripts/compare_inference.py` | service vs cache report |
| `tests/unit/test_inference_service.py` | server and client tests, with fake engines and an in-process server |

---

### Task 1: Contract, server skeleton, API key

**Files:**
- Create: `services/inference/proto/mark_inference.proto`
- Create: `scripts/gen_inference_proto.py`
- Create: generated `pb2` files
- Create: `services/inference/server.py`
- Create: `tests/unit/test_inference_service.py`
- Modify: `pyproject.toml`. Add `grpcio`, `grpcio-tools` and `protobuf` to the `api` extra, pinned to the versions you install, so Jenkins `pip install -e ".[dev,api]"` gets them.

**Interfaces (proto, package `mark.inference.v1`):**
```proto
service MarkInference {
  rpc Health(HealthRequest) returns (HealthReply);
  rpc Page(ImageRequest) returns (PageReply);       // det + rec on one PNG
  rpc Symbols(ImageRequest) returns (SymbolsReply); // YOLO on one PNG
  rpc Rec(RecRequest) returns (RecReply);           // rec on PNG crops, in order
}
message ImageRequest { string name = 1; bytes png = 2; }
message TextItem { float x0 = 1; float y0 = 2; float x1 = 3; float y1 = 4; string text = 5; float score = 6; }
message Symbol { string cls = 1; float conf = 2; float x0 = 3; float y0 = 4; float x1 = 5; float y1 = 6; }
message ModelInfo { string service_version = 1; string device = 2; string ocr_rec_sha256 = 3; string detector_sha256 = 4; string symbol_sha256 = 5; }
message PageReply { repeated TextItem items = 1; ModelInfo model = 2; }
message SymbolsReply { repeated Symbol symbols = 1; ModelInfo model = 2; }
message RecRequest { repeated bytes crops = 1; }
message RecResult { string text = 1; float score = 2; }
message RecReply { repeated RecResult results = 1; ModelInfo model = 2; }
message HealthRequest {}
message HealthReply { string status = 1; string ocr_device = 2; string symbol_device = 3; int32 free_vram_mb = 4; ModelInfo model = 5; }
```

**`server.py`:**
- `build_server(ocr, symbols, api_key: str, port: int, max_msg_mb: int = 32) -> grpc.Server`
- The engines are passed in, so tests can use fakes.
- An interceptor checks the metadata `x-api-key` with `hmac.compare_digest`. A wrong or missing key → `UNAUTHENTICATED`.
- An image that does not decode as a PNG → `INVALID_ARGUMENT`.
- `main()` reads `MARK_INF_API_KEY`, `MARK_INF_PORT` (default 50051), `MARK_INF_MIN_FREE_MB` and `MARK_INF_FORCE_DEVICE`.

- [x] **Step 1: Tests.** Use an in-process server on a free port, with fake engines that return fixed items.
  - `test_health_reports_devices_and_model`
  - `test_missing_or_wrong_api_key_is_unauthenticated` (parametrize: missing / wrong)
  - `test_page_round_trips_items_in_order`
  - `test_bad_png_is_invalid_argument_and_server_survives`: a bad call, then a good call that succeeds.
- [x] **Step 2:** Run `python -m pytest tests/unit/test_inference_service.py -q`. Expected: FAIL (no module).
- [x] **Step 3:** Write the proto, the generator script (`python -m grpc_tools.protoc ...` into `services/inference/`), and `server.py`.
- [x] **Step 4:** Run `python -m pytest tests/unit -q -p no:cacheprovider`. Expected: all pass.
- [x] **Step 5:** Commit `feat(inference): gRPC contract and server skeleton with API key`, then push and wait for a green Jenkins build.

### Task 2: Shared engines and the GPU→CPU fallback

**Files:**
- Create: `services/inference/engines.py`
- Create: `services/inference/devices.py`
- Create: `mark_engine/abs/reocr.py`
- Modify: `det_rec_batch.py`, `yolo_batch.py` and `reocr_batch.py`, so they call the shared code. **The output of the batch scripts must not change.**
- Test: extend `tests/unit/test_inference_service.py`; keep `tests/unit/test_reocr_batch.py` and `test_adapters_reocr.py` passing unchanged, just with new imports.

**Interfaces:**
- **`OcrEngine(device: str, recognizer_dir: str)`:**
  - `.page(png: bytes) -> list[list]`: returns `[x0,y0,x1,y1,text,score]`. The box pad, the rounding (box to 1 place, score to 4) and the predictor settings are exactly those of `det_rec_batch.py`.
  - `.rec(crops: list[bytes]) -> list[tuple[str, float]]`
- **`SymbolEngine(device: str, weights: str)`:**
  - `.symbols(png: bytes) -> list[list]`: returns `[cls, conf, x0,y0,x1,y1]`, with `imgsz=1024`, `conf=0.25`, and the rounding of `yolo_batch.py`.
- **`choose_device(free_vram_mb: int | None, min_free_mb: int, force: str | None) -> str`:**
  - `force` wins.
  - `None` (no GPU or no NVML) → `"cpu"`.
  - `free < min` → `"cpu"`.
  - Otherwise `"gpu"`.
- **`with_cpu_fallback(run_gpu: Callable[[], T], run_cpu: Callable[[], T]) -> tuple[T, str]`:**
  - On a CUDA out-of-memory error, logs one warning and returns `(run_cpu(), "cpu")`.
  - Other errors are raised.
  - The CPU engine loads only on the first fallback, and is cached afterwards.
- `free_vram_mb()` reads NVML (`pynvml`), and returns `None` on error.
- Set `FLAGS_allocator_strategy=auto_growth` before Paddle is imported.

- [x] **Step 1: Tests, with no real models.**
  - `test_choose_device` (parametrize: force cpu / force gpu / None / below min / above min)
  - `test_oom_falls_back_to_cpu_once`: a fake GPU call raises an OOM-like error twice; CPU is used both times, and the CPU engine is built once.
  - `test_other_errors_are_not_swallowed`
  - `test_server_reports_cpu_after_fallback`: the reply has `model.device == "cpu"`.
- [x] **Step 2:** Run them. Expected: FAIL.
- [x] **Step 3:** Implement. Move the model code; do not copy it. The batch scripts become thin `argparse` wrappers.
- [x] **Step 4:** Run the unit suite. Expected: all pass, including the existing reocr tests.
- [x] **Step 5:** Commit `refactor(inference): shared OCR/YOLO engines with GPU->CPU fallback`, then push and wait for a green Jenkins build.

### Task 3: Engine client and the `MARK_INFERENCE` switch

**Files:**
- Create: `mark_engine/adapters/inference_service.py`
- Modify: `scripts/run_blind.py`. Add `--inference cache|service`, defaulting to env `MARK_INFERENCE`, else `cache`.
- Modify: `.env.example`. Add `MARK_INFERENCE=cache`, `MARK_INFERENCE_ADDR=10.151.28.9:50051`, `MARK_INFERENCE_API_KEY=` (empty).
- Test: extend `tests/unit/test_inference_service.py`.

**Interfaces:**
- **`InferenceClient(addr: str, api_key: str, timeout_s: float = 60)`:** methods `.health()`, `.page(name, png)`, `.symbols(name, png)`, `.rec(crops)`.
  - Each returns plain lists in the same shape as `det_rec.json` / `detections.json` entries.
  - Each retries `UNAVAILABLE` twice with a 2 s backoff.
  - On any other error, it raises `InferenceUnavailable`.
- **`load_service_inference(client, images_dir: Path, index_csv: Path, elr_no: str, abs_stem: str) -> InferenceResult`:**
  - Picks the image exactly as `load_cached_inference` does, with the same errors for duplicate or missing entries.
  - Then calls page and symbols.
  - Then builds reocr with `mark_engine.abs.reocr.legend_candidates` plus `client.rec`, with **trim-logo on**, because `run_batch.py` used `--trim-logo` for the cache.
  - Finally returns `build_auto_inference(...)`.
- **Mapping in `run_blind.py`:** `InferenceUnavailable` → job `FAILED` with `hold_reason "INFERENCE_FAILED"` (reuse the existing failure path; there is no new status). There is never a silent fallback to the cache.

- [x] **Step 1: Tests.** Use an in-process server with fake engines that replay a small cache fixture.
  - `test_service_loader_equals_cache_loader`: the same fixture through `load_cached_inference` and `load_service_inference` gives an equal `InferenceResult`.
  - `test_server_down_raises_inference_unavailable`
  - `test_run_blind_service_failure_is_inference_failed`
- [x] **Step 2:** Run them. Expected: FAIL.
- [x] **Step 3:** Implement.
- [x] **Step 4:** Run the unit suite. Expected: all pass.
- [x] **Step 5:** Commit `feat(engine): inference service client and MARK_INFERENCE switch`, then push and wait for a green Jenkins build.

### Task 4: Image and deploy on the A100

**Files:**
- Create: `services/inference/Dockerfile`
- Create: `services/inference/DEPLOY.md` (the exact commands, with no secrets)

**Image `mark-inference:0.1.0`:**
- **Python packages:**
  - PaddleOCR / PaddleX at the same versions as inside `ic-marking-ocr:exp09`. Read them with `ssh 10.151.28.9 docker exec ic-marking-ocr pip freeze`; this is read-only.
  - `paddlepaddle-gpu` for CUDA 12.x, plus `ultralytics==8.3.40`, `torch==2.4.0+cu121`, `grpcio`, `pynvml`.
- **Models:** not in the image. Mount them read-only at `/models` from `~/mark_inference/models/`, copied from:
  - `models/ocr-rec-exp09/ep40`
  - `models/symdet/v2`
  - the PP-OCRv5_server_det files, copied out of `ic-marking-ocr` with `docker cp` (read-only). Its sha256 must equal `detector_sha256` in `cache/models.json`.
- **Run:** `docker run -d --name mark-inference --restart unless-stopped --gpus all -p 50051:50051 --env-file ~/mark_inference/.env -v ~/mark_inference/models:/models:ro mark-inference:0.1.0`

- [x] **Step 1:** Run `ssh 10.151.28.9 'df -h ~; docker system df; nvidia-smi --query-gpu=memory.used,memory.total --format=csv'` and record the output in QA_LOG. Then run the allowed prune and record `df -h ~` again. Stop if the disk rule still fails.
- [x] **Step 2:** Copy the models to `~/mark_inference/models/` with `scp`. Verify every sha256 on the A100 against `models/REGISTRY.json` and `cache/models.json`.
- [x] **Step 3:** Generate the API key into both `.env` files (Global Constraints), then build the image on the A100 and run the container.
- [x] **Step 4:** `Health` from this machine reports `status=ok`, a device, and model hashes equal to the registry. Record `docker image inspect mark-inference:0.1.0 --format '{{.Id}}'` in QA_LOG.
- [x] **Step 5:** Run `nvidia-smi` again. vLLM's memory must be unchanged, and `mark-inference` must be under 4 GB with no images in flight. Record it. Then retire `ic-marking-ocr` as described in Global Constraints. Run `ss -ltn | grep 8095` and confirm port 8095 is closed.
- [x] **Step 6: Network.** Do not change the firewall. `ufw` is inactive on the A100 (checked 2026-11-05), so enabling it would cut off the other services on the box. Port 50051 is protected by the API key.
  - **Check from this dev machine (`10.151.97.18`):** Health works with the key, and gives `UNAUTHENTICATED` without it.
  - **Other callers:** later, the production API on `10.153.90.17` and the Airflow worker on `10.151.28.3` call the same address.
  - **[USER] Only if the user later wants an IP allow-list:** the server admin adds `DOCKER-USER` iptables rules for 50051.
- [x] **Step 7:** Commit `feat(inference): mark-inference image and A100 deploy notes`, then push and wait for a green Jenkins build.

### Task 5: Prove it matches the run-19 cache

**Files:**
- Create: `scripts/compare_inference.py`
- Test: one test in `tests/unit/test_inference_service.py`, `test_compare_counts_box_and_text_diffs`, using small fixtures.

**`compare_inference.py --cache artifacts/blind-2026h2/cache --addr HOST:PORT --out reports/inference-compare/<device>`:**
- For every row of `images_index.csv`:
  - send `cache/images/<image>`;
  - compare `Page` with `det_rec.json`: same box count, every box within 1 px, text equal, score within 0.01;
  - compare `Symbols` with `detections.json`: same class multiset, box within 1 px, conf within 0.01;
  - compare legend `Rec` with `reocr.csv`: key and text equal.
- **Output:** `summary.json` (counts) and `diffs.csv` (image sha256, kind, field). **No OCR text in the output.**

- [x] **Step 1:** Write the test, then the script.
- [x] **Step 2: CPU run.** Restart only `mark-inference` with `MARK_INF_FORCE_DEVICE=cpu`, then run the compare. **Expected: 0 diffs**, because the cache's OCR was made on CPU with the same code.
- [x] **Step 3: GPU run.** Restart `mark-inference` without the force, check that `Health` says `gpu`, then run the compare. Record the diff counts.
- [x] **Step 4: Engine level.** Run:
  `PYTHONPATH=. python scripts/run_blind.py --oracle artifacts/blind-2026h2/oracle --cache artifacts/blind-2026h2/cache --out artifacts/blind-2026h2/run-service --months 7_JUL 8_AUG 9_SEP 10_OCT 11_NOV --allow-unfrozen --workers 3 --inference service`
  Then `python scripts/diff_runs.py --base artifacts/blind-2026h2/run-gates --new artifacts/blind-2026h2/run-service`. **Expected: no job-level changes.**
- [x] **Step 5:** Write the counts from Steps 2–4, plus the ELR numbers of any changed job, into QA_LOG and HANDOFF. Commit `test(inference): service vs run-19 cache comparison`, then push and wait for a green Jenkins build.
- [x] **Step 6: Switch to the real service [user 2026-11-05: "use the real one"].**
  - Set `MARK_INFERENCE=service` in the local `.env`, with the server on GPU, auto-falling back to CPU.
  - Report the GPU diff counts and any changed ELRs from Steps 3–4 to the user **for information**. They do not block the switch.
  - **Exception:** if Step 4 shows an ELR moving from MATCH to an error, or the reverse, list those ELRs in the report.
  - `MARK_INFERENCE=cache` stays available as the manual fallback when the A100 is down.
  - Do not load `run-service` into the DB, and do not re-freeze.
