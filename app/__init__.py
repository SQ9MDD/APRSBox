from __future__ import annotations

from pathlib import Path

__all__ = ["__version__", "get_version"]


def _read_version() -> str:
    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


def get_version() -> str:
    return _read_version()


__version__ = _read_version()
