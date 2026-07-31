import contextlib
import importlib.util
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import execute, get_app_setting, init_db
from app.services.content import has_enabled_modem_interface
from app.services.system import (
    container_system_actions_disabled_message,
    save_update_channel,
    start_application_update_job,
    start_host_poweroff_job,
    start_host_reboot_job,
    start_service_restart_job,
)

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None


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

    def test_settings_router_blocks_runtime_reset_when_any_tnc_is_enabled(self) -> None:
        router_source = Path("app/routers/pages.py").read_text(encoding="utf-8")
        self.assertIn('@router.post("/settings/reset-runtime-data")', router_source)
        self.assertIn("Disable all TNC interfaces before clearing runtime logs and traffic history.", router_source)
        self.assertIn("Runtime logs and traffic history cleared.", router_source)
        self.assertIn("reset_runtime_operational_data()", router_source)

    def test_settings_template_contains_configuration_backup_actions(self) -> None:
        template_source = Path("app/templates/settings.html").read_text(encoding="utf-8")
        self.assertIn('{{ t("Configuration backup") }}', template_source)
        self.assertIn('href="{{ request.scope.root_path }}/settings/config/export"', template_source)
        self.assertIn('action="{{ request.scope.root_path }}/settings/config/import"', template_source)
        self.assertIn('name="backup_file"', template_source)

    def test_settings_template_contains_event_log_controls(self) -> None:
        template_source = Path("app/templates/settings.html").read_text(encoding="utf-8")
        self.assertIn('name="traffic_retention_minutes"', template_source)
        self.assertIn('name="event_log_min_level"', template_source)
        self.assertIn('name="event_log_debug_enabled"', template_source)
        self.assertIn('{{ t("Traffic history retention") }}', template_source)
        self.assertIn('{{ t("Minimum stored log level") }}', template_source)
        self.assertIn('{{ t("Enable DEBUG logs") }}', template_source)
        self.assertIn('action="{{ request.scope.root_path }}/settings/reset-runtime-data"', template_source)
        self.assertIn("data-settings-action-id=\"reset-runtime-data\"", template_source)
        self.assertIn('{{ t("Reset runtime logs/data") }}', template_source)

    def test_settings_template_contains_aprs_alarm_group_configuration_and_diagnostics(self) -> None:
        template_source = Path("app/templates/settings.html").read_text(encoding="utf-8")
        self.assertIn('{{ t("APRS alarm settings") }}', template_source)
        self.assertIn('action="{{ request.scope.root_path }}/settings/alarm-groups"', template_source)
        self.assertIn('name="alarm_enabled"', template_source)
        self.assertIn('{{ t("Enable APRS alarms") }}', template_source)
        self.assertIn('name="alarm_groups"', template_source)
        self.assertIn('name="threshold_category"', template_source)
        self.assertIn('name="alert_level_threshold"', template_source)
        self.assertNotIn('name="map_level_threshold"', template_source)
        self.assertIn('name="popup_level_threshold"', template_source)
        self.assertIn('<option value="off"', template_source)
        self.assertIn('{{ t("Alarm thresholds by event type") }}', template_source)
        self.assertIn('{{ t("Alerts") }}', template_source)
        self.assertIn('{{ t("Alert popup") }}', template_source)
        self.assertIn(
            '{{ t("Alarm visibility on the map is managed directly from the alarm panel on the Map page.") }}',
            template_source,
        )
        self.assertIn("alarm_category_threshold_rows", template_source)
        self.assertIn("aprs_alarm_groups|join(', ')", template_source)
        self.assertIn('{{ t("RF receive groups") }}', template_source)
        self.assertIn("effective_rf_message_groups|join(', ')", template_source)
        self.assertIn('{{ t("Automatic APRS-IS filter") }}', template_source)
        self.assertIn("automatic_aprsis_alarm_filter", template_source)

    def test_settings_template_keeps_global_save_button_below_coverage_controls(self) -> None:
        template_source = Path("app/templates/settings.html").read_text(encoding="utf-8")
        self.assertIn('id="global-settings-form"', template_source)
        self.assertIn('form="global-settings-form"', template_source)
        self.assertLess(
            template_source.index('{{ t("Coverage fill opacity") }}'),
            template_source.index('{{ t("Save Global Settings") }}'),
        )

    def test_settings_template_uses_global_coverage_fill_opacity(self) -> None:
        template_source = Path("app/templates/settings.html").read_text(encoding="utf-8")
        router_source = Path("app/routers/pages.py").read_text(encoding="utf-8")
        self.assertIn('name="coverage_fill_opacity"', template_source)
        self.assertIn('{% if coverage_fill_opacity == value %}selected{% endif %}', template_source)
        self.assertNotIn("aprsbox-map-coverage-fill-opacity", template_source)
        self.assertIn("set_app_setting(COVERAGE_FILL_OPACITY_SETTING_KEY", router_source)

    @unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
    def test_global_settings_save_persists_coverage_fill_opacity(self) -> None:
        from app.models import UserIdentity
        from app.routers.pages import settings_update_global

        with temporary_database():
            response = settings_update_global(
                request=None,
                language="en",
                default_units="metric",
                traffic_retention_minutes="60",
                ui_palette="green-core",
                aprs_symbol_set="legacy",
                event_log_min_level="INFO",
                event_log_debug_enabled=None,
                coverage_fill_opacity="5",
                current_user=UserIdentity(id=1, username="admin", role="admin", is_active=True),
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(get_app_setting("map_coverage_fill_opacity"), "5")

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

    def test_settings_template_contains_container_mode_guards(self) -> None:
        template_source = Path("app/templates/settings.html").read_text(encoding="utf-8")
        self.assertIn("{% if is_container_mode %}", template_source)
        self.assertIn("Docker installation detected. System actions are disabled inside Docker.", template_source)
        self.assertIn("Check version can be used for informational comparison only.", template_source)

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
        self.assertIn('@router.post("/settings/reset-runtime-data")', router_source)
        self.assertIn('@router.post("/settings/restart-services")', router_source)
        self.assertIn('@router.post("/settings/reboot-host")', router_source)
        self.assertIn('@router.post("/settings/poweroff-host")', router_source)
        self.assertIn('@router.get("/api/settings/update/channels")', router_source)
        self.assertIn('@router.get("/api/settings/update/channel")', router_source)
        self.assertIn('@router.post("/api/settings/update/channel")', router_source)
        self.assertIn('@router.get("/api/settings/update/log")', router_source)
        self.assertIn('@router.get("/api/settings/jobs/{job_id}")', router_source)

    def test_settings_router_blocks_danger_zone_endpoints_in_container_mode(self) -> None:
        router_source = Path("app/routers/pages.py").read_text(encoding="utf-8")
        self.assertIn("def _container_mode_system_action_denied_response()", router_source)
        self.assertIn("container_system_actions_disabled_message()", router_source)
        self.assertIn("if is_container_mode():", router_source)
        self.assertIn("status.HTTP_409_CONFLICT", router_source)

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

    def test_system_actions_are_rejected_in_container_mode_without_starting_scripts(self) -> None:
        with patch("app.services.system.is_container_mode", return_value=True), patch(
            "app.services.system._start_background_script"
        ) as runner:
            denied = [
                start_application_update_job(job_id=1),
                start_service_restart_job(job_id=2),
                start_host_reboot_job(job_id=3),
                start_host_poweroff_job(job_id=4),
            ]

        runner.assert_not_called()
        for result in denied:
            self.assertFalse(result["ok"])
            self.assertEqual(result["status_code"], 409)
            self.assertEqual(result["error"], container_system_actions_disabled_message())

    def test_dockerfile_sets_container_env_flag(self) -> None:
        dockerfile_source = Path("Dockerfile").read_text(encoding="utf-8")
        self.assertIn("ENV APRSBOX_CONTAINER=1", dockerfile_source)

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

    def test_base_template_supports_sidebar_collapse_persistence(self) -> None:
        base_source = Path("app/templates/base.html").read_text(encoding="utf-8")
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        self.assertIn('id="app-sidebar"', base_source)
        self.assertIn('id="sidebar-collapse-toggle"', base_source)
        self.assertIn('id="sidebar-collapse-toggle-icon"', base_source)
        self.assertIn('class="sidebar-collapse-slot"', base_source)
        self.assertIn('class="sidebar-logo-icon"', base_source)
        self.assertIn('sidebarStateStorageKey = "aprsbox-sidebar-state"', base_source)
        self.assertIn('root.setAttribute("data-sidebar-state"', base_source)
        self.assertIn("--sidebar-collapsed-width", stylesheet_source)
        self.assertIn(':root[data-sidebar-state="collapsed"] .sidebar', stylesheet_source)
        self.assertIn(':root[data-sidebar-state="collapsed"] .sidebar-user-panel', stylesheet_source)
        self.assertIn(':root[data-sidebar-state="collapsed"] .sidebar-utc-clock', stylesheet_source)
        self.assertIn(".sidebar-logo-icon", stylesheet_source)
        self.assertIn(".nav-label", stylesheet_source)

    def test_sidebar_user_controls_use_compact_icon_strip(self) -> None:
        base_source = Path("app/templates/base.html").read_text(encoding="utf-8")
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")

        self.assertNotIn('class="role-badge">{{ current_user.username }}', base_source)
        self.assertIn('class="sidebar-username"', base_source)
        self.assertIn("{{ current_user.username }}", base_source)
        self.assertIn(".sidebar-user-identity", stylesheet_source)
        self.assertIn("margin-block: calc(-1 * var(--space-2));", stylesheet_source)
        self.assertIn("background: var(--panel-emphasis);", stylesheet_source)
        self.assertIn("justify-content: space-between;", stylesheet_source)

    def test_sidebar_beacon_control_uses_confirmation_and_ten_second_cooldown(self) -> None:
        base_source = Path("app/templates/base.html").read_text(encoding="utf-8")
        modal_source = Path("app/templates/partials/sidebar_beacon_modal.html").read_text(encoding="utf-8")
        script_source = Path("app/static/js/sidebar-beacon.js").read_text(encoding="utf-8")
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")

        self.assertIn('id="sidebar-send-beacon"', base_source)
        self.assertLess(
            base_source.index('id="sidebar-send-beacon"'),
            base_source.index('id="theme-toggle"'),
        )
        self.assertIn('{% include "partials/sidebar_beacon_modal.html" %}', base_source)
        self.assertIn("sidebar-beacon.js", base_source)
        self.assertIn('role="dialog"', modal_source)
        self.assertIn("Are you sure you want to send the beacon now?", modal_source)
        self.assertIn("/station/send-beacon-now", modal_source)
        self.assertIn("const cooldownMs = 10_000;", script_source)
        self.assertIn("aprsbox-beacon-send-cooldown-until", script_source)
        self.assertIn("window.localStorage", script_source)
        self.assertIn("place-items: center;", stylesheet_source)
        self.assertIn(".sidebar-action-button:disabled", stylesheet_source)
        self.assertIn("filter: grayscale(1) var(--icon-filter);", stylesheet_source)

    @unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed in this environment")
    def test_sidebar_beacon_endpoint_queues_saved_station_settings(self) -> None:
        from app.models import UserIdentity
        from app.routers.pages import station_send_beacon_now

        station_settings = {"callsign": "SQ9MDD", "ssid": "7"}
        with (
            patch("app.routers.pages.get_station_settings", return_value=station_settings),
            patch(
                "app.routers.pages.enqueue_beacon_job",
                return_value=(True, "Beacon job queued."),
            ) as enqueue,
        ):
            response = station_send_beacon_now(
                current_user=UserIdentity(
                    id=1,
                    username="admin",
                    role="admin",
                    is_active=True,
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            json.loads(response.body),
            {"ok": True, "message": "Beacon job queued."},
        )
        enqueue.assert_called_once_with(station_settings)


if __name__ == "__main__":
    unittest.main()
