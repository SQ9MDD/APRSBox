from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@dataclass(slots=True)
class Settings:
    app_name: str = "APRSBox"
    app_version: str = "0.1.0"
    app_env: str = os.getenv("APRSBOX_ENV", "development")
    secret_key: str = os.getenv("APRSBOX_SECRET_KEY", "change-me-in-production")
    install_root: Path = Path(os.getenv("APRSBOX_INSTALL_ROOT", "/opt/aprsbox"))
    repo_root: Path = _repo_root()

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
    def config_dir(self) -> Path:
        return Path(os.getenv("APRSBOX_CONFIG_DIR", self.runtime_root / "config"))

    @property
    def backups_dir(self) -> Path:
        return Path(os.getenv("APRSBOX_BACKUPS_DIR", self.runtime_root / "backups"))


settings = Settings()

