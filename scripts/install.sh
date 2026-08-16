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
SSL_DIR="$INSTALL_ROOT/data/ssl"
ADMIN_USER="${APRSBOX_ADMIN_USER:-}"
ADMIN_PASSWORD="${APRSBOX_ADMIN_PASSWORD:-}"
BOOTSTRAP_WORKDIR=""
STAGING_APP_DIR=""
PREVIOUS_VENV_DIR=""
SERVICES_STARTED="0"
SERVICE_MANAGER="unknown"
CORE_PIDFILE="/run/aprsbox-core.pid"
WEB_PIDFILE="/run/aprsbox-web.pid"
HTTP_REDIRECT_PIDFILE="/run/aprsbox-http-redirect.pid"
SERIAL_DEVICE_GLOBS="${APRSBOX_SERIAL_DEVICE_GLOBS:-/dev/ttyACM* /dev/ttyUSB*}"
PRIV_WRAPPER_DIR="/usr/local/libexec/aprsbox"
SUDOERS_FILE="/etc/sudoers.d/aprsbox"
DOAS_CONF_FILE="/etc/doas.d/aprsbox.conf"

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
            apk add --no-cache python3 py3-pip py3-virtualenv sqlite openrc curl git rsync ca-certificates doas
            ;;
        debian|raspbian)
            apt-get update
            apt-get install -y python3 python3-venv python3-pip sqlite3 adduser rsync curl git ca-certificates sudo
            ;;
        *)
            case "$OS_LIKE" in
                *debian*)
                    apt-get update
                    apt-get install -y python3 python3-venv python3-pip sqlite3 adduser rsync curl git ca-certificates sudo
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
        "$SSL_DIR" \
        "$INSTALL_ROOT/config" \
        "$INSTALL_ROOT/logs" \
        "$INSTALL_ROOT/backups"
    chown -R "$APP_USER":"$APP_USER" "$INSTALL_ROOT"
}

stop_services() {
    case "$SERVICE_MANAGER" in
        systemd)
            systemctl stop aprsbox-http-redirect.service aprsbox-web.service aprsbox-core.service >/dev/null 2>&1 || true
            ;;
        openrc)
            if [ -x /etc/init.d/aprsbox-web ]; then
                rc-service aprsbox-web stop || true
            fi
            if [ -x /etc/init.d/aprsbox-core ]; then
                rc-service aprsbox-core stop || true
            fi
            if [ -x /etc/init.d/aprsbox-http-redirect ]; then
                rc-service aprsbox-http-redirect stop || true
            fi
            cleanup_stale_pidfile "$WEB_PIDFILE"
            cleanup_stale_pidfile "$CORE_PIDFILE"
            cleanup_stale_pidfile "$HTTP_REDIRECT_PIDFILE"
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
    if [ -d "$STAGING_APP_DIR/scripts" ]; then
        find "$STAGING_APP_DIR/scripts" -type f -name '*.sh' -exec chmod 0755 {} \;
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
        "$VENV_DIR/bin/python" -c "import uvicorn, app.main, app.core_main"
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
    ADMIN_USER="${ADMIN_USER:-admin}"
    ADMIN_PASSWORD="${ADMIN_PASSWORD:-aprs}"
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
            install -m 0644 "$SYSTEMD_DEPLOY_DIR/aprsbox-http-redirect.service" /etc/systemd/system/aprsbox-http-redirect.service
            ;;
        openrc)
            install -m 0755 "$OPENRC_DEPLOY_DIR/aprsbox-web" /etc/init.d/aprsbox-web
            install -m 0755 "$OPENRC_DEPLOY_DIR/aprsbox-core" /etc/init.d/aprsbox-core
            install -m 0755 "$OPENRC_DEPLOY_DIR/aprsbox-http-redirect" /etc/init.d/aprsbox-http-redirect
            ;;
        *)
            log "No supported service manager detected. Service files were not installed."
            ;;
    esac
}

install_privileged_wrappers() {
    mkdir -p "$PRIV_WRAPPER_DIR"
    cat > "$PRIV_WRAPPER_DIR/restart-services" <<EOF
#!/bin/sh
set -eu
exec "$TARGET_APP_DIR/scripts/restart-services.sh" "\$@"
EOF
    cat > "$PRIV_WRAPPER_DIR/reboot-host" <<EOF
#!/bin/sh
set -eu
exec "$TARGET_APP_DIR/scripts/reboot-host.sh" "\$@"
EOF
    cat > "$PRIV_WRAPPER_DIR/poweroff-host" <<EOF
#!/bin/sh
set -eu
exec "$TARGET_APP_DIR/scripts/poweroff-host.sh" "\$@"
EOF
    chmod 0755 "$PRIV_WRAPPER_DIR/restart-services" "$PRIV_WRAPPER_DIR/reboot-host" "$PRIV_WRAPPER_DIR/poweroff-host"
    chown root:root "$PRIV_WRAPPER_DIR/restart-services" "$PRIV_WRAPPER_DIR/reboot-host" "$PRIV_WRAPPER_DIR/poweroff-host"
}

install_sudoers_policy() {
    if ! command -v sudo >/dev/null 2>&1; then
        fail "sudo is required but not available."
    fi
    cat > "$SUDOERS_FILE" <<EOF
$APP_USER ALL=(root) NOPASSWD: $TARGET_APP_DIR/scripts/update.sh
$APP_USER ALL=(root) NOPASSWD: $TARGET_APP_DIR/scripts/restart-services.sh
$APP_USER ALL=(root) NOPASSWD: $TARGET_APP_DIR/scripts/reboot-host.sh
$APP_USER ALL=(root) NOPASSWD: $TARGET_APP_DIR/scripts/poweroff-host.sh
$APP_USER ALL=(root) NOPASSWD: $PRIV_WRAPPER_DIR/restart-services
$APP_USER ALL=(root) NOPASSWD: $PRIV_WRAPPER_DIR/reboot-host
$APP_USER ALL=(root) NOPASSWD: $PRIV_WRAPPER_DIR/poweroff-host
EOF
    chmod 0440 "$SUDOERS_FILE"
    chown root:root "$SUDOERS_FILE"
    if command -v visudo >/dev/null 2>&1; then
        visudo -cf "$SUDOERS_FILE" >/dev/null
    fi
}

install_doas_policy() {
    if ! command -v doas >/dev/null 2>&1; then
        fail "doas is required but not available."
    fi
    mkdir -p "$(dirname "$DOAS_CONF_FILE")"
    cat > "$DOAS_CONF_FILE" <<EOF
permit nopass setenv { APRSBOX_INSTALL_ROOT APRSBOX_LOG_DIR APRSBOX_DB_PATH APRSBOX_JOB_ID APRSBOX_GIT_URL APRSBOX_GIT_BRANCH } $APP_USER as root cmd $TARGET_APP_DIR/scripts/update.sh
permit nopass setenv { APRSBOX_INSTALL_ROOT APRSBOX_LOG_DIR APRSBOX_DB_PATH APRSBOX_JOB_ID } $APP_USER as root cmd $TARGET_APP_DIR/scripts/restart-services.sh
permit nopass setenv { APRSBOX_INSTALL_ROOT APRSBOX_LOG_DIR APRSBOX_DB_PATH APRSBOX_JOB_ID } $APP_USER as root cmd $TARGET_APP_DIR/scripts/reboot-host.sh
permit nopass setenv { APRSBOX_INSTALL_ROOT APRSBOX_LOG_DIR APRSBOX_DB_PATH APRSBOX_JOB_ID } $APP_USER as root cmd $TARGET_APP_DIR/scripts/poweroff-host.sh
permit nopass setenv { APRSBOX_INSTALL_ROOT APRSBOX_LOG_DIR APRSBOX_DB_PATH APRSBOX_JOB_ID } $APP_USER as root cmd $PRIV_WRAPPER_DIR/restart-services
permit nopass setenv { APRSBOX_INSTALL_ROOT APRSBOX_LOG_DIR APRSBOX_DB_PATH APRSBOX_JOB_ID } $APP_USER as root cmd $PRIV_WRAPPER_DIR/reboot-host
permit nopass setenv { APRSBOX_INSTALL_ROOT APRSBOX_LOG_DIR APRSBOX_DB_PATH APRSBOX_JOB_ID } $APP_USER as root cmd $PRIV_WRAPPER_DIR/poweroff-host
EOF
    chmod 0600 "$DOAS_CONF_FILE"
    chown root:root "$DOAS_CONF_FILE"
    doas -C "$DOAS_CONF_FILE" >/dev/null
}

install_privilege_policy() {
    case "$OS_ID" in
        alpine)
            install_doas_policy
            ;;
        *)
            install_sudoers_policy
            ;;
    esac
}

enable_services() {
    case "$SERVICE_MANAGER" in
        systemd)
            systemctl daemon-reload
            systemctl enable aprsbox-core.service aprsbox-web.service >/dev/null 2>&1 || true
            if [ -f "$SSL_DIR/https-enabled" ]; then
                systemctl enable aprsbox-http-redirect.service >/dev/null 2>&1 || true
                systemctl restart aprsbox-http-redirect.service
            else
                systemctl disable --now aprsbox-http-redirect.service >/dev/null 2>&1 || true
            fi
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
                if [ -f "$SSL_DIR/https-enabled" ]; then
                    rc-update add aprsbox-http-redirect default || true
                    rc-service aprsbox-http-redirect restart || rc-service aprsbox-http-redirect start
                else
                    rc-service aprsbox-http-redirect stop >/dev/null 2>&1 || true
                    rc-update del aprsbox-http-redirect default >/dev/null 2>&1 || true
                fi
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
    if [ -f "$SSL_DIR/https-enabled" ]; then
        wait_for_http https://127.0.0.1:443/health aprsbox-web
    else
        wait_for_http http://127.0.0.1:80/health aprsbox-web
    fi
    log "Health checks passed for aprsbox-core and aprsbox-web."
}

wait_for_http() {
    url="$1"
    service_name="$2"
    attempt=1
    while [ "$attempt" -le 30 ]; do
        if curl -kfsS "$url" >/dev/null 2>&1; then
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
    prepare_staging_installation
    sync_application_files
    setup_venv
    verify_python_runtime
    stop_services
    backup_database
    initialize_database
    create_admin_user
    activate_staged_installation
    install_privileged_wrappers
    install_privilege_policy
    install_service_units
    enable_services
    verify_services
    log ""
    log "========================================"
    log "APRSBox installation finished."
    log "========================================"
    log "Web application root: $TARGET_APP_DIR"
    log "Database path: $DB_PATH"
    log ""
    if [ -f "$SSL_DIR/https-enabled" ]; then
        log "Application URL: https://<your ip address>"
    else
        log "Application URL: http://<your ip address>"
    fi
    log "Login: $ADMIN_USER"
    log "Password: $ADMIN_PASSWORD"
    log ""
}

main "$@"
