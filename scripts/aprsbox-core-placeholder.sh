#!/bin/sh
set -eu

LOG_DIR="${APRSBOX_LOG_DIR:-/opt/aprsbox/logs}"
mkdir -p "$LOG_DIR"

while true; do
    printf '%s aprsbox-core placeholder running\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >> "$LOG_DIR/aprsbox-core.log"
    sleep 300
done

