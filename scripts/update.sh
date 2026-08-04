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
GIT_BRANCH_CLI=""
JOB_ID="${APRSBOX_JOB_ID:-}"
WORKDIR="$(mktemp -d)"
CHECKOUT_DIR="$WORKDIR/repo"
STAGING_APP_DIR="$INSTALL_ROOT/app.new.$$"
NEW_VENV_DIR=""
PREVIOUS_VENV_DIR=""
PREVIOUS_APP_DIR=""
SERVICE_MANAGER="unknown"
UPDATE_CHANNEL_SETTING_KEY="gui_update_branch"
JOB_FINAL_STATUS=""
JOB_FINAL_MESSAGE=""
JOB_FINALIZATION_DEFERRED="0"

log() {
    printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

job_can_update() {
    if [ -z "$JOB_ID" ] || [ -z "$DB_PATH" ]; then
        return 1
    fi
    case "$JOB_ID" in
        *[!0-9]*)
            return 1
            ;;
    esac
    command -v sqlite3 >/dev/null 2>&1
}

job_escape() {
    printf '%s' "$1" | sed "s/'/''/g"
}

job_update() {
    status="$1"
    message="${2:-}"
    exit_code="${3:-}"
    progress_percent="${4:-}"
    stage="${5:-}"
    if ! job_can_update; then
        return 0
    fi
    now="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    safe_message="$(job_escape "$message")"
    safe_status="$(job_escape "$status")"
    safe_stage="$(job_escape "$stage")"
    exit_sql="NULL"
    progress_sql="progress_percent"
    stage_sql="stage"
    if [ -n "$exit_code" ]; then
        exit_sql="$(job_escape "$exit_code")"
    fi
    case "$progress_percent" in
        "" | *[!0-9]*) ;;
        *)
            if [ "$progress_percent" -le 100 ]; then
                progress_sql="$progress_percent"
            fi
            ;;
    esac
    if [ -n "$stage" ]; then
        stage_sql="'$safe_stage'"
    fi
    sqlite3 "$DB_PATH" ".timeout 5000" "UPDATE system_jobs SET status = '$safe_status', message = '$safe_message', progress_percent = $progress_sql, stage = $stage_sql, exit_code = $exit_sql, started_at = COALESCE(started_at, '$now'), finished_at = CASE WHEN '$safe_status' IN ('success','error') THEN COALESCE(finished_at, '$now') ELSE finished_at END, updated_at = '$now' WHERE id = $JOB_ID;" >/dev/null 2>&1 || true
}

fail() {
    log "ERROR: $*"
    JOB_FINAL_STATUS="error"
    JOB_FINAL_MESSAGE="Application update failed: $*"
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

on_exit() {
    code="$?"
    if [ "$JOB_FINALIZATION_DEFERRED" = "1" ] && [ "$code" -eq 0 ]; then
        cleanup
        exit "$code"
    fi
    status="$JOB_FINAL_STATUS"
    message="$JOB_FINAL_MESSAGE"
    if [ -z "$status" ]; then
        if [ "$code" -eq 0 ]; then
            status="success"
            message="Application update finished successfully."
        else
            status="error"
            message="Application update failed (exit $code)."
        fi
    fi
    if [ "$status" = "success" ]; then
        job_update "$status" "$message" "$code" "100" "completed"
    else
        job_update "$status" "$message" "$code" "" "failed"
    fi
    cleanup
    exit "$code"
}

trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

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
            log "Systemd update path: keeping aprsbox-web running during file switch to avoid updater self-termination."
            systemctl stop aprsbox-core.service >/dev/null 2>&1 || true
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
    if [ -n "$GIT_BRANCH_CLI" ]; then
        GIT_BRANCH="$GIT_BRANCH_CLI"
        update_channel_source="argument"
    fi
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

parse_args() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --git-branch)
                if [ "$#" -lt 2 ]; then
                    fail "Missing value for --git-branch"
                fi
                GIT_BRANCH_CLI="$2"
                shift 2
                ;;
            --)
                shift
                break
                ;;
            *)
                fail "Unknown argument: $1"
                ;;
        esac
    done
}

parse_args "$@"
resolve_update_channel
log "Starting application update from $GIT_URL ($GIT_BRANCH)"
job_update "running" "Starting application update." "" "2" "starting"
mkdir -p "$LOG_DIR"
mkdir -p "$INSTALL_ROOT/backups"

job_update "running" "Downloading application files." "" "8" "downloading"
git clone --depth 1 --branch "$GIT_BRANCH" "$GIT_URL" "$CHECKOUT_DIR"

job_update "running" "Preparing downloaded files." "" "25" "preparing-files"
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
job_update "running" "Downloaded files are ready." "" "40" "preparing-files"

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
    job_update "running" "Preparing Python dependencies." "" "45" "preparing-dependencies"
    NEW_VENV_DIR="$INSTALL_ROOT/venv.new.$$"
    rm -rf "$NEW_VENV_DIR"
    python3 -m venv "$NEW_VENV_DIR"
    "$NEW_VENV_DIR/bin/pip" install --upgrade pip setuptools wheel
    "$NEW_VENV_DIR/bin/pip" install -r "$STAGING_APP_DIR/requirements.txt"
    log "Prepared updated Python virtual environment."
else
    log "requirements.txt unchanged. Reusing existing virtual environment."
fi
job_update "running" "Application dependencies are ready." "" "60" "preparing-dependencies"

detect_service_manager
job_update "running" "Stopping application services." "" "64" "stopping-services"
stop_services
job_update "running" "Backing up the database." "" "68" "backing-up-database"
backup_database

job_update "running" "Replacing application files." "" "74" "replacing-files"
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

job_update "running" "Updating the application database." "" "84" "updating-database"
PYTHONPATH="$APP_DIR" \
    APRSBOX_ENV=production \
    APRSBOX_INSTALL_ROOT="$INSTALL_ROOT" \
    APRSBOX_DB_PATH="$DB_PATH" \
    "$VENV_DIR/bin/python" -m app.cli init-db

chown "$APP_USER":"$APP_USER" "$DB_PATH" 2>/dev/null || true

RESTART_SCRIPT="$APP_DIR/scripts/restart-services.sh"
WEB_RESTART_SCRIPT="$APP_DIR/scripts/update-web-restart.sh"
if [ "$SERVICE_MANAGER" = "systemd" ]; then
    job_update "running" "Restarting the core service." "" "90" "restarting-core"
    systemctl restart aprsbox-core.service
fi

job_update "running" "Finalizing the update and cleaning up old files." "" "94" "finalizing"
if [ -n "$PREVIOUS_APP_DIR" ] && [ -d "$PREVIOUS_APP_DIR" ]; then
    rm -rf "$PREVIOUS_APP_DIR"
fi

if [ -n "$PREVIOUS_VENV_DIR" ] && [ -d "$PREVIOUS_VENV_DIR" ]; then
    rm -rf "$PREVIOUS_VENV_DIR"
fi
cleanup

if [ "$SERVICE_MANAGER" = "systemd" ]; then
    job_update "running" "Restarting the web service. The browser may reconnect briefly." "" "98" "restarting-web"
    if command -v systemd-run >/dev/null 2>&1 && [ -x "$WEB_RESTART_SCRIPT" ]; then
        restart_unit="aprsbox-web-restart-$$"
        if systemd-run \
            --quiet \
            --collect \
            --unit "$restart_unit" \
            --setenv="APRSBOX_JOB_ID=$JOB_ID" \
            --setenv="APRSBOX_DB_PATH=$DB_PATH" \
            "$WEB_RESTART_SCRIPT" >/dev/null 2>&1; then
            JOB_FINALIZATION_DEFERRED="1"
            log "Scheduled tracked aprsbox-web restart using transient systemd unit: $restart_unit"
        else
            log "WARNING: Failed to schedule tracked aprsbox-web restart; falling back to direct restart."
            systemctl restart aprsbox-web.service
        fi
    else
        log "WARNING: systemd-run or tracked web restart helper unavailable; restarting aprsbox-web directly."
        systemctl restart aprsbox-web.service
    fi
elif [ -x "$RESTART_SCRIPT" ]; then
    job_update "running" "Restarting application services. The browser may reconnect briefly." "" "96" "restarting-services"
    APRSBOX_JOB_ID="" "$RESTART_SCRIPT"
else
    job_update "running" "Restarting application services. The browser may reconnect briefly." "" "96" "restarting-services"
    log "WARNING: restart script missing at $RESTART_SCRIPT. Using built-in fallback."
    restart_services_fallback
fi

log "Application update finished successfully."
JOB_FINAL_STATUS="success"
JOB_FINAL_MESSAGE="Application update finished successfully."
