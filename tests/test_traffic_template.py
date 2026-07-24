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
        self.assertIn(".traffic-page-panel {\n    padding: 0;", stylesheet_source)
        self.assertIn("border: 0;", stylesheet_source)
        self.assertIn("background: transparent;", stylesheet_source)
        self.assertIn("box-shadow: none;", stylesheet_source)

    def test_traffic_interface_summary_does_not_add_extra_spacing_before_log(self) -> None:
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        self.assertIn(".traffic-summary-stream {", stylesheet_source)
        self.assertIn(".traffic-summary-stream {\n    max-height: none;\n    margin-bottom: 0;", stylesheet_source)

    def test_traffic_page_has_global_color_legend_for_interface_analysis(self) -> None:
        template_source = Path("app/templates/traffic.html").read_text(encoding="utf-8")
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")

        self.assertIn('class="traffic-color-legend"', template_source)
        for row_class in (
            "traffic-log-row-own-wx-tx",
            "traffic-log-row-own-wx-rx",
            "traffic-log-row-own-message-tx",
            "traffic-log-row-own-message-rx",
            "traffic-log-row-repeated-tx",
            "traffic-log-row-proxy-tx",
            "traffic-log-row-aprsis-rx",
            "traffic-log-row-aprsis-to-rf-tx",
        ):
            self.assertIn(f".{row_class}", stylesheet_source)


if __name__ == "__main__":
    unittest.main()
