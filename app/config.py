from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app import __version__


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _env_flag(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = str(raw_value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    return default


@dataclass(slots=True)
class Settings:
    app_name: str = "APRSBox"
    app_version: str = __version__
    app_env: str = os.getenv("APRSBOX_ENV", "development")
    secret_key: str = os.getenv("APRSBOX_SECRET_KEY", "change-me-in-production")
    install_root: Path = Path(os.getenv("APRSBOX_INSTALL_ROOT", "/opt/aprsbox"))
    repo_root: Path = _repo_root()
    gui_update_url: str = os.getenv("APRSBOX_GIT_URL", "https://github.com/SQ9MDD/APRSBox.git")
    gui_update_branch: str = os.getenv("APRSBOX_GIT_BRANCH", "main")
    privileged_runner: str = os.getenv("APRSBOX_PRIVILEGED_RUNNER", "").strip()
    core_host: str = os.getenv("APRSBOX_CORE_HOST", "127.0.0.1")
    core_port: int = int(os.getenv("APRSBOX_CORE_PORT", "18081"))
    root_path: str = os.getenv("APRSBOX_ROOT_PATH", "").rstrip("/")
    proxy_trusted_ips: str = os.getenv("APRSBOX_PROXY_TRUSTED_IPS", "127.0.0.1")
    map_tile_url: str = os.getenv("APRSBOX_MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
    map_tile_attribution: str = os.getenv(
        "APRSBOX_MAP_TILE_ATTRIBUTION",
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    )
    map_tile_source_name: str = os.getenv("APRSBOX_MAP_TILE_SOURCE_NAME", "OpenStreetMap")
    traffic_stream_tick_seconds: float = float(os.getenv("APRSBOX_TRAFFIC_STREAM_TICK_SECONDS", "1.0"))
    traffic_stream_heartbeat_seconds: float = float(os.getenv("APRSBOX_TRAFFIC_STREAM_HEARTBEAT_SECONDS", "25.0"))
    traffic_stream_max_clients: int = int(os.getenv("APRSBOX_TRAFFIC_STREAM_MAX_CLIENTS", "20"))

    @property
    def runtime_root(self) -> Path:
        if self.app_env == "production":
            return self.install_root
        return self.repo_root

    @property
    def database_path(self) -> Path:
        return Path(os.getenv("APRSBOX_DB_PATH", self.runtime_root / "data" / "aprsbox.db"))

    @property
    def templates_dir(self) -> Path:
        return self.repo_root / "app" / "templates"

    @property
    def static_dir(self) -> Path:
        return self.repo_root / "app" / "static"

    @property
    def log_dir(self) -> Path:
        return Path(os.getenv("APRSBOX_LOG_DIR", self.runtime_root / "logs"))

    @property
    def data_dir(self) -> Path:
        return self.database_path.parent

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def config_dir(self) -> Path:
        return Path(os.getenv("APRSBOX_CONFIG_DIR", self.runtime_root / "config"))

    @property
    def backups_dir(self) -> Path:
        return Path(os.getenv("APRSBOX_BACKUPS_DIR", self.runtime_root / "backups"))

    @property
    def version_file(self) -> Path:
        return self.repo_root / "VERSION"

    @property
    def aprs_device_identification_bundle_path(self) -> Path:
        return self.repo_root / "app" / "bundled" / "aprs-deviceid-tocalls.pretty.json"

    @property
    def aprs_device_identification_cache_path(self) -> Path:
        return self.cache_dir / "aprs-deviceid-tocalls.pretty.json"

    @property
    def aprs_device_identification_update_url(self) -> str:
        return os.getenv(
            "APRSBOX_APRS_DEVICE_ID_URL",
            "https://aprs-deviceid.aprsfoundation.org/tocalls.pretty.json",
        )

    @property
    def core_base_url(self) -> str:
        override = os.getenv("APRSBOX_CORE_URL", "").strip()
        if override:
            return override.rstrip("/")
        return f"http://{self.core_host}:{self.core_port}"

    @property
    def is_container_mode(self) -> bool:
        return _env_flag("APRSBOX_CONTAINER", default=False)


settings = Settings()
