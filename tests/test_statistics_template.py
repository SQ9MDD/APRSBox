import unittest
from pathlib import Path


class StatisticsTemplateTests(unittest.TestCase):
    def test_statistics_page_uses_separate_toolbar_panel_and_priority_order(self) -> None:
        template_source = Path("app/templates/statistics.html").read_text(encoding="utf-8")
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        script_source = Path("app/static/js/statistics.js").read_text(encoding="utf-8")

        self.assertIn('class="statistics-page" id="statistics-root"', template_source)
        self.assertIn('class="panel statistics-toolbar-panel"', template_source)
        self.assertNotIn('class="panel dashboard-activity-panel" id="statistics-root"', template_source)
        self.assertIn('class="statistics-priority-grid"', template_source)
        self.assertIn('class="dashboard-activity-grid statistics-secondary-grid"', template_source)
        self.assertNotIn('id="statistics-devices-chart"', template_source)
        self.assertIn('class="dashboard-activity-card-header statistics-direct-heard-header"', template_source)
        self.assertIn('({{ t("Max 20") }})', template_source)
        self.assertNotIn("Max 20 direct-heard stations in selected range.", template_source)

        self.assertIn(".statistics-page {", stylesheet_source)
        self.assertIn(".statistics-toolbar-panel .panel-body {", stylesheet_source)
        self.assertIn(".statistics-priority-grid {", stylesheet_source)
        self.assertIn(".statistics-secondary-grid {", stylesheet_source)
        self.assertIn(".statistics-devices-card {", stylesheet_source)
        self.assertIn(".statistics-priority-grid {\n    display: grid;\n    grid-template-columns: repeat(3, minmax(0, 1fr));", stylesheet_source)
        self.assertNotIn(".statistics-devices-canvas {", stylesheet_source)
        self.assertIn(".statistics-direct-heard-header {", stylesheet_source)
        self.assertIn(".statistics-card-note {", stylesheet_source)
        self.assertIn(".statistics-users-list-item-placeholder {", stylesheet_source)
        self.assertNotIn('const devicesCanvas = document.getElementById("statistics-devices-chart");', script_source)
        self.assertNotIn('type: "doughnut"', script_source)
        self.assertIn("const directHeardVisibleLimit = 20;", script_source)
        self.assertIn("items.slice(0, directHeardVisibleLimit)", script_source)
        self.assertIn("statistics-users-list-item statistics-users-list-item-placeholder", script_source)

        direct_heard_pos = template_source.find('{{ t("HEARD DIRECT") }}')
        top_users_pos = template_source.find('{{ t("TOP20 users") }}')
        top_devices_pos = template_source.find('{{ t("TOP20 devices") }}')
        frame_types_pos = template_source.find('{{ t("APRS Frame Types") }}')
        actions_pos = template_source.find('{{ t("APRSBox Actions") }}')

        self.assertGreaterEqual(direct_heard_pos, 0)
        self.assertGreaterEqual(top_users_pos, 0)
        self.assertGreaterEqual(top_devices_pos, 0)
        self.assertGreaterEqual(frame_types_pos, 0)
        self.assertGreaterEqual(actions_pos, 0)
        self.assertLess(direct_heard_pos, top_users_pos)
        self.assertLess(top_users_pos, top_devices_pos)
        self.assertLess(top_devices_pos, frame_types_pos)
        self.assertLess(top_devices_pos, actions_pos)


if __name__ == "__main__":
    unittest.main()
