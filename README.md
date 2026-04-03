# APRSBox

APRSBox is a lightweight APRS operations application for Raspberry Pi and Linux systems with a native deployment model. The repository contains two FastAPI applications:

- `app.main`: the web GUI
- `app.core_main`: the APRS runtime process responsible for traffic monitoring, outbound queue processing, and periodic schedulers

The project is no longer "GUI only". It already includes a working SQLite-backed configuration model, authenticated GUI, a TCP KISS traffic monitor, outbound APRS transmission for selected packet types, and native installation scripts for OpenRC and systemd hosts.

## Fast Install

If you want to install APRSBox on a target Linux machine, the simplest message is:

- run one command
- the script installs packages, creates the Python environment, initializes the database, installs services, and starts the app

Alpine Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/SQ9MDD/APRSBox/main/scripts/install.sh | \
  env APRSBOX_GIT_URL=https://github.com/SQ9MDD/APRSBox.git APRSBOX_GIT_BRANCH=main sh
```

Raspberry Pi OS / Debian:

```bash
curl -fsSL https://raw.githubusercontent.com/SQ9MDD/APRSBox/main/scripts/install.sh | \
  sudo env APRSBOX_GIT_URL=https://github.com/SQ9MDD/APRSBox.git APRSBOX_GIT_BRANCH=main sh
```

After installation:

- web GUI: `http://<host>:8000/login`
- default login: `admin`
- default password: `aprs`

If you want to set custom initial credentials during install:

```bash
curl -fsSL https://raw.githubusercontent.com/SQ9MDD/APRSBox/main/scripts/install.sh | \
  sudo env \
    APRSBOX_GIT_URL=https://github.com/SQ9MDD/APRSBox.git \
    APRSBOX_GIT_BRANCH=main \
    APRSBOX_ADMIN_USER=myadmin \
    APRSBOX_ADMIN_PASSWORD='strong-password' \
    sh
```

## Current Project Status

Implemented now:

- FastAPI web GUI with Jinja2 templates and plain CSS
- Session-based login flow with role-aware authorization
- Roles: `admin`, `operator`, `viewer`
- SQLite schema bootstrap with inline schema evolution in `init_db()`
- Native install script for Alpine Linux and Debian-like Raspberry Pi OS targets
- native services for `aprsbox-web` and `aprsbox-core` on OpenRC and systemd hosts
- Station settings with:
  - callsign and SSID
  - selected outbound interface
  - beacon comment and beacon interval
  - separate APRS Status text and interval
  - map-based location picker
  - symbol selection
- Manual beacon enqueue from the GUI
- Scheduled outbound station position beacons
- Scheduled outbound APRS Status frames
- Scheduled outbound APRS object frames
- Outbound queue persisted in SQLite
- KISS/TNC2 frame generation for:
  - station beacon
  - APRS Status
  - APRS object
- TCP TNC outbound delivery through the core worker
- TCP TNC traffic monitor with KISS frame ingestion and TNC2 decoding
- Traffic persistence to `traffic_frames`
- Heard-station views and station detail pages
- Leaflet-based map page backed by heard-station data
- Band condition processing based on received traffic history
- Logs and recent outbound job history in the GUI
- User management from the admin area

Not implemented yet:

- APRS-IS client connectivity
- iGate runtime logic
- digipeater runtime logic
- outbound APRS item scheduling/transmission
- outbound bulletin scheduling/transmission
- APRS message transmit
- runtime support for serial TNC links; current runtime code works with TCP TNC endpoints
- advanced migration framework; schema updates are handled directly in `app.db.init_db()`

## Repository Layout

```text
APRSBox/
  app/
    __init__.py
    auth.py
    cli.py
    config.py
    core_main.py
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
    systemd/
  scripts/
    install.sh
    aprsbox-core-placeholder.sh
    update-gui.sh
  tests/
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
- Config directory: `/opt/aprsbox/config`
- Backup directory: `/opt/aprsbox/backups`

## Development Quick Start

Requirements:

- Python 3.11 or newer recommended
- `venv` support available

Create a local environment:

```bash
git clone https://github.com/SQ9MDD/APRSBox.git
cd APRSBox
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m app.cli init-db
python -m app.cli create-admin --username admin
```

Run the web GUI:

```bash
uvicorn app.main:app --reload
```

Run the core runtime in a second terminal:

```bash
uvicorn app.core_main:app --reload --port 18081
```

Then open [http://127.0.0.1:8000/login](http://127.0.0.1:8000/login).

By default in development mode, the SQLite database is stored under `./data/aprsbox.db`.

Useful endpoints:

- Web:
  - `/health`
  - `/version`
- Core:
  - `/health`
  - `/version`
  - `/api/traffic`

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

Changing a password later:

```bash
python -m app.cli set-password --username admin
```

For an installed system:

```bash
sudo -u aprsbox /opt/aprsbox/venv/bin/python -m app.cli set-password --username admin
```

## APRS Runtime Scope

Current APRS runtime behavior:

- RX:
  - connects to an enabled TCP TNC
  - reads KISS frames
  - decodes AX.25 UI frames to TNC2 when possible
  - stores frames in SQLite
  - updates heard-station views and band condition processing
- TX:
  - queues outbound jobs in SQLite
  - processes jobs from the core worker
  - currently supports `beacon`, `status`, and `object`
  - builds TNC2 lines and wraps them into KISS frames
  - sends them to the configured TCP TNC endpoint
- Scheduling:
  - station beacon scheduler
  - station APRS Status scheduler
  - object scheduler with jitter spacing between object transmissions

Important current limitation:

- The runtime path uses the interface selected in station settings for station beacon/status/object TX.
- Runtime transport currently expects `TCP` modem definitions with `host:port`.
- `SERIALL` may appear in configuration, but runtime RX/TX code does not use it yet.

## Native Installation On Raspberry Pi

### Supported Targets

- Alpine Linux: first-class target
- Raspberry Pi OS / Debian-like systems: supported

### Online Bootstrap

The intended deployment model is an online bootstrap that downloads and runs `install.sh` on a clean target host. Because a raw shell script does not contain the full application tree by itself, bootstrap mode expects a repository URL via `APRSBOX_GIT_URL`.

General bootstrap:

```bash
curl -fsSL https://raw.githubusercontent.com/SQ9MDD/APRSBox/main/scripts/install.sh | \
  env APRSBOX_GIT_URL=https://github.com/SQ9MDD/APRSBox.git APRSBOX_GIT_BRANCH=main sh
```

On Raspberry Pi OS / Debian-like systems, `sudo` must be part of the bootstrap command itself:

```bash
curl -fsSL https://raw.githubusercontent.com/SQ9MDD/APRSBox/main/scripts/install.sh | \
  sudo env APRSBOX_GIT_URL=https://github.com/SQ9MDD/APRSBox.git APRSBOX_GIT_BRANCH=main sh
```

If you do not provide admin credentials, the installer uses the default initial login `admin` and password `aprs`.

### What `install.sh` Does

`scripts/install.sh` currently:

- detects Alpine vs Debian-like systems
- installs required system packages
- creates the `aprsbox` system user
- creates `/opt/aprsbox` runtime directories
- stops existing `aprsbox-core` and `aprsbox-web` services before replacing files
- creates a timestamped backup of the SQLite database under `/opt/aprsbox/backups` when a database already exists
- creates a Python virtual environment under `/opt/aprsbox/venv`
- installs Python requirements
- copies the repository into `/opt/aprsbox/app`
- initializes the SQLite database if needed
- creates the initial admin user if an active admin does not already exist
- installs OpenRC service scripts or systemd units for `aprsbox-web` and `aprsbox-core`
- enables and starts `aprsbox-core` and `aprsbox-web` when a supported service manager is available
- runs local health checks for both services when `curl` is available

The installer is designed to be idempotent where practical. It does not intentionally wipe existing database, logs, config, or backups on reinstall.

Current reinstall behavior:

- `/opt/aprsbox/app` is rebuilt on each installer run
- `/opt/aprsbox/venv` is rebuilt on each installer run
- the SQLite database in `/opt/aprsbox/data/aprsbox.db` is preserved
- a fresh backup copy of the database is created before reinstall work starts

## Running The Installed Services

Service names:

- `aprsbox-web`
- `aprsbox-core`

Manual service commands on OpenRC:

```bash
rc-service aprsbox-web status
rc-service aprsbox-web restart
rc-service aprsbox-core status
rc-service aprsbox-core restart
```

Manual service commands on systemd:

```bash
systemctl status aprsbox-web
systemctl restart aprsbox-web
systemctl status aprsbox-core
systemctl restart aprsbox-core
```

Default ports:

- web GUI: `8000`
- core runtime API: `18081`

## Manual Checks On An Installed System

After native installation, the application source tree is under `/opt/aprsbox/app` and the production virtual environment is `/opt/aprsbox/venv`.

Do not run development commands from `/opt/aprsbox`, because that directory only contains runtime folders and not the repository root files such as `requirements.txt`.

Correct manual checks on an installed host:

```bash
cd /opt/aprsbox/app
/opt/aprsbox/venv/bin/pip install -r requirements.txt
/opt/aprsbox/venv/bin/python -m app.cli init-db
/opt/aprsbox/venv/bin/python -m app.cli admin-exists
/opt/aprsbox/venv/bin/gunicorn --reload --bind 0.0.0.0:8000 --workers 1 --worker-class uvicorn.workers.UvicornWorker app.main:app
```

If you need to reset the admin password on an installed host:

```bash
cd /opt/aprsbox/app
PYTHONPATH=/opt/aprsbox/app /opt/aprsbox/venv/bin/python -m app.cli set-password --username admin
```

## GUI Areas

The GUI currently includes:

- Login
- Dashboard
- My Settings
- Settings / TNC
- Settings / APRS-IS Servers
- iGate Rules
- DIGI Rules
- Objects
- Items
- Bulletins
- Logs
- Traffic
- Map
- Stations
- Station detail
- Users / Roles management

Current behavior by area:

- `My Settings`:
  - stores station identity, symbol and location
  - supports scheduled beacon and APRS Status configuration
  - allows manual beacon enqueue
  - shows recent station TX log
- `Objects`:
  - validates APRS-safe object fields
  - stores object definitions
  - supports scheduled object transmission through the core scheduler
- `Items`:
  - validates APRS-safe item fields
  - stores item definitions
  - does not transmit items yet
- `Traffic`:
  - shows live persisted RX/TX frame history from SQLite
- `Map`:
  - renders heard stations on a Leaflet map using stored/decoded traffic data
- `Stations` and `Station detail`:
  - show heard station snapshots derived from incoming traffic
  - message form is present, but message TX is not implemented

## Database Scope

The SQLite schema currently includes:

- `users`
- `app_settings`
- `modems`
- `aprsis_servers`
- `station_settings`
- `outbound_jobs`
- `igate_rules`
- `digi_rules`
- `aprs_objects`
- `aprs_items`
- `bulletins`
- `event_logs`
- `traffic_frames`
- `traffic_runtime_state`
- `band_condition_reference_stations`
- `band_condition_audibility_buckets`
- `band_condition_activity_station_buckets`
- `band_condition_activity_buckets`
- `band_condition_audibility_baseline`
- `band_condition_activity_baseline`
- `band_condition_fixed_station_baseline`

SQLite pragmas currently enabled on connection:

- `foreign_keys = ON`
- `journal_mode = WAL`
- `synchronous = NORMAL`
- `temp_store = MEMORY`
- `busy_timeout = 5000`

## Notes And Limitations

- Station beacon, APRS Status and object TX currently depend on the core process being up
- Runtime RX/TX currently supports TCP TNC endpoints, not serial runtime links
- APRS-IS, iGate and DIGI sections are configuration storage only at this stage
- Items and bulletins are stored in SQLite but not transmitted yet
- APRS message transmit UI exists, but message sending is not implemented
- Schema evolution is handled directly in code during startup; there is no separate migration framework yet
- No Docker deployment is provided or recommended for this project

---

# APRSBox PL

APRSBox to lekka aplikacja APRS dla Raspberry Pi i systemów Linux z natywnym modelem instalacji. Repozytorium zawiera dwie aplikacje FastAPI:

- `app.main`: web GUI
- `app.core_main`: proces runtime odpowiedzialny za monitoring ruchu, kolejkę outbound i schedulery okresowe

Projekt nie jest już wyłącznie szkieletem GUI. W repo są już działające elementy runtime: TCP KISS RX, outbound beacon/status/object, kolejka TX w SQLite, mapa, heard stations i band condition.

## Szybka instalacja

Najprostszy przekaz dla mniej zaawansowanego użytkownika jest taki:

- uruchamiasz jedno polecenie
- skrypt robi resztę sam

To znaczy:

- instaluje wymagane pakiety systemowe
- tworzy virtualenv Pythona
- kopiuje aplikację do `/opt/aprsbox/app`
- inicjalizuje bazę SQLite
- zakłada konto admin
- instaluje serwisy `aprsbox-web` i `aprsbox-core`
- uruchamia aplikację i sprawdza health check

Alpine Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/SQ9MDD/APRSBox/main/scripts/install.sh | \
  env APRSBOX_GIT_URL=https://github.com/SQ9MDD/APRSBox.git APRSBOX_GIT_BRANCH=main sh
```

Raspberry Pi OS / Debian:

```bash
curl -fsSL https://raw.githubusercontent.com/SQ9MDD/APRSBox/main/scripts/install.sh | \
  sudo env APRSBOX_GIT_URL=https://github.com/SQ9MDD/APRSBox.git APRSBOX_GIT_BRANCH=main sh
```

Po instalacji:

- panel WWW: `http://<host>:8000/login`
- domyślny login: `admin`
- domyślne hasło: `aprs`

Jeśli chcesz od razu ustawić własnego administratora:

```bash
curl -fsSL https://raw.githubusercontent.com/SQ9MDD/APRSBox/main/scripts/install.sh | \
  sudo env \
    APRSBOX_GIT_URL=https://github.com/SQ9MDD/APRSBox.git \
    APRSBOX_GIT_BRANCH=main \
    APRSBOX_ADMIN_USER=myadmin \
    APRSBOX_ADMIN_PASSWORD='strong-password' \
    sh
```

## Aktualny stan projektu

Już działa:

- web GUI na FastAPI + Jinja2
- logowanie i role `admin`, `operator`, `viewer`
- SQLite z automatyczną inicjalizacją i aktualizacją schematu przy starcie
- natywna instalacja i usługi OpenRC lub systemd
- ustawienia stacji:
  - callsign i SSID
  - wybór interfejsu nadawczego
  - beacon pozycyjny
  - osobny APRS Status
  - wybór symbolu
  - wybór lokalizacji z mapy
- ręczne wysłanie beaconu z GUI
- okresowa wysyłka:
  - beaconu stacji
  - APRS Status
  - obiektów APRS
- kolejka outbound zapisywana w SQLite
- budowanie ramek TNC2/KISS dla:
  - beaconu
  - statusu
  - obiektu
- monitoring ruchu z TCP TNC
- zapis ramek RX/TX do bazy
- widok heard stations i szczegóły stacji
- mapa Leaflet oparta o odebrane dane
- band condition liczone na podstawie historii ruchu
- logi i historia zadań TX w GUI
- zarządzanie użytkownikami

Jeszcze nie działa:

- APRS-IS runtime
- runtime iGate
- runtime digipeatera
- nadawanie APRS item
- nadawanie bulletinów
- nadawanie wiadomości APRS
- runtime dla połączeń szeregowych TNC; obecny kod działa dla endpointów TCP

## Development local

Lokalne uruchomienie w repo:

```bash
git clone https://github.com/SQ9MDD/APRSBox.git
cd APRSBox
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m app.cli init-db
python -m app.cli create-admin --username admin
uvicorn app.main:app --reload
```

Core uruchamiasz w drugim terminalu:

```bash
uvicorn app.core_main:app --reload --port 18081
```

## Zakres runtime APRS

Obecnie runtime:

- odbiera dane z włączonego TCP TNC
- czyta ramki KISS
- dekoduje AX.25 UI do TNC2, jeśli to możliwe
- zapisuje ruch do SQLite
- aktualizuje widoki stacji i band condition
- pobiera zadania outbound z kolejki SQLite
- wysyła `beacon`, `status` i `object`
- używa aktualnie wybranego interfejsu stacji dla TX

Ważne ograniczenia:

- TX beacon/status/object działa tylko wtedy, gdy działa `aprsbox-core`
- runtime oczekuje modemów typu `TCP` w formacie `host:port`
- wpis typu `SERIALL` może istnieć w konfiguracji, ale runtime go jeszcze nie obsługuje
- sekcje APRS-IS, iGate i DIGI są obecnie głównie konfiguracją do przyszłego runtime

## Serwisy po instalacji

Nazwy serwisów:

- `aprsbox-web`
- `aprsbox-core`

Przydatne komendy w OpenRC:

```bash
rc-service aprsbox-web status
rc-service aprsbox-web restart
rc-service aprsbox-core status
rc-service aprsbox-core restart
```

Przydatne komendy w systemd:

```bash
systemctl status aprsbox-web
systemctl restart aprsbox-web
systemctl status aprsbox-core
systemctl restart aprsbox-core
```

Domyślne porty:

- web GUI: `8000`
- API procesu core: `18081`

## Najważniejsze ograniczenia

- APRS-IS, iGate i DIGI nie mają jeszcze runtime
- itemy i bulletiny są przechowywane, ale nie są nadawane
- formularz APRS message istnieje, ale nie wysyła wiadomości
- ewolucja schematu bazy jest robiona w kodzie przy starcie, bez osobnego frameworka migracji
- projekt nie ma i nie promuje deploymentu przez Docker
