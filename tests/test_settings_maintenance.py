import contextlib
import os
import tempfile
import unittest
from pathlib import Path

from app.db import execute, init_db
from app.services.content import has_enabled_modem_interface


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


def insert_modem(*, enabled: int) -> None:
    execute(
        """
        INSERT INTO modems(name, modem_type, band, device_path, baud_rate, enabled, notes, created_at, updated_at)
        VALUES ('Test TNC', 'TCP', '2m', '127.0.0.1:8001', NULL, ?, '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
        """,
        (enabled,),
    )


class SettingsMaintenanceTests(unittest.TestCase):
    def test_enabled_tnc_helper_matches_modem_configuration(self) -> None:
        with temporary_database():
            self.assertFalse(has_enabled_modem_interface())

            insert_modem(enabled=1)
            self.assertTrue(has_enabled_modem_interface())

    def test_settings_template_disables_vacuum_button_when_tnc_is_enabled(self) -> None:
        template_source = Path("app/templates/settings.html").read_text(encoding="utf-8")
        self.assertIn('action="{{ request.scope.root_path }}/settings/vacuum-db"', template_source)
        self.assertIn(
            """{% if database_vacuum_blocked %}disabled title="{{ t('Disable all TNC interfaces before running database vacuum.') }}"{% endif %}""",
            template_source,
        )

    def test_settings_router_blocks_vacuum_when_any_tnc_is_enabled(self) -> None:
        router_source = Path("app/routers/pages.py").read_text(encoding="utf-8")
        self.assertIn('@router.post("/settings/vacuum-db")', router_source)
        self.assertIn("if has_enabled_modem_interface():", router_source)
        self.assertIn('flash="Disable all TNC interfaces before running database vacuum."', router_source)

    def test_settings_template_contains_danger_zone_actions(self) -> None:
        template_source = Path("app/templates/settings.html").read_text(encoding="utf-8")
        self.assertIn('{{ t("Danger zone") }}', template_source)
        self.assertIn('action="{{ request.scope.root_path }}/settings/update-application"', template_source)
        self.assertIn('action="{{ request.scope.root_path }}/settings/restart-services"', template_source)
        self.assertIn('action="{{ request.scope.root_path }}/settings/reboot-host"', template_source)
        self.assertIn('action="{{ request.scope.root_path }}/settings/poweroff-host"', template_source)
        self.assertIn("Type REBOOT to confirm host reboot.", template_source)
        self.assertIn("Type POWER OFF to confirm host shutdown.", template_source)
        self.assertIn('action="{{ request.scope.root_path }}/settings/update-channel"', template_source)
        self.assertIn('{{ t("Update log") }}', template_source)
        self.assertIn("update-log-preview", template_source)

    def test_settings_router_contains_danger_zone_endpoints(self) -> None:
        router_source = Path("app/routers/pages.py").read_text(encoding="utf-8")
        self.assertIn('@router.post("/settings/update-application")', router_source)
        self.assertIn('@router.post("/settings/update-channel")', router_source)
        self.assertIn('@router.post("/settings/restart-services")', router_source)
        self.assertIn('@router.post("/settings/reboot-host")', router_source)
        self.assertIn('@router.post("/settings/poweroff-host")', router_source)
        self.assertIn('@router.get("/api/settings/update/channels")', router_source)
        self.assertIn('@router.get("/api/settings/update/channel")', router_source)
        self.assertIn('@router.post("/api/settings/update/channel")', router_source)
        self.assertIn('@router.get("/api/settings/update/log")', router_source)


if __name__ == "__main__":
    unittest.main()
