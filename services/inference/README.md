# Inference worker (AI server)

This directory contains batch entry points for the AI host. The application/engine host extracts images and passes a batch of PNGs; this worker produces JSON for the engine host. It does not connect to Oracle or PostgreSQL. Copy only this directory and the approved model artifacts to the worker; do not copy `.env` or database credentials.

`run_batch.py` is the transfer/orchestration client and runs on the engine host, where `mark_engine`, Paramiko and the AI-server credential are available. Only `det_rec_batch.py`, `yolo_batch.py` and the image batch need to be copied to the AI host. `reocr_batch.py` can run on the engine host against the AI recognizer endpoint.

`det_rec_batch.py IMAGE_DIR det_rec.json` runs with `ic-marking-ocr:exp09` and its `/models/exp09` model. `yolo_batch.py WEIGHTS IMAGE_DIR detections.json` needs the approved Ultralytics environment and GPU. `reocr_batch.py IMAGE_DIR det_rec.json reocr.csv` calls the recognizer service; optional `--trim-logo` additionally requires the engine package on the host that runs it.

YOLO was compared with all 95 historical May–June images: class/count/box differences over one pixel were zero. Detection/recognition produced the same image keys, box counts and text, with no box difference over one pixel. Re-OCR with `--trim-logo` matched the six historical legend candidates in key, text and score; this particular historical sample did not trigger an auto-layout logo trim. Provenance and cache checks were enforced for run 17; see the holdout report for limitations.

The validated server used Ultralytics `8.3.40`, PyTorch `2.4.0+cu121`, and OCR image ID `sha256:e437bcc7b08c8deb5905e3fe7dd9301e7aaeeaf2c3194e184e46d2b784e6efd5`. The server's EXP09 and symbol detector weight hashes matched `models/REGISTRY.json`. Preserve these artifacts and record the actual model and container hashes for every batch; image tags alone are not sufficient.
