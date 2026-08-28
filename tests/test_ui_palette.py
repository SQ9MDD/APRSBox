import json
import re
import unittest
from pathlib import Path

from app.ui_palette import (
    DEFAULT_UI_PALETTE,
    UI_PALETTE_OPTIONS,
    get_ui_palette_label,
    get_ui_palette_options,
    is_supported_ui_palette,
    normalize_ui_palette,
)


class UiPaletteTests(unittest.TestCase):
    def test_palette_identifiers_are_unique_and_default_is_preserved(self) -> None:
        values = [option["value"] for option in UI_PALETTE_OPTIONS]
        self.assertEqual(DEFAULT_UI_PALETTE, "green-core")
        self.assertEqual(len(values), len(set(values)))
        self.assertGreaterEqual(len(values), 31)

    def test_every_extended_palette_has_both_theme_definitions_and_a_gui_swatch(self) -> None:
        stylesheet = Path("app/static/css/style.css").read_text(encoding="utf-8")
        template = Path("app/templates/settings.html").read_text(encoding="utf-8")
        existing_values = {
            "green-core",
            "red-tactic",
            "forest-pine",
            "nordic-blue",
            "slate-cyan",
            "amber-graphite",
            "crimson-ops",
            "violet-signal",
            "monochrome-neutral",
            "copper-radar",
            "orange-workshop",
        }

        self.assertIn('type="radio"', template)
        self.assertIn('name="ui_palette"', template)
        self.assertIn('data-palette-preview="{{ option.value }}"', template)
        for option in UI_PALETTE_OPTIONS:
            palette = option["value"]
            with self.subTest(palette=palette):
                self.assertIn(
                    f'.palette-picker-swatch[data-palette-preview="{palette}"]',
                    stylesheet,
                )
                if palette not in existing_values:
                    for theme in ("dark", "light"):
                        selector = (
                            f':root[data-theme="{theme}"]'
                            f'[data-palette="{palette}"]'
                        )
                        self.assertIn(selector, stylesheet)
                        block_match = re.search(
                            re.escape(selector) + r"\s*\{([^}]+)\}",
                            stylesheet,
                        )
                        self.assertIsNotNone(block_match)
                        block = block_match.group(1)
                        for token in (
                            "bg",
                            "bg-layer",
                            "panel",
                            "surface",
                            "border",
                            "text",
                            "muted",
                            "accent",
                            "accent-strong",
                        ):
                            self.assertIn(f"--palette-{token}:", block)

    def test_orange_workshop_palette_is_available(self) -> None:
        self.assertTrue(is_supported_ui_palette("orange-workshop"))
        self.assertEqual(normalize_ui_palette("Orange-Workshop"), "orange-workshop")
        self.assertEqual(get_ui_palette_label("orange-workshop"), "Orange Workshop")
        self.assertIn(
            {"value": "orange-workshop", "label": "Orange Workshop"},
            get_ui_palette_options(),
        )

    def test_orange_workshop_supports_both_themes(self) -> None:
        stylesheet = Path("app/static/css/style.css").read_text(encoding="utf-8")
        self.assertIn(
            ':root[data-theme="dark"][data-palette="orange-workshop"]',
            stylesheet,
        )
        self.assertIn(
            ':root[data-theme="light"][data-palette="orange-workshop"]',
            stylesheet,
        )
        self.assertIn("--accent: #fa6831;", stylesheet)
        self.assertGreaterEqual(stylesheet.count("--logo-accent: #fa6831;"), 2)
        self.assertIn("radial-gradient(circle at top left, var(--page-glow)", stylesheet)
        self.assertIn(
            '--sidebar-pattern-image: url("../media/orange-workshop-honeycomb.svg");',
            stylesheet,
        )
        self.assertIn(':root[data-palette="orange-workshop"] .panel,', stylesheet)
        self.assertIn(
            ':root[data-palette="orange-workshop"] .dashboard-activity-card {',
            stylesheet,
        )
        self.assertIn(
            ':root[data-palette="orange-workshop"] :is(',
            stylesheet,
        )
        for window_selector in (
            ".page-map .map-toolbar",
            ".page-map .map-stage",
            ".map-latest-overlay",
            ".map-scroller-overlay",
            ".traffic-toolbar",
            ".traffic-stream",
            ".traffic-legend-dialog",
            ".station-settings-group",
            ".location-picker-dialog",
            ".phg-generator-dialog",
            ".settings-progress-modal",
        ):
            with self.subTest(window_selector=window_selector):
                self.assertIn(window_selector, stylesheet)
        self.assertIn(':root[data-palette="orange-workshop"] .nav-link.active {', stylesheet)
        self.assertIn(':root[data-palette="orange-workshop"] .modem-type-panel {', stylesheet)
        self.assertIn("background: var(--panel-alt);", stylesheet)
        self.assertIn(".sidebar::before {", stylesheet)
        self.assertTrue(
            Path("app/static/media/orange-workshop-honeycomb.svg").is_file()
        )

    def test_orange_workshop_label_exists_in_every_language(self) -> None:
        for language_path in Path("app/languages").glob("*.json"):
            with self.subTest(language=language_path.stem):
                catalog = json.loads(language_path.read_text(encoding="utf-8"))
                self.assertIn("Orange Workshop", catalog)


if __name__ == "__main__":
    unittest.main()
