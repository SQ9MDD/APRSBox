import unittest
from pathlib import Path


class StationDistanceUiTests(unittest.TestCase):
    def test_stations_template_renders_distance_column(self) -> None:
        template_source = Path("app/templates/stations.html").read_text(encoding="utf-8")
        self.assertIn('{{ t("Distance") }}', template_source)
        self.assertIn("row.distance_km", template_source)
        self.assertIn('colspan="9"', template_source)

    def test_map_tooltip_renders_distance_when_available(self) -> None:
        script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        self.assertIn("function formatDistance(distanceKm)", script_source)
        self.assertIn("station.distance_km", script_source)
        self.assertIn("Odległość:", script_source)

    def test_map_script_skips_marker_rerender_when_station_payload_is_unchanged(self) -> None:
        script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        self.assertIn("let lastStationsSignature = \"\";", script_source)
        self.assertIn("function stationsSignature(stations)", script_source)
        self.assertIn("if (nextSignature === lastStationsSignature)", script_source)

    def test_stations_page_script_skips_table_rerender_when_payload_is_unchanged(self) -> None:
        template_source = Path("app/templates/stations.html").read_text(encoding="utf-8")
        self.assertIn("let lastStationsSignature = \"\";", template_source)
        self.assertIn("let lastSummarySignature = \"\";", template_source)
        self.assertIn("function stationsSignature(stations)", template_source)
        self.assertIn("if (nextStationsSignature !== lastStationsSignature)", template_source)


if __name__ == "__main__":
    unittest.main()
