#!/bin/sh
set -eu

JOB_ID="${APRSBOX_JOB_ID:-}"
DB_PATH="${APRSBOX_DB_PATH:-}"
INSTALL_ROOT="${APRSBOX_INSTALL_ROOT:-/opt/aprsbox}"
APP_DIR="$INSTALL_ROOT/app"

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
    safe_status="$(job_escape "$status")"
    safe_message="$(job_escape "$message")"
    safe_stage="$(job_escape "$stage")"
    exit_sql="NULL"
    if [ -n "$exit_code" ]; then
        exit_sql="$(job_escape "$exit_code")"
    fi
    update_sql="UPDATE system_jobs SET status = '$safe_status', message = '$safe_message', progress_percent = $progress_percent, stage = '$safe_stage', exit_code = $exit_sql, started_at = COALESCE(started_at, '$now'), finished_at = CASE WHEN '$safe_status' IN ('success','error') THEN COALESCE(finished_at, '$now') ELSE finished_at END, updated_at = '$now' WHERE id = $JOB_ID;"
    attempt="0"
    while [ "$attempt" -lt 3 ]; do
        if sqlite3 "$DB_PATH" ".timeout 5000" "$update_sql" >/dev/null 2>&1; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    return 0
}

on_exit() {
    code="$?"
    if [ "$code" -eq 0 ]; then
        job_update "success" "Application update finished successfully." "0" "100" "completed"
    else
        job_update "error" "Web service restart failed (exit $code)." "$code" "98" "failed"
    fi
    exit "$code"
}

trap on_exit EXIT
job_update "running" "Restarting the web service. The browser may reconnect briefly." "" "98" "restarting-web"
sleep 1
install -m 0644 "$APP_DIR/deploy/systemd/aprsbox-core.service" /etc/systemd/system/aprsbox-core.service
install -m 0644 "$APP_DIR/deploy/systemd/aprsbox-web.service" /etc/systemd/system/aprsbox-web.service
install -m 0644 "$APP_DIR/deploy/systemd/aprsbox-http-redirect.service" /etc/systemd/system/aprsbox-http-redirect.service
systemctl daemon-reload
systemctl enable aprsbox-http-redirect.service >/dev/null 2>&1 || true
systemctl restart aprsbox-core.service
systemctl restart aprsbox-http-redirect.service
systemctl restart aprsbox-web.service
