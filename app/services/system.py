from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from app import get_version
from app.config import settings
from app.db import get_app_setting, set_app_setting

UPDATE_CHANNEL_SETTING_KEY = "gui_update_branch"
UPDATE_LOG_FILE_NAME = "application-update.log"
_UPDATE_CHANNEL_RE = re.compile(r"^[A-Za-z0-9._/-]{1,128}$")
_GUI_VERSION_RE = re.compile(r"^v?(?P<numbers>\d+(?:\.\d+)*)(?P<suffix>.*)$", re.IGNORECASE)
CONTAINER_SYSTEM_ACTIONS_DISABLED_MESSAGE = (
    "Docker installation detected. In-app system actions are disabled. "
    "Update APRSBox by pulling a newer Docker image and recreating the container with the same volumes. "
    "Restart or stop APRSBox using Docker commands."
)


def current_gui_version() -> str:
    return get_version()


def is_container_mode() -> bool:
    return bool(settings.is_container_mode)


def container_system_actions_disabled_message() -> str:
    return CONTAINER_SYSTEM_ACTIONS_DISABLED_MESSAGE


def _container_mode_action_blocked_result() -> dict[str, Any]:
    return {"ok": False, "error": CONTAINER_SYSTEM_ACTIONS_DISABLED_MESSAGE, "status_code": 409}


def _default_update_channel() -> str:
    return settings.gui_update_branch.strip() or "main"


def normalize_update_channel(value: str | None) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return _default_update_channel()
    if not _UPDATE_CHANNEL_RE.fullmatch(candidate):
        raise ValueError("Invalid update channel name.")
    return candidate


def current_update_channel() -> str:
    stored = get_app_setting(UPDATE_CHANNEL_SETTING_KEY)
    try:
        return normalize_update_channel(stored)
    except ValueError:
        return _default_update_channel()


def save_update_channel(channel: str) -> str:
    normalized = normalize_update_channel(channel)
    set_app_setting(UPDATE_CHANNEL_SETTING_KEY, normalized)
    return normalized


def list_update_channels() -> dict[str, Any]:
    selected_channel = current_update_channel()
    stable_channel = _default_update_channel()
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", "--refs", settings.gui_update_url],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "ok": False,
            "channels": [selected_channel],
            "selected_channel": selected_channel,
            "stable_channel": stable_channel,
            "source": settings.gui_update_url,
            "error": f"Failed to fetch update channels: {exc}",
        }

    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or "git ls-remote failed"
        return {
            "ok": False,
            "channels": [selected_channel],
            "selected_channel": selected_channel,
            "stable_channel": stable_channel,
            "source": settings.gui_update_url,
            "error": error,
        }

    names: list[str] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split("\t", 1)
        if len(parts) != 2:
            continue
        ref_name = parts[1].strip()
        prefix = "refs/heads/"
        if not ref_name.startswith(prefix):
            continue
        name = ref_name[len(prefix):]
        try:
            normalized = normalize_update_channel(name)
        except ValueError:
            continue
        names.append(normalized)

    unique = sorted(set(names), key=str.casefold)
    if selected_channel not in unique:
        unique.append(selected_channel)
    if stable_channel not in unique:
        unique.append(stable_channel)

    unique = sorted(set(unique), key=str.casefold)
    ordered: list[str] = []
    for preferred in (stable_channel, selected_channel):
        if preferred in unique and preferred not in ordered:
            ordered.append(preferred)
    for name in unique:
        if name not in ordered:
            ordered.append(name)

    return {
        "ok": True,
        "channels": ordered,
        "selected_channel": selected_channel,
        "stable_channel": stable_channel,
        "source": settings.gui_update_url,
        "error": None,
    }


def _github_raw_version_url(repository_url: str, update_channel: str) -> str | None:
    parsed = urlsplit(str(repository_url or "").strip())
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"github.com", "www.github.com"}:
        return None
    repository_path = parsed.path.strip("/")
    if repository_path.endswith(".git"):
        repository_path = repository_path[:-4]
    path_parts = repository_path.split("/")
    if len(path_parts) != 2 or not all(path_parts):
        return None
    owner, repository = (quote(part, safe="") for part in path_parts)
    channel = quote(str(update_channel or "").strip(), safe="/")
    if not channel:
        return None
    return f"https://raw.githubusercontent.com/{owner}/{repository}/{channel}/VERSION"


def _read_github_version(repository_url: str, update_channel: str) -> tuple[str, str] | None:
    version_url = _github_raw_version_url(repository_url, update_channel)
    if version_url is None:
        return None
    request = Request(
        version_url,
        headers={
            "Accept": "text/plain",
            "User-Agent": "APRSBox-version-check",
        },
    )
    with urlopen(request, timeout=15) as response:
        remote_version = response.read(256).decode("utf-8", errors="replace").strip()
    if not remote_version or "\n" in remote_version or "\r" in remote_version:
        raise ValueError("Remote VERSION file is empty or invalid")
    return remote_version, version_url


def _compare_gui_versions(current_version: str, remote_version: str) -> int | None:
    current_match = _GUI_VERSION_RE.fullmatch(str(current_version or "").strip())
    remote_match = _GUI_VERSION_RE.fullmatch(str(remote_version or "").strip())
    if current_match is None or remote_match is None:
        return None

    current_numbers = tuple(int(part) for part in current_match.group("numbers").split("."))
    remote_numbers = tuple(int(part) for part in remote_match.group("numbers").split("."))
    width = max(len(current_numbers), len(remote_numbers))
    current_numbers += (0,) * (width - len(current_numbers))
    remote_numbers += (0,) * (width - len(remote_numbers))
    if current_numbers != remote_numbers:
        return 1 if current_numbers > remote_numbers else -1

    current_suffix = current_match.group("suffix").strip().lower()
    remote_suffix = remote_match.group("suffix").strip().lower()
    if current_suffix == remote_suffix:
        return 0
    if not current_suffix:
        return 1
    if not remote_suffix:
        return -1
    return 1 if current_suffix > remote_suffix else -1


def _gui_version_result(*, remote_version: str, source: str, update_channel: str) -> dict[str, Any]:
    current_version = current_gui_version()
    comparison = _compare_gui_versions(current_version, remote_version)
    up_to_date = current_version == remote_version if comparison is None else comparison >= 0
    return {
        "ok": True,
        "current_version": current_version,
        "latest_version": remote_version,
        "up_to_date": up_to_date,
        "source": source,
        "channel": update_channel,
    }


def latest_gui_version() -> dict[str, Any]:
    update_channel = current_update_channel()
    remote_version = ""
    source = f"{settings.gui_update_url}@{update_channel}"
    github_error = ""
    try:
        github_result = _read_github_version(settings.gui_update_url, update_channel)
    except (HTTPError, URLError, OSError, UnicodeError, ValueError) as exc:
        github_result = None
        github_error = str(exc).strip()
    if github_result is not None:
        remote_version, source = github_result

    if remote_version:
        return _gui_version_result(remote_version=remote_version, source=source, update_channel=update_channel)

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
                    update_channel,
                    settings.gui_update_url,
                    str(checkout_dir),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            detail = github_error or str(exc)
            return {"ok": False, "error": f"Version check failed: {detail}"}

        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or "git clone failed"
            return {"ok": False, "error": error}

        version_file = checkout_dir / "VERSION"
        if not version_file.exists():
            return {"ok": False, "error": "Remote VERSION file not found"}

        remote_version = version_file.read_text(encoding="utf-8").strip()
        return _gui_version_result(
            remote_version=remote_version,
            source=f"{settings.gui_update_url}@{update_channel}",
            update_channel=update_channel,
        )


def read_update_log(*, max_bytes: int = 65536) -> dict[str, Any]:
    log_file = settings.log_dir / UPDATE_LOG_FILE_NAME
    if not log_file.exists():
        return {"ok": True, "exists": False, "path": str(log_file), "content": "", "truncated": False}

    size = log_file.stat().st_size
    read_from = max(0, size - max(1024, int(max_bytes)))
    with log_file.open("rb") as handle:
        handle.seek(read_from)
        payload = handle.read()

    content = payload.decode("utf-8", errors="replace")
    truncated = read_from > 0
    if truncated and "\n" in content:
        content = content.split("\n", 1)[1]

    return {
        "ok": True,
        "exists": True,
        "path": str(log_file),
        "content": content.rstrip("\n"),
        "truncated": truncated,
    }


def _auto_privileged_runner() -> list[str]:
    for candidate in (["sudo", "-n"], ["doas", "-n"]):
        if shutil.which(candidate[0]):
            return candidate
    return []


def _script_command(script_path: Path) -> list[str]:
    command = [str(script_path)]
    runner_raw = settings.privileged_runner.strip()
    if runner_raw:
        runner_tokens = shlex.split(runner_raw)
        if runner_tokens and shutil.which(runner_tokens[0]):
            return [*runner_tokens, *command]
        # Configured runner is unavailable on this host. Try a compatible fallback.
        fallback_runner = _auto_privileged_runner()
        if fallback_runner:
            return [*fallback_runner, *command]
        return command
    auto_runner = _auto_privileged_runner()
    if auto_runner:
        return [*auto_runner, *command]
    return command


def _start_background_script(
    *,
    script_name: str,
    log_filename: str,
    extra_env: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
    job_id: int | None = None,
) -> dict[str, Any]:
    script_path = settings.repo_root / "scripts" / script_name
    log_file = settings.log_dir / log_filename
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    if not script_path.is_file():
        return {"ok": False, "error": f"Script not found: {script_path}"}

    log_handle = log_file.open("a", encoding="utf-8")
    command = _script_command(script_path)
    if extra_args:
        command = [*command, *[str(arg) for arg in extra_args]]
    if job_id is not None:
        command = [
            *command,
            "--job-id",
            str(int(job_id)),
            "--db-path",
            str(settings.database_path),
        ]
    try:
        process = subprocess.Popen(
            command,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=settings.repo_root,
            env={
                **dict(os.environ),
                "APRSBOX_INSTALL_ROOT": str(settings.install_root),
                "APRSBOX_LOG_DIR": str(settings.log_dir),
                "APRSBOX_DB_PATH": str(settings.database_path),
                **({"APRSBOX_JOB_ID": str(int(job_id))} if job_id is not None else {}),
                **(extra_env or {}),
            },
        )
    except OSError as exc:
        log_handle.close()
        return {"ok": False, "error": f"Failed to start script: {exc}"}

    log_handle.close()
    return {"ok": True, "pid": process.pid, "log_file": str(log_file), "command": " ".join(command)}


def start_application_update() -> dict[str, Any]:
    if is_container_mode():
        return _container_mode_action_blocked_result()
    update_channel = current_update_channel()
    return _start_background_script(
        script_name="update.sh",
        log_filename=UPDATE_LOG_FILE_NAME,
        extra_env={
            "APRSBOX_GIT_URL": settings.gui_update_url,
            "APRSBOX_GIT_BRANCH": update_channel,
        },
        extra_args=["--git-branch", update_channel],
    )


def start_application_update_job(*, job_id: int) -> dict[str, Any]:
    if is_container_mode():
        return _container_mode_action_blocked_result()
    update_channel = current_update_channel()
    return _start_background_script(
        script_name="update.sh",
        log_filename=UPDATE_LOG_FILE_NAME,
        job_id=job_id,
        extra_env={
            "APRSBOX_GIT_URL": settings.gui_update_url,
            "APRSBOX_GIT_BRANCH": update_channel,
        },
        extra_args=["--git-branch", update_channel],
    )


def start_service_restart() -> dict[str, Any]:
    if is_container_mode():
        return _container_mode_action_blocked_result()
    return _start_background_script(
        script_name="restart-services.sh",
        log_filename="service-restart.log",
    )


def start_service_restart_job(*, job_id: int, https_enabled: bool | None = None) -> dict[str, Any]:
    if is_container_mode():
        return _container_mode_action_blocked_result()
    return _start_background_script(
        script_name="restart-services.sh",
        log_filename="service-restart.log",
        job_id=job_id,
        extra_args=(
            ["--https-enabled", "1" if https_enabled else "0"]
            if https_enabled is not None
            else None
        ),
    )


def start_host_reboot() -> dict[str, Any]:
    if is_container_mode():
        return _container_mode_action_blocked_result()
    return _start_background_script(
        script_name="reboot-host.sh",
        log_filename="host-reboot.log",
    )


def start_host_reboot_job(*, job_id: int) -> dict[str, Any]:
    if is_container_mode():
        return _container_mode_action_blocked_result()
    return _start_background_script(
        script_name="reboot-host.sh",
        log_filename="host-reboot.log",
        job_id=job_id,
    )


def start_host_poweroff() -> dict[str, Any]:
    if is_container_mode():
        return _container_mode_action_blocked_result()
    return _start_background_script(
        script_name="poweroff-host.sh",
        log_filename="host-poweroff.log",
    )


def start_host_poweroff_job(*, job_id: int) -> dict[str, Any]:
    if is_container_mode():
        return _container_mode_action_blocked_result()
    return _start_background_script(
        script_name="poweroff-host.sh",
        log_filename="host-poweroff.log",
        job_id=job_id,
    )


def start_gui_update() -> dict[str, Any]:
    # Backward-compatible alias for older call sites.
    return start_application_update()
