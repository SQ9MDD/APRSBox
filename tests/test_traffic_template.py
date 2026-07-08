import unittest
from pathlib import Path


class TrafficTemplateTests(unittest.TestCase):
    def test_traffic_template_uses_single_interface_summary_block(self) -> None:
        template_source = Path("app/templates/traffic.html").read_text(encoding="utf-8")
        self.assertIn('id="traffic-interface-summary"', template_source)
        self.assertIn('id="traffic-initial-data"', template_source)
        self.assertNotIn('id="traffic-expose-summary"', template_source)

    def test_traffic_page_uses_chromeless_outer_panel_wrapper(self) -> None:
        template_source = Path("app/templates/traffic.html").read_text(encoding="utf-8")
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        self.assertIn('class="panel traffic-page-panel"', template_source)
        self.assertIn(".traffic-page-panel {", stylesheet_source)
        self.assertIn("padding: var(--space-4);", stylesheet_source)
        self.assertIn("border: 0;", stylesheet_source)
        self.assertIn("background: transparent;", stylesheet_source)
        self.assertIn("box-shadow: none;", stylesheet_source)


if __name__ == "__main__":
    unittest.main()
