# Deploying mark-inference on A100

This document outlines the deployment procedure for the `mark-inference:0.1.0` container on the shared A100 GPU host (`10.151.28.9`).

## 1. Directory Structure on Host

```
~/mark_inference/
├── .env                # chmod 600, contains MARK_INF_API_KEY (never commit)
└── models/             # Mounted read-only at /models
    ├── exp09/          # Fine-tuned PP-OCRv5_server_rec (inference.*)
    ├── symdet/
    │   └── v2/weights/best.pt
    ├── PP-OCRv5_server_det/
    └── paddlex_cache/official_models/PP-OCRv5_server_det/
```

## 2. Environment Configuration (`~/mark_inference/.env`)

Ensure `chmod 600 ~/mark_inference/.env` is set. Configuration keys:
- `MARK_INF_API_KEY`: Secret API token
- `MARK_INF_PORT`: `50051`
- `MARK_INF_MIN_FREE_MB`: `3000`
- `MARK_INF_RECOGNIZER_DIR`: `/models/exp09`
- `MARK_INF_SYMBOL_WEIGHTS`: `/models/symdet/v2/weights/best.pt`

## 3. Build Container Image

From repository root:
```bash
docker build -t mark-inference:0.1.0 -f services/inference/Dockerfile .
```

## 4. Run Container

```bash
docker run -d \
  --name mark-inference \
  --restart unless-stopped \
  --gpus all \
  -p 50051:50051 \
  --env-file ~/mark_inference/.env \
  -v ~/mark_inference/models:/models:ro \
  mark-inference:0.1.0
```

## 5. Verification

Check container status and logs:
```bash
docker logs mark-inference
```

Verify Health RPC from authorized client:
```bash
python -c "
from mark_engine.adapters.inference_service import InferenceClient
import os
client = InferenceClient('10.151.28.9:50051', os.environ['MARK_INFERENCE_API_KEY'])
print(client.health())
"
```

## 6. Retire Legacy OCR Service

Once `mark-inference` is verified healthy:
```bash
docker stop ic-marking-ocr
docker rm ic-marking-ocr
ss -ltn | grep 8095  # Confirm port 8095 is closed
```
