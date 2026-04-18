from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from app import get_version
from app.config import settings
from app.db import log_event
from app.services.map_service import get_map_source, increment_map_source_cache_stats, reset_map_source_cache_stats

MAP_TILE_PROXY_TIMEOUT_SECONDS = 8.0
MAP_TILE_MIN_ZOOM = 0
MAP_TILE_MAX_ZOOM = 30
_MAP_TILE_CACHE_ROOT_NAME = "map-tiles"
_MAP_TILE_SUBDOMAIN_RE = re.compile(r"^[a-z0-9-]{1,32}$", flags=re.IGNORECASE)
_MAP_TILE_EXTENSION_RE = re.compile(r"^[a-z0-9]{1,8}$", flags=re.IGNORECASE)


class MapTileProxyError(Exception):
    def __init__(self, *, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = int(status_code)
        self.message = str(message)


@dataclass(slots=True)
class MapTileProxyResult:
    cache_hit: bool
    cache_path: Path | None
    body: bytes | None
    media_type: str | None


def safe_clear_map_source_cache(source_id: int) -> tuple[bool, str | None]:
    try:
        clear_map_source_cache(source_id)
    except ValueError as exc:
        return False, str(exc)
    return True, None


def clear_map_source_cache(source_id: int) -> None:
    source = get_map_source(source_id)
    if source is None:
        raise ValueError("Map source not found.")

    source_cache_dir = _source_cache_dir(source_id)
    try:
        if source_cache_dir.exists():
            shutil.rmtree(source_cache_dir)
    except OSError as exc:
        raise ValueError(f"Failed to clear cache: {exc}") from exc

    reset_map_source_cache_stats(source_id)
    log_event("INFO", "map", f"Cleared map tile cache for source {int(source_id)}")


def resolve_map_tile(
    *,
    source_id: int,
    z: int,
    x: int,
    y: int,
    requested_subdomain: str = "",
) -> MapTileProxyResult:
    source = get_map_source(source_id)
    if source is None:
        raise MapTileProxyError(status_code=404, message="Map source not found.")
    if not bool(source.get("local_cache_enabled")):
        raise MapTileProxyError(status_code=404, message="Local cache/proxy is disabled for this map source.")

    _validate_tile_coordinates(z=z, x=x, y=y)
    upstream_url = _build_upstream_url(source, z=z, x=x, y=y, requested_subdomain=requested_subdomain)
    tile_extension = _tile_extension_from_url(upstream_url)
    cache_path = _tile_cache_path(source_id=source_id, z=z, x=x, y=y, tile_extension=tile_extension)

    if cache_path.exists():
        return MapTileProxyResult(cache_hit=True, cache_path=cache_path, body=None, media_type=None)

    body, media_type = _download_tile(upstream_url)

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with cache_path.open("xb") as cache_file:
            cache_file.write(body)
        increment_map_source_cache_stats(source_id, tile_size_bytes=len(body))
    except FileExistsError:
        if cache_path.exists():
            return MapTileProxyResult(cache_hit=True, cache_path=cache_path, body=None, media_type=None)
    except OSError as exc:
        log_event(
            "WARNING",
            "map",
            f"Failed to write tile cache for source {int(source_id)} z={z} x={x} y={y}: {exc}",
        )

    return MapTileProxyResult(cache_hit=False, cache_path=cache_path, body=body, media_type=media_type)


def _download_tile(upstream_url: str) -> tuple[bytes, str | None]:
    request = Request(
        upstream_url,
        headers={
            "User-Agent": f"APRSBox/{get_version()}",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=MAP_TILE_PROXY_TIMEOUT_SECONDS) as response:
            body = response.read()
            media_type = response.headers.get_content_type()
            return body, str(media_type or "") or None
    except HTTPError as exc:
        status_code = int(exc.code) if 400 <= int(exc.code) <= 599 else 502
        raise MapTileProxyError(status_code=status_code, message=f"Upstream tile error: HTTP {int(exc.code)}") from exc
    except (URLError, OSError) as exc:
        raise MapTileProxyError(status_code=502, message=f"Upstream tile fetch failed: {exc}") from exc


def _validate_tile_coordinates(*, z: int, x: int, y: int) -> None:
    zoom = int(z)
    x_value = int(x)
    y_value = int(y)
    if zoom < MAP_TILE_MIN_ZOOM or zoom > MAP_TILE_MAX_ZOOM:
        raise MapTileProxyError(status_code=400, message="Invalid tile zoom.")
    max_index = (1 << zoom) - 1
    if x_value < 0 or x_value > max_index or y_value < 0 or y_value > max_index:
        raise MapTileProxyError(status_code=400, message="Invalid tile coordinates.")


def _build_upstream_url(
    source: dict[str, Any],
    *,
    z: int,
    x: int,
    y: int,
    requested_subdomain: str,
) -> str:
    url_template = str(source.get("url_template") or "").strip()
    api_key = str(source.get("api_key") or "")
    prepared = url_template.replace("{apiKey}", quote(api_key, safe=""))
    prepared = _decode_brace_tokens(prepared)

    resolved_subdomain = _resolve_subdomain(source, requested_subdomain=requested_subdomain)
    prepared = _replace_tile_token(prepared, token="z", replacement=str(int(z)))
    prepared = _replace_tile_token(prepared, token="x", replacement=str(int(x)))
    prepared = _replace_tile_token(prepared, token="y", replacement=str(int(y)))
    prepared = _replace_tile_token(prepared, token="s", replacement=resolved_subdomain)
    return prepared


def _decode_brace_tokens(value: str) -> str:
    return (
        str(value or "")
        .replace("%7B", "{")
        .replace("%7b", "{")
        .replace("%7D", "}")
        .replace("%7d", "}")
        .replace("&#123;", "{")
        .replace("&#125;", "}")
    )


def _replace_tile_token(template: str, *, token: str, replacement: str) -> str:
    return re.sub(r"\{\s*" + re.escape(token) + r"\s*\}", replacement, str(template or ""), flags=re.IGNORECASE)


def _resolve_subdomain(source: dict[str, Any], *, requested_subdomain: str) -> str:
    configured = [token for token in re.split(r"[,\s]+", str(source.get("subdomains") or "").strip()) if token]
    configured_normalized = {token.lower() for token in configured}
    fallback = configured[0] if configured else "a"
    candidate = str(requested_subdomain or "").strip()
    if not candidate:
        return fallback
    if not _MAP_TILE_SUBDOMAIN_RE.fullmatch(candidate):
        return fallback
    if configured and candidate.lower() not in configured_normalized:
        return fallback
    return candidate


def _tile_extension_from_url(url: str) -> str:
    parsed_path = str(urlparse(url).path or "")
    suffix = Path(parsed_path).suffix.lstrip(".").lower()
    if not suffix:
        return "bin"
    if _MAP_TILE_EXTENSION_RE.fullmatch(suffix):
        return suffix
    return "bin"


def _tile_cache_path(*, source_id: int, z: int, x: int, y: int, tile_extension: str) -> Path:
    safe_extension = tile_extension if _MAP_TILE_EXTENSION_RE.fullmatch(tile_extension) else "bin"
    return _source_cache_dir(source_id) / str(int(z)) / str(int(x)) / f"{int(y)}.{safe_extension}"


def _source_cache_dir(source_id: int) -> Path:
    return settings.cache_dir / _MAP_TILE_CACHE_ROOT_NAME / str(int(source_id))
