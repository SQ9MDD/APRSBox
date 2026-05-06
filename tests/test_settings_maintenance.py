import contextlib
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import execute, init_db
from app.services.content import has_enabled_modem_interface
from app.services.system import save_update_channel, start_application_update_job


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
        self.assertIn("Disable all TNC interfaces before running database vacuum.", router_source)
        self.assertIn("status.HTTP_409_CONFLICT", router_source)

    def test_settings_template_contains_configuration_backup_actions(self) -> None:
        template_source = Path("app/templates/settings.html").read_text(encoding="utf-8")
        self.assertIn('{{ t("Configuration backup") }}', template_source)
        self.assertIn('href="{{ request.scope.root_path }}/settings/config/export"', template_source)
        self.assertIn('action="{{ request.scope.root_path }}/settings/config/import"', template_source)
        self.assertIn('name="backup_file"', template_source)

    def test_settings_template_contains_event_log_controls(self) -> None:
        template_source = Path("app/templates/settings.html").read_text(encoding="utf-8")
        self.assertIn('name="event_log_min_level"', template_source)
        self.assertIn('name="event_log_debug_enabled"', template_source)
        self.assertIn('{{ t("Minimum stored log level") }}', template_source)
        self.assertIn('{{ t("Enable DEBUG logs") }}', template_source)

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
        self.assertNotIn('{{ t("Update log") }}', template_source)
        self.assertNotIn("update-log-preview", template_source)

    def test_settings_template_uses_shared_async_action_handler(self) -> None:
        template_source = Path("app/templates/settings.html").read_text(encoding="utf-8")
        self.assertIn("window.aprsboxSubmitSettingsAction", template_source)
        self.assertIn("window.__aprsboxSettingsSubmit", template_source)
        self.assertIn("settings-progress-close", template_source)
        self.assertIn('data-settings-action-id="check-gui-version"', template_source)
        self.assertIn('data-settings-action-id="update-application"', template_source)
        self.assertIn('data-settings-action-id="restart-services"', template_source)
        self.assertIn('data-settings-action-id="reboot-host"', template_source)
        self.assertIn('data-settings-action-id="poweroff-host"', template_source)
        self.assertIn('data-settings-action-group="update-controls"', template_source)
        self.assertIn('data-settings-action-group="danger-actions"', template_source)

    def test_settings_styles_include_busy_state_spinner(self) -> None:
        style_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        self.assertIn(".settings-action-button-busy", style_source)
        self.assertIn(".settings-progress-spinner", style_source)
        self.assertIn("@keyframes settings-spin", style_source)

    def test_settings_router_contains_danger_zone_endpoints(self) -> None:
        router_source = Path("app/routers/pages.py").read_text(encoding="utf-8")
        self.assertIn('@router.get("/settings/config/export")', router_source)
        self.assertIn('@router.post("/settings/config/import")', router_source)
        self.assertIn("_CONFIG_BACKUP_MAX_BYTES = 5 * 1024 * 1024", router_source)
        self.assertIn('@router.post("/settings/update-application")', router_source)
        self.assertIn('@router.post("/settings/update-channel")', router_source)
        self.assertIn('@router.post("/settings/restart-services")', router_source)
        self.assertIn('@router.post("/settings/reboot-host")', router_source)
        self.assertIn('@router.post("/settings/poweroff-host")', router_source)
        self.assertIn('@router.get("/api/settings/update/channels")', router_source)
        self.assertIn('@router.get("/api/settings/update/channel")', router_source)
        self.assertIn('@router.post("/api/settings/update/channel")', router_source)
        self.assertIn('@router.get("/api/settings/update/log")', router_source)
        self.assertIn('@router.get("/api/settings/jobs/{job_id}")', router_source)

    def test_settings_template_escapes_tojson_in_onsubmit_attributes(self) -> None:
        template_source = Path("app/templates/settings.html").read_text(encoding="utf-8")
        unescaped_tojson = re.findall(r'onsubmit="[^"]*\|tojson(?!\|forceescape)', template_source)
        self.assertEqual([], unescaped_tojson)

    def test_update_application_has_forty_five_second_timeout(self) -> None:
        template_source = Path("app/templates/settings.html").read_text(encoding="utf-8")
        self.assertIn("actionId: 'update-application'", template_source)
        self.assertIn("lockTimeoutMs: 45000", template_source)

    def test_restart_services_has_reload_delay(self) -> None:
        template_source = Path("app/templates/settings.html").read_text(encoding="utf-8")
        self.assertIn("actionId: 'restart-services'", template_source)
        self.assertIn("lockTimeoutMs: 45000", template_source)
        self.assertIn("reloadDelayMs: 7000", template_source)

    def test_update_job_passes_selected_channel_as_cli_argument(self) -> None:
        with temporary_database(), patch("app.services.system._start_background_script", return_value={"ok": True}) as runner:
            save_update_channel("dev")
            result = start_application_update_job(job_id=123)

            self.assertTrue(result["ok"])
            kwargs = runner.call_args.kwargs
            self.assertEqual(kwargs.get("extra_args"), ["--git-branch", "dev"])

    def test_update_script_accepts_git_branch_argument(self) -> None:
        script_source = Path("scripts/update.sh").read_text(encoding="utf-8")
        self.assertIn("parse_args()", script_source)
        self.assertIn("--git-branch", script_source)
        self.assertIn('update_channel_source="argument"', script_source)

    def test_base_template_supports_clock_mode_toggle_persistence(self) -> None:
        base_source = Path("app/templates/base.html").read_text(encoding="utf-8")
        self.assertIn('id="sidebar-utc-clock"', base_source)
        self.assertIn('id="sidebar-utc-clock-zone"', base_source)
        self.assertIn('clockModeStorageKey = "aprsbox-clock-mode"', base_source)
        self.assertIn("localStorage.setItem(clockModeStorageKey", base_source)
        self.assertIn('utcClockRoot.addEventListener("click"', base_source)


if __name__ == "__main__":
    unittest.main()
