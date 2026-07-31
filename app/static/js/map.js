(function () {
    const root = document.getElementById("map-root");
    if (!root || typeof window.L === "undefined") {
        return;
    }

    const defaultView = {
        latitude: Number.parseFloat(root.dataset.stationLatitude || ""),
        longitude: Number.parseFloat(root.dataset.stationLongitude || ""),
        zoom: Number.parseInt(root.dataset.defaultZoom || "", 10),
    };
    const stationsEndpoint = root.dataset.stationsEndpoint || "/api/map/stations";
    const stationDetailsEndpoint = root.dataset.stationDetailsEndpoint || "";
    const mobileTracksEndpoint = root.dataset.mobileTracksEndpoint || "";
    const mapTileEventsEndpoint = root.dataset.mapTileEventsEndpoint || "";
    const tileUrl = root.dataset.tileUrl || "";
    const tileAttribution = root.dataset.tileAttribution || "";
    const tileSourceName = root.dataset.tileSourceName || "";
    const tileMinZoom = Number.parseInt(root.dataset.tileMinZoom || "", 10);
    const tileMaxZoom = Number.parseInt(root.dataset.tileMaxZoom || "", 10);
    const tileSubdomains = String(root.dataset.tileSubdomains || "")
        .split(/[,\s]+/)
        .map((token) => token.trim())
        .filter((token) => token.length > 0);

    const centerOutput = document.getElementById("map-center");
    const zoomOutput = document.getElementById("map-zoom");
    const tileSourceOutput = document.getElementById("map-tile-source");
    const tileStatusOutput = document.getElementById("map-tile-status");
    const mapStage = document.getElementById("map-stage");
    const mapCanvas = document.getElementById("map-canvas");
    const mapInterfaceFilters = document.getElementById("map-interface-filters");
    const resetButton = document.getElementById("map-reset-view");
    const toggleTracksButton = document.getElementById("map-toggle-tracks");
    const toggleTracksIcon = document.getElementById("map-toggle-tracks-icon");
    const toggleCoverageButton = document.getElementById("map-toggle-coverage");
    const toggleCoverageIcon = document.getElementById("map-toggle-coverage-icon");
    const toggleAlarmAreasButton = document.getElementById("map-toggle-alarm-areas");
    const toggleAlarmAreasIcon = document.getElementById("map-toggle-alarm-areas-icon");
    const alertsOverlay = document.getElementById("map-alerts-overlay");
    const alertsOverlayList = document.getElementById("map-alerts-overlay-list");
    const alertsOverlayClose = document.getElementById("map-alerts-overlay-close");
    const toggleRulerButton = document.getElementById("map-toggle-ruler");
    const toggleRulerIcon = document.getElementById("map-toggle-ruler-icon");
    const maskOpacitySelect = document.getElementById("map-mask-opacity");
    const coverageFillOpacitySelect = document.getElementById("map-coverage-fill-opacity");
    const coverageOutlineOpacitySelect = document.getElementById("map-coverage-outline-opacity");
    const staticRoot = root.dataset.staticRoot || "/static/";
    const aprsSymbolIconFallback = window.APRSBOX_APRS_SYMBOL_ICON_FALLBACK || "icons/verG/x.gif";
    const rootPath = root.dataset.rootPath || "";
    const locale = document.documentElement.lang || undefined;
    const relativeTimeFormatter = (typeof Intl !== "undefined" && typeof Intl.RelativeTimeFormat === "function")
        ? new Intl.RelativeTimeFormat(locale, { numeric: "auto" })
        : null;
    const i18n = Object.freeze({
        aprsClient: root.dataset.i18nAprsClient || "APRS client",
        lastActivity: root.dataset.i18nLastActivity || "Last activity",
        age: root.dataset.i18nAge || "Age",
        source: root.dataset.i18nSource || "Source",
        path: root.dataset.i18nPath || "Path",
        destination: root.dataset.i18nDestination || "Destination",
        distance: root.dataset.i18nDistance || "Distance",
        speed: root.dataset.i18nSpeed || "Speed",
        course: root.dataset.i18nCourse || "Course",
        altitude: root.dataset.i18nAltitude || "Altitude",
        packetType: root.dataset.i18nPacketType || "Packet type",
        comment: root.dataset.i18nComment || "Comment",
        showTracks: root.dataset.i18nShowTracks || "Show tracks",
        hideTracks: root.dataset.i18nHideTracks || "Hide tracks",
        showCoverage: root.dataset.i18nShowCoverage || "Show coverage",
        hideCoverage: root.dataset.i18nHideCoverage || "Hide coverage",
        showAlarmList: root.dataset.i18nShowAlarmList || "Show alarm list",
        hideAlarmList: root.dataset.i18nHideAlarmList || "Hide alarm list",
        activeAlarms: root.dataset.i18nActiveAlarms || "Active alarms",
        noActiveMapAlarms: root.dataset.i18nNoActiveMapAlarms || "No active alarms with map areas.",
        visibleOnMap: root.dataset.i18nVisibleOnMap || "Visible on map",
        noMapArea: root.dataset.i18nNoMapArea || "No map area available",
        areaCount: root.dataset.i18nAreaCount || "Area count",
        expiresAt: root.dataset.i18nExpiresAt || "Expires at",
        details: root.dataset.i18nDetails || "Details",
        severityLevel: root.dataset.i18nSeverityLevel || "Severity level",
        showRuler: root.dataset.i18nShowRuler || "Show ruler",
        hideRuler: root.dataset.i18nHideRuler || "Hide ruler",
        tileProviderUnavailable: root.dataset.i18nTileProviderUnavailable || "Tile provider unavailable",
        tileProviderRecovered: root.dataset.i18nTileProviderRecovered || "Tile provider recovered",
        show: root.dataset.i18nShow || "Show",
        hide: root.dataset.i18nHide || "Hide",
    });
    const coverageLayerGroup = window.L.layerGroup();
    const trackLayerGroup = window.L.layerGroup();
    const markerLayerGroup = window.L.layerGroup();
    const rulerLayer = window.L.layerGroup();
    let alertAreaLayer = null;
    const mapViewStorageKey = "aprsbox-map-view";
    const mapTracksVisibleStorageKey = "aprsbox-map-tracks-visible";
    const mapCoverageVisibleStorageKey = "aprsbox-map-coverage-visible";
    const mapHiddenAlertIdsStorageKey = "aprsbox-map-hidden-alert-ids";
    const mapRulerVisibleStorageKey = "aprsbox-map-ruler-visible";
    const mapCoverageOutlineOpacityStorageKey = "aprsbox-map-coverage-outline-opacity";
    const mapStationsRefreshEventName = "aprsbox:map-stations-refreshed";
    const mapViewRefreshEventName = "aprsbox:map-view-refreshed";
    const mobileTrackMaxRenderedPoints = 60;
    const maximumVisibleAlertCards = 4;
    const isModernAprsSymbolSet = String(document.documentElement.getAttribute("data-aprs-symbol-set") || "").trim().toLowerCase() === "modern";
    const aprsIconSize = isModernAprsSymbolSet ? [32, 32] : [20, 20];
    const aprsIconAnchor = isModernAprsSymbolSet ? [16, 16] : [10, 10];
    let refreshTimer = null;
    let lastStationsSignature = "";
    let tracksVisible = true;
    let coverageVisible = true;
    let alertsOverlayOpen = false;
    let rulerVisible = true;
    let coverageFillOpacity = 0.05;
    let coverageOutlineOpacity = 1;
    let latestStations = [];
    let latestMobileTracks = [];
    let latestInterfaces = [];
    let latestStationRevision = "";
    let latestStationDetailsRevision = "";
    let latestTrackRevision = "";
    let detailsLoadingRevision = "";
    let tracksLoadingRevision = "";
    let lastAlertAreasSignature = "";
    let lastAlertPanelSignature = "";
    let latestAlertAreaCollection = { type: "FeatureCollection", features: [] };
    let latestMapAlerts = [];
    let hiddenAlertIds = resolveHiddenAlertIds();
    const interfaceVisibilityByKey = new Map();
    const markerLayersByKey = new Map();
    const coverageLayersByKey = new Map();
    const trackLayersByKey = new Map();
    let rulerState = null;
    let tileErrorActive = false;
    let tileErrorCount = 0;
    let tileLoadCount = 0;
    let consecutiveTileErrors = 0;
    let lastTileErrorUrl = "";
    let tileStatusClearTimer = null;
    let lastTileErrorReportedAt = 0;
    let lastTileRecoveryReportedAt = 0;
    const tileEventReportIntervalMs = 120000;
    const visibleIconPath = `${staticRoot}icons/eye.svg`;
    const hiddenIconPath = `${staticRoot}icons/eye-off.svg`;

    function currentThemeName() {
        return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    }

    function maskOpacityStorageKey() {
        return `aprsbox-map-mask-opacity-${currentThemeName()}`;
    }

    function opacityFractionFromPercent(opacityPercent) {
        return Math.max(0, Math.min(100, opacityPercent)) / 100;
    }

    function normalizeOpacityPercent(opacityPercent, fallbackPercent) {
        const normalizedFallback = Number.isInteger(fallbackPercent) && fallbackPercent >= 0 && fallbackPercent <= 100
            ? fallbackPercent - (fallbackPercent % 10)
            : 100;
        if (Number.isInteger(opacityPercent) && opacityPercent >= 0 && opacityPercent <= 100) {
            return opacityPercent - (opacityPercent % 10);
        }
        return normalizedFallback;
    }

    function normalizeCoverageOpacityPercent(opacityPercent, fallbackPercent) {
        const normalizedFallback = Number.isInteger(fallbackPercent) && fallbackPercent >= 0 && fallbackPercent <= 20
            ? fallbackPercent
            : 20;
        if (Number.isInteger(opacityPercent) && opacityPercent >= 0 && opacityPercent <= 20) {
            return opacityPercent;
        }
        return normalizedFallback;
    }

    function normalizeRevision(value) {
        if (value === null || value === undefined) {
            return "";
        }
        return String(value);
    }

    function normalizeAlertAreaFeatureCollection(value) {
        if (!value || value.type !== "FeatureCollection" || !Array.isArray(value.features)) {
            return { type: "FeatureCollection", features: [], alerts: [] };
        }
        return {
            type: "FeatureCollection",
            features: value.features.filter((feature) => (
                feature
                && feature.type === "Feature"
                && feature.geometry
                && typeof feature.geometry === "object"
            )),
            alerts: Array.isArray(value.alerts)
                ? value.alerts.filter((alert) => alert && Number.isInteger(Number(alert.id)))
                : [],
        };
    }

    function resolveHiddenAlertIds() {
        try {
            const parsed = JSON.parse(window.localStorage.getItem(mapHiddenAlertIdsStorageKey) || "[]");
            if (!Array.isArray(parsed)) {
                return new Set();
            }
            return new Set(
                parsed
                    .map((value) => Number.parseInt(String(value), 10))
                    .filter((value) => Number.isInteger(value) && value > 0)
            );
        } catch (_error) {
            return new Set();
        }
    }

    function persistHiddenAlertIds() {
        window.localStorage.setItem(
            mapHiddenAlertIdsStorageKey,
            JSON.stringify(Array.from(hiddenAlertIds).sort((left, right) => left - right))
        );
    }

    function alertSeverityColor(severityLevel) {
        const normalizedLevel = Number.parseInt(String(severityLevel ?? ""), 10);
        if (normalizedLevel === 1) {
            return "yellow";
        }
        if (normalizedLevel === 2) {
            return "orange";
        }
        if (normalizedLevel === 3) {
            return "red";
        }
        return "gray";
    }

    function visibleAlertAreaFeatureCollection() {
        const features = latestAlertAreaCollection.features.flatMap((feature) => {
            const properties = feature?.properties && typeof feature.properties === "object"
                ? feature.properties
                : {};
            const hasContributorMetadata = Array.isArray(properties.aprsbox_alerts);
            const contributors = hasContributorMetadata
                ? properties.aprsbox_alerts.filter((contributor) => {
                    const alertId = Number.parseInt(String(contributor?.id ?? ""), 10);
                    return Number.isInteger(alertId) && !hiddenAlertIds.has(alertId);
                })
                : [];
            if (!hasContributorMetadata) {
                return [feature];
            }
            if (contributors.length === 0) {
                return [];
            }
            const strongestSeverity = contributors.reduce((strongest, contributor) => {
                const severity = Number.parseInt(String(contributor?.severity_level ?? ""), 10);
                return [1, 2, 3].includes(severity) ? Math.max(strongest, severity) : strongest;
            }, 0);
            return [{
                ...feature,
                properties: {
                    ...properties,
                    aprsbox_alerts: contributors,
                    aprsbox_severity_level: strongestSeverity || null,
                    aprsbox_alert_color: alertSeverityColor(strongestSeverity),
                },
            }];
        });
        return { type: "FeatureCollection", features };
    }

    function renderVisibleAlertAreas() {
        if (!alertAreaLayer) {
            return;
        }
        const featureCollection = visibleAlertAreaFeatureCollection();
        let nextSignature = "";
        try {
            nextSignature = JSON.stringify(featureCollection);
        } catch (_error) {
            nextSignature = '{"type":"FeatureCollection","features":[]}';
            featureCollection.features = [];
        }
        if (nextSignature === lastAlertAreasSignature) {
            return;
        }
        lastAlertAreasSignature = nextSignature;
        alertAreaLayer.clearLayers();
        if (featureCollection.features.length === 0) {
            return;
        }
        try {
            alertAreaLayer.addData(featureCollection);
        } catch (_error) {
            alertAreaLayer.clearLayers();
        }
    }

    function formatAlertExpiry(value) {
        const normalized = String(value || "").trim();
        if (!normalized) {
            return "";
        }
        const parsed = new Date(normalized);
        if (Number.isNaN(parsed.getTime())) {
            return normalized;
        }
        return parsed.toLocaleString(locale, {
            dateStyle: "short",
            timeStyle: "short",
        });
    }

    function severityBadgeClass(severityLevel) {
        const normalizedLevel = Number.parseInt(String(severityLevel ?? ""), 10);
        return [1, 2, 3].includes(normalizedLevel)
            ? `alert-category-badge-level-${normalizedLevel}`
            : "alert-category-badge-unknown";
    }

    function constrainAlertPanelListHeight() {
        if (!alertsOverlayList || !alertsOverlayOpen) {
            return;
        }
        const cards = Array.from(alertsOverlayList.querySelectorAll(".map-alert-item"));
        const shouldScroll = cards.length > maximumVisibleAlertCards;
        alertsOverlayList.dataset.scrollable = shouldScroll ? "true" : "false";
        alertsOverlayList.style.removeProperty("--map-alert-list-limit");
        if (!shouldScroll) {
            return;
        }
        const listStyle = window.getComputedStyle(alertsOverlayList);
        let visibleHeight = (
            Number.parseFloat(listStyle.paddingTop || "0")
            + Number.parseFloat(listStyle.paddingBottom || "0")
        );
        for (const [index, card] of cards.slice(0, maximumVisibleAlertCards).entries()) {
            visibleHeight += card.getBoundingClientRect().height;
            if (index > 0) {
                visibleHeight += Number.parseFloat(
                    window.getComputedStyle(card).marginTop || "0"
                );
            }
        }
        alertsOverlayList.style.setProperty(
            "--map-alert-list-limit",
            `${Math.ceil(visibleHeight)}px`
        );
    }

    function scheduleAlertPanelListConstraint() {
        window.requestAnimationFrame(constrainAlertPanelListHeight);
    }

    function positionAlertPanelBelowLeafletControls() {
        if (!alertsOverlay || !mapStage || !mapCanvas) {
            return;
        }
        const zoomControl = mapCanvas.querySelector(".leaflet-control-zoom");
        if (!zoomControl) {
            return;
        }
        const mapStageRect = mapStage.getBoundingClientRect();
        const zoomControlRect = zoomControl.getBoundingClientRect();
        const panelTop = Math.ceil(zoomControlRect.bottom - mapStageRect.top + 10);
        alertsOverlay.style.setProperty("--map-alert-overlay-top", `${panelTop}px`);
    }

    function refreshAlertPanelLayout() {
        positionAlertPanelBelowLeafletControls();
        scheduleAlertPanelListConstraint();
    }

    function renderAlertPanel() {
        if (!alertsOverlayList) {
            return;
        }
        const nextPanelSignature = JSON.stringify({
            alerts: latestMapAlerts,
            hidden: Array.from(hiddenAlertIds).sort((left, right) => left - right),
        });
        if (nextPanelSignature === lastAlertPanelSignature) {
            syncAlertPanelButton();
            return;
        }
        lastAlertPanelSignature = nextPanelSignature;
        alertsOverlayList.replaceChildren();
        if (latestMapAlerts.length === 0) {
            const empty = document.createElement("p");
            empty.className = "map-alerts-overlay-empty";
            empty.textContent = i18n.noActiveMapAlarms;
            alertsOverlayList.appendChild(empty);
            syncAlertPanelButton();
            scheduleAlertPanelListConstraint();
            return;
        }
        for (const alert of latestMapAlerts) {
            const alertId = Number.parseInt(String(alert.id), 10);
            const hasGeometry = Boolean(alert.has_geometry);
            const isVisible = hasGeometry && !hiddenAlertIds.has(alertId);
            const item = document.createElement("article");
            item.className = "map-alert-item";
            item.dataset.visible = isVisible ? "true" : "false";
            item.dataset.hasGeometry = hasGeometry ? "true" : "false";

            const heading = document.createElement("div");
            heading.className = "map-alert-item-heading";
            const category = document.createElement("span");
            category.className = `frame-type-badge alert-category-badge ${severityBadgeClass(alert.severity_level)}`;
            const eventIcon = document.createElement("img");
            eventIcon.className = "alert-category-event-icon";
            eventIcon.src = `${staticRoot}icons/${String(alert.event_icon || "alert-outline.svg")}`;
            eventIcon.alt = "";
            category.appendChild(eventIcon);
            category.append(document.createTextNode(String(alert.event_code || i18n.activeAlarms)));
            heading.appendChild(category);

            const switchLabel = document.createElement("label");
            switchLabel.className = "map-alert-visibility-toggle";
            switchLabel.title = hasGeometry ? i18n.visibleOnMap : i18n.noMapArea;
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.checked = isVisible;
            checkbox.disabled = !hasGeometry;
            checkbox.setAttribute("role", "switch");
            checkbox.setAttribute(
                "aria-label",
                `${i18n.visibleOnMap}: ${String(alert.event_code || alert.source_callsign || alertId)}`
            );
            const switchTrack = document.createElement("span");
            switchTrack.className = "map-alert-switch-track";
            switchLabel.append(checkbox, switchTrack);
            heading.appendChild(switchLabel);
            item.appendChild(heading);

            const source = document.createElement("div");
            source.className = "map-alert-item-source";
            source.textContent = [alert.source_callsign, alert.alarm_group]
                .map((value) => String(value || "").trim())
                .filter(Boolean)
                .join(" · ");
            item.appendChild(source);

            const meta = document.createElement("div");
            meta.className = "map-alert-item-meta";
            const severity = Number.parseInt(String(alert.severity_level ?? ""), 10);
            if (Number.isInteger(severity)) {
                const severityText = document.createElement("span");
                severityText.textContent = `${i18n.severityLevel}: ${severity}`;
                meta.appendChild(severityText);
            }
            const areaCount = document.createElement("span");
            areaCount.textContent = `${i18n.areaCount}: ${Number.parseInt(String(alert.area_count || 0), 10)}`;
            meta.appendChild(areaCount);
            const expiry = formatAlertExpiry(alert.expires_at);
            if (expiry) {
                const expiryText = document.createElement("span");
                expiryText.textContent = `${i18n.expiresAt}: ${expiry}`;
                meta.appendChild(expiryText);
            }
            if (!hasGeometry) {
                const noArea = document.createElement("span");
                noArea.className = "map-alert-item-no-area";
                noArea.textContent = i18n.noMapArea;
                meta.appendChild(noArea);
            }
            item.appendChild(meta);

            if (alert.detail_href) {
                const detailsLink = document.createElement("a");
                detailsLink.className = "map-alert-item-details";
                detailsLink.href = `${rootPath}${String(alert.detail_href)}`;
                detailsLink.textContent = i18n.details;
                item.appendChild(detailsLink);
            }

            checkbox.addEventListener("change", function () {
                if (checkbox.checked) {
                    hiddenAlertIds.delete(alertId);
                } else {
                    hiddenAlertIds.add(alertId);
                }
                persistHiddenAlertIds();
                renderVisibleAlertAreas();
                renderAlertPanel();
            });
            alertsOverlayList.appendChild(item);
        }
        syncAlertPanelButton();
        scheduleAlertPanelListConstraint();
    }

    function syncAlertPanelButton() {
        const alertsWithGeometry = latestMapAlerts.filter((alert) => Boolean(alert.has_geometry));
        const visibleCount = alertsWithGeometry.filter((alert) => (
            !hiddenAlertIds.has(Number.parseInt(String(alert.id), 10))
        )).length;
        if (toggleAlarmAreasIcon) {
            toggleAlarmAreasIcon.setAttribute(
                "src",
                `${staticRoot}icons/${alertsWithGeometry.length > 0 && visibleCount === 0 ? "alarm-light-off-outline.svg" : "alarm-light-outline.svg"}`
            );
        }
        if (toggleAlarmAreasButton) {
            const label = alertsOverlayOpen ? i18n.hideAlarmList : i18n.showAlarmList;
            toggleAlarmAreasButton.setAttribute("title", label);
            toggleAlarmAreasButton.setAttribute("aria-label", label);
            toggleAlarmAreasButton.setAttribute("aria-expanded", alertsOverlayOpen ? "true" : "false");
        }
    }

    function setAlertsOverlayOpen(open) {
        alertsOverlayOpen = Boolean(open);
        if (alertsOverlay) {
            alertsOverlay.hidden = !alertsOverlayOpen;
        }
        syncAlertPanelButton();
        if (alertsOverlayOpen) {
            refreshAlertPanelLayout();
        }
    }

    function reconcileAlertAreas(value) {
        latestAlertAreaCollection = normalizeAlertAreaFeatureCollection(value);
        latestMapAlerts = latestAlertAreaCollection.alerts;
        const activeAlertIds = new Set(
            latestMapAlerts.map((alert) => Number.parseInt(String(alert.id), 10))
        );
        const retainedHiddenIds = new Set(
            Array.from(hiddenAlertIds).filter((alertId) => activeAlertIds.has(alertId))
        );
        if (retainedHiddenIds.size !== hiddenAlertIds.size) {
            hiddenAlertIds = retainedHiddenIds;
            persistHiddenAlertIds();
        }
        renderVisibleAlertAreas();
        renderAlertPanel();
    }

    function resolveInitialView() {
        try {
            const raw = window.localStorage.getItem(mapViewStorageKey);
            if (!raw) {
                return defaultView;
            }
            const parsed = JSON.parse(raw);
            const latitude = Number(parsed?.latitude);
            const longitude = Number(parsed?.longitude);
            const zoom = Number.parseInt(String(parsed?.zoom ?? ""), 10);
            if (
                Number.isFinite(latitude)
                && Number.isFinite(longitude)
                && Number.isInteger(zoom)
                && zoom >= 0
            ) {
                const looksLikeModalRegressionView = (
                    Math.abs(latitude) < 0.001
                    && Math.abs(longitude) < 0.001
                    && zoom === 15
                );
                if (looksLikeModalRegressionView) {
                    window.localStorage.removeItem(mapViewStorageKey);
                    return defaultView;
                }
                return { latitude, longitude, zoom };
            }
        } catch (_error) {
        }
        return defaultView;
    }

    const initialView = resolveInitialView();

    const map = window.L.map("map-canvas", {
        center: [initialView.latitude, initialView.longitude],
        zoom: initialView.zoom,
        zoomControl: true,
    });
    window.aprsboxCenterMapOn = function (latitude, longitude) {
        if (!Number.isFinite(Number(latitude)) || !Number.isFinite(Number(longitude))) {
            return;
        }
        map.setView([Number(latitude), Number(longitude)], Math.max(map.getZoom(), 15));
    };
    const mapMaskPaneName = "map-mask-pane";
    let mapMaskPane = null;
    let mapMaskLayer = null;

    const tileLayerOptions = {
        attribution: tileAttribution,
    };
    if (Number.isInteger(tileMinZoom)) {
        tileLayerOptions.minZoom = tileMinZoom;
    }
    if (Number.isInteger(tileMaxZoom)) {
        tileLayerOptions.maxZoom = tileMaxZoom;
    }
    if (tileSubdomains.length > 0) {
        tileLayerOptions.subdomains = tileSubdomains;
    }

    function syncMapMaskLayerViewport() {
        if (!mapMaskPane) {
            return;
        }
        const size = map.getSize();
        const mapPaneElement = map.getPane("mapPane");
        const mapPanePosition = mapPaneElement
            ? window.L.DomUtil.getPosition(mapPaneElement)
            : null;
        const offsetX = Number.isFinite(mapPanePosition && mapPanePosition.x)
            ? mapPanePosition.x
            : 0;
        const offsetY = Number.isFinite(mapPanePosition && mapPanePosition.y)
            ? mapPanePosition.y
            : 0;
        mapMaskPane.style.transform = "";
        mapMaskPane.style.left = `${-offsetX}px`;
        mapMaskPane.style.top = `${-offsetY}px`;
        mapMaskPane.style.width = `${size.x}px`;
        mapMaskPane.style.height = `${size.y}px`;
    }

    function ensureMapMaskLayer(mapInstance) {
        mapMaskPane = mapInstance.getPane(mapMaskPaneName);
        if (!mapMaskPane) {
            mapMaskPane = mapInstance.createPane(mapMaskPaneName);
        }
        mapMaskPane.classList.add("map-mask-pane");
        mapMaskPane.style.zIndex = "300";
        mapMaskPane.style.pointerEvents = "none";
        const mapPaneElement = mapInstance.getPane("mapPane");
        if (mapPaneElement && mapMaskPane.parentElement !== mapPaneElement) {
            mapPaneElement.appendChild(mapMaskPane);
        }
        syncMapMaskLayerViewport();
        let layer = mapMaskPane.querySelector(".map-mask-layer");
        if (!layer) {
            layer = document.createElement("div");
            layer.className = "map-mask-layer";
            mapMaskPane.appendChild(layer);
        }
        return layer;
    }

    map.on("resize zoom move", syncMapMaskLayerViewport);
    mapMaskLayer = ensureMapMaskLayer(map);
    const tileLayer = window.L.tileLayer(tileUrl, tileLayerOptions).addTo(map);
    const alertAreasPaneName = "alert-areas-pane";
    const alertAreasPane = map.createPane(alertAreasPaneName);
    alertAreasPane.style.zIndex = "350";
    alertAreasPane.style.pointerEvents = "none";
    alertAreaLayer = window.L.geoJSON(null, {
        pane: alertAreasPaneName,
        interactive: false,
        style: (feature) => {
            const requestedColor = String(
                feature?.properties?.aprsbox_alert_color || "gray"
            ).toLowerCase();
            const color = ["yellow", "orange", "red", "gray"].includes(requestedColor)
                ? requestedColor
                : "gray";
            return {
                stroke: true,
                color,
                opacity: 1,
                weight: 2,
                dashArray: null,
                fill: true,
                fillColor: color,
                fillOpacity: 0.10,
            };
        },
    }).addTo(map);
    coverageLayerGroup.addTo(map);
    trackLayerGroup.addTo(map);
    markerLayerGroup.addTo(map);
    rulerLayer.addTo(map);

    if (tileSourceOutput) {
        tileSourceOutput.textContent = tileSourceName;
    }
    if (tileStatusOutput) {
        tileStatusOutput.textContent = "";
    }

    function setTileStatusOutput(message, { clearAfterMs = 0 } = {}) {
        if (!tileStatusOutput) {
            return;
        }
        if (tileStatusClearTimer) {
            window.clearTimeout(tileStatusClearTimer);
            tileStatusClearTimer = null;
        }
        tileStatusOutput.textContent = message ? `(${message})` : "";
        if (clearAfterMs > 0) {
            tileStatusClearTimer = window.setTimeout(function () {
                tileStatusOutput.textContent = "";
                tileStatusClearTimer = null;
            }, clearAfterMs);
        }
    }

    async function reportTileEvent(eventType) {
        if (!mapTileEventsEndpoint) {
            return;
        }
        try {
            await fetch(mapTileEventsEndpoint, {
                method: "POST",
                headers: {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    event_type: eventType,
                    source_name: tileSourceName,
                    provider_url: tileUrl,
                    tile_url: lastTileErrorUrl,
                    error_count: tileErrorCount,
                    load_count: tileLoadCount,
                }),
            });
        } catch (_error) {
        }
    }

    function handleTileError(tileSourceUrl) {
        tileErrorCount += 1;
        consecutiveTileErrors += 1;
        lastTileErrorUrl = String(tileSourceUrl || "").trim();
        if (!tileErrorActive && consecutiveTileErrors >= 5) {
            tileErrorActive = true;
            setTileStatusOutput(i18n.tileProviderUnavailable);
            const now = Date.now();
            if ((now - lastTileErrorReportedAt) >= tileEventReportIntervalMs) {
                lastTileErrorReportedAt = now;
                void reportTileEvent("tile_error");
            }
        }
    }

    function handleTileLoad() {
        tileLoadCount += 1;
        consecutiveTileErrors = 0;
        if (!tileErrorActive) {
            return;
        }
        tileErrorActive = false;
        setTileStatusOutput(i18n.tileProviderRecovered, { clearAfterMs: 8000 });
        const now = Date.now();
        if ((now - lastTileRecoveryReportedAt) >= tileEventReportIntervalMs) {
            lastTileRecoveryReportedAt = now;
            void reportTileEvent("tile_recovered");
        }
    }

    tileLayer.on("tileerror", function (event) {
        handleTileError(event?.tile?.src || event?.url || "");
    });
    tileLayer.on("tileload", function () {
        handleTileLoad();
    });

    function resolveDefaultMaskOpacity() {
        const storedOpacity = Number.parseInt(window.localStorage.getItem(maskOpacityStorageKey()) || "", 10);
        if (Number.isInteger(storedOpacity) && storedOpacity >= 0 && storedOpacity <= 100 && storedOpacity % 10 === 0) {
            return storedOpacity;
        }
        const computedDefaultOpacity = Number.parseFloat(
            window.getComputedStyle(document.documentElement).getPropertyValue("--map-mask-default-opacity") || ""
        );
        if (Number.isFinite(computedDefaultOpacity)) {
            const asPercent = Math.max(0, Math.min(100, Math.round(computedDefaultOpacity * 100)));
            return asPercent - (asPercent % 10);
        }
        return 20;
    }

    function applyMaskOpacity(opacityPercent) {
        const normalizedOpacity = normalizeOpacityPercent(opacityPercent, 20);
        const maskLayerOpacity = opacityFractionFromPercent(normalizedOpacity);
        if (!mapMaskLayer) {
            mapMaskLayer = ensureMapMaskLayer(map);
        }
        if (mapMaskLayer) {
            mapMaskLayer.style.opacity = String(maskLayerOpacity);
        }
        if (mapCanvas) {
            mapCanvas.style.setProperty("--map-mask-layer-opacity", String(maskLayerOpacity));
        }
        if (maskOpacitySelect) {
            maskOpacitySelect.value = String(normalizedOpacity);
        }
        window.localStorage.setItem(maskOpacityStorageKey(), String(normalizedOpacity));
    }

    function resolveDefaultCoverageFillOpacity() {
        const configuredOpacity = Number.parseInt(root.dataset.coverageFillOpacity || "", 10);
        return normalizeCoverageOpacityPercent(configuredOpacity, 5);
    }

    function resolveDefaultCoverageOutlineOpacity() {
        const storedOpacity = Number.parseInt(window.localStorage.getItem(mapCoverageOutlineOpacityStorageKey) || "", 10);
        return normalizeOpacityPercent(storedOpacity, 100);
    }

    function applyCoverageFillOpacity(opacityPercent) {
        const normalizedOpacity = normalizeCoverageOpacityPercent(opacityPercent, 5);
        coverageFillOpacity = opacityFractionFromPercent(normalizedOpacity);
        if (coverageFillOpacitySelect) {
            coverageFillOpacitySelect.value = String(normalizedOpacity);
        }
    }

    function applyCoverageOutlineOpacity(opacityPercent) {
        const normalizedOpacity = normalizeOpacityPercent(opacityPercent, 100);
        coverageOutlineOpacity = opacityFractionFromPercent(normalizedOpacity);
        if (coverageOutlineOpacitySelect) {
            coverageOutlineOpacitySelect.value = String(normalizedOpacity);
        }
        window.localStorage.setItem(mapCoverageOutlineOpacityStorageKey, String(normalizedOpacity));
    }

    function resolveTracksVisible() {
        const storedValue = String(window.localStorage.getItem(mapTracksVisibleStorageKey) || "").trim();
        if (storedValue === "0" || storedValue.toLowerCase() === "false") {
            return false;
        }
        if (storedValue === "1" || storedValue.toLowerCase() === "true") {
            return true;
        }
        return true;
    }

    function applyTracksToggleState(visible) {
        tracksVisible = Boolean(visible);
        window.localStorage.setItem(mapTracksVisibleStorageKey, tracksVisible ? "1" : "0");
        if (toggleTracksIcon) {
            toggleTracksIcon.setAttribute("src", `${staticRoot}icons/${tracksVisible ? "track-light.svg" : "track-light-off.svg"}`);
        }
        if (toggleTracksButton) {
            const label = tracksVisible ? i18n.hideTracks : i18n.showTracks;
            toggleTracksButton.setAttribute("title", label);
            toggleTracksButton.setAttribute("aria-label", label);
        }
    }

    function resolveCoverageVisible() {
        const storedValue = String(window.localStorage.getItem(mapCoverageVisibleStorageKey) || "").trim();
        if (storedValue === "0" || storedValue.toLowerCase() === "false") {
            return false;
        }
        if (storedValue === "1" || storedValue.toLowerCase() === "true") {
            return true;
        }
        return true;
    }

    function applyCoverageToggleState(visible) {
        coverageVisible = Boolean(visible);
        window.localStorage.setItem(mapCoverageVisibleStorageKey, coverageVisible ? "1" : "0");
        if (toggleCoverageIcon) {
            toggleCoverageIcon.setAttribute("src", `${staticRoot}icons/${coverageVisible ? "map-marker-radius.svg" : "map-marker-radius-outline.svg"}`);
        }
        if (toggleCoverageButton) {
            const label = coverageVisible ? i18n.hideCoverage : i18n.showCoverage;
            toggleCoverageButton.setAttribute("title", label);
            toggleCoverageButton.setAttribute("aria-label", label);
        }
    }

    function resolveRulerVisible() {
        const storedValue = String(window.localStorage.getItem(mapRulerVisibleStorageKey) || "").trim();
        if (storedValue === "0" || storedValue.toLowerCase() === "false") {
            return false;
        }
        if (storedValue === "1" || storedValue.toLowerCase() === "true") {
            return true;
        }
        return true;
    }

    function syncRulerLayerVisibility() {
        if (rulerVisible) {
            if (!map.hasLayer(rulerLayer)) {
                rulerLayer.addTo(map);
            }
            return;
        }
        if (map.hasLayer(rulerLayer)) {
            map.removeLayer(rulerLayer);
        }
    }

    function applyRulerToggleState(visible) {
        rulerVisible = Boolean(visible);
        window.localStorage.setItem(mapRulerVisibleStorageKey, rulerVisible ? "1" : "0");
        syncRulerLayerVisibility();
        if (toggleRulerIcon) {
            toggleRulerIcon.setAttribute("src", `${staticRoot}icons/${rulerVisible ? "ruler.svg" : "ruler-square.svg"}`);
        }
        if (toggleRulerButton) {
            const label = rulerVisible ? i18n.hideRuler : i18n.showRuler;
            toggleRulerButton.setAttribute("title", label);
            toggleRulerButton.setAttribute("aria-label", label);
        }
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll("\"", "&quot;")
            .replaceAll("'", "&#39;");
    }

    function formatCoordinate(value) {
        return Number.isFinite(value) ? value.toFixed(5) : "--";
    }

    function visibleMapRadiusKm() {
        const center = map.getCenter();
        const size = map.getSize();
        if (!Number.isFinite(center.lat) || !Number.isFinite(center.lng)) {
            return NaN;
        }
        if (!size || size.x <= 0 || size.y <= 0) {
            return NaN;
        }
        const centerPoint = map.latLngToContainerPoint(center);
        const radiusPixels = Math.max(1, Math.floor(Math.min(size.x, size.y) / 2));
        const edgePoint = window.L.point(centerPoint.x, Math.max(0, centerPoint.y - radiusPixels));
        const edgeLatLng = map.containerPointToLatLng(edgePoint);
        const radiusMeters = map.distance(center, edgeLatLng);
        if (!Number.isFinite(radiusMeters) || radiusMeters <= 0) {
            return NaN;
        }
        return radiusMeters / 1000;
    }

    function parseUtcDate(value) {
        const text = String(value || "").trim();
        if (!text) {
            return null;
        }
        const normalized = /(?:[zZ]|[+-]\d{2}:\d{2})$/.test(text) ? text : `${text}Z`;
        const date = new Date(normalized);
        if (Number.isNaN(date.getTime())) {
            return null;
        }
        return date;
    }

    function formatTimestamp(value) {
        if (!value) {
            return "";
        }
        const date = parseUtcDate(value);
        if (date === null) {
            return String(value);
        }
        const year = date.getUTCFullYear();
        const month = String(date.getUTCMonth() + 1).padStart(2, "0");
        const day = String(date.getUTCDate()).padStart(2, "0");
        const hour = String(date.getUTCHours()).padStart(2, "0");
        const minute = String(date.getUTCMinutes()).padStart(2, "0");
        return `${year}.${month}.${day} ${hour}:${minute} UTC`;
    }

    function formatAge(seconds) {
        if (!Number.isFinite(seconds) || seconds < 0) {
            return "";
        }
        const relative = relativeTimeFormatter;
        if (!relative) {
            if (seconds < 60) return `${Math.round(seconds)}s`;
            if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
            if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
            return `${Math.round(seconds / 86400)}d`;
        }
        if (seconds < 60) {
            return relative.format(-Math.round(seconds), "second");
        }
        if (seconds < 3600) {
            return relative.format(-Math.round(seconds / 60), "minute");
        }
        if (seconds < 86400) {
            return relative.format(-Math.round(seconds / 3600), "hour");
        }
        return relative.format(-Math.round(seconds / 86400), "day");
    }

    function formatDistance(distanceKm) {
        if (!Number.isFinite(distanceKm)) {
            return "";
        }
        return `${distanceKm} km`;
    }

    function normalizeInterfaceId(value) {
        const parsed = Number.parseInt(String(value ?? "").trim(), 10);
        return Number.isInteger(parsed) ? parsed : null;
    }

    function interfaceKey(item) {
        const interfaceId = normalizeInterfaceId(item && item.modem_id);
        if (interfaceId !== null) {
            return `modem:${interfaceId}`;
        }
        return `fallback:${String((item && item.name) || "").trim()}:${String((item && item.band) || "").trim()}`;
    }

    function syncInterfaceVisibility(interfaces) {
        const currentKeys = new Set();
        for (const item of interfaces || []) {
            const key = interfaceKey(item);
            currentKeys.add(key);
            if (!interfaceVisibilityByKey.has(key)) {
                interfaceVisibilityByKey.set(key, true);
            }
        }
        for (const key of Array.from(interfaceVisibilityByKey.keys())) {
            if (!currentKeys.has(key)) {
                interfaceVisibilityByKey.delete(key);
            }
        }
    }

    function interfaceVisibilityContext(interfaces) {
        const interfacesById = new Map();
        const visibleInterfaceIds = new Set();
        for (const item of interfaces || []) {
            const interfaceId = normalizeInterfaceId(item && item.modem_id);
            if (interfaceId === null) {
                continue;
            }
            interfacesById.set(interfaceId, item);
            if (interfaceVisibilityByKey.get(interfaceKey(item)) !== false) {
                visibleInterfaceIds.add(interfaceId);
            }
        }
        return { interfacesById, visibleInterfaceIds };
    }

    function isStationInterfaceVisible(interfaceId, interfacesById, visibleInterfaceIds) {
        if (!Number.isInteger(interfaceId)) {
            return true;
        }
        if (!interfacesById.has(interfaceId)) {
            return true;
        }
        return visibleInterfaceIds.has(interfaceId);
    }

    function filteredStations(stations, interfacesById, visibleInterfaceIds) {
        return (stations || []).filter((station) => {
            const interfaceId = normalizeInterfaceId(station && station.interface_id);
            return isStationInterfaceVisible(interfaceId, interfacesById, visibleInterfaceIds);
        });
    }

    function isSameTrackPointPosition(previous, current) {
        const previousLatitude = Number(previous && previous.latitude);
        const previousLongitude = Number(previous && previous.longitude);
        const currentLatitude = Number(current && current.latitude);
        const currentLongitude = Number(current && current.longitude);
        return Number.isFinite(previousLatitude)
            && Number.isFinite(previousLongitude)
            && Number.isFinite(currentLatitude)
            && Number.isFinite(currentLongitude)
            && Math.abs(previousLatitude - currentLatitude) < 1e-6
            && Math.abs(previousLongitude - currentLongitude) < 1e-6;
    }

    function rebuildVisibleTrackPoints(points, interfacesById, visibleInterfaceIds) {
        const rebuilt = [];
        for (const point of points || []) {
            const interfaceId = normalizeInterfaceId(point && point.interface_id);
            if (!isStationInterfaceVisible(interfaceId, interfacesById, visibleInterfaceIds)) {
                continue;
            }
            const previous = rebuilt[rebuilt.length - 1];
            if (previous && isSameTrackPointPosition(previous, point)) {
                continue;
            }
            rebuilt.push(point);
        }
        return rebuilt.slice(-mobileTrackMaxRenderedPoints);
    }

    function filteredMobileTracks(mobileTracks, interfacesById, visibleInterfaceIds) {
        const filteredTracks = [];
        for (const track of mobileTracks || []) {
            const rebuiltPoints = rebuildVisibleTrackPoints(
                track.points,
                interfacesById,
                visibleInterfaceIds
            );
            if (rebuiltPoints.length < 2) {
                continue;
            }
            filteredTracks.push({
                ...track,
                points: rebuiltPoints,
            });
        }
        return filteredTracks;
    }

    function filteredMapData(stations, mobileTracks, interfaces) {
        const { interfacesById, visibleInterfaceIds } = interfaceVisibilityContext(interfaces);
        return {
            stations: filteredStations(stations, interfacesById, visibleInterfaceIds),
            mobileTracks: filteredMobileTracks(mobileTracks, interfacesById, visibleInterfaceIds),
        };
    }

    function mergeInterfaces(...groups) {
        const merged = [];
        const seen = new Set();
        for (const group of groups) {
            for (const item of group || []) {
                const key = interfaceKey(item);
                if (seen.has(key)) {
                    continue;
                }
                seen.add(key);
                merged.push(item);
            }
        }
        return merged;
    }

    function hiddenInterfaceSignature() {
        return Array.from(interfaceVisibilityByKey.entries())
            .filter(([, isVisible]) => isVisible === false)
            .map(([key]) => key)
            .sort()
            .join("|");
    }

    function interfacesSignature(interfaces) {
        return (interfaces || [])
            .map((item) => {
                const interfaceId = normalizeInterfaceId(item && item.modem_id);
                const name = String((item && item.name) || "").trim();
                const band = String((item && item.band) || "").trim();
                return `${interfaceId === null ? "" : interfaceId}:${name}:${band}`;
            })
            .join("|");
    }

    function buildRenderSignature() {
        return [
            normalizeRevision(latestStationRevision),
            normalizeRevision(latestStationDetailsRevision),
            tracksVisible ? normalizeRevision(latestTrackRevision) : "tracks-off",
            coverageVisible ? normalizeRevision(latestStationDetailsRevision) : "coverage-off",
            String(latestStations.length),
            String(latestMobileTracks.length),
            interfacesSignature(latestInterfaces),
            hiddenInterfaceSignature(),
            tracksVisible ? "tracks-on" : "tracks-hidden",
            coverageVisible ? "coverage-on" : "coverage-hidden",
        ].join("||");
    }

    function stationIdentityKey(station) {
        return String(
            (station && station.display_callsign)
            || (station && station.callsign)
            || ""
        ).trim();
    }

    function mergeStationDetails(stations, details) {
        const detailsByKey = new Map();
        for (const detail of details || []) {
            const key = stationIdentityKey(detail);
            if (!key) {
                continue;
            }
            detailsByKey.set(key, detail);
        }
        return (stations || []).map((station) => {
            const key = stationIdentityKey(station);
            const detail = detailsByKey.get(key);
            return detail ? detail : station;
        });
    }

    function mergeStationSupplementalData(stations, previousStations) {
        const previousByKey = new Map();
        for (const station of previousStations || []) {
            const key = stationIdentityKey(station);
            if (!key) {
                continue;
            }
            previousByKey.set(key, station);
        }
        return (stations || []).map((station) => {
            const key = stationIdentityKey(station);
            const previous = previousByKey.get(key);
            if (!previous) {
                return station;
            }
            return {
                ...station,
                comment: previous.comment,
                data: previous.data,
                path: previous.path,
                aprs_device_short: previous.aprs_device_short,
                speed: previous.speed,
                course: previous.course,
                altitude: previous.altitude,
                phg_power_w: previous.phg_power_w,
                phg_height_ft: previous.phg_height_ft,
                phg_gain_dbi: previous.phg_gain_dbi,
                phg_direction: previous.phg_direction,
                phg_range_km: previous.phg_range_km,
                qsy_frequency_mhz: previous.qsy_frequency_mhz,
                qsy_tone: previous.qsy_tone,
                qsy_offset_khz: previous.qsy_offset_khz,
                qsy_callsign: previous.qsy_callsign,
                destination: previous.destination,
            };
        });
    }

    function retainVisibleMobileTracks(mobileTracks, stations) {
        const visibleKeys = new Set(
            (stations || [])
                .map((station) => stationIdentityKey(station))
                .filter((key) => Boolean(key))
        );
        return (mobileTracks || []).filter((track) => visibleKeys.has(String(track.display_callsign || "").trim()));
    }

    function renderInterfaceFilters(interfaces) {
        if (!mapInterfaceFilters) {
            return;
        }
        const resolvedInterfaces = Array.isArray(interfaces) ? interfaces : [];
        if (resolvedInterfaces.length === 0) {
            mapInterfaceFilters.textContent = "";
            mapInterfaceFilters.hidden = true;
            return;
        }

        mapInterfaceFilters.hidden = false;
        mapInterfaceFilters.textContent = "";

        for (const item of resolvedInterfaces) {
            const key = interfaceKey(item);
            const isVisible = interfaceVisibilityByKey.get(key) !== false;
            const chip = document.createElement("div");
            chip.className = "map-interface-filter-chip";
            chip.dataset.visible = isVisible ? "true" : "false";

            const toggle = document.createElement("button");
            toggle.type = "button";
            toggle.className = "table-icon-button map-interface-filter-toggle";
            toggle.setAttribute("aria-pressed", isVisible ? "true" : "false");
            toggle.setAttribute("aria-label", isVisible ? i18n.hide : i18n.show);
            toggle.setAttribute("title", isVisible ? i18n.hide : i18n.show);
            const icon = document.createElement("img");
            icon.src = isVisible ? visibleIconPath : hiddenIconPath;
            icon.alt = "";
            toggle.appendChild(icon);
            toggle.addEventListener("click", function () {
                const currentVisible = interfaceVisibilityByKey.get(key) !== false;
                interfaceVisibilityByKey.set(key, !currentVisible);
                applyLatestMapData({ forceRender: true });
            });

            const bandNode = document.createElement("span");
            bandNode.className = "map-interface-filter-band";
            bandNode.textContent = String(item.band || "-");

            const nameNode = document.createElement("span");
            nameNode.className = "map-interface-filter-name";
            nameNode.textContent = String(item.name || "-");

            chip.append(toggle, bandNode, nameNode);
            mapInterfaceFilters.appendChild(chip);
        }
    }

    function applyLatestMapData({ forceRender = false } = {}) {
        syncInterfaceVisibility(latestInterfaces);
        renderInterfaceFilters(latestInterfaces);
        const filtered = filteredMapData(latestStations, latestMobileTracks, latestInterfaces);
        root.dispatchEvent(new window.CustomEvent(mapStationsRefreshEventName, {
            detail: {
                stations: filtered.stations,
                mobileTracks: filtered.mobileTracks,
                stationLatitude: defaultView.latitude,
                stationLongitude: defaultView.longitude,
            },
        }));
        const nextSignature = buildRenderSignature();
        if (!forceRender && nextSignature === lastStationsSignature) {
            return;
        }
        lastStationsSignature = nextSignature;
        renderStations(filtered.stations, filtered.mobileTracks);
    }

    function renderDecodedData(dataItems) {
        if (!Array.isArray(dataItems) || !dataItems.length) {
            return "";
        }
        const chips = dataItems
            .filter((item) => item && item.icon && item.label && item.value)
            .map((item) => (
                `<span class="weather-chip" title="${escapeHtml(item.label)}: ${escapeHtml(item.value)}">`
                    + `<img src="${staticRoot}icons/${escapeHtml(item.icon)}" alt="${escapeHtml(item.label)}">`
                    + `<span>${escapeHtml(item.value)}</span>`
                + "</span>"
            ))
            .join("");
        if (!chips) {
            return "";
        }
        return `<div class="weather-inline">${chips}</div>`;
    }

    function normalizeBearing(bearingDeg) {
        return (bearingDeg + 360) % 360;
    }

    function bearingBetweenPoints(fromLatLng, toLatLng) {
        const fromLatitudeRad = (fromLatLng.lat * Math.PI) / 180;
        const toLatitudeRad = (toLatLng.lat * Math.PI) / 180;
        const deltaLongitudeRad = ((toLatLng.lng - fromLatLng.lng) * Math.PI) / 180;
        const y = Math.sin(deltaLongitudeRad) * Math.cos(toLatitudeRad);
        const x = (
            (Math.cos(fromLatitudeRad) * Math.sin(toLatitudeRad))
            - (Math.sin(fromLatitudeRad) * Math.cos(toLatitudeRad) * Math.cos(deltaLongitudeRad))
        );
        return normalizeBearing((Math.atan2(y, x) * 180) / Math.PI);
    }

    function formatRulerDistance(distanceMeters) {
        if (!Number.isFinite(distanceMeters) || distanceMeters < 0) {
            return "--";
        }
        const distanceKm = distanceMeters / 1000;
        const precision = distanceKm < 10 ? 2 : 1;
        return `${distanceKm.toFixed(precision)} km`;
    }

    function buildRulerPickerIcon(side) {
        return window.L.divIcon({
            className: "map-ruler-picker-icon",
            html: `<span class="map-ruler-picker map-ruler-picker-${side.toLowerCase()}">${escapeHtml(side)}</span>`,
            iconSize: [16, 16],
            iconAnchor: [8, 8],
            tooltipAnchor: [0, -12],
        });
    }

    function buildRulerInitialPoints() {
        const viewportSize = map.getSize();
        const anchorY = Math.max(40, viewportSize.y - 56);
        const leftPadding = 16;
        const rightPadding = 24;
        const viewportRight = Math.max(leftPadding + 48, viewportSize.x - rightPadding);
        const minGap = Math.max(48, Math.min(90, viewportRight - leftPadding));
        const preferredGap = Math.max(minGap, Math.min(220, viewportRight - leftPadding));
        let firstAnchorX = Math.min(168, viewportRight - minGap);
        firstAnchorX = Math.max(leftPadding, firstAnchorX);
        let secondAnchorX = Math.min(firstAnchorX + preferredGap, viewportRight);
        if ((secondAnchorX - firstAnchorX) < minGap) {
            firstAnchorX = Math.max(leftPadding, secondAnchorX - minGap);
        }
        return [
            map.containerPointToLatLng([firstAnchorX, anchorY]),
            map.containerPointToLatLng([secondAnchorX, anchorY]),
        ];
    }

    function buildRulerTooltipHtml(title, bearingDeg, distanceMeters) {
        return `
            <div class="map-ruler-tooltip-content">
                <strong>${escapeHtml(title)}</strong>
                <span>${escapeHtml(i18n.course)}: ${Math.round(normalizeBearing(bearingDeg))}°</span>
                <span>${escapeHtml(i18n.distance)}: ${escapeHtml(formatRulerDistance(distanceMeters))}</span>
            </div>
        `;
    }

    function syncRulerMeasurements() {
        if (!rulerState) {
            return;
        }
        const pointA = rulerState.markerA.getLatLng();
        const pointB = rulerState.markerB.getLatLng();
        const distanceMeters = map.distance(pointA, pointB);
        const bearingAtoB = bearingBetweenPoints(pointA, pointB);
        const bearingBtoA = bearingBetweenPoints(pointB, pointA);
        rulerState.lineHalo.setLatLngs([pointA, pointB]);
        rulerState.lineCore.setLatLngs([pointA, pointB]);
        rulerState.markerA.setTooltipContent(buildRulerTooltipHtml("A -> B", bearingAtoB, distanceMeters));
        rulerState.markerB.setTooltipContent(buildRulerTooltipHtml("B -> A", bearingBtoA, distanceMeters));
    }

    function anchorRulerToFrameIfIdle() {
        if (!rulerState || rulerState.measurementActive) {
            return;
        }
        const [anchorPointA, anchorPointB] = buildRulerInitialPoints();
        rulerState.markerA.setLatLng(anchorPointA);
        rulerState.markerB.setLatLng(anchorPointB);
        rulerState.lineHalo.setLatLngs([anchorPointA, anchorPointB]);
        rulerState.lineCore.setLatLngs([anchorPointA, anchorPointB]);
    }

    function initializeRuler() {
        const [startPointA, startPointB] = buildRulerInitialPoints();
        const rulerLineHalo = window.L.polyline([startPointA, startPointB], {
            color: "rgba(255, 255, 255, 0.98)",
            weight: 8,
            opacity: 0.98,
            lineCap: "round",
            lineJoin: "round",
            interactive: false,
        });
        const rulerLineCore = window.L.polyline([startPointA, startPointB], {
            color: "#0078ff",
            weight: 3.4,
            opacity: 1,
            lineCap: "round",
            lineJoin: "round",
            interactive: false,
        });
        const markerA = window.L.marker(startPointA, {
            icon: buildRulerPickerIcon("A"),
            draggable: true,
            keyboard: false,
            autoPan: true,
            zIndexOffset: 1000,
        });
        const markerB = window.L.marker(startPointB, {
            icon: buildRulerPickerIcon("B"),
            draggable: true,
            keyboard: false,
            autoPan: true,
            zIndexOffset: 1000,
        });
        markerA.bindTooltip("", {
            direction: "top",
            className: "aprs-tooltip map-ruler-tooltip",
            opacity: 0.96,
            permanent: true,
            sticky: false,
            offset: [-28, -10],
        });
        markerB.bindTooltip("", {
            direction: "top",
            className: "aprs-tooltip map-ruler-tooltip",
            opacity: 0.96,
            permanent: true,
            sticky: false,
            offset: [28, -10],
        });

        markerA.on("dragstart", function () {
            if (rulerState) {
                rulerState.measurementActive = true;
            }
        });
        markerB.on("dragstart", function () {
            if (rulerState) {
                rulerState.measurementActive = true;
            }
        });
        markerA.on("drag dragend", syncRulerMeasurements);
        markerB.on("drag dragend", syncRulerMeasurements);

        rulerLayer.addLayer(rulerLineHalo);
        rulerLayer.addLayer(rulerLineCore);
        rulerLayer.addLayer(markerA);
        rulerLayer.addLayer(markerB);
        rulerState = {
            lineHalo: rulerLineHalo,
            lineCore: rulerLineCore,
            markerA,
            markerB,
            measurementActive: false,
        };
        anchorRulerToFrameIfIdle();
        syncRulerMeasurements();
    }

    function syncStatus() {
        const center = map.getCenter();
        if (centerOutput) {
            centerOutput.textContent = `${formatCoordinate(center.lat)}, ${formatCoordinate(center.lng)}`;
        }
        if (zoomOutput) {
            zoomOutput.textContent = String(map.getZoom());
        }
        root.dispatchEvent(new window.CustomEvent(mapViewRefreshEventName, {
            detail: {
                center_latitude: center.lat,
                center_longitude: center.lng,
                visible_radius_km: visibleMapRadiusKm(),
                zoom: map.getZoom(),
            },
        }));
    }

    function persistView() {
        const center = map.getCenter();
        window.localStorage.setItem(mapViewStorageKey, JSON.stringify({
            latitude: center.lat,
            longitude: center.lng,
            zoom: map.getZoom(),
        }));
    }

    if (resetButton) {
        resetButton.addEventListener("click", function () {
            window.localStorage.removeItem(mapViewStorageKey);
            map.setView([defaultView.latitude, defaultView.longitude], defaultView.zoom);
        });
    }

    if (maskOpacitySelect) {
        applyMaskOpacity(resolveDefaultMaskOpacity());
        maskOpacitySelect.addEventListener("change", function () {
            applyMaskOpacity(Number.parseInt(maskOpacitySelect.value || "", 10));
        });
    }
    applyCoverageFillOpacity(resolveDefaultCoverageFillOpacity());
    if (coverageFillOpacitySelect) {
        coverageFillOpacitySelect.addEventListener("change", function () {
            applyCoverageFillOpacity(Number.parseInt(coverageFillOpacitySelect.value || "", 10));
            applyLatestMapData({ forceRender: true });
        });
    }
    applyCoverageOutlineOpacity(resolveDefaultCoverageOutlineOpacity());
    if (coverageOutlineOpacitySelect) {
        coverageOutlineOpacitySelect.addEventListener("change", function () {
            applyCoverageOutlineOpacity(Number.parseInt(coverageOutlineOpacitySelect.value || "", 10));
            applyLatestMapData({ forceRender: true });
        });
    }
    applyTracksToggleState(resolveTracksVisible());
    if (toggleTracksButton) {
        toggleTracksButton.addEventListener("click", function () {
            applyTracksToggleState(!tracksVisible);
            if (tracksVisible && latestTrackRevision !== latestStationRevision) {
                void loadMobileTracks(latestStationRevision);
            }
            applyLatestMapData({ forceRender: true });
        });
    }
    applyCoverageToggleState(resolveCoverageVisible());
    if (toggleCoverageButton) {
        toggleCoverageButton.addEventListener("click", function () {
            applyCoverageToggleState(!coverageVisible);
            if (coverageVisible && latestStationDetailsRevision !== latestStationRevision) {
                void loadStationDetails(latestStationRevision);
            }
            applyLatestMapData({ forceRender: true });
        });
    }
    setAlertsOverlayOpen(false);
    if (toggleAlarmAreasButton) {
        toggleAlarmAreasButton.addEventListener("click", function () {
            setAlertsOverlayOpen(!alertsOverlayOpen);
        });
    }
    if (alertsOverlayClose) {
        alertsOverlayClose.addEventListener("click", function () {
            setAlertsOverlayOpen(false);
            toggleAlarmAreasButton?.focus();
        });
    }
    positionAlertPanelBelowLeafletControls();
    window.addEventListener("resize", refreshAlertPanelLayout);
    applyRulerToggleState(resolveRulerVisible());
    if (toggleRulerButton) {
        toggleRulerButton.addEventListener("click", function () {
            applyRulerToggleState(!rulerVisible);
        });
    }

    const themeObserver = new window.MutationObserver(function (mutations) {
        for (const mutation of mutations) {
            if (mutation.type === "attributes" && mutation.attributeName === "data-theme") {
                applyMaskOpacity(resolveDefaultMaskOpacity());
                applyLatestMapData({ forceRender: true });
                break;
            }
        }
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    let mapResizeFrameRequest = null;
    function scheduleMapInvalidateSize() {
        if (mapResizeFrameRequest !== null) {
            return;
        }
        mapResizeFrameRequest = window.requestAnimationFrame(function () {
            mapResizeFrameRequest = null;
            map.invalidateSize();
        });
    }

    window.addEventListener("resize", function () {
        scheduleMapInvalidateSize();
    });

    if (mapStage && typeof window.ResizeObserver === "function") {
        let previousWidth = mapStage.clientWidth;
        let previousHeight = mapStage.clientHeight;
        const stageResizeObserver = new window.ResizeObserver(function () {
            const nextWidth = mapStage.clientWidth;
            const nextHeight = mapStage.clientHeight;
            if (nextWidth <= 0 || nextHeight <= 0) {
                return;
            }
            if (nextWidth === previousWidth && nextHeight === previousHeight) {
                return;
            }
            previousWidth = nextWidth;
            previousHeight = nextHeight;
            scheduleMapInvalidateSize();
        });
        stageResizeObserver.observe(mapStage);
        window.addEventListener("beforeunload", function () {
            stageResizeObserver.disconnect();
        }, { once: true });
    }

    function tooltipHtml(station) {
        const lines = [];
        const detailHref = station.detail_href && station.detail_href.startsWith("/") ? `${rootPath}${station.detail_href}` : (station.detail_href || "");
        const title = detailHref
            ? `<a class="map-station-link" href="${escapeHtml(detailHref)}">${escapeHtml(station.display_callsign || station.callsign || "")}</a>`
            : `<strong>${escapeHtml(station.display_callsign || station.callsign || "")}</strong>`;
        const heardAt = formatTimestamp(station.last_heard_at);
        const heardAge = formatAge(station.last_heard_age_s);
        lines.push(title);
        if (station.aprs_device_short) {
            lines.push(`<span><strong>${escapeHtml(i18n.aprsClient)}:</strong> ${escapeHtml(station.aprs_device_short)}</span>`);
        }
        if (heardAt) {
            lines.push(`<span><strong>${escapeHtml(station.activity_label || i18n.lastActivity)}:</strong> ${escapeHtml(heardAt)}</span>`);
        }
        if (heardAge) {
            lines.push(`<span><strong>${escapeHtml(station.activity_age_label || i18n.age)}:</strong> ${escapeHtml(heardAge)}</span>`);
        }
        if (station.source) {
            lines.push(`<span><strong>${escapeHtml(i18n.source)}:</strong> ${escapeHtml(station.source)}</span>`);
        }
        if (station.path) {
            lines.push(`<span><strong>${escapeHtml(i18n.path)}:</strong> ${escapeHtml(station.path)}</span>`);
        }
        if (Number.isFinite(station.distance_km)) {
            lines.push(`<span><strong>${escapeHtml(i18n.distance)}:</strong> ${escapeHtml(formatDistance(station.distance_km))}</span>`);
        }
        if (station.comment) {
            lines.push(`<span><strong>${escapeHtml(i18n.comment)}:</strong> ${escapeHtml(station.comment)}</span>`);
        }
        if (Number.isFinite(station.altitude)) {
            lines.push(`<span><strong>${escapeHtml(i18n.altitude)}:</strong> ${escapeHtml(`${station.altitude} m`)}</span>`);
        }
        const decodedData = renderDecodedData(station.data);
        if (decodedData) {
            lines.push(`<div class="map-station-tooltip-data-section">${decodedData}</div>`);
        }
        return `<div class="map-station-tooltip">${lines.join("")}</div>`;
    }

    function resolveSymbolOverlay(symbolTable) {
        const normalized = String(symbolTable || "").trim();
        if (!normalized || normalized === "/" || normalized === "\\") {
            return "";
        }
        return normalized.charAt(0);
    }

    function buildStationIcon(station) {
        const staleClass = station.stale ? " map-station-icon-stale" : "";
        const iconPath = station.symbol_icon ? `${staticRoot}${station.symbol_icon}` : `${staticRoot}${aprsSymbolIconFallback}`;
        const iconAlt = station.symbol_table || station.symbol_code ? `${station.symbol_table || ""}${station.symbol_code || ""}` : "";
        const overlay = resolveSymbolOverlay(station.symbol_table);
        return window.L.divIcon({
            className: `map-station-icon${staleClass}`,
            html: `
                <img class="map-station-aprs-icon" src="${escapeHtml(iconPath)}" alt="${escapeHtml(iconAlt)}">
                ${overlay ? `<span class="map-station-aprs-overlay" aria-hidden="true">${escapeHtml(overlay)}</span>` : ""}
                <span class="map-station-label">${escapeHtml(station.display_callsign || station.callsign || "")}</span>
            `,
            iconSize: aprsIconSize,
            iconAnchor: aprsIconAnchor,
            tooltipAnchor: [0, -10],
        });
    }

    const callsignColorPalette = Object.freeze([
        { hue: 302, saturation: 100, lightness: 56 },
        { hue: 188, saturation: 100, lightness: 51 },
        { hue: 272, saturation: 94, lightness: 63 },
        { hue: 334, saturation: 100, lightness: 60 },
        { hue: 203, saturation: 100, lightness: 55 },
        { hue: 287, saturation: 90, lightness: 68 },
        { hue: 352, saturation: 100, lightness: 63 },
        { hue: 170, saturation: 100, lightness: 46 },
        { hue: 248, saturation: 100, lightness: 67 },
        { hue: 318, saturation: 100, lightness: 54 },
        { hue: 194, saturation: 100, lightness: 47 },
        { hue: 283, saturation: 100, lightness: 50 },
    ]);
    const callsignColorVariants = Object.freeze([
        { hueShift: 0, saturationShift: 0, lightnessShift: 0 },
        { hueShift: 6, saturationShift: -5, lightnessShift: 7 },
        { hueShift: -7, saturationShift: 5, lightnessShift: -6 },
    ]);

    function clampNumber(value, minValue, maxValue) {
        return Math.max(minValue, Math.min(maxValue, value));
    }

    function hashCallsign(callsign) {
        const value = String(callsign || "").trim().toUpperCase();
        let hash = 2166136261;
        for (let index = 0; index < value.length; index += 1) {
            hash ^= value.charCodeAt(index);
            hash = Math.imul(hash, 16777619) >>> 0;
        }
        return hash >>> 0;
    }

    // Bias the palette toward neon magenta/cyan/violet tones that rarely occur on default OSM tiles.
    function colorForCallsign(callsign) {
        const hash = hashCallsign(callsign);
        const base = callsignColorPalette[hash % callsignColorPalette.length];
        const variant = callsignColorVariants[(hash >>> 8) % callsignColorVariants.length];
        const hue = (base.hue + variant.hueShift + (((hash >>> 16) % 5) - 2) + 360) % 360;
        const saturation = clampNumber(base.saturation + variant.saturationShift, 86, 100);
        const lightness = clampNumber(base.lightness + variant.lightnessShift, 44, 72);
        return `hsl(${hue} ${saturation}% ${lightness}%)`;
    }

    function overlayContrastColor() {
        return currentThemeName() === "light"
            ? "rgba(16, 24, 40, 0.82)"
            : "rgba(255, 255, 255, 0.92)";
    }

    function overlayContrastOpacity() {
        return currentThemeName() === "light" ? 0.72 : 0.82;
    }

    function phgDirectionAzimuth(directionValue) {
        if (directionValue === null || directionValue === undefined) {
            return null;
        }
        const normalized = String(directionValue).trim().toUpperCase();
        if (!normalized || normalized === "OMNI" || normalized === "0") {
            return null;
        }
        const codeMap = Object.freeze({
            1: 45,
            2: 90,
            3: 135,
            4: 180,
            5: 225,
            6: 270,
            7: 315,
            8: 0,
        });
        if (Object.prototype.hasOwnProperty.call(codeMap, normalized)) {
            return codeMap[normalized];
        }
        const directionMap = Object.freeze({
            N: 0,
            NE: 45,
            E: 90,
            SE: 135,
            S: 180,
            SW: 225,
            W: 270,
            NW: 315,
        });
        if (Object.prototype.hasOwnProperty.call(directionMap, normalized)) {
            return directionMap[normalized];
        }
        return null;
    }

    function destinationPoint(latitude, longitude, bearingDeg, distanceMeters) {
        const earthRadiusMeters = 6371000;
        const angularDistance = distanceMeters / earthRadiusMeters;
        const bearingRad = (bearingDeg * Math.PI) / 180;
        const latitudeRad = (latitude * Math.PI) / 180;
        const longitudeRad = (longitude * Math.PI) / 180;
        const sinLatitude = Math.sin(latitudeRad);
        const cosLatitude = Math.cos(latitudeRad);
        const sinAngularDistance = Math.sin(angularDistance);
        const cosAngularDistance = Math.cos(angularDistance);

        const targetLatitudeRad = Math.asin(
            (sinLatitude * cosAngularDistance)
            + (cosLatitude * sinAngularDistance * Math.cos(bearingRad))
        );
        const targetLongitudeRad = longitudeRad + Math.atan2(
            Math.sin(bearingRad) * sinAngularDistance * cosLatitude,
            cosAngularDistance - (sinLatitude * Math.sin(targetLatitudeRad))
        );
        const targetLongitudeDeg = ((((targetLongitudeRad * 180) / Math.PI) + 540) % 360) - 180;
        return [(targetLatitudeRad * 180) / Math.PI, targetLongitudeDeg];
    }

    function buildPhgCardioidPoints(station, azimuthDeg, radiusMeters) {
        const sampleCount = 96;
        const points = [];
        const backwardOffsetMeters = radiusMeters / 3;
        const cardioidRadiusMeters = radiusMeters + backwardOffsetMeters;
        const azimuthRad = (azimuthDeg * Math.PI) / 180;
        const cosAzimuth = Math.cos(azimuthRad);
        const sinAzimuth = Math.sin(azimuthRad);

        for (let index = 0; index < sampleCount; index += 1) {
            const theta = (index / sampleCount) * Math.PI * 2;
            const radialDistance = cardioidRadiusMeters * ((1 + Math.cos(theta)) / 2);
            const localX = radialDistance * Math.sin(theta);
            const localY = (radialDistance * Math.cos(theta)) - backwardOffsetMeters;
            const rotatedX = (localX * cosAzimuth) + (localY * sinAzimuth);
            const rotatedY = (-localX * sinAzimuth) + (localY * cosAzimuth);
            const distanceMeters = Math.hypot(rotatedX, rotatedY);
            if (distanceMeters < 0.01) {
                points.push([station.latitude, station.longitude]);
                continue;
            }
            const bearingDeg = (Math.atan2(rotatedX, rotatedY) * 180) / Math.PI;
            points.push(destinationPoint(station.latitude, station.longitude, bearingDeg, distanceMeters));
        }
        if (points.length > 0) {
            points.push(points[0]);
        }
        return points;
    }

    function buildPhgCoverageLayer(station, coverageColor) {
        const radiusMeters = Number(station.phg_range_km) * 1000;
        const coverageShapeOptions = {
            radius: radiusMeters,
            color: coverageColor,
            fillColor: coverageColor,
            opacity: coverageOutlineOpacity,
            fillOpacity: coverageFillOpacity,
            stroke: true,
            weight: 1.5,
            interactive: false,
        };
        const fallbackCircle = window.L.circle([station.latitude, station.longitude], coverageShapeOptions);
        const azimuth = phgDirectionAzimuth(station.phg_direction);
        if (azimuth === null || !Number.isFinite(azimuth)) {
            return fallbackCircle;
        }
        const cardioidPoints = buildPhgCardioidPoints(station, azimuth, radiusMeters);
        if (cardioidPoints.length < 4) {
            return fallbackCircle;
        }
        return window.L.polygon(cardioidPoints, {
            color: coverageColor,
            fillColor: coverageColor,
            opacity: coverageOutlineOpacity,
            fillOpacity: coverageFillOpacity,
            stroke: true,
            weight: 1.5,
            interactive: false,
        });
    }

    function markerSignature(station) {
        return [
            Number(station.latitude),
            Number(station.longitude),
            String(station.symbol_icon || ""),
            String(station.symbol_table || ""),
            String(station.symbol_code || ""),
            String(station.display_callsign || station.callsign || ""),
            String(station.detail_href || ""),
            station.stale ? "1" : "0",
        ].join("|");
    }

    function tooltipSignature(station) {
        return [
            String(station.display_callsign || station.callsign || ""),
            String(station.last_heard_at || ""),
            String(station.activity_label || ""),
            String(station.activity_age_label || ""),
            String(station.source || ""),
            String(station.path || ""),
            Number.isFinite(station.distance_km) ? String(station.distance_km) : "",
            String(station.comment || ""),
            Number.isFinite(station.altitude) ? String(station.altitude) : "",
            Array.isArray(station.data)
                ? station.data.map((item) => `${item.label || ""}:${item.value || ""}:${item.icon || ""}`).join(";")
                : "",
            String(station.aprs_device_short || ""),
        ].join("|");
    }

    function coverageSignature(station) {
        return [
            Number(station.latitude),
            Number(station.longitude),
            Number(station.phg_range_km),
            String(station.phg_direction || ""),
            String(station.display_callsign || station.callsign || ""),
            String(coverageFillOpacity),
            String(coverageOutlineOpacity),
        ].join("|");
    }

    function trackSignature(track) {
        return [
            String(track.display_callsign || ""),
            String(currentThemeName()),
            (track.points || []).map((point) => (
                `${point.interface_id || ""}:${point.latitude}:${point.longitude}:${point.heard_at || ""}`
            )).join(";"),
        ].join("|");
    }

    function syncMarkerInteractions(marker, station, tooltipContent) {
        if (marker.getTooltip()) {
            marker.setTooltipContent(tooltipContent);
        } else {
            marker.bindTooltip(tooltipContent, {
                direction: "top",
                className: "aprs-tooltip",
                opacity: 0.96,
                sticky: true,
            });
        }
        marker.off("click");
        if (station.detail_href) {
            marker.on("click", function () {
                window.location.href = station.detail_href;
            });
        }
    }

    function removeMissingLayerRecords(recordsByKey, layerGroup, nextKeys) {
        for (const [key, record] of Array.from(recordsByKey.entries())) {
            if (nextKeys.has(key)) {
                continue;
            }
            layerGroup.removeLayer(record.layer);
            recordsByKey.delete(key);
        }
    }

    function buildTrackLayer(track) {
        const group = window.L.layerGroup();
        const points = (track.points || []).filter((point) => (
            Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
        ));
        if (points.length < 2) {
            return group;
        }
        const trackColor = colorForCallsign(track.display_callsign || "");
        const haloPolyline = window.L.polyline(
            points.map((point) => ([point.latitude, point.longitude])),
            {
                color: overlayContrastColor(),
                weight: 3,
                opacity: overlayContrastOpacity(),
                lineJoin: "round",
                lineCap: "round",
                interactive: false,
            }
        );
        const polyline = window.L.polyline(
            points.map((point) => ([point.latitude, point.longitude])),
            {
                color: trackColor,
                weight: 1.75,
                opacity: 0.96,
                lineJoin: "round",
                lineCap: "round",
                interactive: false,
            }
        );
        group.addLayer(haloPolyline);
        group.addLayer(polyline);
        for (const point of points.slice(0, -1)) {
            const dot = window.L.circleMarker([point.latitude, point.longitude], {
                radius: 4,
                color: overlayContrastColor(),
                fillColor: trackColor,
                fillOpacity: 0.94,
                opacity: 0.96,
                weight: 2,
                interactive: false,
            });
            group.addLayer(dot);
        }
        return group;
    }

    function reconcileMarkers(stations) {
        const nextKeys = new Set();
        for (const station of stations || []) {
            if (!Number.isFinite(station.latitude) || !Number.isFinite(station.longitude)) {
                continue;
            }
            const key = stationIdentityKey(station);
            if (!key) {
                continue;
            }
            nextKeys.add(key);
            const nextMarkerSignature = markerSignature(station);
            const nextTooltipSignature = tooltipSignature(station);
            const nextTooltipContent = tooltipHtml(station);
            const existing = markerLayersByKey.get(key);
            if (!existing) {
                const marker = window.L.marker([station.latitude, station.longitude], {
                    icon: buildStationIcon(station),
                    keyboard: false,
                });
                syncMarkerInteractions(marker, station, nextTooltipContent);
                markerLayerGroup.addLayer(marker);
                markerLayersByKey.set(key, {
                    layer: marker,
                    markerSignature: nextMarkerSignature,
                    tooltipSignature: nextTooltipSignature,
                });
                continue;
            }
            if (existing.markerSignature !== nextMarkerSignature) {
                existing.layer.setLatLng([station.latitude, station.longitude]);
                existing.layer.setIcon(buildStationIcon(station));
                existing.markerSignature = nextMarkerSignature;
                syncMarkerInteractions(existing.layer, station, nextTooltipContent);
                existing.tooltipSignature = nextTooltipSignature;
                continue;
            }
            if (existing.tooltipSignature !== nextTooltipSignature) {
                syncMarkerInteractions(existing.layer, station, nextTooltipContent);
                existing.tooltipSignature = nextTooltipSignature;
            }
        }
        removeMissingLayerRecords(markerLayersByKey, markerLayerGroup, nextKeys);
    }

    function reconcileCoverage(stations) {
        const nextKeys = new Set();
        if (coverageVisible) {
            for (const station of stations || []) {
                if (!Number.isFinite(station.latitude) || !Number.isFinite(station.longitude)) {
                    continue;
                }
                if (!Number.isFinite(station.phg_range_km) || station.phg_range_km <= 0) {
                    continue;
                }
                const key = stationIdentityKey(station);
                if (!key) {
                    continue;
                }
                nextKeys.add(key);
                const nextCoverageSignature = coverageSignature(station);
                const existing = coverageLayersByKey.get(key);
                if (existing && existing.signature === nextCoverageSignature) {
                    continue;
                }
                if (existing) {
                    coverageLayerGroup.removeLayer(existing.layer);
                    coverageLayersByKey.delete(key);
                }
                const coverageColor = colorForCallsign(station.display_callsign || station.callsign || "");
                const layer = buildPhgCoverageLayer(station, coverageColor);
                if (!layer) {
                    continue;
                }
                coverageLayerGroup.addLayer(layer);
                coverageLayersByKey.set(key, {
                    layer,
                    signature: nextCoverageSignature,
                });
            }
        }
        removeMissingLayerRecords(coverageLayersByKey, coverageLayerGroup, nextKeys);
    }

    function reconcileTracks(mobileTracks) {
        const nextKeys = new Set();
        if (tracksVisible) {
            for (const track of mobileTracks || []) {
                const points = (track.points || []).filter((point) => (
                    Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
                ));
                if (points.length < 2) {
                    continue;
                }
                const key = String(track.display_callsign || "").trim();
                if (!key) {
                    continue;
                }
                nextKeys.add(key);
                const nextTrackSignature = trackSignature(track);
                const existing = trackLayersByKey.get(key);
                if (existing && existing.signature === nextTrackSignature) {
                    continue;
                }
                if (existing) {
                    trackLayerGroup.removeLayer(existing.layer);
                    trackLayersByKey.delete(key);
                }
                const layer = buildTrackLayer(track);
                trackLayerGroup.addLayer(layer);
                trackLayersByKey.set(key, {
                    layer,
                    signature: nextTrackSignature,
                });
            }
        }
        removeMissingLayerRecords(trackLayersByKey, trackLayerGroup, nextKeys);
    }

    function renderStations(stations, mobileTracks) {
        reconcileCoverage(stations);
        reconcileTracks(mobileTracks);
        reconcileMarkers(stations);
    }

    async function loadStationDetails(expectedRevision) {
        const targetRevision = normalizeRevision(expectedRevision);
        if (!stationDetailsEndpoint || !targetRevision) {
            return;
        }
        if (latestStationDetailsRevision === targetRevision || detailsLoadingRevision === targetRevision) {
            return;
        }
        detailsLoadingRevision = targetRevision;
        try {
            const response = await fetch(stationDetailsEndpoint, {
                headers: { Accept: "application/json" },
            });
            if (!response.ok) {
                return;
            }
            const payload = await response.json();
            const payloadRevision = normalizeRevision(payload.revision);
            if (!payloadRevision || payloadRevision !== targetRevision || payloadRevision !== latestStationRevision) {
                return;
            }
            latestStations = mergeStationDetails(latestStations, payload.stations || []);
            latestInterfaces = mergeInterfaces(payload.interfaces || [], latestInterfaces);
            latestStationDetailsRevision = payloadRevision;
            applyLatestMapData({ forceRender: true });
        } catch (_error) {
        } finally {
            if (detailsLoadingRevision === targetRevision) {
                detailsLoadingRevision = "";
            }
        }
    }

    async function loadMobileTracks(expectedRevision) {
        const targetRevision = normalizeRevision(expectedRevision);
        if (!mobileTracksEndpoint || !targetRevision) {
            return;
        }
        if (latestTrackRevision === targetRevision || tracksLoadingRevision === targetRevision) {
            return;
        }
        tracksLoadingRevision = targetRevision;
        try {
            const response = await fetch(mobileTracksEndpoint, {
                headers: { Accept: "application/json" },
            });
            if (!response.ok) {
                return;
            }
            const payload = await response.json();
            const payloadRevision = normalizeRevision(payload.revision);
            if (!payloadRevision || payloadRevision !== targetRevision || payloadRevision !== latestStationRevision) {
                return;
            }
            latestMobileTracks = payload.mobile_tracks || [];
            latestInterfaces = mergeInterfaces(latestInterfaces, payload.interfaces || []);
            latestTrackRevision = payloadRevision;
            applyLatestMapData({ forceRender: true });
        } catch (_error) {
        } finally {
            if (tracksLoadingRevision === targetRevision) {
                tracksLoadingRevision = "";
            }
        }
    }

    function scheduleDeferredMapDataLoad() {
        const targetRevision = normalizeRevision(latestStationRevision);
        if (!targetRevision) {
            return;
        }
        window.requestAnimationFrame(function () {
            if (normalizeRevision(latestStationRevision) !== targetRevision) {
                return;
            }
            if (latestStationDetailsRevision !== targetRevision) {
                void loadStationDetails(targetRevision);
            }
            if (tracksVisible && latestTrackRevision !== targetRevision) {
                void loadMobileTracks(targetRevision);
            }
        });
    }

    async function refreshStations() {
        try {
            const response = await fetch(stationsEndpoint, {
                headers: { Accept: "application/json" },
            });
            if (!response.ok) {
                return;
            }
            const payload = await response.json();
            reconcileAlertAreas(payload.alert_areas);
            const stations = payload.stations || [];
            const interfaces = payload.interfaces || [];
            const payloadRevision = normalizeRevision(payload.revision);
            const revisionChanged = payloadRevision !== latestStationRevision;
            latestStations = (latestStationDetailsRevision === payloadRevision)
                ? mergeStationDetails(stations, latestStations)
                : mergeStationSupplementalData(stations, latestStations);
            latestStationRevision = payloadRevision;
            latestInterfaces = revisionChanged
                ? (Array.isArray(interfaces) ? interfaces : [])
                : mergeInterfaces(Array.isArray(interfaces) ? interfaces : [], latestInterfaces);
            if (revisionChanged) {
                latestMobileTracks = retainVisibleMobileTracks(latestMobileTracks, latestStations);
            }
            applyLatestMapData({ forceRender: revisionChanged });
            scheduleDeferredMapDataLoad();
        } catch (_error) {
        }
    }

    function startPolling() {
        if (refreshTimer) {
            window.clearInterval(refreshTimer);
        }
        refreshTimer = window.setInterval(refreshStations, 10000);
    }

    map.on("moveend zoomend", function () {
        anchorRulerToFrameIfIdle();
        syncStatus();
        persistView();
    });
    map.on("resize", function () {
        anchorRulerToFrameIfIdle();
        syncStatus();
    });
    map.whenReady(function () {
        window.setTimeout(function () {
            scheduleMapInvalidateSize();
            initializeRuler();
        }, 0);
    });
    refreshStations();
    startPolling();
    syncStatus();
})();
