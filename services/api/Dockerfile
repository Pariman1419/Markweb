FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir ".[api]"

COPY mark_engine/ mark_engine/
COPY services/ services/

ENV PYTHONPATH="/app:/app/services/api"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "mark_api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
