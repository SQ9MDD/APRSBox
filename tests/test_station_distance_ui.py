import unittest
from pathlib import Path


class StationDistanceUiTests(unittest.TestCase):
    def test_stations_template_renders_distance_column(self) -> None:
        template_source = Path("app/templates/stations.html").read_text(encoding="utf-8")
        self.assertIn('{{ t("Distance") }}', template_source)
        self.assertIn("row.distance_km", template_source)
        self.assertIn('colspan="9"', template_source)

    def test_stations_template_wraps_comment_column(self) -> None:
        template_source = Path("app/templates/stations.html").read_text(encoding="utf-8")
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        self.assertIn("stations-comment-cell", template_source)
        self.assertIn("stations-comment-text", template_source)
        self.assertIn(".stations-comment-text", stylesheet_source)
        self.assertIn("overflow-wrap: anywhere;", stylesheet_source)

    def test_map_tooltip_renders_distance_when_available(self) -> None:
        script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        self.assertIn("function formatDistance(distanceKm)", script_source)
        self.assertIn("station.distance_km", script_source)
        self.assertIn("i18n.distance", script_source)
        self.assertIn("root.dataset.i18nDistance", script_source)

    def test_map_script_skips_marker_rerender_when_station_payload_is_unchanged(self) -> None:
        script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        self.assertIn("let lastStationsSignature = \"\";", script_source)
        self.assertIn("function buildRenderSignature()", script_source)
        self.assertIn("if (!forceRender && nextSignature === lastStationsSignature)", script_source)

    def test_map_script_progressively_renders_visible_station_markers(self) -> None:
        script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")

        self.assertIn("const initialMarkerBatchSize = 20;", script_source)
        self.assertIn("const markerBatchSize = 40;", script_source)
        self.assertIn("const markerBatchTimeBudgetMs = 8;", script_source)
        self.assertIn("function cancelPendingMarkerRender()", script_source)
        self.assertIn("function prioritizeMarkerRecords(records)", script_source)
        self.assertIn("record.visiblePriority = currentBounds && currentBounds.contains([", script_source)
        self.assertIn("function renderMarkerBatch(records, startIndex, renderGeneration, maximumBatchSize)", script_source)
        self.assertIn("renderGeneration !== markerRenderGeneration", script_source)
        self.assertIn(
            "renderMarkerBatch(prioritizedRecords, 0, renderGeneration, initialMarkerBatchSize);",
            script_source,
        )
        self.assertIn(
            "renderMarkerBatch(records, nextIndex, renderGeneration, markerBatchSize);",
            script_source,
        )

        render_start = script_source.index("function renderStations(stations, mobileTracks)")
        render_end = script_source.index("async function loadStationDetails", render_start)
        render_source = script_source[render_start:render_end]
        self.assertLess(render_source.index("reconcileMarkers(stations);"), render_source.index("reconcileCoverage(stations);"))
        self.assertLess(render_source.index("reconcileCoverage(stations);"), render_source.index("reconcileTracks(mobileTracks);"))

    def test_map_script_renders_track_dots_for_older_positions(self) -> None:
        script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        self.assertIn("window.L.circleMarker", script_source)
        self.assertIn("points.slice(0, -1)", script_source)
        self.assertIn("const callsignColorPalette = Object.freeze([", script_source)
        self.assertIn("function overlayContrastColor()", script_source)
        self.assertIn("const haloPolyline = window.L.polyline(", script_source)

    def test_map_template_renders_track_toggle_button(self) -> None:
        template_source = Path("app/templates/map.html").read_text(encoding="utf-8")
        self.assertIn("data-map-tile-events-endpoint", template_source)
        self.assertIn('id="map-tile-status"', template_source)
        self.assertIn("data-i18n-tile-provider-unavailable", template_source)
        self.assertIn("data-i18n-tile-provider-recovered", template_source)
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
        self.assertIn('id="map-interface-filters"', template_source)
        self.assertLess(template_source.find('id="map-interface-filters"'), template_source.find('class="map-info-strip"'))

    def test_map_stylesheet_removes_extra_chrome_from_full_map_layout(self) -> None:
        stylesheet_source = Path("app/static/css/map.css").read_text(encoding="utf-8")
        self.assertIn(".page-map .content {", stylesheet_source)
        self.assertIn(".page-map .map-panel {", stylesheet_source)
        self.assertIn(".page-map .map-toolbar {", stylesheet_source)
        self.assertIn(".page-map .map-stage {", stylesheet_source)
        self.assertIn("padding: var(--space-4);", stylesheet_source)
        self.assertIn(".page-map .map-panel {\n    padding: 0;", stylesheet_source)
        self.assertIn("border: 0;", stylesheet_source)
        self.assertIn("gap: var(--space-4);", stylesheet_source)
        self.assertIn("box-shadow: none;", stylesheet_source)
        self.assertIn("border: 1px solid var(--border);", stylesheet_source)
        self.assertIn("border-radius: var(--radius-sm);", stylesheet_source)
        self.assertIn("border-radius: var(--radius);", stylesheet_source)
        self.assertIn("box-shadow: var(--shadow-soft);", stylesheet_source)

    def test_map_script_supports_track_toggle_state(self) -> None:
        script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        self.assertIn("mapTileEventsEndpoint", script_source)
        self.assertIn("tileerror", script_source)
        self.assertIn("tileload", script_source)
        self.assertIn("function reportTileEvent(eventType)", script_source)
        self.assertIn("tileProviderUnavailable", script_source)
        self.assertIn("tileProviderRecovered", script_source)
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

    def test_map_script_supports_interface_filtering(self) -> None:
        script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        self.assertIn("const mapInterfaceFilters = document.getElementById(\"map-interface-filters\");", script_source)
        self.assertIn("const interfaceVisibilityByKey = new Map();", script_source)
        self.assertIn("function syncInterfaceVisibility(interfaces)", script_source)
        self.assertIn("function renderInterfaceFilters(interfaces)", script_source)
        self.assertIn("function filteredMapData(stations, mobileTracks, interfaces)", script_source)
        self.assertIn("interface_id", script_source)

    def test_map_script_rebuilds_tracks_from_currently_visible_points(self) -> None:
        script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        self.assertIn("const mobileTrackMaxRenderedPoints = 60;", script_source)
        self.assertIn("function rebuildVisibleTrackPoints(points, interfacesById, visibleInterfaceIds)", script_source)
        self.assertIn("isStationInterfaceVisible(interfaceId, interfacesById, visibleInterfaceIds)", script_source)
        self.assertIn("isSameTrackPointPosition(previous, point)", script_source)
        self.assertIn("return rebuilt.slice(-mobileTrackMaxRenderedPoints);", script_source)

    def test_station_detail_map_script_renders_station_track(self) -> None:
        script_source = Path("app/static/js/station-detail-map.js").read_text(encoding="utf-8")
        self.assertIn("function renderTrack(station, stationTrack)", script_source)
        self.assertIn("window.L.polyline(", script_source)
        self.assertIn("window.L.circleMarker(", script_source)
        self.assertIn("ensureMap(station, mapConfig, stationTrack)", script_source)
        self.assertIn("const callsignColorPalette = Object.freeze([", script_source)
        self.assertIn("function overlayContrastColor()", script_source)

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

    def test_map_mask_uses_theme_tint_layer_between_tiles_and_overlays(self) -> None:
        map_script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        detail_script_source = Path("app/static/js/station-detail-map.js").read_text(encoding="utf-8")
        map_stylesheet_source = Path("app/static/css/map.css").read_text(encoding="utf-8")
        app_stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        map_template_source = Path("app/templates/map.html").read_text(encoding="utf-8")
        detail_template_source = Path("app/templates/station_detail.html").read_text(encoding="utf-8")

        self.assertIn("--map-mask-layer-opacity", map_script_source)
        self.assertIn("--map-mask-layer-opacity", detail_script_source)
        self.assertIn("function opacityFractionFromPercent(opacityPercent)", map_script_source)
        self.assertIn("function maskLayerOpacityForMaskOpacity(opacityPercent)", detail_script_source)
        self.assertIn("return Math.max(0, Math.min(100, opacityPercent)) / 100;", map_script_source)
        self.assertIn("return Math.max(0, Math.min(100, opacityPercent)) / 100;", detail_script_source)
        self.assertIn('const mapMaskPaneName = "map-mask-pane";', map_script_source)
        self.assertIn('const mapMaskPaneName = "map-mask-pane";', detail_script_source)
        self.assertIn('classList.add("map-mask-pane");', map_script_source)
        self.assertIn('classList.add("map-mask-pane");', detail_script_source)
        self.assertIn("createPane(mapMaskPaneName)", map_script_source)
        self.assertIn("createPane(mapMaskPaneName)", detail_script_source)
        self.assertIn("window.L.DomUtil.getPosition(mapPaneElement)", map_script_source)
        self.assertIn("window.L.DomUtil.getPosition(mapPaneElement)", detail_script_source)
        self.assertIn('mapMaskPane.style.left = `${-offsetX}px`;', map_script_source)
        self.assertIn('mapMaskPane.style.left = `${-offsetX}px`;', detail_script_source)
        self.assertIn('mapMaskPane.style.width = `${size.x}px`;', map_script_source)
        self.assertIn('mapMaskPane.style.width = `${size.x}px`;', detail_script_source)
        self.assertNotIn("const bleedX = size.x;", map_script_source)
        self.assertNotIn("const bleedX = size.x;", detail_script_source)
        self.assertIn(".map-canvas .leaflet-pane.map-mask-pane", map_stylesheet_source)
        self.assertIn(".station-detail-map-canvas .leaflet-pane.map-mask-pane", app_stylesheet_source)
        self.assertIn(".map-canvas .map-mask-layer", map_stylesheet_source)
        self.assertIn(".station-detail-map-canvas .map-mask-layer", app_stylesheet_source)
        self.assertIn("background: var(--map-mask-layer-color);", map_stylesheet_source)
        self.assertIn("background: var(--map-mask-layer-color);", app_stylesheet_source)
        self.assertIn("opacity: var(--map-mask-layer-opacity);", map_stylesheet_source)
        self.assertIn("opacity: var(--map-mask-layer-opacity);", app_stylesheet_source)
        self.assertNotIn("--map-tile-brightness", map_script_source)
        self.assertNotIn("--map-tile-brightness", detail_script_source)
        self.assertNotIn("tileBrightnessForMaskOpacity", map_script_source)
        self.assertNotIn("tileBrightnessForMaskOpacity", detail_script_source)
        self.assertNotIn('id="map-mask"', map_template_source)
        self.assertNotIn('id="station-detail-map-mask"', detail_template_source)
        self.assertNotIn("--map-pane-opacity", map_stylesheet_source)
        self.assertNotIn("--map-pane-opacity", app_stylesheet_source)
        self.assertNotIn(".map-canvas .leaflet-overlay-pane", map_stylesheet_source)
        self.assertNotIn(".station-detail-map-canvas .leaflet-overlay-pane", app_stylesheet_source)
        self.assertNotIn("filter: brightness(var(--map-tile-brightness));", map_stylesheet_source)
        self.assertNotIn("filter: brightness(var(--map-tile-brightness));", app_stylesheet_source)

    def test_map_uses_global_coverage_fill_opacity_with_five_percent_default(self) -> None:
        map_script_source = Path("app/static/js/map.js").read_text(encoding="utf-8")
        map_template_source = Path("app/templates/map.html").read_text(encoding="utf-8")

        self.assertIn('data-coverage-fill-opacity="{{ map_config.coverage_fill_opacity }}"', map_template_source)
        self.assertIn('root.dataset.coverageFillOpacity || ""', map_script_source)
        self.assertIn("normalizeCoverageOpacityPercent(configuredOpacity, 5)", map_script_source)
        self.assertIn("let coverageFillOpacity = 0.05;", map_script_source)
        self.assertNotIn("aprsbox-map-coverage-fill-opacity", map_script_source)

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
        self.assertIn('field.html is defined', template_source)

    def test_station_detail_script_renders_linkified_comment_html(self) -> None:
        script_source = Path("app/static/js/station-detail-map.js").read_text(encoding="utf-8")
        self.assertIn("field.html || escapeHtml(field.value)", script_source)
        stylesheet_source = Path("app/static/css/style.css").read_text(encoding="utf-8")
        self.assertIn(".station-detail-comment-link", stylesheet_source)

    def test_stations_page_script_skips_table_rerender_when_payload_is_unchanged(self) -> None:
        template_source = Path("app/templates/stations.html").read_text(encoding="utf-8")
        self.assertIn("let lastStationsSignature = \"\";", template_source)
        self.assertIn("let lastSummarySignature = \"\";", template_source)
        self.assertIn("function stationsSignature(stations)", template_source)
        self.assertIn("if (nextStationsSignature !== lastStationsSignature)", template_source)

    def test_stations_page_supports_metric_card_filtering(self) -> None:
        template_source = Path("app/templates/stations.html").read_text(encoding="utf-8")
        self.assertIn('data-station-filter="all"', template_source)
        self.assertIn('data-station-filter="direct"', template_source)
        self.assertIn('data-station-filter="stationary"', template_source)
        self.assertIn('data-station-filter="mobile"', template_source)
        self.assertIn('data-station-filter="object"', template_source)
        self.assertIn('data-station-filter="weather"', template_source)
        self.assertIn('id="summary-weather"', template_source)
        self.assertIn('id="summary-direct"', template_source)
        self.assertIn("function filteredStations(stations, filter)", template_source)
        self.assertIn("function isDirectlyHeardStation(station)", template_source)
        self.assertIn("function isWeatherStation(station)", template_source)
        self.assertIn("function updateDerivedSummaries(stations)", template_source)
        self.assertIn('filter === "stationary"', template_source)
        self.assertIn("!isWeatherStation(station)", template_source)
        self.assertIn("normalizeEntityClass(station)", template_source)
        self.assertIn("updateFilterCardState()", template_source)
        self.assertIn("classList.toggle(\"is-active\", active)", template_source)

    def test_stations_page_supports_table_sorting(self) -> None:
        template_source = Path("app/templates/stations.html").read_text(encoding="utf-8")
        self.assertIn('data-stations-sort="callsign"', template_source)
        self.assertIn('data-stations-sort="last_heard"', template_source)
        self.assertIn('data-stations-sort="distance"', template_source)
        self.assertIn('let activeStationsSortKey = "last_heard";', template_source)
        self.assertIn('let activeStationsSortDirection = "desc";', template_source)
        self.assertIn("function sortStations(stations, sortKey, sortDirection)", template_source)
        self.assertIn("function setStationsSort(sortKey)", template_source)
        self.assertIn("function applyStationsView()", template_source)
        self.assertIn("updateSortState()", template_source)
        self.assertIn('setStationsSort(button.dataset.stationsSort || "last_heard")', template_source)


if __name__ == "__main__":
    unittest.main()
