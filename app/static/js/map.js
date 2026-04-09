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
    const tileUrl = root.dataset.tileUrl || "";
    const tileAttribution = root.dataset.tileAttribution || "";
    const tileSourceName = root.dataset.tileSourceName || "";

    const centerOutput = document.getElementById("map-center");
    const zoomOutput = document.getElementById("map-zoom");
    const tileSourceOutput = document.getElementById("map-tile-source");
    const mapCanvas = document.getElementById("map-canvas");
    const resetButton = document.getElementById("map-reset-view");
    const toggleTracksButton = document.getElementById("map-toggle-tracks");
    const toggleTracksIcon = document.getElementById("map-toggle-tracks-icon");
    const toggleCoverageButton = document.getElementById("map-toggle-coverage");
    const toggleCoverageIcon = document.getElementById("map-toggle-coverage-icon");
    const maskOpacitySelect = document.getElementById("map-mask-opacity");
    const staticRoot = root.dataset.staticRoot || "/static/";
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
    });
    const stationLayer = window.L.layerGroup();
    const mapViewStorageKey = "aprsbox-map-view";
    const mapTracksVisibleStorageKey = "aprsbox-map-tracks-visible";
    const mapCoverageVisibleStorageKey = "aprsbox-map-coverage-visible";
    const aprsIconSize = [20, 20];
    const aprsIconAnchor = [10, 10];
    let refreshTimer = null;
    let lastStationsSignature = "";
    let tracksVisible = true;
    let coverageVisible = true;
    let latestStations = [];
    let latestMobileTracks = [];

    function currentThemeName() {
        return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    }

    function maskOpacityStorageKey() {
        return `aprsbox-map-mask-opacity-${currentThemeName()}`;
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

    // Keep the tile endpoint configurable from the backend so the frontend can
    // switch later from the public development tiles to a local cache/proxy.
    window.L.tileLayer(tileUrl, {
        attribution: tileAttribution,
        maxZoom: 19,
    }).addTo(map);
    stationLayer.addTo(map);

    if (tileSourceOutput) {
        tileSourceOutput.textContent = tileSourceName;
    }

    function resolveDefaultMaskOpacity() {
        const storedOpacity = Number.parseInt(window.localStorage.getItem(maskOpacityStorageKey()) || "", 10);
        if (Number.isInteger(storedOpacity) && storedOpacity >= 0 && storedOpacity <= 100 && storedOpacity % 10 === 0) {
            return storedOpacity;
        }
        return 20;
    }

    function applyMaskOpacity(opacityPercent) {
        const normalizedOpacity = Number.isInteger(opacityPercent) && opacityPercent >= 0 && opacityPercent <= 100
            ? opacityPercent - (opacityPercent % 10)
            : 20;
        if (mapCanvas) {
            mapCanvas.style.setProperty("--map-pane-opacity", String(1 - (normalizedOpacity / 100)));
        }
        if (maskOpacitySelect) {
            maskOpacitySelect.value = String(normalizedOpacity);
        }
        window.localStorage.setItem(maskOpacityStorageKey(), String(normalizedOpacity));
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

    function formatTimestamp(value) {
        if (!value) {
            return "";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return String(value);
        }
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, "0");
        const day = String(date.getDate()).padStart(2, "0");
        const hour = String(date.getHours()).padStart(2, "0");
        const minute = String(date.getMinutes()).padStart(2, "0");
        return `${year}.${month}.${day} ${hour}:${minute}`;
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

    function syncStatus() {
        const center = map.getCenter();
        if (centerOutput) {
            centerOutput.textContent = `${formatCoordinate(center.lat)}, ${formatCoordinate(center.lng)}`;
        }
        if (zoomOutput) {
            zoomOutput.textContent = String(map.getZoom());
        }
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
    applyTracksToggleState(resolveTracksVisible());
    if (toggleTracksButton) {
        toggleTracksButton.addEventListener("click", function () {
            applyTracksToggleState(!tracksVisible);
            renderStations(latestStations, latestMobileTracks);
        });
    }
    applyCoverageToggleState(resolveCoverageVisible());
    if (toggleCoverageButton) {
        toggleCoverageButton.addEventListener("click", function () {
            applyCoverageToggleState(!coverageVisible);
            renderStations(latestStations, latestMobileTracks);
        });
    }

    const themeObserver = new window.MutationObserver(function (mutations) {
        for (const mutation of mutations) {
            if (mutation.type === "attributes" && mutation.attributeName === "data-theme") {
                applyMaskOpacity(resolveDefaultMaskOpacity());
                break;
            }
        }
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    window.addEventListener("resize", function () {
        map.invalidateSize();
    });

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
        if (station.destination) {
            lines.push(`<span><strong>${escapeHtml(i18n.destination)}:</strong> ${escapeHtml(station.destination)}</span>`);
        }
        if (Number.isFinite(station.distance_km)) {
            lines.push(`<span><strong>${escapeHtml(i18n.distance)}:</strong> ${escapeHtml(formatDistance(station.distance_km))}</span>`);
        }
        if (station.comment) {
            lines.push(`<span><strong>${escapeHtml(i18n.comment)}:</strong> ${escapeHtml(station.comment)}</span>`);
        }
        if (Number.isFinite(station.speed)) {
            lines.push(`<span><strong>${escapeHtml(i18n.speed)}:</strong> ${escapeHtml(`${station.speed} km/h`)}</span>`);
        }
        if (Number.isFinite(station.course)) {
            lines.push(`<span><strong>${escapeHtml(i18n.course)}:</strong> ${escapeHtml(`${station.course}°`)}</span>`);
        }
        if (Number.isFinite(station.altitude)) {
            lines.push(`<span><strong>${escapeHtml(i18n.altitude)}:</strong> ${escapeHtml(`${station.altitude} m`)}</span>`);
        }
        if (station.packet_type) {
            lines.push(`<span><strong>${escapeHtml(i18n.packetType)}:</strong> ${escapeHtml(station.packet_type)}</span>`);
        }
        return `<div class="map-station-tooltip">${lines.join("")}</div>`;
    }

    function buildStationIcon(station) {
        const staleClass = station.stale ? " map-station-icon-stale" : "";
        const iconPath = station.symbol_icon ? `${staticRoot}${station.symbol_icon}` : `${staticRoot}icons/verG/x.gif`;
        const iconAlt = station.symbol_table || station.symbol_code ? `${station.symbol_table || ""}${station.symbol_code || ""}` : "";
        return window.L.divIcon({
            className: `map-station-icon${staleClass}`,
            html: `
                <img class="map-station-aprs-icon" src="${escapeHtml(iconPath)}" alt="${escapeHtml(iconAlt)}">
                <span class="map-station-label">${escapeHtml(station.display_callsign || station.callsign || "")}</span>
            `,
            iconSize: aprsIconSize,
            iconAnchor: aprsIconAnchor,
            tooltipAnchor: [0, -10],
        });
    }

    function stationsSignature(stations) {
        return JSON.stringify((stations || []).map((station) => ([
            station.display_callsign || station.callsign || "",
            station.last_heard_at || "",
            station.latitude,
            station.longitude,
            station.symbol_icon || "",
            station.comment || "",
            station.distance_km,
            station.stale,
        ])));
    }

    function mobileTracksSignature(mobileTracks) {
        return JSON.stringify((mobileTracks || []).map((track) => ([
            track.display_callsign || "",
            (track.points || []).map((point) => ([
                point.latitude,
                point.longitude,
                point.heard_at || "",
            ])),
        ])));
    }

    function colorForCallsign(callsign) {
        const value = String(callsign || "");
        let hash = 0;
        for (let index = 0; index < value.length; index += 1) {
            hash = ((hash * 31) + value.charCodeAt(index)) >>> 0;
        }
        const hue = hash % 360;
        return `hsl(${hue} 80% 52%)`;
    }

    function renderStations(stations, mobileTracks) {
        stationLayer.clearLayers();
        if (coverageVisible) {
            for (const station of stations || []) {
                if (!Number.isFinite(station.latitude) || !Number.isFinite(station.longitude)) {
                    continue;
                }
                if (!Number.isFinite(station.phg_range_km) || station.phg_range_km <= 0) {
                    continue;
                }
                const coverageColor = colorForCallsign(station.display_callsign || station.callsign || "");
                const coverageCircle = window.L.circle([station.latitude, station.longitude], {
                    radius: station.phg_range_km * 1000,
                    color: coverageColor,
                    fillColor: coverageColor,
                    opacity: 0.2,
                    fillOpacity: 0.2,
                    weight: 1,
                    interactive: false,
                });
                stationLayer.addLayer(coverageCircle);
            }
        }
        if (tracksVisible) {
            for (const track of mobileTracks || []) {
                const points = (track.points || []).filter((point) => (
                    Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
                ));
                if (points.length < 2) {
                    continue;
                }
                const trackColor = colorForCallsign(track.display_callsign || "");
                const polyline = window.L.polyline(
                    points.map((point) => ([point.latitude, point.longitude])),
                    {
                        color: trackColor,
                        weight: 3,
                        opacity: 0.85,
                        lineJoin: "round",
                        lineCap: "round",
                        interactive: false,
                    }
                );
                stationLayer.addLayer(polyline);
                for (const point of points.slice(0, -1)) {
                    const dot = window.L.circleMarker([point.latitude, point.longitude], {
                        radius: 3,
                        color: trackColor,
                        fillColor: trackColor,
                        fillOpacity: 0.65,
                        opacity: 0.95,
                        weight: 1,
                        interactive: false,
                    });
                    stationLayer.addLayer(dot);
                }
            }
        }
        for (const station of stations || []) {
            if (!Number.isFinite(station.latitude) || !Number.isFinite(station.longitude)) {
                continue;
            }
            const marker = window.L.marker([station.latitude, station.longitude], {
                icon: buildStationIcon(station),
                keyboard: false,
            });
            marker.bindTooltip(tooltipHtml(station), {
                direction: "top",
                className: "aprs-tooltip",
                opacity: 0.96,
                sticky: true,
            });
            if (station.detail_href) {
                marker.on("click", function () {
                    window.location.href = station.detail_href;
                });
            }
            stationLayer.addLayer(marker);
        }
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
            const stations = payload.stations || [];
            const mobileTracks = payload.mobile_tracks || [];
            latestStations = stations;
            latestMobileTracks = mobileTracks;
            const nextSignature = `${stationsSignature(stations)}|${mobileTracksSignature(mobileTracks)}`;
            if (nextSignature === lastStationsSignature) {
                return;
            }
            lastStationsSignature = nextSignature;
            renderStations(stations, mobileTracks);
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
        syncStatus();
        persistView();
    });
    map.whenReady(function () {
        window.setTimeout(function () {
            map.invalidateSize();
        }, 0);
    });
    refreshStations();
    startPolling();
    syncStatus();
})();
