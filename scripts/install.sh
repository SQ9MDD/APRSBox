#!/bin/sh
set -eu

APP_NAME="aprsbox"
APP_USER="aprsbox"
INSTALL_ROOT="${APRSBOX_INSTALL_ROOT:-/opt/aprsbox}"
BOOTSTRAP_GIT_URL="${APRSBOX_GIT_URL:-}"
BOOTSTRAP_GIT_BRANCH="${APRSBOX_GIT_BRANCH:-main}"
REPO_ROOT="$(pwd)"
if [ -n "${0:-}" ] && [ -f "${0:-}" ]; then
    REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
fi
DEPLOY_ROOT="$REPO_ROOT/deploy"
OPENRC_DEPLOY_DIR="$DEPLOY_ROOT/openrc"
SYSTEMD_DEPLOY_DIR="$DEPLOY_ROOT/systemd"
VENV_DIR="$INSTALL_ROOT/venv"
TARGET_APP_DIR="$INSTALL_ROOT/app"
DB_PATH="${APRSBOX_DB_PATH:-$INSTALL_ROOT/data/aprsbox.db}"
ADMIN_USER="${APRSBOX_ADMIN_USER:-}"
ADMIN_PASSWORD="${APRSBOX_ADMIN_PASSWORD:-}"
BOOTSTRAP_WORKDIR=""
STAGING_APP_DIR=""
PREVIOUS_VENV_DIR=""
SERVICES_STARTED="0"
SERVICE_MANAGER="unknown"
CORE_PIDFILE="/run/aprsbox-core.pid"
WEB_PIDFILE="/run/aprsbox-web.pid"
SERIAL_DEVICE_GLOBS="${APRSBOX_SERIAL_DEVICE_GLOBS:-/dev/ttyACM* /dev/ttyUSB*}"

log() {
    printf '%s\n' "$*"
}

fail() {
    log "ERROR: $*"
    exit 1
}

cleanup() {
    if [ -n "$BOOTSTRAP_WORKDIR" ] && [ -d "$BOOTSTRAP_WORKDIR" ]; then
        rm -rf "$BOOTSTRAP_WORKDIR"
    fi
    if [ -n "$STAGING_APP_DIR" ] && [ -d "$STAGING_APP_DIR" ]; then
        rm -rf "$STAGING_APP_DIR"
    fi
    if [ -n "$PREVIOUS_VENV_DIR" ] && [ -d "$PREVIOUS_VENV_DIR" ] && [ ! -d "$VENV_DIR" ]; then
        mv "$PREVIOUS_VENV_DIR" "$VENV_DIR"
        PREVIOUS_VENV_DIR=""
    fi
    if [ -n "$PREVIOUS_VENV_DIR" ] && [ -d "$PREVIOUS_VENV_DIR" ]; then
        rm -rf "$PREVIOUS_VENV_DIR"
    fi
}

trap cleanup EXIT INT TERM

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        fail "This installer must run as root."
    fi
}

detect_os() {
    if [ ! -f /etc/os-release ]; then
        fail "Cannot detect operating system."
    fi
    . /etc/os-release
    OS_ID="${ID:-unknown}"
    OS_LIKE="${ID_LIKE:-}"
}

install_system_packages() {
    case "$OS_ID" in
        alpine)
            apk add --no-cache python3 py3-pip py3-virtualenv sqlite openrc shadow curl git rsync ca-certificates
            ;;
        debian|raspbian)
            apt-get update
            apt-get install -y python3 python3-venv python3-pip sqlite3 adduser rsync curl git ca-certificates
            ;;
        *)
            case "$OS_LIKE" in
                *debian*)
                    apt-get update
                    apt-get install -y python3 python3-venv python3-pip sqlite3 adduser rsync curl git ca-certificates
                    ;;
                *)
                    fail "Unsupported operating system: $OS_ID"
                    ;;
            esac
            ;;
    esac
}

validate_source_tree() {
    if [ ! -d "$REPO_ROOT/app" ]; then
        fail "Source tree is missing directory: $REPO_ROOT/app"
    fi
    if [ ! -f "$REPO_ROOT/requirements.txt" ]; then
        fail "Source tree is missing file: $REPO_ROOT/requirements.txt"
    fi
    if [ ! -d "$OPENRC_DEPLOY_DIR" ]; then
        fail "Source tree is missing directory: $OPENRC_DEPLOY_DIR"
    fi
    if [ ! -d "$SYSTEMD_DEPLOY_DIR" ]; then
        fail "Source tree is missing directory: $SYSTEMD_DEPLOY_DIR"
    fi
}

obtain_source_tree() {
    if [ -d "$REPO_ROOT/app" ] && [ -f "$REPO_ROOT/requirements.txt" ]; then
        validate_source_tree
        return
    fi
    if [ -z "$BOOTSTRAP_GIT_URL" ]; then
        log "No local repository checkout detected."
        log "Set APRSBOX_GIT_URL when running the installer from a downloaded script."
        exit 1
    fi
    BOOTSTRAP_WORKDIR="$(mktemp -d)"
    git clone --depth 1 --branch "$BOOTSTRAP_GIT_BRANCH" "$BOOTSTRAP_GIT_URL" "$BOOTSTRAP_WORKDIR/repo"
    REPO_ROOT="$BOOTSTRAP_WORKDIR/repo"
    DEPLOY_ROOT="$REPO_ROOT/deploy"
    OPENRC_DEPLOY_DIR="$DEPLOY_ROOT/openrc"
    SYSTEMD_DEPLOY_DIR="$DEPLOY_ROOT/systemd"
    validate_source_tree
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

ensure_user() {
    if ! id "$APP_USER" >/dev/null 2>&1; then
        case "$OS_ID" in
            alpine)
                adduser -D -H -s /sbin/nologin "$APP_USER"
                ;;
            *)
                adduser --system --home "$INSTALL_ROOT" --group --shell /usr/sbin/nologin "$APP_USER"
                ;;
        esac
    fi
}

group_exists() {
    getent group "$1" >/dev/null 2>&1
}

user_in_group() {
    id -nG "$APP_USER" 2>/dev/null | tr ' ' '\n' | grep -Fx "$1" >/dev/null 2>&1
}

add_user_to_group() {
    group_name="$1"
    if ! group_exists "$group_name"; then
        return
    fi
    if user_in_group "$group_name"; then
        return
    fi
    if command -v usermod >/dev/null 2>&1; then
        usermod -a -G "$group_name" "$APP_USER"
    else
        case "$OS_ID" in
            alpine)
                addgroup "$APP_USER" "$group_name"
                ;;
            *)
                adduser "$APP_USER" "$group_name"
                ;;
        esac
    fi
    log "Granted serial access group '$group_name' to user '$APP_USER'."
}

device_group_name() {
    device_path="$1"
    if command -v stat >/dev/null 2>&1; then
        if group_name="$(stat -c '%G' "$device_path" 2>/dev/null)"; then
            printf '%s\n' "$group_name"
            return 0
        fi
    fi
    ls -ld "$device_path" 2>/dev/null | awk '{print $4}'
}

grant_serial_permissions() {
    for group_name in dialout uucp tty; do
        add_user_to_group "$group_name"
    done

    for pattern in $SERIAL_DEVICE_GLOBS; do
        for device_path in $pattern; do
            if [ ! -e "$device_path" ]; then
                continue
            fi
            group_name="$(device_group_name "$device_path" | tr -d '\n' || true)"
            if [ -n "$group_name" ]; then
                add_user_to_group "$group_name"
            fi
        done
    done
}

prepare_directories() {
    mkdir -p \
        "$INSTALL_ROOT" \
        "$INSTALL_ROOT/data" \
        "$INSTALL_ROOT/config" \
        "$INSTALL_ROOT/logs" \
        "$INSTALL_ROOT/backups"
    chown -R "$APP_USER":"$APP_USER" "$INSTALL_ROOT"
}

stop_services() {
    case "$SERVICE_MANAGER" in
        systemd)
            systemctl stop aprsbox-web.service aprsbox-core.service >/dev/null 2>&1 || true
            ;;
        openrc)
            if [ -x /etc/init.d/aprsbox-web ]; then
                rc-service aprsbox-web stop || true
            fi
            if [ -x /etc/init.d/aprsbox-core ]; then
                rc-service aprsbox-core stop || true
            fi
            cleanup_stale_pidfile "$WEB_PIDFILE"
            cleanup_stale_pidfile "$CORE_PIDFILE"
            ;;
    esac
}

cleanup_stale_pidfile() {
    pidfile="$1"
    if [ ! -f "$pidfile" ]; then
        return
    fi

    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill -TERM "$pid" 2>/dev/null || true
        sleep 2
    fi

    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill -KILL "$pid" 2>/dev/null || true
        sleep 1
    fi

    rm -f "$pidfile"
}

backup_database() {
    if [ ! -f "$DB_PATH" ]; then
        return
    fi

    timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
    backup_path="$INSTALL_ROOT/backups/aprsbox-db-$timestamp.sqlite3"
    cp "$DB_PATH" "$backup_path"
    chown "$APP_USER":"$APP_USER" "$backup_path" 2>/dev/null || true
    log "Database backup created: $backup_path"
}

prepare_staging_installation() {
    STAGING_APP_DIR="$INSTALL_ROOT/app.new.$$"
    rm -rf "$STAGING_APP_DIR"
    mkdir -p "$STAGING_APP_DIR"
}

sync_application_files() {
    if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete \
            --exclude '.git' \
            --exclude '.venv' \
            --exclude '__pycache__' \
            --exclude '.pytest_cache' \
            "$REPO_ROOT/" "$STAGING_APP_DIR/"
    else
        cp -R "$REPO_ROOT/app" "$STAGING_APP_DIR/"
        cp "$REPO_ROOT/requirements.txt" "$STAGING_APP_DIR/"
        cp -R "$REPO_ROOT/scripts" "$STAGING_APP_DIR/"
        cp -R "$REPO_ROOT/deploy" "$STAGING_APP_DIR/"
        cp "$REPO_ROOT/README.md" "$STAGING_APP_DIR/"
    fi
    chown -R "$APP_USER":"$APP_USER" "$STAGING_APP_DIR"
}

setup_venv() {
    PREVIOUS_VENV_DIR=""
    if [ -d "$VENV_DIR" ]; then
        PREVIOUS_VENV_DIR="$INSTALL_ROOT/venv.old.$$"
        rm -rf "$PREVIOUS_VENV_DIR"
        mv "$VENV_DIR" "$PREVIOUS_VENV_DIR"
    fi

    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel
    "$VENV_DIR/bin/pip" install -r "$STAGING_APP_DIR/requirements.txt"
}

verify_python_runtime() {
    if [ ! -x "$VENV_DIR/bin/python" ]; then
        fail "python was not installed into $VENV_DIR"
    fi

    PYTHONPATH="$STAGING_APP_DIR" \
        APRSBOX_ENV=production \
        APRSBOX_INSTALL_ROOT="$INSTALL_ROOT" \
        APRSBOX_DB_PATH="$DB_PATH" \
        "$VENV_DIR/bin/python" -c "import gunicorn.app.wsgiapp, app.main, app.core_main"

    PYTHONPATH="$STAGING_APP_DIR" \
        APRSBOX_ENV=production \
        APRSBOX_INSTALL_ROOT="$INSTALL_ROOT" \
        APRSBOX_DB_PATH="$DB_PATH" \
        "$VENV_DIR/bin/python" -m gunicorn --check-config --reload --bind 0.0.0.0:8000 --workers 1 --worker-class uvicorn.workers.UvicornWorker app.main:app

    PYTHONPATH="$STAGING_APP_DIR" \
        APRSBOX_ENV=production \
        APRSBOX_INSTALL_ROOT="$INSTALL_ROOT" \
        APRSBOX_DB_PATH="$DB_PATH" \
        "$VENV_DIR/bin/python" -m gunicorn --check-config --reload --bind 127.0.0.1:18081 --workers 1 --worker-class uvicorn.workers.UvicornWorker app.core_main:app
}

activate_staged_installation() {
    rm -rf "$TARGET_APP_DIR"
    mv "$STAGING_APP_DIR" "$TARGET_APP_DIR"
    STAGING_APP_DIR=""
    chown -R "$APP_USER":"$APP_USER" "$TARGET_APP_DIR" "$VENV_DIR"
    if [ -n "$PREVIOUS_VENV_DIR" ] && [ -d "$PREVIOUS_VENV_DIR" ]; then
        rm -rf "$PREVIOUS_VENV_DIR"
        PREVIOUS_VENV_DIR=""
    fi
}

initialize_database() {
    PYTHONPATH="$STAGING_APP_DIR" \
        APRSBOX_ENV=production \
        APRSBOX_INSTALL_ROOT="$INSTALL_ROOT" \
        APRSBOX_DB_PATH="$DB_PATH" \
        "$VENV_DIR/bin/python" -m app.cli init-db
    chown "$APP_USER":"$APP_USER" "$DB_PATH" 2>/dev/null || true
}

prompt_admin() {
    if [ -z "$ADMIN_USER" ]; then
        if [ -r /dev/tty ]; then
            printf 'Initial admin username [admin]: ' >/dev/tty
            read -r ADMIN_USER </dev/tty
        fi
        ADMIN_USER="${ADMIN_USER:-admin}"
    fi
    if [ -z "$ADMIN_PASSWORD" ]; then
        ADMIN_PASSWORD="aprs"
        log "Initial admin password not provided. Using default password: aprs"
    fi
}

create_admin_user() {
    if PYTHONPATH="$STAGING_APP_DIR" \
        APRSBOX_ENV=production \
        APRSBOX_INSTALL_ROOT="$INSTALL_ROOT" \
        APRSBOX_DB_PATH="$DB_PATH" \
        "$VENV_DIR/bin/python" -m app.cli admin-exists
    then
        log "Active admin user already present. Skipping initial admin creation."
        return
    fi
    prompt_admin
    PYTHONPATH="$STAGING_APP_DIR" \
        APRSBOX_ENV=production \
        APRSBOX_INSTALL_ROOT="$INSTALL_ROOT" \
        APRSBOX_DB_PATH="$DB_PATH" \
        "$VENV_DIR/bin/python" -m app.cli create-admin --username "$ADMIN_USER" --password "$ADMIN_PASSWORD"
    chown "$APP_USER":"$APP_USER" "$DB_PATH" 2>/dev/null || true
}

install_service_units() {
    case "$SERVICE_MANAGER" in
        systemd)
            install -m 0644 "$SYSTEMD_DEPLOY_DIR/aprsbox-core.service" /etc/systemd/system/aprsbox-core.service
            install -m 0644 "$SYSTEMD_DEPLOY_DIR/aprsbox-web.service" /etc/systemd/system/aprsbox-web.service
            ;;
        openrc)
            install -m 0755 "$OPENRC_DEPLOY_DIR/aprsbox-web" /etc/init.d/aprsbox-web
            install -m 0755 "$OPENRC_DEPLOY_DIR/aprsbox-core" /etc/init.d/aprsbox-core
            ;;
        *)
            log "No supported service manager detected. Service files were not installed."
            ;;
    esac
}

enable_services() {
    case "$SERVICE_MANAGER" in
        systemd)
            systemctl daemon-reload
            systemctl enable aprsbox-core.service aprsbox-web.service >/dev/null 2>&1 || true
            if systemctl restart aprsbox-core.service && systemctl restart aprsbox-web.service; then
                SERVICES_STARTED="1"
                return
            fi
            log "systemd is available, but services could not be started automatically."
            log "Check 'systemctl status aprsbox-core' and 'systemctl status aprsbox-web' after install."
            ;;
        openrc)
            if command -v rc-update >/dev/null 2>&1; then
                rc-update add aprsbox-core default || true
                rc-update add aprsbox-web default || true
                if rc-service aprsbox-core restart || rc-service aprsbox-core start; then
                    if rc-service aprsbox-web restart || rc-service aprsbox-web start; then
                        SERVICES_STARTED="1"
                        return
                    fi
                fi
                log "OpenRC commands are available, but services could not be started automatically."
                log "Check 'rc-service aprsbox-core status' and 'rc-service aprsbox-web status' after install."
            else
                log "OpenRC detected, but required service commands are unavailable."
            fi
            ;;
        *)
            log "No supported service manager detected. Services were not enabled."
            ;;
    esac
}

verify_services() {
    if [ "$SERVICES_STARTED" != "1" ]; then
        log "Service health checks skipped because services were not started by the installer."
        return
    fi
    if ! command -v curl >/dev/null 2>&1; then
        log "curl not available, health checks skipped."
        return
    fi

    wait_for_http http://127.0.0.1:18081/health aprsbox-core
    wait_for_http http://127.0.0.1:8000/health aprsbox-web
    log "Health checks passed for aprsbox-core and aprsbox-web."
}

wait_for_http() {
    url="$1"
    service_name="$2"
    attempt=1
    while [ "$attempt" -le 30 ]; do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
        attempt=$((attempt + 1))
    done
    fail "Health check failed for $service_name ($url)"
}

main() {
    require_root
    detect_os
    install_system_packages
    detect_service_manager
    obtain_source_tree
    ensure_user
    grant_serial_permissions
    prepare_directories
    stop_services
    backup_database
    prepare_staging_installation
    sync_application_files
    setup_venv
    initialize_database
    verify_python_runtime
    create_admin_user
    activate_staged_installation
    install_service_units
    enable_services
    verify_services
    log "APRSBox installation finished."
    log "Web application root: $TARGET_APP_DIR"
    log "Database path: $DB_PATH"
}

main "$@"
