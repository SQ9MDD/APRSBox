FROM alpine:3.20

ENV APRSBOX_INSTALL_ROOT=/opt/aprsbox
ENV APRSBOX_DB_PATH=/opt/aprsbox/data/aprsbox.db
ENV APRSBOX_LOG_DIR=/opt/aprsbox/logs
ENV APRSBOX_CORE_HOST=127.0.0.1
ENV APRSBOX_CORE_PORT=18081
ENV APRSBOX_WEB_HTTP_PORT=8000
ENV PYTHONPATH=/opt/aprsbox/app
ENV PYTHONUNBUFFERED=1
ENV APRSBOX_CONTAINER=1

RUN apk add --no-cache \
    python3 \
    py3-pip \
    bash \
    curl \
    sqlite \
    sqlite-dev \
    ca-certificates

WORKDIR /opt/aprsbox/app

COPY requirements.txt requirements-accelerators.txt /opt/aprsbox/app/

RUN python3 -m venv /opt/aprsbox/venv && \
    /opt/aprsbox/venv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/aprsbox/venv/bin/pip install -r /opt/aprsbox/app/requirements.txt && \
    if /opt/aprsbox/venv/bin/pip install --only-binary=:all: -r /opt/aprsbox/app/requirements-accelerators.txt; then \
        :; \
    else \
        echo "[APRSBox] Optional Uvicorn accelerators unavailable; using asyncio and h11."; \
    fi

COPY . /opt/aprsbox/app

RUN mkdir -p /opt/aprsbox/data /opt/aprsbox/logs /opt/aprsbox/config /opt/aprsbox/backups

RUN cat > /opt/aprsbox/start-docker.sh <<'EOF'
#!/bin/sh
set -eu

cd /opt/aprsbox/app
. /opt/aprsbox/venv/bin/activate

export APRSBOX_INSTALL_ROOT="${APRSBOX_INSTALL_ROOT:-/opt/aprsbox}"
export APRSBOX_DB_PATH="${APRSBOX_DB_PATH:-/opt/aprsbox/data/aprsbox.db}"
export APRSBOX_LOG_DIR="${APRSBOX_LOG_DIR:-/opt/aprsbox/logs}"
export APRSBOX_CORE_HOST="${APRSBOX_CORE_HOST:-127.0.0.1}"
export APRSBOX_CORE_PORT="${APRSBOX_CORE_PORT:-18081}"
export APRSBOX_WEB_HTTP_PORT="${APRSBOX_WEB_HTTP_PORT:-8000}"
export PYTHONPATH="${PYTHONPATH:-/opt/aprsbox/app}"
export APRSBOX_CONTAINER="${APRSBOX_CONTAINER:-1}"

mkdir -p /opt/aprsbox/data /opt/aprsbox/logs /opt/aprsbox/config /opt/aprsbox/backups

python -m app.cli init-db

if python -m app.cli admin-exists >/dev/null 2>&1; then
  echo "[APRSBox] Admin already exists."
else
  echo "[APRSBox] Creating default admin."
  python -m app.cli create-admin \
    --username "${APRSBOX_ADMIN_USER:-admin}" \
    --password "${APRSBOX_ADMIN_PASSWORD:-aprs}"
fi

echo "[APRSBox] Starting core..."
uvicorn app.core_main:app --host 127.0.0.1 --port 18081 --access-log &

CORE_PID=$!

echo "[APRSBox] Starting web..."
uvicorn app.main:app --host 0.0.0.0 --port "$APRSBOX_WEB_HTTP_PORT" --access-log &

WEB_PID=$!

shutdown() {
  echo "[APRSBox] Stopping..."
  kill "$CORE_PID" "$WEB_PID" 2>/dev/null || true
  wait "$CORE_PID" "$WEB_PID" 2>/dev/null || true
}

trap shutdown INT TERM

while true; do
  if ! kill -0 "$CORE_PID" 2>/dev/null; then
    echo "[APRSBox] Core stopped."
    shutdown
    exit 1
  fi

  if ! kill -0 "$WEB_PID" 2>/dev/null; then
    echo "[APRSBox] Web stopped."
    shutdown
    exit 1
  fi

  sleep 2
done
EOF

RUN sed -i 's/\r$//' /opt/aprsbox/start-docker.sh && chmod +x /opt/aprsbox/start-docker.sh

EXPOSE 8000

ENTRYPOINT ["/opt/aprsbox/start-docker.sh"]
