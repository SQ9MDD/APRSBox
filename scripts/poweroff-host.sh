#!/bin/sh
set -eu

JOB_ID="${APRSBOX_JOB_ID:-}"
DB_PATH="${APRSBOX_DB_PATH:-}"

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
                    exit 2
                fi
                case "$2" in
                    "" | *[!0-9]*) exit 2 ;;
                esac
                JOB_ID="$2"
                shift 2
                ;;
            --db-path)
                if [ "$#" -lt 2 ] || [ -z "$2" ]; then
                    exit 2
                fi
                DB_PATH="$2"
                shift 2
                ;;
            --)
                shift
                break
                ;;
            *)
                exit 2
                ;;
        esac
    done
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
        job_update "success" "Host power off initiated." "0"
    else
        job_update "error" "Host power off failed (exit $code)." "$code"
    fi
    exit "$code"
}

parse_args "$@"
trap on_exit EXIT
job_update "running" "Powering off host..." ""

if command -v systemctl >/dev/null 2>&1; then
    systemctl --no-block poweroff
    exit 0
fi

if command -v poweroff >/dev/null 2>&1; then
    poweroff &
    exit 0
fi

printf '%s\n' "No poweroff command found."
exit 1
