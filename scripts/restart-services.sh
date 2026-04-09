#!/bin/sh
set -eu

SERVICE_MANAGER="unknown"

log() {
    printf '%s\n' "$*"
}

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
        rc-service aprsbox-core restart || rc-service aprsbox-core start
        rc-service aprsbox-web restart || rc-service aprsbox-web start
        ;;
    *)
        log "No supported service manager detected."
        exit 1
        ;;
esac
