# APRSBox

APRSBox is intended to become a lightweight APRS operational center for Raspberry Pi systems with a native Linux deployment model. This repository currently provides the first project skeleton: a FastAPI web GUI, session-based authentication, SQLite persistence, installer scaffolding, and OpenRC service integration for a future split between the web UI and a separate APRS core process.

This stage does not implement APRS protocol handling, KISS, APRS-IS connectivity, iGate behavior, DIGI behavior, object transmission, bulletin transmission, or map engine logic. Those areas are intentionally deferred.

## Project Status

Current status: early skeleton, GUI only.

Implemented now:

- FastAPI application with Jinja2 templates and plain CSS
- Session-based login flow with role-aware authorization
- Roles: `admin`, `operator`, `viewer`
- SQLite schema bootstrap and startup initialization
- GUI sections for dashboard, settings, station data, rules, objects, items, bulletins, logs, traffic, map, and admin user management
- Native install script for Alpine Linux and Debian-like Raspberry Pi OS targets
- OpenRC service scaffolding for `aprsbox-web` and placeholder `aprsbox-core`

Planned later:

- APRS transport and protocol engine
- KISS TNC handling
- APRS-IS client/iGate behavior
- DIGI behavior
- Object and bulletin scheduling/transmission
- Traffic monitor backed by live frames
- Map engine integration
- Additional service management and operational tooling

## Repository Layout

```text
aprsbox/
  app/
    __init__.py
    auth.py
    cli.py
    config.py
    db.py
    dependencies.py
    main.py
    models.py
    sections.py
    template_helpers.py
    routers/
    services/
    static/
    templates/
  deploy/
    openrc/
  migrations/
  scripts/
    install.sh
    aprsbox-core-placeholder.sh
  requirements.txt
  README.md
```

## Runtime Layout On Target Host

Native installation is designed around:

```text
/opt/aprsbox/
  app/
  venv/
  data/
  config/
  logs/
  backups/
```

Important paths:

- App code: `/opt/aprsbox/app`
- Virtual environment: `/opt/aprsbox/venv`
- SQLite database: `/opt/aprsbox/data/aprsbox.db`
- Log files: `/opt/aprsbox/logs`
- Future local configuration files: `/opt/aprsbox/config`
- Future backups: `/opt/aprsbox/backups`

## Development Quick Start

Requirements:

- Python 3.11 or newer recommended
- `venv` support available

Create a local environment and run the web app:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m app.cli init-db
python -m app.cli create-admin --username admin
uvicorn app.main:app --reload
```

Then open [http://127.0.0.1:8000/login](http://127.0.0.1:8000/login).

By default in development mode, the SQLite database is stored under `./data/aprsbox.db`.

Useful endpoints:

- `/health`
- `/version`

## Authentication Model

- Login is username/password based
- Passwords are hashed with Python `hashlib.scrypt`
- The web GUI uses signed cookie sessions
- Role policy:
  - `admin`: full access, including user management
  - `operator`: configuration read/write access except admin-only areas
  - `viewer`: read-only access

Initial admin account creation:

- The installer creates the initial admin user
- Default credentials are `admin` / `aprs`
- You can provide credentials interactively
- Or you can set environment variables:
  - `APRSBOX_ADMIN_USER`
  - `APRSBOX_ADMIN_PASSWORD`
- Change the password after the first login

Changing an admin password later:

```bash
python -m app.cli set-password --username admin
```

For an installed system:

```bash
sudo -u aprsbox /opt/aprsbox/venv/bin/python -m app.cli set-password --username admin
```

## Native Installation On Raspberry Pi

### Supported Targets

- Alpine Linux: first-class target
- Raspberry Pi OS / Debian-like systems: supported, but currently a secondary target

### One-Line Bootstrap

The intended deployment model is a one-line bootstrap that downloads and runs `install.sh` on a clean target host. Because a raw shell script does not contain the full application tree by itself, standalone bootstrap mode expects a repository URL via `APRSBOX_GIT_URL`.

After publishing the repository on GitHub, the pattern is:

```bash
curl -fsSL https://raw.githubusercontent.com/SQ9MDD/APRSBox/main/scripts/install.sh | \
  APRSBOX_GIT_URL=https://github.com/SQ9MDD/APRSBox.git sh
```

If you do not provide admin credentials, the installer uses the default initial login `admin` and password `aprs`.

If you prefer to clone first:

```bash
git clone https://github.com/SQ9MDD/APRSBox.git
cd APRSBox
sudo ./scripts/install.sh
```

### What `install.sh` Does

`scripts/install.sh` currently:

- Detects Alpine vs Debian-like systems
- Installs required system packages
- Creates the `aprsbox` system user
- Creates `/opt/aprsbox` runtime directories
- Creates a Python virtual environment under `/opt/aprsbox/venv`
- Installs Python requirements
- Copies the repository into `/opt/aprsbox/app`
- Initializes the SQLite database if needed
- Creates the initial admin user if an active admin does not already exist
- Installs OpenRC service scripts for `aprsbox-web` and `aprsbox-core`
- Enables and starts `aprsbox-web` when OpenRC tooling is available

The installer is designed to be idempotent where practical. It does not intentionally wipe existing database, logs, config, or backups on reinstall.

## Running The Installed Web Service

OpenRC service names:

- `aprsbox-web`
- `aprsbox-core`

Manual service commands:

```bash
rc-service aprsbox-web status
rc-service aprsbox-web restart
rc-service aprsbox-core status
```

The web service listens on port `8000` by default.

## GUI Sections Included In This Skeleton

- Login
- Dashboard
- Settings / Modems
- Settings / APRS-IS Servers
- Station Settings
- iGate Rules
- DIGI Rules
- Objects
- Items
- Bulletins
- Logs
- Traffic Monitor
- Map
- Users / Roles management

Most pages currently provide realistic storage-oriented placeholders: tables, forms, navigation, and permissions are wired, but APRS runtime actions are intentionally absent.

## Database Scope

The initial SQLite schema includes:

- `users`
- `app_settings`
- `modems`
- `aprsis_servers`
- `station_settings`
- `igate_rules`
- `digi_rules`
- `aprs_objects`
- `aprs_items`
- `bulletins`
- `event_logs`

SQLite pragmas currently enabled on connection:

- `foreign_keys = ON`
- `journal_mode = WAL`
- `synchronous = NORMAL`
- `temp_store = MEMORY`
- `busy_timeout = 5000`

## Notes And Limitations

- `aprsbox-core` is only a placeholder service right now
- The traffic monitor and map pages are UI placeholders
- User editing is intentionally minimal in this first skeleton
- There is no migration framework yet; the `migrations/` directory is reserved for future work
- No Docker deployment is provided or recommended for this project
