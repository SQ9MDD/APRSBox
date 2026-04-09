#!/bin/sh
set -eu

APP_USER="aprsbox"
INSTALL_ROOT="${APRSBOX_INSTALL_ROOT:-/opt/aprsbox}"
APP_DIR="$INSTALL_ROOT/app"
VENV_DIR="$INSTALL_ROOT/venv"
DB_PATH="${APRSBOX_DB_PATH:-$INSTALL_ROOT/data/aprsbox.db}"
LOG_DIR="${APRSBOX_LOG_DIR:-$INSTALL_ROOT/logs}"
GIT_URL="${APRSBOX_GIT_URL:-https://github.com/SQ9MDD/APRSBox.git}"
GIT_BRANCH="${APRSBOX_GIT_BRANCH:-}"
WORKDIR="$(mktemp -d)"
CHECKOUT_DIR="$WORKDIR/repo"
STAGING_APP_DIR="$INSTALL_ROOT/app.new.$$"
NEW_VENV_DIR=""
PREVIOUS_VENV_DIR=""
PREVIOUS_APP_DIR=""
SERVICE_MANAGER="unknown"
UPDATE_CHANNEL_SETTING_KEY="gui_update_branch"

log() {
    printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

fail() {
    log "ERROR: $*"
    exit 1
}

cleanup() {
    if [ -d "$WORKDIR" ]; then
        rm -rf "$WORKDIR"
    fi
    if [ -n "$STAGING_APP_DIR" ] && [ -d "$STAGING_APP_DIR" ]; then
        rm -rf "$STAGING_APP_DIR"
    fi
    if [ -n "$NEW_VENV_DIR" ] && [ -d "$NEW_VENV_DIR" ]; then
        rm -rf "$NEW_VENV_DIR"
    fi
}

trap cleanup EXIT INT TERM

detect_service_manager() {
    init_comm="$(cat /proc/1/comm 2>/dev/null || true)"
    if command -v systemctl >/dev/null 2>&1 && { [ "$init_comm" = "systemd" ] || [ -d /run/systemd/system ]; }; then
        SERVICE_MANAGER="systemd"
        return
    fi
    if command -v rc-service >/dev/null 2>&1 && { [ -d /run/openrc ] || [ -x /sbin/openrc-run ]; }; then
        SERVICE_MANAGER="openrc"
        return
    fi
    SERVICE_MANAGER="unknown"
}

running_inside_systemd_web_unit() {
    if [ "$SERVICE_MANAGER" != "systemd" ]; then
        return 1
    fi
    if [ ! -r /proc/self/cgroup ]; then
        return 1
    fi
    grep -F "aprsbox-web.service" /proc/self/cgroup >/dev/null 2>&1
}

restart_services_fallback() {
    detect_service_manager
    case "$SERVICE_MANAGER" in
        systemd)
            systemctl restart aprsbox-core.service
            systemctl restart aprsbox-web.service
            ;;
        openrc)
            if rc-service aprsbox-core status >/dev/null 2>&1; then
                rc-service aprsbox-core restart || { rc-service aprsbox-core stop || true; rc-service aprsbox-core start; }
            else
                rc-service aprsbox-core start
            fi
            if rc-service aprsbox-web status >/dev/null 2>&1; then
                rc-service aprsbox-web restart || { rc-service aprsbox-web stop || true; rc-service aprsbox-web start; }
            else
                rc-service aprsbox-web start
            fi
            ;;
        *)
            fail "No supported service manager detected for restart."
            ;;
    esac
}

stop_services() {
    case "$SERVICE_MANAGER" in
        systemd)
            if running_inside_systemd_web_unit; then
                log "Detected updater running in aprsbox-web.service scope; skipping direct web stop to avoid self-termination."
                systemctl stop aprsbox-core.service >/dev/null 2>&1 || true
            else
                systemctl stop aprsbox-web.service aprsbox-core.service >/dev/null 2>&1 || true
            fi
            ;;
        openrc)
            rc-service aprsbox-web stop >/dev/null 2>&1 || true
            rc-service aprsbox-core stop >/dev/null 2>&1 || true
            ;;
    esac
}

backup_database() {
    if [ ! -f "$DB_PATH" ]; then
        return
    fi

    timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
    backup_path="$INSTALL_ROOT/backups/aprsbox-db-$timestamp.sqlite3"
    rm -f "$backup_path" "$backup_path-wal" "$backup_path-shm"

    if command -v sqlite3 >/dev/null 2>&1; then
        if sqlite3 "$DB_PATH" ".timeout 5000" ".backup '$backup_path'" >/dev/null 2>&1; then
            chown "$APP_USER":"$APP_USER" "$backup_path" 2>/dev/null || true
            log "Database backup created: $backup_path"
            return
        fi
        log "WARNING: sqlite3 backup failed for $DB_PATH, falling back to file copy."
        rm -f "$backup_path" "$backup_path-wal" "$backup_path-shm"
    fi

    if cp "$DB_PATH" "$backup_path"; then
        if [ -f "$DB_PATH-wal" ]; then
            cp "$DB_PATH-wal" "$backup_path-wal" || true
        fi
        if [ -f "$DB_PATH-shm" ]; then
            cp "$DB_PATH-shm" "$backup_path-shm" || true
        fi
        chown "$APP_USER":"$APP_USER" "$backup_path" "$backup_path-wal" "$backup_path-shm" 2>/dev/null || true
        log "Database backup created: $backup_path"
        return
    fi

    log "WARNING: database backup could not be created for $DB_PATH. Continuing without a backup."
}

resolve_update_channel() {
    update_channel_source="environment"
    if [ -z "$GIT_BRANCH" ] && [ -f "$DB_PATH" ] && command -v sqlite3 >/dev/null 2>&1; then
        stored_branch="$(sqlite3 "$DB_PATH" "SELECT value FROM app_settings WHERE key = '$UPDATE_CHANNEL_SETTING_KEY' LIMIT 1;" 2>/dev/null | tr -d '\r' | head -n 1)"
        if [ -n "$stored_branch" ]; then
            GIT_BRANCH="$stored_branch"
            update_channel_source="database"
        fi
    fi
    if [ -z "$GIT_BRANCH" ]; then
        GIT_BRANCH="main"
        update_channel_source="default"
    fi
    case "$GIT_BRANCH" in
        *[!A-Za-z0-9._/-]* | "")
            fail "Invalid update channel value: $GIT_BRANCH"
            ;;
    esac
    log "Using update channel '$GIT_BRANCH' (source: $update_channel_source)"
}

resolve_update_channel
log "Starting application update from $GIT_URL ($GIT_BRANCH)"
mkdir -p "$LOG_DIR"
mkdir -p "$INSTALL_ROOT/backups"

git clone --depth 1 --branch "$GIT_BRANCH" "$GIT_URL" "$CHECKOUT_DIR"

mkdir -p "$STAGING_APP_DIR"
if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
        --exclude '.git' \
        --exclude '.venv' \
        --exclude '__pycache__' \
        --exclude '.pytest_cache' \
        "$CHECKOUT_DIR/" "$STAGING_APP_DIR/"
else
    fail "rsync is required for application update."
fi

if [ -d "$STAGING_APP_DIR/scripts" ]; then
    find "$STAGING_APP_DIR/scripts" -type f -name '*.sh' -exec chmod 0755 {} \;
fi

REQUIREMENTS_CHANGED="1"
if [ -f "$APP_DIR/requirements.txt" ] && cmp -s "$APP_DIR/requirements.txt" "$STAGING_APP_DIR/requirements.txt"; then
    REQUIREMENTS_CHANGED="0"
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
    REQUIREMENTS_CHANGED="1"
fi

if [ "$REQUIREMENTS_CHANGED" = "1" ]; then
    NEW_VENV_DIR="$INSTALL_ROOT/venv.new.$$"
    rm -rf "$NEW_VENV_DIR"
    python3 -m venv "$NEW_VENV_DIR"
    "$NEW_VENV_DIR/bin/pip" install --upgrade pip setuptools wheel
    "$NEW_VENV_DIR/bin/pip" install -r "$STAGING_APP_DIR/requirements.txt"
    log "Prepared updated Python virtual environment."
else
    log "requirements.txt unchanged. Reusing existing virtual environment."
fi

detect_service_manager
stop_services
backup_database

if [ -d "$APP_DIR" ]; then
    PREVIOUS_APP_DIR="$INSTALL_ROOT/app.old.$$"
    rm -rf "$PREVIOUS_APP_DIR"
    mv "$APP_DIR" "$PREVIOUS_APP_DIR"
fi

if ! mv "$STAGING_APP_DIR" "$APP_DIR"; then
    if [ -n "$PREVIOUS_APP_DIR" ] && [ -d "$PREVIOUS_APP_DIR" ]; then
        mv "$PREVIOUS_APP_DIR" "$APP_DIR" || true
        PREVIOUS_APP_DIR=""
    fi
    fail "Failed to activate updated application files."
fi
STAGING_APP_DIR=""

if [ "$REQUIREMENTS_CHANGED" = "1" ]; then
    if [ -d "$VENV_DIR" ]; then
        PREVIOUS_VENV_DIR="$INSTALL_ROOT/venv.old.$$"
        rm -rf "$PREVIOUS_VENV_DIR"
        mv "$VENV_DIR" "$PREVIOUS_VENV_DIR"
    fi
    if ! mv "$NEW_VENV_DIR" "$VENV_DIR"; then
        if [ -n "$PREVIOUS_VENV_DIR" ] && [ -d "$PREVIOUS_VENV_DIR" ]; then
            mv "$PREVIOUS_VENV_DIR" "$VENV_DIR" || true
            PREVIOUS_VENV_DIR=""
        fi
        fail "Failed to activate updated Python virtual environment."
    fi
    NEW_VENV_DIR=""
fi

chown -R "$APP_USER":"$APP_USER" "$APP_DIR" "$VENV_DIR" 2>/dev/null || true

PYTHONPATH="$APP_DIR" \
    APRSBOX_ENV=production \
    APRSBOX_INSTALL_ROOT="$INSTALL_ROOT" \
    APRSBOX_DB_PATH="$DB_PATH" \
    "$VENV_DIR/bin/python" -m app.cli init-db

chown "$APP_USER":"$APP_USER" "$DB_PATH" 2>/dev/null || true

RESTART_SCRIPT="$APP_DIR/scripts/restart-services.sh"
if [ "$SERVICE_MANAGER" = "systemd" ] && running_inside_systemd_web_unit; then
    systemctl restart aprsbox-core.service
    if command -v systemd-run >/dev/null 2>&1; then
        restart_unit="aprsbox-web-restart-$$"
        if systemd-run --quiet --collect --unit "$restart_unit" /bin/sh -c "sleep 1; systemctl restart aprsbox-web.service" >/dev/null 2>&1; then
            log "Scheduled aprsbox-web restart using transient systemd unit: $restart_unit"
        else
            log "WARNING: Failed to schedule deferred aprsbox-web restart; falling back to direct restart."
            systemctl restart aprsbox-web.service
        fi
    else
        log "WARNING: systemd-run not available; restarting aprsbox-web directly."
        systemctl restart aprsbox-web.service
    fi
elif [ -x "$RESTART_SCRIPT" ]; then
    "$RESTART_SCRIPT"
else
    log "WARNING: restart script missing at $RESTART_SCRIPT. Using built-in fallback."
    restart_services_fallback
fi

if [ -n "$PREVIOUS_APP_DIR" ] && [ -d "$PREVIOUS_APP_DIR" ]; then
    rm -rf "$PREVIOUS_APP_DIR"
fi

if [ -n "$PREVIOUS_VENV_DIR" ] && [ -d "$PREVIOUS_VENV_DIR" ]; then
    rm -rf "$PREVIOUS_VENV_DIR"
fi

log "Application update finished successfully."
