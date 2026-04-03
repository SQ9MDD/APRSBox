import contextlib
import os
import tempfile
import unittest
from pathlib import Path

from app.db import init_db, set_app_setting
from app.i18n import get_app_language, get_supported_languages, get_translator, normalize_language


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        try:
            yield database_path
        finally:
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


class I18nTests(unittest.TestCase):
    def test_normalize_language_uses_default_for_unsupported_values(self) -> None:
        self.assertEqual(normalize_language("de"), "en")
        self.assertEqual(normalize_language(None), "en")
        self.assertEqual(normalize_language("PL"), "pl")

    def test_translator_uses_catalog_and_falls_back_to_source_text(self) -> None:
        translator = get_translator("pl")
        self.assertEqual(translator("Settings"), "Ustawienia")
        self.assertEqual(translator("Direct Only"), "Tylko direct")
        self.assertEqual(translator("Unmapped text"), "Unmapped text")

    def test_get_app_language_reads_saved_setting(self) -> None:
        with temporary_database():
            init_db()
            set_app_setting("app_language", "pl")

            self.assertEqual(get_app_language(), "pl")

    def test_supported_languages_include_english_and_polish(self) -> None:
        self.assertEqual(get_supported_languages(), [{"code": "en", "label": "English"}, {"code": "pl", "label": "Polski"}])


if __name__ == "__main__":
    unittest.main()
