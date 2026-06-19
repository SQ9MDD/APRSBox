import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.routers import pages


class HelpMarkdownTests(unittest.TestCase):
    def test_reads_language_specific_help_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            help_root = Path(temp_dir) / "help"
            application_dir = help_root / "application"
            application_dir.mkdir(parents=True)
            (application_dir / "objects.pl.md").write_text("# PL", encoding="utf-8")
            (application_dir / "objects.en.md").write_text("# EN", encoding="utf-8")
            with patch.object(pages, "_HELP_ROOT_DIR", help_root):
                resolved = pages._read_help_markdown(page="application/objects", language="pl")
            self.assertEqual(resolved, ("application/objects.pl.md", "# PL"))

    def test_help_falls_back_to_english(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            help_root = Path(temp_dir) / "help"
            application_dir = help_root / "application"
            application_dir.mkdir(parents=True)
            (application_dir / "objects.en.md").write_text("# EN", encoding="utf-8")
            with patch.object(pages, "_HELP_ROOT_DIR", help_root):
                resolved = pages._read_help_markdown(page="application/objects", language="es")
            self.assertEqual(resolved, ("application/objects.en.md", "# EN"))

    def test_reads_relative_help_link_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            help_root = Path(temp_dir) / "help"
            target_dir = help_root / "protocoll"
            target_dir.mkdir(parents=True)
            (target_dir / "repeaters_qsy.pl.md").write_text("# Repeaters", encoding="utf-8")
            with patch.object(pages, "_HELP_ROOT_DIR", help_root):
                resolved = pages._read_help_markdown(path="protocoll/repeaters_qsy.pl.md")
            self.assertEqual(resolved, ("protocoll/repeaters_qsy.pl.md", "# Repeaters"))

    def test_rejects_path_traversal_outside_help_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            help_root = Path(temp_dir) / "help"
            help_root.mkdir(parents=True)
            with patch.object(pages, "_HELP_ROOT_DIR", help_root):
                self.assertIsNone(pages._read_help_markdown(path="../secrets.md"))
                self.assertIsNone(pages._read_help_markdown(page="../application/objects", language="en"))


if __name__ == "__main__":
    unittest.main()
