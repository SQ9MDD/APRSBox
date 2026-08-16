from __future__ import annotations

import ipaddress
import json
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote


_IPV4_ROUTE_PROBE = "1.1.1.1"


def _run(command: Sequence[str], *, timeout: float = 1.5) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _usable_address(value: object, *, version: int) -> str | None:
    candidate = str(value or "").strip().split("%", 1)[0]
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    if address.version != version or address.is_loopback or address.is_unspecified:
        return None
    return str(address)


def _read_ip_json(arguments: Sequence[str]) -> list[dict[str, Any]]:
    if shutil.which("ip") is None:
        return []
    result = _run(["ip", "-j", *arguments])
    if result is None or result.returncode != 0:
        return []
    try:
        payload = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError):
        return []
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _linux_default_interface() -> str | None:
    try:
        rows = Path("/proc/net/route").read_text(encoding="utf-8").splitlines()[1:]
    except OSError:
        return None
    candidates: list[tuple[int, str]] = []
    for row in rows:
        fields = row.split()
        if len(fields) < 8 or fields[1] != "00000000":
            continue
        try:
            flags = int(fields[3], 16)
            metric = int(fields[6])
        except ValueError:
            continue
        if flags & 0x1:
            candidates.append((metric, fields[0]))
    return min(candidates)[1] if candidates else None


def _bsd_default_interface() -> str | None:
    route_command = shutil.which("route")
    if route_command is None:
        return None
    result = _run([route_command, "-n", "get", "default"])
    if result is None or result.returncode != 0:
        return None
    for row in result.stdout.splitlines():
        key, separator, value = row.partition(":")
        if separator and key.strip().lower() == "interface":
            return value.strip() or None
    return None


def _socket_route_ipv4() -> str | None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.settimeout(0.5)
        probe.connect((_IPV4_ROUTE_PROBE, 53))
        return _usable_address(probe.getsockname()[0], version=4)
    except OSError:
        return None
    finally:
        probe.close()


def _active_ipv4_route() -> tuple[str | None, str | None]:
    routes = _read_ip_json(["-4", "route", "get", _IPV4_ROUTE_PROBE])
    for route in routes:
        interface = str(route.get("dev") or "").strip() or None
        address = _usable_address(route.get("prefsrc") or route.get("src"), version=4)
        if interface and address:
            return interface, address

    interface = _linux_default_interface() or _bsd_default_interface()
    return interface, _socket_route_ipv4()


def _interface_ipv6(interface: str | None) -> str | None:
    if not interface:
        return None
    candidates: list[tuple[int, str]] = []
    for row in _read_ip_json(["-6", "address", "show", "dev", interface]):
        for info in row.get("addr_info") or []:
            if not isinstance(info, dict):
                continue
            address = _usable_address(info.get("local"), version=6)
            if address:
                candidates.append((1 if ipaddress.ip_address(address).is_link_local else 0, address))
    if candidates:
        return min(candidates)[1]

    try:
        rows = Path("/proc/net/if_inet6").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for row in rows:
        fields = row.split()
        if len(fields) != 6 or fields[5] != interface:
            continue
        try:
            address = str(ipaddress.IPv6Address(int(fields[0], 16)))
        except ValueError:
            continue
        usable = _usable_address(address, version=6)
        if usable:
            candidates.append((1 if ipaddress.ip_address(usable).is_link_local else 0, usable))
    return min(candidates)[1] if candidates else None


def _mdns_name(hostname: str | None) -> str | None:
    label = str(hostname or "").strip().rstrip(".").split(".", 1)[0]
    if not label:
        return None
    return f"{label}.local"


def _avahi_status() -> tuple[str, str]:
    if shutil.which("systemctl"):
        result = _run(["systemctl", "is-active", "avahi-daemon.service"])
        state = str((result.stdout if result else "") or "").strip().lower()
        if state == "active":
            return "Active", "ok"
        if state in {"inactive", "failed", "activating", "deactivating"}:
            return "Inactive", "warn"

    if shutil.which("rc-service"):
        result = _run(["rc-service", "avahi-daemon", "status"])
        output = " ".join(((result.stdout if result else "") or "", (result.stderr if result else "") or "")).lower()
        if result and result.returncode == 0 and any(word in output for word in ("started", "running")):
            return "Active", "ok"
        if any(word in output for word in ("stopped", "crashed", "inactive")):
            return "Inactive", "warn"

    if shutil.which("avahi-daemon"):
        result = _run(["avahi-daemon", "--check"])
        return ("Active", "ok") if result and result.returncode == 0 else ("Inactive", "warn")
    return "Unavailable", "neutral"


def _resolve_mdns(name: str | None) -> str | None:
    if not name:
        return None
    commands: list[list[str]] = []
    if shutil.which("avahi-resolve-host-name"):
        commands.append(["avahi-resolve-host-name", "-4", name])
    if shutil.which("getent"):
        commands.append(["getent", "ahostsv4", name])
    for command in commands:
        result = _run(command)
        if result is None or result.returncode != 0:
            continue
        for token in result.stdout.replace("\t", " ").split():
            address = _usable_address(token, version=4)
            if address:
                return address
    return None


def build_web_ui_url(*, mdns_name: str | None, scheme: str, port: int | None, root_path: str = "") -> str | None:
    if not mdns_name:
        return None
    normalized_scheme = str(scheme or "").strip().lower()
    if normalized_scheme not in {"http", "https"}:
        return None
    port_suffix = "" if port is None or (normalized_scheme, port) in {("http", 80), ("https", 443)} else f":{port}"
    normalized_root = "/" + quote(str(root_path or "").strip().strip("/"), safe="/") if str(root_path or "").strip("/") else ""
    return f"{normalized_scheme}://{mdns_name}{port_suffix}{normalized_root}"


def get_network_diagnostics(*, scheme: str, port: int | None, root_path: str = "") -> dict[str, Any]:
    try:
        hostname = socket.gethostname().strip() or None
    except OSError:
        hostname = None
    interface, ipv4 = _active_ipv4_route()
    ipv6 = _interface_ipv6(interface)
    mdns_name = _mdns_name(hostname)
    avahi_status, avahi_tone = _avahi_status()
    resolved_address = _resolve_mdns(mdns_name)
    return {
        "hostname": hostname,
        "interface": interface,
        "ipv4": ipv4,
        "ipv6": ipv6,
        "mdns_name": mdns_name,
        "avahi_status": avahi_status,
        "avahi_tone": avahi_tone,
        "mdns_resolve": resolved_address,
        "mdns_resolve_tone": "ok" if resolved_address else "neutral",
        "web_ui_url": build_web_ui_url(
            mdns_name=mdns_name,
            scheme=scheme,
            port=port,
            root_path=root_path,
        ),
    }
