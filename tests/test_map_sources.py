import contextlib
import os
import tempfile
import unittest
from pathlib import Path

from app.db import init_db
from app.services.map_service import (
    delete_map_source,
    list_map_sources,
    resolve_active_tile_layer,
    save_map_source,
    set_default_map_source,
)


@contextlib.contextmanager
def temporary_database() -> Path:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "aprsbox-test.db"
        previous = os.environ.get("APRSBOX_DB_PATH")
        os.environ["APRSBOX_DB_PATH"] = str(database_path)
        try:
            init_db()
            yield database_path
        finally:
            if previous is None:
                os.environ.pop("APRSBOX_DB_PATH", None)
            else:
                os.environ["APRSBOX_DB_PATH"] = previous


def valid_source_payload(
    *,
    name: str = "Custom tiles",
    url_template: str = "https://tiles.example/{z}/{x}/{y}.png",
    attribution: str = "Tiles",
    min_zoom: str = "0",
    max_zoom: str = "19",
    subdomains: str = "",
    api_key: str = "",
    enabled: str | None = "1",
    is_default: str | None = None,
    sort_order: str = "10",
    notes: str = "",
) -> dict[str, str | None]:
    return {
        "name": name,
        "url_template": url_template,
        "attribution": attribution,
        "min_zoom": min_zoom,
        "max_zoom": max_zoom,
        "subdomains": subdomains,
        "api_key": api_key,
        "enabled": enabled,
        "is_default": is_default,
        "sort_order": sort_order,
        "notes": notes,
    }


class MapSourcesTests(unittest.TestCase):
    def test_init_db_seeds_single_default_map_source(self) -> None:
        with temporary_database():
            sources = list_map_sources()
            self.assertEqual(len(sources), 1)
            self.assertTrue(sources[0]["enabled"])
            self.assertTrue(sources[0]["is_default"])
            self.assertIn("{z}", sources[0]["url_template"])
            self.assertIn("{x}", sources[0]["url_template"])
            self.assertIn("{y}", sources[0]["url_template"])

    def test_save_map_source_validates_required_fields(self) -> None:
        with temporary_database():
            with self.assertRaisesRegex(ValueError, "Map source name is required."):
                save_map_source(valid_source_payload(name=""))
            with self.assertRaisesRegex(ValueError, "Map URL template is required."):
                save_map_source(valid_source_payload(url_template=""))
            with self.assertRaisesRegex(ValueError, "Map URL template must include"):
                save_map_source(valid_source_payload(url_template="https://tiles.example/{z}/{x}.png"))
            with self.assertRaisesRegex(ValueError, "Disabled map source cannot be default."):
                save_map_source(valid_source_payload(enabled=None, is_default="1"))

    def test_delete_blocks_only_and_default_source(self) -> None:
        with temporary_database():
            first = list_map_sources()[0]
            with self.assertRaisesRegex(ValueError, "Cannot delete the only map source."):
                delete_map_source(int(first["id"]))

            second_id = save_map_source(valid_source_payload(name="Second source"))
            set_default_map_source(second_id)
            with self.assertRaisesRegex(ValueError, "Select another default map source"):
                delete_map_source(second_id)

    def test_set_default_switches_between_sources(self) -> None:
        with temporary_database():
            first = list_map_sources()[0]
            second_id = save_map_source(valid_source_payload(name="Second source"))
            set_default_map_source(second_id)
            sources = list_map_sources()
            first_row = next(item for item in sources if int(item["id"]) == int(first["id"]))
            second_row = next(item for item in sources if int(item["id"]) == int(second_id))
            self.assertFalse(first_row["is_default"])
            self.assertTrue(second_row["is_default"])

    def test_runtime_tile_config_applies_api_key_placeholder(self) -> None:
        with temporary_database():
            save_map_source(
                valid_source_payload(
                    name="API source",
                    url_template="https://tiles.example/{z}/{x}/{y}.png?key={apiKey}",
                    api_key="A B",
                    is_default="1",
                )
            )
            tile_layer = resolve_active_tile_layer()
            self.assertEqual(tile_layer["tile_source_name"], "API source")
            self.assertIn("key=A%20B", tile_layer["tile_url"])

    def test_runtime_tile_url_is_deterministic_without_cache_busting(self) -> None:
        with temporary_database():
            save_map_source(
                valid_source_payload(
                    name="Deterministic source",
                    url_template="https://tiles.example/{z}/{x}/{y}.png?apikey={apiKey}",
                    api_key="CONST_KEY",
                    is_default="1",
                )
            )
            first = resolve_active_tile_layer()["tile_url"]
            second = resolve_active_tile_layer()["tile_url"]
            self.assertEqual(first, second)
            self.assertEqual(first, "https://tiles.example/{z}/{x}/{y}.png?apikey=CONST_KEY")
            self.assertNotIn("_=", first)
            self.assertNotIn("timestamp=", first)

    def test_validation_accepts_url_encoded_tile_tokens(self) -> None:
        with temporary_database():
            source_id = save_map_source(
                valid_source_payload(
                    name="Encoded tokens",
                    url_template="https://tiles.example/%7BZ%7D/%7BX%7D/%7BY%7D.png",
                )
            )
            self.assertGreater(source_id, 0)


if __name__ == "__main__":
    unittest.main()
