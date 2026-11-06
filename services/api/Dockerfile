FROM python:3.12-slim

WORKDIR /app
RUN mkdir -p /app/work /app/data/files /app/logs

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    libaio1t64 \
    && rm -rf /var/lib/apt/lists/*

# Install Oracle Instant Client (basic lite 21.13) for thick mode connection to Oracle 10g
RUN mkdir -p /opt/oracle && cd /opt/oracle \
    && curl -fsSL -o ic.zip https://download.oracle.com/otn_software/linux/instantclient/2113000/instantclient-basiclite-linux.x64-21.13.0.0.0dbru.zip \
    && unzip -q ic.zip \
    && rm ic.zip \
    && if [ -f /usr/lib/x86_64-linux-gnu/libaio.so.1t64 ] && [ ! -f /usr/lib/x86_64-linux-gnu/libaio.so.1 ]; then \
        ln -s /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/x86_64-linux-gnu/libaio.so.1; \
    fi \
    && echo /opt/oracle/instantclient_21_13 > /etc/ld.so.conf.d/oracle.conf \
    && ldconfig

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir ".[api]"

COPY mark_engine/ mark_engine/
COPY services/ services/

ENV PYTHONPATH="/app:/app/services/api"
ENV PYTHONUNBUFFERED=1
ENV ORACLE_CLIENT_DIR="/opt/oracle/instantclient_21_13"
ENV LD_LIBRARY_PATH="/opt/oracle/instantclient_21_13:${LD_LIBRARY_PATH}"

EXPOSE 8000

CMD ["uvicorn", "mark_api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
