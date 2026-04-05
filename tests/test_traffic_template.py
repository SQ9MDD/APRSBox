import unittest
from pathlib import Path


class TrafficTemplateTests(unittest.TestCase):
    def test_traffic_template_uses_single_interface_summary_block(self) -> None:
        template_source = Path("app/templates/traffic.html").read_text(encoding="utf-8")
        self.assertIn('id="traffic-interface-summary"', template_source)
        self.assertIn('id="traffic-initial-data"', template_source)
        self.assertNotIn('id="traffic-expose-summary"', template_source)

    def test_traffic_template_exposes_manual_tnc_reconnect_action(self) -> None:
        template_source = Path("app/templates/traffic.html").read_text(encoding="utf-8")
        self.assertIn('action="{{ request.scope.root_path }}/traffic/reconnect"', template_source)
        self.assertIn('Restart traffic monitor runtime now?', template_source)
        self.assertIn('Reconnect TNC', template_source)


if __name__ == "__main__":
    unittest.main()
