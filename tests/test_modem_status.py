import contextlib
import json
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
    def test_interface_list_includes_enable_disable_action(self) -> None:
        template_source = Path("app/templates/section.html").read_text(encoding="utf-8")
        self.assertIn("data-interface-toggle-action", template_source)
        self.assertIn("/settings/modems/{{ row.id }}/toggle", template_source)
        self.assertIn("pause-circle-outline.svg", template_source)
        self.assertIn("play-circle-outline.svg", template_source)
        self.assertIn('"X-Requested-With": "XMLHttpRequest"', template_source)

    def test_interface_toggle_updates_only_enabled_state_and_returns_modal_payload(self) -> None:
        with temporary_database():
            from app.models import UserIdentity
            from app.routers.pages import modems_toggle
            from starlette.requests import Request

            execute(
                """
                INSERT INTO modems(name, modem_type, band, device_path, baud_rate, enabled, tx_blocked,
                                   expose_port_enabled, expose_bind_address, expose_port, expose_whitelist,
                                   notes, created_at, updated_at)
                VALUES ('Toggle TNC', 'TCP', '2m', '127.0.0.1:8001', NULL, 0, 1,
                        0, '0.0.0.0', 8002, '', '', '2026-01-01T00:00:00+00:00',
                        '2026-01-01T00:00:00+00:00')
                """
            )
            current_user = UserIdentity(
                id=1,
                username="admin",
                role="admin",
                is_active=True,
            )
            request = Request(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/settings/modems/1/toggle",
                    "root_path": "",
                    "headers": [(b"x-requested-with", b"XMLHttpRequest")],
                    "query_string": b"",
                    "client": ("127.0.0.1", 12345),
                    "server": ("testserver", 80),
                    "scheme": "http",
                }
            )
            response = modems_toggle(1, request, current_user, enabled=1)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                json.loads(response.body),
                {
                    "ok": True,
                    "message": "Interface status updated.",
                    "reload": True,
                    "redirect": "/settings/modems",
                },
            )
            row = get_section_row("modems", 1)
            assert row is not None
            self.assertEqual(int(row["enabled"]), 1)
            self.assertEqual(int(row["tx_blocked"]), 1)
            self.assertEqual(row["name"], "Toggle TNC")
            self.assertNotEqual(row["updated_at"], "2026-01-01T00:00:00+00:00")

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

    def test_aprsis_disabled_for_rx_still_shows_connected_when_tx_flow_is_active(self) -> None:
        with temporary_database():
            execute(
                """
                INSERT INTO modems(name, modem_type, band, device_path, baud_rate, enabled, tx_blocked, expose_port_enabled, expose_bind_address, expose_port, expose_whitelist, notes, created_at, updated_at)
                VALUES ('APRS-IS', 'APRSIS', '', 'm/20', NULL, 0, 1, 0, '0.0.0.0', 8002, '', '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """
            )
            execute(
                """
                INSERT INTO digi_flows(name, description, source_kind, source_ref, target_kind, target_ref, enabled, created_at, updated_at)
                VALUES ('RF to APRS-IS', '', 'receiver_rf', 'TNC', 'tx_aprsis', 'aprsis', 1, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """
            )
            execute(
                """
                UPDATE aprsis_runtime_state
                SET status = 'inactive',
                    status_detail = 'Waiting for runtime.',
                    updated_at = '2026-01-01T00:00:04+00:00'
                WHERE id = 1
                """
            )

            inactive_row = get_section_row("modems", 1)
            assert inactive_row is not None
            self.assertFalse(inactive_row["aprsis_rx_enabled"])
            self.assertTrue(inactive_row["aprsis_tx_configured"])
            self.assertFalse(inactive_row["aprsis_tx_enabled"])
            self.assertEqual(inactive_row["modem_runtime_label"], "Disabled")
            self.assertEqual(
                inactive_row["aprsis_direction_title"],
                "APRS-IS connection is disabled; the TX flow is configured but cannot transmit.",
            )

            execute(
                """
                UPDATE aprsis_runtime_state
                SET status = 'connected',
                    status_detail = 'Connected for TX.',
                    updated_at = '2026-01-01T00:00:05+00:00'
                WHERE id = 1
                """
            )
            connected_row = get_section_row("modems", 1)
            assert connected_row is not None
            self.assertEqual(connected_row["modem_runtime_label"], "Disabled")


if __name__ == "__main__":
    unittest.main()
