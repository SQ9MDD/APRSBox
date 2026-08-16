#!/bin/sh
set -eu

INSTALL_ROOT="${APRSBOX_INSTALL_ROOT:-/opt/aprsbox}"
SSL_DIR="$INSTALL_ROOT/data/ssl"

if [ -f "$SSL_DIR/https-enabled" ] && [ -f "$SSL_DIR/aprsbox.crt" ] && [ -f "$SSL_DIR/aprsbox.key" ]; then
    exec "$INSTALL_ROOT/venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 443 --ssl-certfile "$SSL_DIR/aprsbox.crt" --ssl-keyfile "$SSL_DIR/aprsbox.key" --access-log
fi

exec "$INSTALL_ROOT/venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 80 --access-log
