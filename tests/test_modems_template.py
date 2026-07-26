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


if __name__ == "__main__":
    unittest.main()
