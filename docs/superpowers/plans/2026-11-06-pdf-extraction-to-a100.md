# Implementation Plan: Move PDF Extraction to A100 AI Server (10.151.28.9)

> **Context**: Currently, the Worker container on `10.153.90.17` extracts the Brand/Marking image from ABS PDFs using PyMuPDF locally, then sends the resulting PNG over gRPC to `10.151.28.9:50051` across three separate round-trips (`Page`, `Symbols`, `Rec`).
> **Objective**: Move the PDF-to-image extraction and full inference pipeline to `10.151.28.9`, turning the flow into a single unified gRPC call (`ProcessPdf`), reducing CPU/RAM load on `10.153.90.17` and minimizing network round-trips.

---

## 1. Overview & Architectural Shift

```
[ AS-IS ]
10.153.90.17 (Worker)                                        10.151.28.9 (A100)
┌───────────────────────────┐                               ┌───────────────────────────┐
│ 1. Read PDF from NAS      │                               │                           │
│ 2. PyMuPDF Render to PNG  │ ──── (3 round-trips) ───────> │ - gRPC: Page (OCR)        │
│    (High CPU on .17)      │ <─── PNG, crops, results ───  │ - gRPC: Symbols (YOLO)    │
│ 3. Save PNG for Web UI    │                               │ - gRPC: Rec (Re-OCR)      │
└───────────────────────────┘                               └───────────────────────────┘

[ TO-BE ]
10.153.90.17 (Worker)                                        10.151.28.9 (A100)
┌───────────────────────────┐                               ┌───────────────────────────┐
│ 1. Read PDF from NAS      │                               │ 1. PyMuPDF Render to PNG  │
│ 2. Send PDF bytes (1 RPC) │ ── gRPC: ProcessPdf(pdf) ───> │ 2. Page OCR + YOLO        │
│                           │ <── PNG + Full Inference ───  │ 3. Auto Re-OCR (TrimLogo) │
│ 3. Save returned PNG      │                               │ (All in-memory on GPU)    │
└───────────────────────────┘                               └───────────────────────────┘
```

---

## 2. Constraints & Rules

1. **A100 Host Safety**:
   - **Never stop vLLM** running on `10.151.28.9`.
   - VRAM headroom must remain safe (OCR uses CPU, YOLO uses GPU with auto-growth).
   - Python wheel for `pymupdf` is ~15MB (well under the 100MB threshold rule).
2. **Backward Compatibility**:
   - Keep existing `Page`, `Symbols`, `Rec` RPCs intact so existing test suites and cached image replay flows continue to work without breaking changes.
3. **Web UI Support**:
   - The Web UI on `10.153.90.17:8093` still requires the extracted PNG for browser display. The response from `.9` will return the extracted PNG bytes so `.17` can cache and serve it.

---

## 3. Phased Implementation Steps

### Phase 1: gRPC Protocol & Message Definitions
- [ ] **Step 1.1**: Update `services/inference/proto/mark_inference.proto`:
  ```protobuf
  service MarkInference {
    rpc Health(HealthRequest) returns (HealthReply);
    rpc Page(ImageRequest) returns (PageReply);
    rpc Symbols(ImageRequest) returns (SymbolsReply);
    rpc Rec(RecRequest) returns (RecReply);
    
    // New unified endpoint
    rpc ProcessPdf(PdfRequest) returns (FullInferenceReply);
  }

  message PdfRequest {
    string name = 1;
    bytes pdf = 2;
  }

  message FullInferenceReply {
    bytes png = 1;
    string png_sha256 = 2;
    string extraction_method = 3; // 'raster' or 'render200'
    int32 page_number = 4;
    repeated TextItem items = 5;
    repeated Symbol symbols = 6;
    map<string, string> reocr = 7;
    ModelInfo model = 8;
  }
  ```
- [ ] **Step 1.2**: Recompile protobuf stubs with `grpc_tools.protoc`.
- **Verification**: `python -c "from services.inference import mark_inference_pb2; assert hasattr(mark_inference_pb2, 'PdfRequest')"`

---

### Phase 2: A100 Inference Service Implementation (`10.151.28.9`)
- [ ] **Step 2.1**: Update `services/inference/Dockerfile` to include `pymupdf`:
  ```dockerfile
  RUN pip install --no-cache-dir pymupdf==1.24.11
  ```
- [ ] **Step 2.2**: Implement `ProcessPdf` handler in `services/inference/server.py`:
  - Receive PDF bytes.
  - Call `extract_brand_image(pdf_bytes)` in-memory via `io.BytesIO`.
  - Feed extracted PNG directly into `engines.page()` (OCR) and `engines.symbols()` (YOLO).
  - Perform `legend_candidates` & `trim_logo` in-memory, run `engines.rec()`.
  - Return consolidated `FullInferenceReply`.
- [ ] **Step 2.3**: Build and test docker image `mark-inference:0.2.0` on dev machine.
- [ ] **Step 2.4**: Transfer and deploy updated container to `10.151.28.9` (without stopping vLLM).
- **Verification**: Run RPC test sending a sample PDF to `10.151.28.9:50051`, verify it returns PNG + OCR + YOLO results in one call.

---

### Phase 3: Worker & Engine Client Integration (`10.153.90.17`)
- [ ] **Step 3.1**: Add `client.process_pdf(name, pdf_bytes)` in `mark_engine/adapters/inference_service.py`.
- [ ] **Step 3.2**: Update `services/worker/main.py`:
  - Read PDF from NAS CIFS mount.
  - Call `client.process_pdf(...)`.
  - Save the returned PNG into `work/<elr_no>/images/<sha256>.png` for web frontend serving.
  - Pass the inference results directly to Rule Engine.
- [ ] **Step 3.3**: Run full local test suite (`pytest tests/unit/ -v`).
- **Verification**: All worker and pipeline unit tests pass.

---

### Phase 4: Production Deployment & Validation
- [ ] **Step 4.1**: Commit changes to `phase2/trial`.
- [ ] **Step 4.2**: Trigger Jenkins Build on `10.153.90.17`.
- [ ] **Step 4.3**: End-to-end verification:
  - Trigger manual recheck on `ADI2607006`.
  - Verify worker logs confirm PDF was processed remotely on `.9`.
  - Verify web UI at `http://10.153.90.17:8093` still displays the image and bounding boxes correctly.
  - Verify `check_trial_readonly.py --run 19` remains 8/8 OK.
