from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app import get_version
from app.config import settings


def current_gui_version() -> str:
    return get_version()


def latest_gui_version() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="aprsbox-version-check-") as temp_dir:
        checkout_dir = Path(temp_dir) / "repo"
        try:
            result = subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    settings.gui_update_branch,
                    settings.gui_update_url,
                    str(checkout_dir),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "error": f"Version check failed: {exc}"}

        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or "git clone failed"
            return {"ok": False, "error": error}

        version_file = checkout_dir / "VERSION"
        if not version_file.exists():
            return {"ok": False, "error": "Remote VERSION file not found"}

        remote_version = version_file.read_text(encoding="utf-8").strip()
        return {
            "ok": True,
            "current_version": current_gui_version(),
            "latest_version": remote_version,
            "up_to_date": remote_version == current_gui_version(),
            "source": f"{settings.gui_update_url}@{settings.gui_update_branch}",
        }


def start_gui_update() -> dict[str, Any]:
    script_path = settings.repo_root / "scripts" / "update-gui.sh"
    log_file = settings.log_dir / "gui-update.log"
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    if not script_path.exists():
        return {"ok": False, "error": f"Update script not found: {script_path}"}

    log_handle = log_file.open("a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            [str(script_path)],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=settings.repo_root,
            env={
                **dict(os.environ),
                "APRSBOX_INSTALL_ROOT": str(settings.install_root),
                "APRSBOX_LOG_DIR": str(settings.log_dir),
                "APRSBOX_GIT_URL": settings.gui_update_url,
                "APRSBOX_GIT_BRANCH": settings.gui_update_branch,
            },
        )
    except OSError as exc:
        log_handle.close()
        return {"ok": False, "error": f"Failed to start update script: {exc}"}

    log_handle.close()
    return {"ok": True, "pid": process.pid, "log_file": str(log_file)}
