from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote, urlsplit

OPENWEBRX_MQTT_MODEM_TYPE = "OPENWEBRX_MQTT"
TX_CAPABLE_MODEM_TYPES = ("TCP", "SERIALL", "SERIAL")
RX_CAPABLE_MODEM_TYPES = TX_CAPABLE_MODEM_TYPES + (OPENWEBRX_MQTT_MODEM_TYPE,)
MQTT_DEFAULT_PORTS = {
    "mqtt": 1883,
    "mqtts": 8883,
}


@dataclass(frozen=True)
class MqttEndpoint:
    scheme: str
    host: str
    port: int
    topic: str
    username: str | None
    password: str | None

    @property
    def use_tls(self) -> bool:
        return self.scheme == "mqtts"

    @property
    def broker_display(self) -> str:
        return f"{_format_host(self.host)}:{self.port}"

    @property
    def normalized_url(self) -> str:
        return build_mqtt_url(
            scheme=self.scheme,
            host=self.host,
            port=self.port,
            topic=self.topic,
            username=self.username,
            password=self.password,
        )

    @property
    def masked_url(self) -> str:
        masked_password = "***" if self.password is not None else None
        return build_mqtt_url(
            scheme=self.scheme,
            host=self.host,
            port=self.port,
            topic=self.topic,
            username=self.username,
            password=masked_password,
        )


def parse_mqtt_url(value: Any, *, label: str = "MQTT URL", require_topic: bool = True) -> MqttEndpoint:
    raw_value = str(value or "").strip()
    if not raw_value:
        raise ValueError(f"{label} is required.")

    parsed = urlsplit(raw_value)
    scheme = str(parsed.scheme or "").strip().lower()
    if scheme not in MQTT_DEFAULT_PORTS:
        raise ValueError(f"{label} must use mqtt:// or mqtts:// scheme.")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{label} cannot contain query parameters or fragments.")
    if not parsed.hostname:
        raise ValueError(f"{label} must include a broker host.")

    try:
        port = int(parsed.port) if parsed.port is not None else int(MQTT_DEFAULT_PORTS[scheme])
    except ValueError as exc:
        raise ValueError(f"{label} contains an invalid broker port.") from exc
    if port < 1 or port > 65535:
        raise ValueError(f"{label} broker port must be between 1 and 65535.")

    topic = str(parsed.path or "").lstrip("/")
    if require_topic and not topic:
        raise ValueError(f"{label} must include MQTT topic in URL path.")

    username = unquote(parsed.username) if parsed.username is not None else None
    password = unquote(parsed.password) if parsed.password is not None else None
    return MqttEndpoint(
        scheme=scheme,
        host=str(parsed.hostname),
        port=port,
        topic=topic,
        username=username,
        password=password,
    )


def mask_mqtt_url(value: Any) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""
    try:
        endpoint = parse_mqtt_url(raw_value, require_topic=False)
    except ValueError:
        return raw_value
    return endpoint.masked_url


def build_mqtt_url(
    *,
    scheme: str,
    host: str,
    port: int,
    topic: str,
    username: str | None,
    password: str | None,
) -> str:
    authority = _format_host(host)
    if username is not None:
        user = quote(str(username), safe="")
        if password is not None:
            rendered_password = "***" if str(password) == "***" else quote(str(password), safe="")
            authority = f"{user}:{rendered_password}@{authority}"
        else:
            authority = f"{user}@{authority}"
    path = f"/{topic}" if topic else ""
    return f"{scheme}://{authority}:{int(port)}{path}"


def sanitize_url_passwords(message: Any) -> str:
    text = str(message or "")
    if "://" not in text or "@" not in text:
        return text
    words = text.split()
    sanitized: list[str] = []
    for token in words:
        prefix = ""
        suffix = ""
        normalized = token
        while normalized and normalized[0] in "\"'([{<":
            prefix += normalized[0]
            normalized = normalized[1:]
        while normalized and normalized[-1] in "\"')]}>,;":
            suffix = normalized[-1] + suffix
            normalized = normalized[:-1]
        if normalized:
            sanitized.append(prefix + mask_mqtt_url(normalized) + suffix)
        else:
            sanitized.append(token)
    return " ".join(sanitized)


def _format_host(host: str) -> str:
    host_text = str(host or "").strip()
    if ":" in host_text and not host_text.startswith("[") and not host_text.endswith("]"):
        return f"[{host_text}]"
    return host_text
