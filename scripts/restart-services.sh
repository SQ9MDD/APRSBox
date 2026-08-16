#!/bin/sh
set -eu

SERVICE_MANAGER="unknown"
JOB_ID="${APRSBOX_JOB_ID:-}"
DB_PATH="${APRSBOX_DB_PATH:-}"
INSTALL_ROOT="${APRSBOX_INSTALL_ROOT:-/opt/aprsbox}"
APP_DIR="$INSTALL_ROOT/app"
SSL_DIR="$INSTALL_ROOT/data/ssl"
HTTPS_ENABLED_REQUEST=""
JOB_FINALIZATION_DEFERRED="0"

log() {
    printf '%s\n' "$*"
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

parse_args() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --job-id)
                if [ "$#" -lt 2 ]; then
                    log "Missing value for --job-id"
                    exit 2
                fi
                case "$2" in
                    "" | *[!0-9]*)
                        log "Invalid job ID: $2"
                        exit 2
                        ;;
                esac
                JOB_ID="$2"
                shift 2
                ;;
            --db-path)
                if [ "$#" -lt 2 ] || [ -z "$2" ]; then
                    log "Missing value for --db-path"
                    exit 2
                fi
                DB_PATH="$2"
                shift 2
                ;;
            --https-enabled)
                if [ "$#" -lt 2 ] || { [ "$2" != "0" ] && [ "$2" != "1" ]; }; then
                    log "Invalid HTTPS enabled value"
                    exit 2
                fi
                HTTPS_ENABLED_REQUEST="$2"
                shift 2
                ;;
            --)
                shift
                break
                ;;
            *)
                log "Unknown argument: $1"
                exit 2
                ;;
        esac
    done
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

on_exit() {
    code="$?"
    if [ "$JOB_FINALIZATION_DEFERRED" = "1" ] && [ "$code" -eq 0 ]; then
        exit "$code"
    fi
    if [ "$code" -eq 0 ]; then
        job_update "success" "Service restart finished." "0" "100" "completed"
    else
        job_update "error" "Service restart failed (exit $code)." "$code" "" "failed"
    fi
    exit "$code"
}

parse_args "$@"
trap on_exit EXIT
job_update "running" "Preparing to restart services." "" "10" "starting"

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

detect_service_manager

if [ "$HTTPS_ENABLED_REQUEST" = "1" ]; then
    if [ ! -f "$SSL_DIR/aprsbox.crt" ] || [ ! -f "$SSL_DIR/aprsbox.key" ]; then
        log "Cannot enable HTTPS: aprsbox.crt or aprsbox.key is missing."
        exit 1
    fi
    touch "$SSL_DIR/https-enabled"
    chown aprsbox:aprsbox "$SSL_DIR/https-enabled" 2>/dev/null || true
elif [ "$HTTPS_ENABLED_REQUEST" = "0" ]; then
    rm -f "$SSL_DIR/https-enabled"
fi

case "$SERVICE_MANAGER" in
    systemd)
        mkdir -p "$SSL_DIR"
        chown aprsbox:aprsbox "$SSL_DIR" 2>/dev/null || true
        chmod 0750 "$SSL_DIR"
        if [ ! -f "$SSL_DIR/https-enabled" ] && grep -q -- "--ssl-certfile" /etc/systemd/system/aprsbox-web.service 2>/dev/null; then
            touch "$SSL_DIR/https-enabled"
            chown aprsbox:aprsbox "$SSL_DIR/https-enabled" 2>/dev/null || true
        fi
        install -m 0644 "$APP_DIR/deploy/systemd/aprsbox-core.service" /etc/systemd/system/aprsbox-core.service
        install -m 0644 "$APP_DIR/deploy/systemd/aprsbox-web.service" /etc/systemd/system/aprsbox-web.service
        install -m 0644 "$APP_DIR/deploy/systemd/aprsbox-http-redirect.service" /etc/systemd/system/aprsbox-http-redirect.service
        systemctl daemon-reload
        job_update "running" "Restarting the web service. The browser may reconnect briefly." "" "75" "restarting-web"
        WEB_RESTART_SCRIPT="$APP_DIR/scripts/update-web-restart.sh"
        if command -v systemd-run >/dev/null 2>&1 && [ -x "$WEB_RESTART_SCRIPT" ] && systemd-run \
            --quiet \
            --collect \
            --unit "aprsbox-service-restart-$$" \
            --setenv="APRSBOX_JOB_ID=$JOB_ID" \
            --setenv="APRSBOX_DB_PATH=$DB_PATH" \
            --setenv="APRSBOX_INSTALL_ROOT=$INSTALL_ROOT" \
            --setenv="APRSBOX_JOB_SUCCESS_MESSAGE=Service restart finished." \
            "$WEB_RESTART_SCRIPT" >/dev/null 2>&1; then
            JOB_FINALIZATION_DEFERRED="1"
        else
            job_update "running" "Restarting the core service." "" "45" "restarting-core"
            systemctl restart aprsbox-core.service
            if [ -f "$SSL_DIR/https-enabled" ]; then
                systemctl enable aprsbox-http-redirect.service >/dev/null 2>&1 || true
                systemctl restart aprsbox-http-redirect.service
            else
                systemctl disable --now aprsbox-http-redirect.service >/dev/null 2>&1 || true
            fi
            systemctl restart aprsbox-web.service
        fi
        ;;
    openrc)
        mkdir -p "$SSL_DIR"
        chown aprsbox:aprsbox "$SSL_DIR" 2>/dev/null || true
        chmod 0750 "$SSL_DIR"
        if [ ! -f "$SSL_DIR/https-enabled" ] && grep -q -- "--ssl-certfile" /etc/init.d/aprsbox-web 2>/dev/null; then
            touch "$SSL_DIR/https-enabled"
            chown aprsbox:aprsbox "$SSL_DIR/https-enabled" 2>/dev/null || true
        fi
        install -m 0755 "$APP_DIR/deploy/openrc/aprsbox-core" /etc/init.d/aprsbox-core
        install -m 0755 "$APP_DIR/deploy/openrc/aprsbox-web" /etc/init.d/aprsbox-web
        install -m 0755 "$APP_DIR/deploy/openrc/aprsbox-http-redirect" /etc/init.d/aprsbox-http-redirect
        job_update "running" "Restarting the core service." "" "45" "restarting-core"
        if rc-service aprsbox-core status >/dev/null 2>&1; then
            rc-service aprsbox-core restart || { rc-service aprsbox-core stop || true; rc-service aprsbox-core start; }
        else
            rc-service aprsbox-core start
        fi
        if [ -f "$SSL_DIR/https-enabled" ]; then
            rc-update add aprsbox-http-redirect default >/dev/null 2>&1 || true
            if rc-service aprsbox-http-redirect status >/dev/null 2>&1; then
                rc-service aprsbox-http-redirect restart || { rc-service aprsbox-http-redirect stop || true; rc-service aprsbox-http-redirect start; }
            else
                rc-service aprsbox-http-redirect start
            fi
        else
            rc-service aprsbox-http-redirect stop >/dev/null 2>&1 || true
            rc-update del aprsbox-http-redirect default >/dev/null 2>&1 || true
        fi
        job_update "running" "Restarting the web service. The browser may reconnect briefly." "" "75" "restarting-web"
        if rc-service aprsbox-web status >/dev/null 2>&1; then
            rc-service aprsbox-web restart || { rc-service aprsbox-web stop || true; rc-service aprsbox-web start; }
        else
            rc-service aprsbox-web start
        fi
        ;;
    *)
        log "No supported service manager detected."
        exit 1
        ;;
esac
