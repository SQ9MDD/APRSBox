#!/bin/sh
set -eu

SERVICE_MANAGER="unknown"
JOB_ID="${APRSBOX_JOB_ID:-}"
DB_PATH="${APRSBOX_DB_PATH:-}"

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

job_update() {
    status="$1"
    message="${2:-}"
    exit_code="${3:-}"
    if ! job_can_update; then
        return 0
    fi
    now="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    safe_message="$(job_escape "$message")"
    safe_status="$(job_escape "$status")"
    exit_sql="NULL"
    if [ -n "$exit_code" ]; then
        exit_sql="$(job_escape "$exit_code")"
    fi
    sqlite3 "$DB_PATH" ".timeout 5000" "UPDATE system_jobs SET status = '$safe_status', message = '$safe_message', exit_code = $exit_sql, started_at = COALESCE(started_at, '$now'), finished_at = CASE WHEN '$safe_status' IN ('success','error') THEN COALESCE(finished_at, '$now') ELSE finished_at END, updated_at = '$now' WHERE id = $JOB_ID;" >/dev/null 2>&1 || true
}

on_exit() {
    code="$?"
    if [ "$code" -eq 0 ]; then
        job_update "success" "Service restart finished." "0"
    else
        job_update "error" "Service restart failed (exit $code)." "$code"
    fi
    exit "$code"
}

trap on_exit EXIT
job_update "running" "Restarting services..." ""

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
        log "No supported service manager detected."
        exit 1
        ;;
esac
