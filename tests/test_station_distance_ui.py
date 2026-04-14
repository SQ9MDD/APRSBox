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
        self.assertIn("i18n.distance", script_source)
        self.assertIn("root.dataset.i18nDistance", script_source)

    def test_map_script_skips_marker_rerender_when_station_payload_is_unchanged(self) -> None:
        script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        self.assertIn("let lastStationsSignature = \"\";", script_source)
        self.assertIn("function stationsSignature(stations)", script_source)
        self.assertIn("if (nextSignature === lastStationsSignature)", script_source)

    def test_map_script_renders_track_dots_for_older_positions(self) -> None:
        script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        self.assertIn("window.L.circleMarker", script_source)
        self.assertIn("points.slice(0, -1)", script_source)

    def test_map_template_renders_track_toggle_button(self) -> None:
        template_source = Path("app/templates/map.html").read_text(encoding="utf-8")
        self.assertIn('id="map-toggle-tracks"', template_source)
        self.assertIn('id="map-toggle-tracks-icon"', template_source)
        self.assertIn("data-i18n-show-tracks", template_source)
        self.assertIn("data-i18n-hide-tracks", template_source)
        self.assertIn('id="map-toggle-coverage"', template_source)
        self.assertIn('id="map-toggle-coverage-icon"', template_source)
        self.assertIn("data-i18n-show-coverage", template_source)
        self.assertIn("data-i18n-hide-coverage", template_source)
        self.assertIn('id="map-toggle-ruler"', template_source)
        self.assertIn('id="map-toggle-ruler-icon"', template_source)
        self.assertIn("data-i18n-show-ruler", template_source)
        self.assertIn("data-i18n-hide-ruler", template_source)
        self.assertIn('id="map-toggle-latest-overlay"', template_source)
        self.assertIn('id="map-toggle-latest-overlay-icon"', template_source)
        self.assertIn("data-i18n-show-latest-overlay", template_source)
        self.assertIn("data-i18n-hide-latest-overlay", template_source)
        self.assertIn('id="map-latest-overlay"', template_source)
        self.assertIn("data-i18n-distance-azimuth", template_source)
        self.assertIn("data-i18n-qsy", template_source)
        self.assertIn("data-i18n-latest-packet", template_source)
        self.assertIn("/static/js/map-latest-overlay.js", template_source)

    def test_map_script_supports_track_toggle_state(self) -> None:
        script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        self.assertIn("mapTracksVisibleStorageKey", script_source)
        self.assertIn("function resolveTracksVisible()", script_source)
        self.assertIn("function applyTracksToggleState(visible)", script_source)
        self.assertIn("if (tracksVisible)", script_source)
        self.assertIn("mapCoverageVisibleStorageKey", script_source)
        self.assertIn("function resolveCoverageVisible()", script_source)
        self.assertIn("function applyCoverageToggleState(visible)", script_source)
        self.assertIn("if (coverageVisible)", script_source)
        self.assertIn("mapRulerVisibleStorageKey", script_source)
        self.assertIn("function resolveRulerVisible()", script_source)
        self.assertIn("function applyRulerToggleState(visible)", script_source)
        self.assertIn("function buildPhgCoverageLayer(station, coverageColor)", script_source)
        self.assertIn("function buildPhgCardioidPoints(station, azimuthDeg, radiusMeters)", script_source)
        self.assertIn("window.L.polygon(", script_source)
        self.assertIn("window.L.circle([station.latitude, station.longitude]", script_source)

    def test_station_detail_map_script_renders_station_track(self) -> None:
        script_source = Path("app/static/js/station-detail-map.js").read_text(encoding="utf-8")
        self.assertIn("function renderTrack(station, stationTrack)", script_source)
        self.assertIn("window.L.polyline(", script_source)
        self.assertIn("window.L.circleMarker(", script_source)
        self.assertIn("ensureMap(station, mapConfig, stationTrack)", script_source)

    def test_map_script_initializes_ruler_with_draggable_markers(self) -> None:
        script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        self.assertIn("const rulerLayer = window.L.layerGroup();", script_source)
        self.assertIn("function initializeRuler()", script_source)
        self.assertIn("function anchorRulerToFrameIfIdle()", script_source)
        self.assertIn("function buildRulerInitialPoints()", script_source)
        self.assertIn("draggable: true", script_source)
        self.assertIn("measurementActive: false", script_source)
        self.assertIn("color: \"rgba(255, 255, 255, 0.98)\"", script_source)
        self.assertIn("color: \"#0078ff\"", script_source)
        self.assertIn("map.containerPointToLatLng(", script_source)
        self.assertIn("map-ruler-tooltip", script_source)

    def test_map_script_emits_refresh_event_for_overlay_widget(self) -> None:
        script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        self.assertIn("const mapStationsRefreshEventName = \"aprsbox:map-stations-refreshed\";", script_source)
        self.assertIn("root.dispatchEvent(new window.CustomEvent(mapStationsRefreshEventName", script_source)

    def test_map_latest_overlay_script_handles_overlay_toggle_and_qsy(self) -> None:
        script_source = Path("app/static/js/map-latest-overlay.js").read_text(encoding="utf-8")
        self.assertIn("const stationsRefreshEventName = \"aprsbox:map-stations-refreshed\";", script_source)
        self.assertIn("map-toggle-latest-overlay", script_source)
        self.assertIn("formatQsy(station)", script_source)
        self.assertIn("qsy_frequency_mhz", script_source)
        self.assertIn("map-latest-overlay-visible", script_source)

    def test_station_detail_template_exposes_initial_track_points(self) -> None:
        template_source = Path("app/templates/station_detail.html").read_text(encoding="utf-8")
        self.assertIn("data-track-points=", template_source)
        self.assertIn("station_map_config.track_points|tojson", template_source)

    def test_stations_page_script_skips_table_rerender_when_payload_is_unchanged(self) -> None:
        template_source = Path("app/templates/stations.html").read_text(encoding="utf-8")
        self.assertIn("let lastStationsSignature = \"\";", template_source)
        self.assertIn("let lastSummarySignature = \"\";", template_source)
        self.assertIn("function stationsSignature(stations)", template_source)
        self.assertIn("if (nextStationsSignature !== lastStationsSignature)", template_source)


if __name__ == "__main__":
    unittest.main()
