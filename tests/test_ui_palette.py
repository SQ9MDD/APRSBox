import json
import unittest
from pathlib import Path

from app.ui_palette import (
    get_ui_palette_label,
    get_ui_palette_options,
    is_supported_ui_palette,
    normalize_ui_palette,
)


class UiPaletteTests(unittest.TestCase):
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
