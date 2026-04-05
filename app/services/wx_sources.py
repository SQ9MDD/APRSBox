from __future__ import annotations

import base64
import json
import ssl
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from app.services.wx_definitions import WX_SELECTOR_KINDS


class WxSourceError(RuntimeError):
    pass


@dataclass(slots=True)
class WxSourceReadResult:
    raw_value: Any
    raw_unit: str | None
    details: dict[str, Any]


def parse_value_selector(value: str | None) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "state", ""
    if ":" not in text:
        normalized_kind = text.strip().lower()
        if normalized_kind not in WX_SELECTOR_KINDS:
            raise WxSourceError(f"Unsupported selector kind: {normalized_kind}")
        return normalized_kind, ""
    kind, selector_name = text.split(":", 1)
    normalized_kind = kind.strip().lower()
    if normalized_kind not in WX_SELECTOR_KINDS:
        raise WxSourceError(f"Unsupported selector kind: {normalized_kind}")
    return normalized_kind, selector_name.strip()


class WxSourceAdapter:
    def __init__(self, source: dict[str, Any]) -> None:
        self.source = source

    def test_connection(self) -> dict[str, Any]:
        raise NotImplementedError

    def discover_items(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def read_value(self, mapping: dict[str, Any]) -> WxSourceReadResult:
        raise NotImplementedError

    def _request_json(
        self,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        request_headers = {
            "Accept": "application/json",
            **self._auth_headers(),
            **(headers or {}),
        }
        request = Request(self._build_url(path, query=query), headers=request_headers)
        try:
            with urlopen(request, timeout=float(self.source.get("timeout_s") or 5), context=self._ssl_context()) as response:
                raw_payload = response.read().decode("utf-8")
        except HTTPError as exc:
            raise WxSourceError(f"HTTP {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise WxSourceError(f"Network error: {exc.reason}") from exc
        except OSError as exc:
            raise WxSourceError(f"Connection failed: {exc}") from exc
        try:
            return json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise WxSourceError("Source returned invalid JSON.") from exc

    def _build_url(self, path: str, *, query: dict[str, Any] | None = None) -> str:
        base_url = str(self.source.get("base_url") or "").strip().rstrip("/")
        normalized_path = path if path.startswith("/") else f"/{path}"
        if not query:
            return f"{base_url}{normalized_path}"
        encoded_query = urlencode({key: value for key, value in query.items() if value not in {None, ""}})
        return f"{base_url}{normalized_path}?{encoded_query}"

    def _auth_headers(self) -> dict[str, str]:
        auth_type = str(self.source.get("auth_type") or "none").strip().lower()
        auth_payload = self.source.get("auth_payload") or {}
        if auth_type == "bearer":
            token = str(auth_payload.get("token") or "").strip()
            if not token:
                raise WxSourceError("Bearer token is required.")
            return {"Authorization": f"Bearer {token}"}
        if auth_type == "basic":
            username = str(auth_payload.get("username") or "")
            password = str(auth_payload.get("password") or "")
            token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            return {"Authorization": f"Basic {token}"}
        return {}

    def _ssl_context(self) -> ssl.SSLContext | None:
        if str(self.source.get("base_url") or "").strip().lower().startswith("https://"):
            verify_tls = bool(self.source.get("verify_tls", 1))
            if verify_tls:
                return ssl.create_default_context()
            return ssl._create_unverified_context()
        return None


class HomeAssistantSourceAdapter(WxSourceAdapter):
    def test_connection(self) -> dict[str, Any]:
        payload = self._request_json("/api/")
        return {
            "ok": str(payload.get("message") or "").strip().lower() == "api running.",
            "details": payload,
        }

    def discover_items(self) -> list[dict[str, Any]]:
        payload = self._request_json("/api/states")
        if not isinstance(payload, list):
            raise WxSourceError("Home Assistant discovery returned an unexpected payload.")
        items: list[dict[str, Any]] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            attributes = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
            entity_id = str(row.get("entity_id") or "").strip()
            if not entity_id:
                continue
            items.append(
                {
                    "identifier": entity_id,
                    "label": str(attributes.get("friendly_name") or entity_id),
                    "selector_hint": "state",
                    "value_preview": str(row.get("state") or ""),
                    "unit": str(attributes.get("unit_of_measurement") or "").strip(),
                    "extra": {
                        "domain": entity_id.split(".", 1)[0],
                        "attributes": sorted(str(key) for key in attributes.keys()),
                    },
                }
            )
        items.sort(key=lambda item: (item["identifier"].casefold(), item["label"].casefold()))
        return items

    def read_value(self, mapping: dict[str, Any]) -> WxSourceReadResult:
        identifier = str(mapping.get("identifier") or "").strip()
        if not identifier:
            raise WxSourceError("Home Assistant entity_id is required.")
        payload = self._request_json(f"/api/states/{quote(identifier, safe='.')}")
        if not isinstance(payload, dict):
            raise WxSourceError("Home Assistant entity lookup returned an unexpected payload.")
        selector_kind, selector_name = parse_value_selector(mapping.get("value_selector"))
        attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
        if selector_kind == "state":
            raw_value = payload.get("state")
        elif selector_kind == "attribute":
            if not selector_name:
                raise WxSourceError("Selector attribute name is required.")
            if selector_name not in attributes:
                raise WxSourceError(f"Attribute not found: {selector_name}")
            raw_value = attributes.get(selector_name)
        elif selector_kind == "field":
            if not selector_name:
                raise WxSourceError("Selector field name is required.")
            if selector_name not in payload:
                raise WxSourceError(f"Field not found: {selector_name}")
            raw_value = payload.get(selector_name)
        else:
            if not selector_name:
                raise WxSourceError("Selector key path is required.")
            raw_value = _resolve_key_path(payload, selector_name)
        raw_unit = str(attributes.get("unit_of_measurement") or "").strip() or None
        return WxSourceReadResult(
            raw_value=raw_value,
            raw_unit=raw_unit,
            details={
                "entity_id": identifier,
                "last_changed": payload.get("last_changed"),
                "last_updated": payload.get("last_updated"),
            },
        )


class DomoticzSourceAdapter(WxSourceAdapter):
    def test_connection(self) -> dict[str, Any]:
        payload = self._request_json(
            "/json.htm",
            query={"type": "command", "param": "getdevices", "filter": "all", "used": "true", "order": "Name"},
        )
        if not isinstance(payload, dict):
            raise WxSourceError("Domoticz connection test returned an unexpected payload.")
        return {
            "ok": str(payload.get("status") or "").strip().upper() == "OK",
            "details": payload,
        }

    def discover_items(self) -> list[dict[str, Any]]:
        payload = self._request_json(
            "/json.htm",
            query={"type": "command", "param": "getdevices", "filter": "all", "used": "true", "order": "Name"},
        )
        if not isinstance(payload, dict):
            raise WxSourceError("Domoticz discovery returned an unexpected payload.")
        rows = payload.get("result")
        if not isinstance(rows, list):
            raise WxSourceError("Domoticz discovery returned no device list.")
        items: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            identifier = str(row.get("idx") or "").strip()
            if not identifier:
                continue
            items.append(
                {
                    "identifier": identifier,
                    "label": str(row.get("Name") or f"IDX {identifier}"),
                    "selector_hint": "field:Data",
                    "value_preview": str(row.get("Data") or row.get("Status") or ""),
                    "unit": "",
                    "extra": {
                        "type": str(row.get("Type") or ""),
                        "subtype": str(row.get("SubType") or ""),
                        "fields": sorted(str(key) for key in row.keys()),
                    },
                }
            )
        items.sort(key=lambda item: (item["label"].casefold(), item["identifier"].casefold()))
        return items

    def read_value(self, mapping: dict[str, Any]) -> WxSourceReadResult:
        identifier = str(mapping.get("identifier") or "").strip()
        if not identifier:
            raise WxSourceError("Domoticz idx is required.")
        payload = self._request_json(
            "/json.htm",
            query={"type": "command", "param": "getdevices", "rid": identifier},
        )
        if not isinstance(payload, dict):
            raise WxSourceError("Domoticz device lookup returned an unexpected payload.")
        rows = payload.get("result")
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            raise WxSourceError(f"Domoticz device not found for idx {identifier}.")
        row = rows[0]
        selector_kind, selector_name = parse_value_selector(mapping.get("value_selector") or "field:Data")
        if selector_kind == "state":
            if "Data" in row:
                raw_value = row.get("Data")
            elif "Status" in row:
                raw_value = row.get("Status")
            else:
                raise WxSourceError("Domoticz device does not expose Data or Status.")
        elif selector_kind == "field":
            if not selector_name:
                raise WxSourceError("Selector field name is required.")
            if selector_name not in row:
                raise WxSourceError(f"Field not found: {selector_name}")
            raw_value = row.get(selector_name)
        elif selector_kind == "key":
            if not selector_name:
                raise WxSourceError("Selector key path is required.")
            raw_value = _resolve_key_path(row, selector_name)
        else:
            raise WxSourceError("Domoticz supports selector kinds: state, field, key.")
        raw_unit = _extract_domoticz_unit(row, selector_kind, selector_name)
        return WxSourceReadResult(
            raw_value=raw_value,
            raw_unit=raw_unit,
            details={
                "idx": identifier,
                "name": row.get("Name"),
                "type": row.get("Type"),
                "subtype": row.get("SubType"),
                "last_update": row.get("LastUpdate"),
            },
        )


def build_wx_source_adapter(source: dict[str, Any]) -> WxSourceAdapter:
    source_type = str(source.get("source_type") or "").strip().lower()
    if source_type == "home_assistant":
        return HomeAssistantSourceAdapter(source)
    if source_type == "domoticz":
        return DomoticzSourceAdapter(source)
    raise WxSourceError(f"Unsupported WX source type: {source_type}")


def _resolve_key_path(payload: Any, path: str) -> Any:
    current = payload
    for part in [segment.strip() for segment in path.split(".") if segment.strip()]:
        if isinstance(current, dict):
            if part not in current:
                raise WxSourceError(f"Key path not found: {path}")
            current = current[part]
            continue
        if isinstance(current, list):
            try:
                index = int(part)
            except ValueError as exc:
                raise WxSourceError(f"List index expected in key path: {path}") from exc
            if index < 0 or index >= len(current):
                raise WxSourceError(f"List index out of range in key path: {path}")
            current = current[index]
            continue
        raise WxSourceError(f"Key path not found: {path}")
    return current


def _extract_domoticz_unit(row: dict[str, Any], selector_kind: str, selector_name: str) -> str | None:
    if selector_kind != "field":
        return None
    field_name = selector_name.strip()
    if not field_name:
        return None
    if field_name in {"Temp", "Chill", "DewPoint"}:
        return str(row.get("TempUnit") or "").strip() or None
    if field_name in {"Humidity"}:
        return "%"
    if field_name in {"Barometer"}:
        return "hPa"
    if field_name in {"Rain", "RainRate"}:
        return str(row.get("RainUnit") or "").strip() or None
    if field_name in {"Speed", "Speedms", "Gust"}:
        return str(row.get("SpeedUnit") or "").strip() or None
    return None
