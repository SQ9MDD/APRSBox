# APRSBox

APRSBox is a lightweight APRS operations application for Raspberry Pi and Linux systems with a native deployment model. The repository contains two FastAPI applications:

- `app.main`: the web GUI
- `app.core_main`: the APRS runtime process responsible for traffic monitoring, outbound queue processing, and periodic schedulers

The project is no longer "GUI only". It already includes a working SQLite-backed configuration model, authenticated GUI, TCP KISS and serial KISS traffic monitoring, outbound APRS transmission for selected packet types, and native installation scripts for OpenRC and systemd hosts.

<img width="1702" height="1147" alt="APRSBox" src="https://github.com/user-attachments/assets/cfa35f80-3db4-4601-af37-ad8fb9f1f4ce" />


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
  - connects to an enabled TCP or serial KISS TNC
  - reads KISS frames
  - decodes AX.25 UI frames to TNC2 when possible
  - stores frames in SQLite
  - updates heard-station views and band condition processing
- TX:
  - queues outbound jobs in SQLite
  - processes jobs from the core worker
  - currently supports `beacon`, `status`, `object`, APRS messages, and bulletin / announcement frames
  - builds TNC2 lines and wraps them into KISS frames
  - sends them to the configured TCP or serial KISS TNC
- Scheduling:
  - station beacon scheduler
  - station APRS Status scheduler
  - object scheduler with jitter spacing between object transmissions
  - bulletin / announcement scheduler with jitter spacing between message transmissions

Important current limitation:

- The runtime path uses the interface selected in station settings for station beacon/status/object/message/bulletin TX.
- Runtime transport supports `TCP` modem definitions with `host:port` and `SERIALL` modem definitions with `device_path` plus `baud_rate`.

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
