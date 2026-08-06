import unittest
from pathlib import Path


class UiConsistencyTemplateTests(unittest.TestCase):
    def test_explanatory_copy_is_kept_in_help_instead_of_repeated_on_screens(self) -> None:
        forbidden_by_template = {
            "alerts.html": [
                "Logical APRS emergency alerts consolidated by source callsign.",
            ],
            "notifications.html": [
                "Use commas or line breaks. Wildcards are supported.",
                "Distance is measured from My Station coordinates.",
            ],
            "messages.html": [
                "Stored APRS message conversations from the local SQLite database.",
                "Choose a callsign on the left or start a new APRS message thread.",
                "startNewMessageFromLeft",
            ],
            "wx.html": [
                "Prepare one WX identity for this APRSBox instance.",
                "Map APRS WX parameters to configured sources.",
                "Store HTTP source definitions for Home Assistant and Domoticz.",
                "Recent WX jobs with delivery state",
            ],
            "station.html": [
                "Configure the APRS position beacon.",
                "Internal TX does not use physical RF transport.",
                "Proportional Path sends frequent local beacons",
                "Status is sent as a separate APRS frame",
                "Set power, antenna height above ground",
                "Recent beacon and APRS Status jobs",
                "beacon-schedule-note",
            ],
            "section.html": [
                "Recommended path is blank for direct.",
                "Prepared scheduling only.",
                "Activation schedule controls when sending is allowed.",
                "Manual: Leave empty to keep sending",
                "Uses the same outbound queue and scheduler path",
                "Recent object jobs with delivery state",
                "Recent bulletin jobs with delivery state",
            ],
            "digi_flow_form.html": [
                "Each block below shows one packet running through this flow",
                "appendFieldHelp",
                "stepMeta.description",
            ],
            "settings.html": [
                "Configure the interface language and default measurement units",
                "Applies globally across the GUI.",
                "Configure the update channel and run application update",
                "Use Check version to compare local VERSION",
                "Use a local cached APRS device identification database",
            ],
            "band_condition.html": [
                "What has been collected and how close the model is to a stable baseline.",
                "Confidence grows mainly with regular observations",
            ],
            "dashboard.html": [
                "Historical activity from 5-minute aggregates.",
            ],
            "logs.html": [
                "This log currently captures application and configuration events",
            ],
            "users.html": [
                "Only administrators can manage accounts and assign one of the built-in roles",
            ],
        }

        for template_name, forbidden_fragments in forbidden_by_template.items():
            template_source = Path("app/templates", template_name).read_text(encoding="utf-8")
            for fragment in forbidden_fragments:
                self.assertNotIn(fragment, template_source, msg=f"{fragment!r} remains in {template_name}")

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
        self.assertIn("const telegramOnlyRows", template_source)
        self.assertIn("const webhookOnlyRows", template_source)
        self.assertIn("row.hidden = !isTelegram", template_source)
        self.assertIn("row.hidden = !isWebhook", template_source)
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
