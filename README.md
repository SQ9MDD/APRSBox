# APRSBox

APRSBox is a lightweight APRS operations application for Raspberry Pi and Linux systems with a native deployment model. The repository contains two FastAPI applications:

- `app.main`: the web GUI
- `app.core_main`: the APRS runtime process responsible for traffic monitoring, outbound queue processing, and periodic schedulers

The project is no longer "GUI only". It already includes a working SQLite-backed configuration model, authenticated GUI, APRS runtime services, Packet Routing flows, APRS-IS uplink runtime, and native installation scripts for OpenRC and systemd hosts.

<img width="1702" height="1147" alt="APRSBox" src="https://github.com/user-attachments/assets/cfa35f80-3db4-4601-af37-ad8fb9f1f4ce" />


## Run Docker Container

If you want to install APRSBox container just use this command:

```bash
docker run -d \
  --name aprsbox \
  --restart unless-stopped \
  -p 8000:8000 \
  -v aprsbox_data:/opt/aprsbox/data \
  -v aprsbox_logs:/opt/aprsbox/logs \
  sq9mddpl/aprsbox:1.8.24
```
Open the web interface: http://127.0.0.1:8000


## Fast Install

If you want to install APRSBox on a target Linux machine, the fastest path is a single installer command.

- run one command
- the script installs packages, creates the Python environment, initializes the database, installs services, and starts the app

**Installer-supported targets**

- Alpine Linux
- Debian, Raspberry Pi OS / Raspbian, and Debian-like systems exposing `ID_LIKE=debian`

**Alpine Linux** (run as root):

```bash
curl -fsSL https://raw.githubusercontent.com/SQ9MDD/APRSBox/main/scripts/install.sh | \
  env APRSBOX_GIT_URL=https://github.com/SQ9MDD/APRSBox.git APRSBOX_GIT_BRANCH=main sh
```

**Raspberry Pi OS / Debian / Debian-like** (use `sudo`):

```bash
curl -fsSL https://raw.githubusercontent.com/SQ9MDD/APRSBox/main/scripts/install.sh | \
  sudo env APRSBOX_GIT_URL=https://github.com/SQ9MDD/APRSBox.git APRSBOX_GIT_BRANCH=main sh
```

**After installation**

- web GUI: `http://<host>:8000/login`
- default login: `admin`
- default password: `aprs`

## APRS Runtime Scope

Current APRS runtime behavior:

- RX:
  - connects to enabled TCP or serial KISS TNC interfaces
  - reads KISS frames
  - decodes AX.25 UI frames to TNC2 when possible
  - stores frames in SQLite
  - updates heard-station views, band condition processing, and APRS message ingestion
- TX:
  - queues outbound jobs in SQLite
  - processes jobs from the core worker
  - supports `beacon`, `status`, `object`, APRS messages (`direct`, `query`, `ack`), bulletins / announcements, WX, and DIGI TX jobs
  - builds TNC2 lines and wraps them into KISS frames
  - sends them via active monitor connection (with direct transport fallback)
- Packet Routing (DIGI Flows):
  - source is currently `receiver_rf`
  - supports filters (`dupe`, `path`, `strict`, `direct_only`, `digi`, `callsign`, `packet_type`, `icon`, `distance`)
  - supports targets `tx_rf`, `tx_aprsis`, `action_log`, `action_drop`
- APRS-IS uplink:
  - managed automatically from enabled Packet Routing flows with `tx_aprsis` target
  - includes strict guard for blocked path tokens and malformed third-party frames
  - provides runtime diagnostics and counters in GUI
- Scheduling:
  - station beacon scheduler
  - station APRS Status scheduler
  - object scheduler with jitter spacing between object transmissions
  - bulletin / announcement scheduler with jitter spacing between message transmissions
  - WX scheduler

Important current limitation:

- Runtime transport supports `TCP` modem definitions with `host:port` and `SERIALL` modem definitions with `device_path` plus `baud_rate`.
- Packet Routing source runtime is currently limited to `receiver_rf`.

---

# APRSBox PL

APRSBox to lekka aplikacja APRS dla Raspberry Pi i systemów Linux z natywnym modelem instalacji. Repozytorium zawiera dwie aplikacje FastAPI:

- `app.main`: web GUI
- `app.core_main`: proces runtime odpowiedzialny za monitoring ruchu, kolejkę outbound i schedulery okresowe

Projekt nie jest już wyłącznie szkieletem GUI. W repo są działające elementy runtime APRS: RX/TX KISS, kolejka outbound w SQLite, Packet Routing (DIGI Flows), uplink APRS-IS, wiadomości APRS oraz schedulery beacon/status/object/bulletin/WX.

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
