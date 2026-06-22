import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import init_db, set_app_setting
from app.i18n import LANGUAGES_DIR, get_app_language, get_supported_languages, get_translator, normalize_language


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
        self.assertEqual(normalize_language("de"), "de")
        self.assertEqual(normalize_language(None), "en")
        self.assertEqual(normalize_language("PL"), "pl")
        self.assertEqual(normalize_language("tlh"), "tlh")

    def test_translator_uses_catalog_and_falls_back_to_source_text(self) -> None:
        translator = get_translator("pl")
        self.assertEqual(translator("Settings"), "Ustawienia")
        self.assertEqual(translator("Direct Only"), "Tylko direct")
        self.assertEqual(
            translator("Required. Use up to 43 printable ASCII characters if you want a plain object report without extra data extensions."),
            "Pole wymagane. Użyj maksymalnie 43 drukowalnych znaków ASCII, jeśli chcesz zwykły raport obiektu bez dodatkowych rozszerzeń danych.",
        )
        self.assertEqual(translator("Unmapped text"), "Unmapped text")

    def test_get_app_language_reads_saved_setting(self) -> None:
        with temporary_database():
            init_db()
            set_app_setting("app_language", "pl")

            self.assertEqual(get_app_language(), "pl")

    def test_supported_languages_include_registered_gui_options(self) -> None:
        self.assertEqual(
            get_supported_languages(),
            [
                {"code": "en", "label": "English"},
                {"code": "de", "label": "Deutsch"},
                {"code": "pl", "label": "Polski"},
                {"code": "es", "label": "Español"},
                {"code": "tlh", "label": "tlhIngan Hol"},
            ],
        )

    def test_german_translator_uses_catalog_and_english_fallback(self) -> None:
        with patch(
            "app.i18n._load_catalog",
            side_effect=lambda language: {
                "en": {"Settings": "Settings", "Fallback only": "Fallback only"},
                "de": {"Settings": "Einstellungen"},
            }[language],
        ):
            translator = get_translator("de")
            self.assertEqual(translator("Settings"), "Einstellungen")
            self.assertEqual(translator("Fallback only"), "Fallback only")

    def test_klingon_catalog_matches_english_keys(self) -> None:
        english_catalog = json.loads((LANGUAGES_DIR / "en.json").read_text(encoding="utf-8"))
        klingon_catalog = json.loads((LANGUAGES_DIR / "tlh.json").read_text(encoding="utf-8"))
        self.assertEqual(set(klingon_catalog), set(english_catalog))

    def test_german_catalog_matches_english_keys(self) -> None:
        english_catalog = json.loads((LANGUAGES_DIR / "en.json").read_text(encoding="utf-8"))
        german_catalog = json.loads((LANGUAGES_DIR / "de.json").read_text(encoding="utf-8"))
        self.assertEqual(set(german_catalog), set(english_catalog))

    def test_spanish_catalog_matches_english_keys(self) -> None:
        english_catalog = json.loads((LANGUAGES_DIR / "en.json").read_text(encoding="utf-8"))
        spanish_catalog = json.loads((LANGUAGES_DIR / "es.json").read_text(encoding="utf-8"))
        self.assertEqual(set(spanish_catalog), set(english_catalog))


if __name__ == "__main__":
    unittest.main()
