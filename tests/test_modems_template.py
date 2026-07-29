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

    def test_aprsis_gui_explains_independent_rx_and_packet_routing_tx(self) -> None:
        template_source = Path("app/templates/section.html").read_text(encoding="utf-8")
        self.assertIn("Enable APRS-IS reception", template_source)
        self.assertIn("transmission uses the same connection", template_source)
        self.assertIn("APRS-IS TX is enabled by Packet Routing.", template_source)
        self.assertIn("source-branch-check.svg", template_source)

        section_source = Path("app/sections.py").read_text(encoding="utf-8")
        self.assertIn('"APRS-IS (RX/TX)"', section_source)
        self.assertIn("APRS-IS reception and transmission", section_source)

        css_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        self.assertIn(".form-grid > [hidden]", css_source)
        self.assertIn("display: none !important;", css_source)

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
