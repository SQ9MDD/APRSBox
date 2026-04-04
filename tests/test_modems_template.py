import unittest
from pathlib import Path


class ModemsTemplateTests(unittest.TestCase):
    def test_modems_status_column_uses_icon_indicator_instead_of_badge(self) -> None:
        template_source = Path("app/templates/section.html").read_text(encoding="utf-8")
        self.assertIn("tnc-status-icon", template_source)
        self.assertIn("row.modem_runtime_status", template_source)
        self.assertIn("row.modem_runtime_icon", template_source)


if __name__ == "__main__":
    unittest.main()
