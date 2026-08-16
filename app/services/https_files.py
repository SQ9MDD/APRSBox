from __future__ import annotations

import os
import ssl
from pathlib import Path
from tempfile import NamedTemporaryFile


HTTPS_CERTIFICATE_FILENAME = "aprsbox.crt"
HTTPS_PRIVATE_KEY_FILENAME = "aprsbox.key"
HTTPS_CA_CHAIN_FILENAME = "aprsbox-ca-chain.crt"
HTTPS_ENABLED_FILENAME = "https-enabled"
HTTPS_FILE_MAX_BYTES = 1024 * 1024


def https_file_status(ssl_dir: Path) -> dict[str, bool]:
    certificate_path = ssl_dir / HTTPS_CERTIFICATE_FILENAME
    private_key_path = ssl_dir / HTTPS_PRIVATE_KEY_FILENAME
    certificate_available = certificate_path.is_file()
    private_key_available = private_key_path.is_file()
    https_ready = False
    if certificate_available and private_key_available:
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile=str(certificate_path), keyfile=str(private_key_path))
            https_ready = True
        except (OSError, ssl.SSLError):
            pass
    return {
        "certificate_available": certificate_available,
        "private_key_available": private_key_available,
        "ca_chain_available": (ssl_dir / HTTPS_CA_CHAIN_FILENAME).is_file(),
        "https_ready": https_ready,
        "https_enabled": (ssl_dir / HTTPS_ENABLED_FILENAME).is_file(),
    }


def save_https_enabled(ssl_dir: Path, enabled: bool) -> None:
    ssl_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
    marker_path = ssl_dir / HTTPS_ENABLED_FILENAME
    if enabled:
        marker_path.touch(mode=0o600, exist_ok=True)
    elif marker_path.exists():
        marker_path.unlink()


def save_https_file(ssl_dir: Path, filename: str, payload: bytes, *, private: bool = False) -> None:
    ssl_dir.mkdir(parents=True, exist_ok=True, mode=0o750)
    target_path = ssl_dir / filename
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(dir=ssl_dir, prefix=f".{filename}.", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(payload)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        temp_path.chmod(0o600 if private else 0o644)
        os.replace(temp_path, target_path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
