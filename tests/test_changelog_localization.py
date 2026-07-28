import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.routers import pages


class ChangelogLocalizationTests(unittest.TestCase):
    def test_all_localized_changelogs_include_current_version(self) -> None:
        current_version = Path("VERSION").read_text(encoding="utf-8").strip()
        for language, changelog_path in pages._CHANGELOG_FILES_BY_LANGUAGE.items():
            with self.subTest(language=language):
                changelog = changelog_path.read_text(encoding="utf-8")
                self.assertIn(f"## {current_version} ", changelog)

    def _changelog_paths(self, root: Path) -> dict[str, Path]:
        return {
            "pl": root / "changelog.md",
            "en": root / "changelog.en.md",
            "es": root / "changelog.es.md",
        }

    def test_reads_language_specific_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._changelog_paths(root)
            paths["pl"].write_text("PL", encoding="utf-8")
            paths["en"].write_text("EN", encoding="utf-8")
            paths["es"].write_text("ES", encoding="utf-8")
            with patch.dict(pages._CHANGELOG_FILES_BY_LANGUAGE, paths, clear=True):
                self.assertEqual(pages._read_changelog_markdown("pl"), "PL")
                self.assertEqual(pages._read_changelog_markdown("en"), "EN")
                self.assertEqual(pages._read_changelog_markdown("es"), "ES")

    def test_uses_current_app_language_when_argument_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._changelog_paths(root)
            paths["pl"].write_text("PL", encoding="utf-8")
            paths["es"].write_text("ES", encoding="utf-8")
            with patch.dict(pages._CHANGELOG_FILES_BY_LANGUAGE, paths, clear=True):
                with patch.object(pages, "get_app_language", return_value="es"):
                    self.assertEqual(pages._read_changelog_markdown(), "ES")

    def test_falls_back_to_polish_when_selected_language_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._changelog_paths(root)
            paths["pl"].write_text("PL", encoding="utf-8")
            with patch.dict(pages._CHANGELOG_FILES_BY_LANGUAGE, paths, clear=True):
                self.assertEqual(pages._read_changelog_markdown("es"), "PL")

    def test_falls_back_to_english_when_polish_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._changelog_paths(root)
            paths["en"].write_text("EN", encoding="utf-8")
            with patch.dict(pages._CHANGELOG_FILES_BY_LANGUAGE, paths, clear=True):
                self.assertEqual(pages._read_changelog_markdown("pl"), "EN")


if __name__ == "__main__":
    unittest.main()
