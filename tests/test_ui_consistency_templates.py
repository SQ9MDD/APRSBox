import unittest
from pathlib import Path


class UiConsistencyTemplateTests(unittest.TestCase):
    def test_changelog_uses_standard_panel_body_header_structure(self) -> None:
        template_source = Path("app/templates/changelog.html").read_text(encoding="utf-8")
        self.assertIn('<section class="panel">\n    <div class="panel-body">\n        <div class="panel-header">', template_source)
        self.assertNotIn('<section class="panel">\n    <div class="panel-header">', template_source)

    def test_notifications_template_uses_shared_subsection_classes_without_inline_styles(self) -> None:
        template_source = Path("app/templates/notifications.html").read_text(encoding="utf-8")
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")

        self.assertNotIn('style="', template_source)
        self.assertIn('class="panel-subsection"', template_source)
        self.assertIn('class="panel-subsection-header"', template_source)
        self.assertIn(".panel-subsection {", stylesheet_source)
        self.assertIn(".panel-subsection + .panel-subsection {", stylesheet_source)
        self.assertIn(".panel-subsection-header {", stylesheet_source)
        self.assertIn(".panel-subsection-header h3 {", stylesheet_source)

    def test_stations_page_uses_default_panel_h2_typography(self) -> None:
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        self.assertIn(".panel h2 {", stylesheet_source)
        self.assertNotIn(".stations-summary-header h2 {", stylesheet_source)
        self.assertNotIn("font-size: 1.05rem;", stylesheet_source)

    def test_global_layout_keeps_stable_scrollbar_gutter(self) -> None:
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        self.assertIn("html {\n    scrollbar-gutter: stable;\n}", stylesheet_source)

    def test_top_level_layout_wrappers_do_not_duplicate_content_gap_with_extra_margin(self) -> None:
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        band_condition_block = stylesheet_source.partition(".band-condition-layout {")[2].split("}", 1)[0]
        settings_block = stylesheet_source.partition(".settings-primary-grid {")[2].split("}", 1)[0]

        self.assertIn("gap: var(--space-4);", band_condition_block)
        self.assertNotIn("margin-bottom", band_condition_block)
        self.assertIn("align-items: start;", settings_block)
        self.assertNotIn("margin-bottom", settings_block)


if __name__ == "__main__":
    unittest.main()
