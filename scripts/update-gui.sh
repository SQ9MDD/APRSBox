#!/bin/sh
set -eu

INSTALL_ROOT="${APRSBOX_INSTALL_ROOT:-/opt/aprsbox}"
APP_DIR="$INSTALL_ROOT/app"
VENV_DIR="$INSTALL_ROOT/venv"
LOG_DIR="${APRSBOX_LOG_DIR:-$INSTALL_ROOT/logs}"
DB_PATH="${APRSBOX_DB_PATH:-$INSTALL_ROOT/data/aprsbox.db}"
REPO_URL="${APRSBOX_GIT_URL:-https://github.com/SQ9MDD/APRSBox.git}"
REPO_BRANCH="${APRSBOX_GIT_BRANCH:-main}"
WORKDIR="$(mktemp -d)"
CHECKOUT_DIR="$WORKDIR/repo"

cleanup() {
    rm -rf "$WORKDIR"
}

trap cleanup EXIT INT TERM

mkdir -p "$LOG_DIR"
printf '%s Starting GUI update from %s (%s)\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$REPO_URL" "$REPO_BRANCH"

if [ -f "$APP_DIR/VERSION" ]; then
    printf '%s Current installed GUI version: %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$(cat "$APP_DIR/VERSION")"
fi

git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$CHECKOUT_DIR"

if [ -f "$CHECKOUT_DIR/VERSION" ]; then
    printf '%s Downloaded GUI version: %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$(cat "$CHECKOUT_DIR/VERSION")"
fi

if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
        --exclude '.git' \
        --exclude '.venv' \
        --exclude '__pycache__' \
        --exclude '.pytest_cache' \
        "$CHECKOUT_DIR/" "$APP_DIR/"
else
    printf '%s rsync is required for GUI updates\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    exit 1
fi

if [ -f "$APP_DIR/VERSION" ]; then
    printf '%s Installed GUI version after sync: %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$(cat "$APP_DIR/VERSION")"
else
    printf '%s ERROR: VERSION file missing after sync\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    exit 1
fi

if [ -x "$VENV_DIR/bin/pip" ] && [ -f "$APP_DIR/requirements.txt" ]; then
    "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"
fi

if [ -x "$VENV_DIR/bin/python" ]; then
    PYTHONPATH="$APP_DIR" \
        APRSBOX_ENV=production \
        APRSBOX_INSTALL_ROOT="$INSTALL_ROOT" \
        APRSBOX_DB_PATH="$DB_PATH" \
        "$VENV_DIR/bin/python" -m app.cli init-db
fi

printf '%s Files updated successfully\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

if command -v rc-service >/dev/null 2>&1; then
    rc-service aprsbox-core restart || rc-service aprsbox-core start
    printf '%s aprsbox-core restarted\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    rc-service aprsbox-web restart || rc-service aprsbox-web start
    printf '%s aprsbox-web restarted\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
else
    printf '%s rc-service not available, restart skipped\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
fi
