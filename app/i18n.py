from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Callable

from app.db import get_app_setting


DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES: tuple[dict[str, str], ...] = (
    {"code": "en", "label": "English"},
    {"code": "de", "label": "Deutsch"},
    {"code": "pl", "label": "Polski"},
    {"code": "es", "label": "Español"},
    {"code": "tlh", "label": "tlhIngan Hol"},
)
SUPPORTED_LANGUAGE_CODES = frozenset(item["code"] for item in SUPPORTED_LANGUAGES)
LANGUAGES_DIR = Path(__file__).resolve().parent / "languages"


def normalize_language(code: str | None) -> str:
    value = str(code or "").strip().lower()
    if value in SUPPORTED_LANGUAGE_CODES:
        return value
    return DEFAULT_LANGUAGE


def get_supported_languages() -> list[dict[str, str]]:
    return [dict(item) for item in SUPPORTED_LANGUAGES]


def get_app_language() -> str:
    try:
        return normalize_language(get_app_setting("app_language"))
    except Exception:
        # Allow templates and tests to render safely before DB init or when runtime storage is unavailable.
        return DEFAULT_LANGUAGE


@lru_cache(maxsize=None)
def _load_catalog(language: str) -> dict[str, str]:
    path = LANGUAGES_DIR / f"{normalize_language(language)}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get_translator(language: str) -> Callable[[object], str]:
    resolved_language = normalize_language(language)
    english_catalog = _load_catalog(DEFAULT_LANGUAGE)
    language_catalog = _load_catalog(resolved_language)

    def translate(message: object) -> str:
        text = str(message or "")
        if not text:
            return ""
        return language_catalog.get(text, english_catalog.get(text, text))

    return translate


def get_format_translator(language: str) -> Callable[[object, dict[str, object] | None], str]:
    translate = get_translator(language)

    def translate_format(message: object, params: dict[str, object] | None = None) -> str:
        template = translate(message)
        if not params:
            return template
        try:
            return template.format(**params)
        except (KeyError, ValueError):
            return template

    return translate_format
