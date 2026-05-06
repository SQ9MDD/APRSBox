import unittest
from pathlib import Path


class LogsTemplateTests(unittest.TestCase):
    def test_logs_template_contains_min_level_filter_form(self) -> None:
        template_source = Path("app/templates/logs.html").read_text(encoding="utf-8")
        self.assertIn('action="{{ request.scope.root_path }}/logs"', template_source)
        self.assertIn('name="min_level"', template_source)
        self.assertIn('{{ t("Minimum visible log level") }}', template_source)
        self.assertIn('{{ t("Apply filter") }}', template_source)


if __name__ == "__main__":
    unittest.main()
