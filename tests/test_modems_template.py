import unittest
from pathlib import Path


class ModemsTemplateTests(unittest.TestCase):
    def test_modems_status_column_uses_icon_indicator_instead_of_badge(self) -> None:
        template_source = Path("app/templates/section.html").read_text(encoding="utf-8")
        self.assertIn("tnc-status-icon", template_source)
        self.assertIn("row.modem_runtime_status", template_source)
        self.assertIn("row.modem_runtime_icon", template_source)

    def test_modems_template_includes_help_viewer(self) -> None:
        template_source = Path("app/templates/section.html").read_text(encoding="utf-8")
        self.assertIn("static/css/help-viewer.css", template_source)
        self.assertIn("section.slug in ['objects', 'modems', 'bulletins']", template_source)
        self.assertIn("'application/tnc' if section.slug == 'modems'", template_source)
        self.assertIn('class="help-icon-button page-help-button"', template_source)
        self.assertIn('include "partials/help_modal.html"', template_source)
        self.assertIn("static/js/help-viewer.js", template_source)
        for language in ("pl", "en", "es", "de"):
            self.assertTrue(Path(f"help/application/tnc.{language}.md").exists())

    def test_modem_save_uses_settings_style_progress_modal(self) -> None:
        template_source = Path("app/templates/section.html").read_text(encoding="utf-8")
        self.assertIn("data-interface-save-action", template_source)
        self.assertIn('id="interface-save-progress"', template_source)
        self.assertIn("settings-progress-spinner", template_source)
        self.assertIn('"X-Requested-With": "XMLHttpRequest"', template_source)
        self.assertIn('"Accept": "application/json"', template_source)

    def test_aprsis_gui_uses_concise_connection_controls(self) -> None:
        template_source = Path("app/templates/section.html").read_text(encoding="utf-8")
        fields_source = Path("app/templates/partials/modem_form_fields.html").read_text(encoding="utf-8")
        self.assertIn("Enable APRS-IS connection", template_source)
        self.assertNotIn("Enable APRS-IS reception", template_source + fields_source)
        self.assertNotIn("receive and transmit through APRS-IS", fields_source)
        self.assertNotIn("This interface receives OpenWebRX MQTT traffic only", fields_source)
        self.assertNotIn("Serial-only watchdog timeout", fields_source)
        self.assertNotIn("Per-TNC TX pacing gap", fields_source)
        self.assertNotIn("LAN listen address", fields_source)
        self.assertNotIn("TCP port exposed by APRSBox", fields_source)
        self.assertNotIn("Optional allow-list", fields_source)
        self.assertIn("APRS-IS TX is enabled by Packet Routing.", template_source)
        self.assertIn("source-branch-check.svg", template_source)

        section_source = Path("app/sections.py").read_text(encoding="utf-8")
        self.assertIn('"APRS-IS (RX/TX)"', section_source)
        self.assertIn("APRS-IS reception and transmission", section_source)

        css_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        self.assertIn(".form-grid > [hidden]", css_source)
        self.assertIn("display: none !important;", css_source)

    def test_rx_silence_timeout_is_shared_by_serial_and_native_tcp_panels(self) -> None:
        fields_source = Path("app/templates/partials/modem_form_fields.html").read_text(encoding="utf-8")
        self.assertIn("{% macro rx_silence_reconnect_field()", fields_source)
        self.assertEqual(fields_source.count("{{ rx_silence_reconnect_field() }}"), 2)

    def test_tnc_help_does_not_describe_aprsis_as_receive_only(self) -> None:
        receive_only_claims = {
            "pl": "APRS-IS można włączyć jako interfejs tylko do odbioru",
            "en": "APRS-IS can be enabled as a receive-only input",
            "es": "APRS-IS puede activarse como entrada de solo recepción",
            "de": "APRS-IS kann als reiner Empfangseingang aktiviert werden",
        }
        for language, claim in receive_only_claims.items():
            help_source = Path(f"help/application/tnc.{language}.md").read_text(encoding="utf-8")
            self.assertNotIn(claim, help_source)
            self.assertIn("TX APRS-IS", help_source)


if __name__ == "__main__":
    unittest.main()
