# Base image: EXP09 OCR environment with paddleocr 3.7.0 and paddlex 3.7.2
FROM ic-marking-ocr:exp09

WORKDIR /app

# Install PyTorch with CUDA 12.1 for YOLO symbol detector, plus ultralytics, gRPC, and NVML
RUN pip install --default-timeout=1000 --no-cache-dir \
    torch==2.4.0+cu121 torchvision==0.19.0+cu121 --extra-index-url https://download.pytorch.org/whl/cu121 \
    && pip install --default-timeout=1000 --no-cache-dir \
    ultralytics==8.3.40 \
    grpcio==1.85.1 \
    protobuf==7.36.0 \
    pynvml>=11.5.0

# Required environment flags
ENV FLAGS_allocator_strategy=auto_growth
ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
ENV PADDLE_PDX_CACHE_HOME=/models/paddlex_cache
ENV PYTHONPATH=/app

# Copy inference service and engine modules
COPY services/inference /app/services/inference
COPY mark_engine /app/mark_engine

EXPOSE 50051

CMD ["python", "-m", "services.inference.server"]
