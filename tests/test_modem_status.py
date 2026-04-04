import contextlib
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, init_db
from app.services.content import get_section_row


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        try:
            init_db()
            yield database_path
        finally:
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


class ModemStatusTests(unittest.TestCase):
    def test_enabled_modem_with_runtime_error_exposes_error_status(self) -> None:
        with temporary_database():
            execute(
                """
                INSERT INTO modems(name, modem_type, band, device_path, baud_rate, enabled, expose_port_enabled, expose_bind_address, expose_port, expose_whitelist, notes, created_at, updated_at)
                VALUES (?, 'TCP', '2m', ?, NULL, 1, 0, '0.0.0.0', 8002, '', '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """,
                ("Test TNC", "127.0.0.1:8001"),
            )
            execute(
                """
                INSERT INTO traffic_runtime_interfaces(
                    modem_id, modem_name, modem_endpoint, band, status, status_detail,
                    expose_port_enabled, expose_bind_address, expose_port, expose_active_clients,
                    last_error, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 0, '0.0.0.0', 8002, 0, ?, '2026-01-01T00:00:05+00:00')
                """,
                (
                    1,
                    "Test TNC",
                    "127.0.0.1:8001",
                    "2m",
                    "error",
                    "TCP connection failed.",
                    "TCP connection to 127.0.0.1:8001 failed: [Errno 111] Connection refused",
                ),
            )

            row = get_section_row("modems", 1)
            assert row is not None
            self.assertEqual(row["modem_runtime_status"], "error")
            self.assertEqual(row["modem_runtime_label"], "Error")
            self.assertEqual(row["modem_runtime_icon"], "alert-circle-outline.svg")
            self.assertIn("Connection refused", row["modem_runtime_title"])


if __name__ == "__main__":
    unittest.main()
