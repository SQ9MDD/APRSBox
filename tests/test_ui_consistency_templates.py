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

    def test_global_layout_hides_scrollbars_without_disabling_scroll(self) -> None:
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        self.assertIn("scrollbar-width: none;", stylesheet_source)
        self.assertIn("-ms-overflow-style: none;", stylesheet_source)
        self.assertIn("*::-webkit-scrollbar {", stylesheet_source)
        self.assertNotIn("scrollbar-gutter: stable;", stylesheet_source)
        self.assertNotIn("scrollbar-gutter: stable both-edges;", stylesheet_source)

    def test_top_level_layout_wrappers_do_not_duplicate_content_gap_with_extra_margin(self) -> None:
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        band_condition_block = stylesheet_source.partition(".band-condition-layout {")[2].split("}", 1)[0]
        settings_block = stylesheet_source.partition(".settings-primary-grid {")[2].split("}", 1)[0]

        self.assertIn("gap: var(--space-4);", band_condition_block)
        self.assertNotIn("margin-bottom", band_condition_block)
        self.assertIn("align-items: start;", settings_block)
        self.assertNotIn("margin-bottom", settings_block)

    def test_station_page_uses_roomier_spacing_than_dashboard_density(self) -> None:
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        station_group_block = stylesheet_source.partition(".station-settings-group {")[2].split("}", 1)[0]
        station_page_form_block = stylesheet_source.partition(".station-page-panel .form-grid {")[2].split("}", 1)[0]
        station_subgrid_block = stylesheet_source.partition(".station-settings-subgrid {")[2].split("}", 1)[0]

        self.assertIn("padding: var(--space-4);", station_group_block)
        self.assertIn("gap: var(--space-4);", station_group_block)
        self.assertIn("gap: var(--space-4);", station_page_form_block)
        self.assertIn("gap: var(--space-4);", station_subgrid_block)

    def test_digi_step_actions_stay_right_aligned_when_step_summary_wraps(self) -> None:
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        header_block = stylesheet_source.partition(".digi-step-card-header {")[2].split("}", 1)[0]
        meta_block = stylesheet_source.partition(".digi-step-meta {")[2].split("}", 1)[0]
        actions_blocks = stylesheet_source.split(".digi-step-actions {")
        actions_block = actions_blocks[2].split("}", 1)[0]

        self.assertIn("flex-wrap: nowrap;", header_block)
        self.assertIn("flex: 1 1 0;", meta_block)
        self.assertIn("flex: 0 0 auto;", actions_block)


if __name__ == "__main__":
    unittest.main()
