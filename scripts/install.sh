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
DEPLOY_DIR="$REPO_ROOT/deploy/openrc"
VENV_DIR="$INSTALL_ROOT/venv"
TARGET_APP_DIR="$INSTALL_ROOT/app"
DB_PATH="${APRSBOX_DB_PATH:-$INSTALL_ROOT/data/aprsbox.db}"
ADMIN_USER="${APRSBOX_ADMIN_USER:-}"
ADMIN_PASSWORD="${APRSBOX_ADMIN_PASSWORD:-}"
BOOTSTRAP_WORKDIR=""
STAGING_APP_DIR=""
PREVIOUS_VENV_DIR=""
SERVICES_STARTED="0"
CORE_PIDFILE="/run/aprsbox-core.pid"
WEB_PIDFILE="/run/aprsbox-web.pid"

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
    if [ ! -d "$REPO_ROOT/deploy/openrc" ]; then
        fail "Source tree is missing directory: $REPO_ROOT/deploy/openrc"
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
    DEPLOY_DIR="$REPO_ROOT/deploy/openrc"
    validate_source_tree
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
    if ! command -v rc-service >/dev/null 2>&1; then
        return
    fi

    if [ -x /etc/init.d/aprsbox-web ]; then
        rc-service aprsbox-web stop || true
    fi
    if [ -x /etc/init.d/aprsbox-core ]; then
        rc-service aprsbox-core stop || true
    fi

    cleanup_stale_pidfile "$WEB_PIDFILE"
    cleanup_stale_pidfile "$CORE_PIDFILE"
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
    if [ ! -x "$VENV_DIR/bin/gunicorn" ]; then
        fail "gunicorn was not installed into $VENV_DIR"
    fi

    PYTHONPATH="$STAGING_APP_DIR" \
        APRSBOX_ENV=production \
        APRSBOX_INSTALL_ROOT="$INSTALL_ROOT" \
        APRSBOX_DB_PATH="$DB_PATH" \
        "$VENV_DIR/bin/python" -c "import app.main, app.core_main"

    PYTHONPATH="$STAGING_APP_DIR" \
        APRSBOX_ENV=production \
        APRSBOX_INSTALL_ROOT="$INSTALL_ROOT" \
        APRSBOX_DB_PATH="$DB_PATH" \
        "$VENV_DIR/bin/gunicorn" --check-config --bind 0.0.0.0:8000 --workers 1 --worker-class uvicorn.workers.UvicornWorker app.main:app

    PYTHONPATH="$STAGING_APP_DIR" \
        APRSBOX_ENV=production \
        APRSBOX_INSTALL_ROOT="$INSTALL_ROOT" \
        APRSBOX_DB_PATH="$DB_PATH" \
        "$VENV_DIR/bin/gunicorn" --check-config --bind 127.0.0.1:18081 --workers 1 --worker-class uvicorn.workers.UvicornWorker app.core_main:app
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

install_openrc_services() {
    install -m 0755 "$DEPLOY_DIR/aprsbox-web" /etc/init.d/aprsbox-web
    install -m 0755 "$DEPLOY_DIR/aprsbox-core" /etc/init.d/aprsbox-core
}

enable_services() {
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
        log "OpenRC not available on this host. Service files were installed but not enabled."
    fi
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
    obtain_source_tree
    ensure_user
    prepare_directories
    stop_services
    backup_database
    prepare_staging_installation
    sync_application_files
    setup_venv
    verify_python_runtime
    initialize_database
    create_admin_user
    activate_staged_installation
    install_openrc_services
    enable_services
    verify_services
    log "APRSBox installation finished."
    log "Web application root: $TARGET_APP_DIR"
    log "Database path: $DB_PATH"
}

main "$@"
