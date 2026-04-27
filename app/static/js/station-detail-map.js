(function () {
    const pageRoot = document.getElementById("station-detail-page");
    const mapRoot = document.getElementById("station-detail-map-root");
    const mapCanvas = document.getElementById("station-detail-map-canvas");
    const mapPlaceholder = document.getElementById("station-map-placeholder");
    const title = document.getElementById("station-detail-title");
    const meta = document.getElementById("station-detail-meta");
    const fields = document.getElementById("station-detail-fields");
    const devicePanel = document.getElementById("station-device-identification-panel");
    const deviceRoot = document.getElementById("station-device-identification");
    const recentPackets = document.getElementById("station-recent-packets");
    const relatedSsids = document.getElementById("station-related-ssids");

    if (!pageRoot) {
        return;
    }

    const stationEndpoint = pageRoot.dataset.stationEndpoint || "";
    const staticRoot = pageRoot.dataset.staticRoot || "/static/";
    const rootPath = pageRoot.dataset.rootPath || "";
    const refreshMs = Number.parseInt(pageRoot.dataset.refreshMs || "30000", 10);
    const legacyMaskOpacityStorageKey = "aprsbox-map-mask-opacity";
    const aprsIconSize = [20, 20];
    const aprsIconAnchor = [10, 10];
    const i18n = Object.freeze({
        tocall: pageRoot.dataset.i18nTocall || "TOCALL",
        micE: pageRoot.dataset.i18nMicE || "Mic-E",
        identifiedSoftwareDevice: pageRoot.dataset.i18nIdentifiedSoftwareDevice || "Identified software/device",
        vendor: pageRoot.dataset.i18nVendor || "Vendor",
        model: pageRoot.dataset.i18nModel || "Model",
        classLabel: pageRoot.dataset.i18nClass || "Class",
        classDescription: pageRoot.dataset.i18nClassDescription || "Class description",
        os: pageRoot.dataset.i18nOs || "OS",
        capabilities: pageRoot.dataset.i18nCapabilities || "Capabilities",
        lastHeard: pageRoot.dataset.i18nLastHeard || "Last heard",
        source: pageRoot.dataset.i18nSource || "Source",
        path: pageRoot.dataset.i18nPath || "Path",
        noPacketHistory: pageRoot.dataset.i18nNoPacketHistory || "No stored packet history is available for this station yet.",
        noOtherSsids: pageRoot.dataset.i18nNoOtherSsids || "No other known SSIDs are currently available for {callsign}.",
        current: pageRoot.dataset.i18nCurrent || "current",
        timestamp: pageRoot.dataset.i18nTimestamp || "Timestamp",
        destination: pageRoot.dataset.i18nDestination || "Destination",
        rawPacket: pageRoot.dataset.i18nRawPacket || "Raw packet",
        latestRawPacket: pageRoot.dataset.i18nLatestRawPacket || "Latest raw packet",
    });
    let map = null;
    let marker = null;
    let tileLayer = null;
    let trackPolyline = null;
    let trackDots = [];
    const mapMaskPaneName = "map-mask-pane";
    let mapMaskPane = null;
    let mapMaskLayer = null;

    function currentThemeName() {
        return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    }

    function maskOpacityStorageKey() {
        return `aprsbox-map-mask-opacity-${currentThemeName()}`;
    }

    function maskLayerOpacityForMaskOpacity(opacityPercent) {
        return Math.max(0, Math.min(100, opacityPercent)) / 100;
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll("\"", "&quot;")
            .replaceAll("'", "&#39;");
    }

    function formatText(template, params = {}) {
        return String(template || "").replace(/\{(\w+)\}/g, function (match, key) {
            return Object.prototype.hasOwnProperty.call(params, key) ? String(params[key]) : match;
        });
    }

    function renderMeta(station) {
        if (!meta) return;
        const parts = [];
        if (station.last_heard_date) {
            let heard = `${escapeHtml(station.activity_label || i18n.lastHeard)} ${escapeHtml(station.last_heard_date)}`;
            if (station.last_heard_relative) {
                heard += ` <span class="muted">(${escapeHtml(station.last_heard_relative)})</span>`;
            }
            parts.push(heard);
        }
        if (station.source) {
            parts.push(`<span class="muted">• ${escapeHtml(i18n.source)} ${escapeHtml(station.source)}</span>`);
        }
        if (station.path) {
            parts.push(`<span class="muted">• ${escapeHtml(i18n.path)} ${escapeHtml(station.path)}</span>`);
        }
        meta.innerHTML = parts.join(" ");
    }

    function renderFields(station) {
        if (!fields) return;
        fields.innerHTML = (station.fields || []).map((field) => `
            <dt>${escapeHtml(field.label)}</dt>
            <dd>${field.label === i18n.latestRawPacket ? `<code>${escapeHtml(field.value)}</code>` : escapeHtml(field.value)}</dd>
        `).join("");
    }

    function renderAprsDevice(device) {
        if (!devicePanel || !deviceRoot) return;
        if (!device) {
            devicePanel.hidden = true;
            deviceRoot.innerHTML = "";
            return;
        }

        const identifierLabel = device.identifier_kind === "tocall" ? i18n.tocall : i18n.micE;
        const capabilityBlock = Array.isArray(device.features) && device.features.length
            ? `
                <div class="station-device-capabilities">
                    <span class="muted">${escapeHtml(i18n.capabilities)}</span>
                    <div class="station-device-capability-list">
                        ${device.features.map((feature) => `<span class="station-device-capability-chip">${escapeHtml(feature)}</span>`).join("")}
                    </div>
                </div>
            `
            : "";

        deviceRoot.innerHTML = `
            <div class="station-device-block">
                <p class="station-device-summary">
                    <strong>${escapeHtml(device.identified_as || device.short_name || "")}</strong>
                    ${device.vendor && device.vendor !== device.identified_as ? `<span class="muted">• ${escapeHtml(device.vendor)}</span>` : ""}
                </p>
                <dl class="details-grid station-device-grid">
                    ${device.actual_identifier ? `<dt>${identifierLabel}</dt><dd><code>${escapeHtml(device.actual_identifier)}</code></dd>` : ""}
                    <dt>${escapeHtml(i18n.identifiedSoftwareDevice)}</dt>
                    <dd>${escapeHtml(device.identified_as || device.short_name || "")}</dd>
                    ${device.vendor ? `<dt>${escapeHtml(i18n.vendor)}</dt><dd>${escapeHtml(device.vendor)}</dd>` : ""}
                    ${device.model ? `<dt>${escapeHtml(i18n.model)}</dt><dd>${escapeHtml(device.model)}</dd>` : ""}
                    ${device.class_label ? `<dt>${escapeHtml(i18n.classLabel)}</dt><dd>${escapeHtml(device.class_label)}</dd>` : ""}
                    ${device.class_description ? `<dt>${escapeHtml(i18n.classDescription)}</dt><dd>${escapeHtml(device.class_description)}</dd>` : ""}
                    ${device.os ? `<dt>${escapeHtml(i18n.os)}</dt><dd>${escapeHtml(device.os)}</dd>` : ""}
                </dl>
                ${capabilityBlock}
            </div>
        `;
        devicePanel.hidden = false;
    }

    function renderRecentPackets(packets) {
        if (!recentPackets) return;
        if (!packets || !packets.length) {
            recentPackets.innerHTML = `<p class="muted">${escapeHtml(i18n.noPacketHistory)}</p>`;
            return;
        }
        recentPackets.innerHTML = `
            <div class="table-wrap">
                <table class="data-table compact-table station-packets-table">
                    <colgroup>
                        <col style="width: 7rem">
                        <col style="width: 5.5rem">
                        <col style="width: 32rem">
                    </colgroup>
                    <thead>
                        <tr>
                            <th>${escapeHtml(i18n.timestamp)}</th>
                            <th>${escapeHtml(i18n.destination)}</th>
                            <th>${escapeHtml(i18n.rawPacket)}</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${packets.map((packet) => `
                            <tr>
                                <td>
                                    <div class="last-heard-cell">
                                        <span>${escapeHtml(packet.timestamp_label || "")}</span>
                                        ${packet.timestamp_relative ? `<span class="muted">${escapeHtml(packet.timestamp_relative)}</span>` : ""}
                                    </div>
                                </td>
                                <td>${escapeHtml(packet.destination || "")}</td>
                                <td><code>${escapeHtml(packet.raw_packet || "")}</code></td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>
        `;
    }

    function renderRelatedSsids(station, items) {
        if (!relatedSsids) return;
        if (!items || items.length <= 1) {
            relatedSsids.innerHTML = `<p class="muted">${escapeHtml(formatText(i18n.noOtherSsids, { callsign: station.base_callsign || "" }))}</p>`;
            return;
        }
        relatedSsids.innerHTML = `
            <div class="station-ssid-list">
                ${items.map((item) => `
                    <a href="${escapeHtml(item.detail_href && item.detail_href.startsWith("/") ? `${rootPath}${item.detail_href}` : (item.detail_href || "#"))}" class="station-ssid-chip${item.is_current ? " current" : ""}">
                        <span>${escapeHtml(item.display_callsign || "")}</span>
                        ${item.is_current ? `<span class="muted">${escapeHtml(i18n.current)}</span>` : ""}
                    </a>
                `).join("")}
            </div>
        `;
    }

    function resolveSymbolOverlay(symbolTable) {
        const normalized = String(symbolTable || "").trim();
        if (!normalized || normalized === "/" || normalized === "\\") {
            return "";
        }
        return normalized.charAt(0);
    }

    function buildIconHtml(displayCallsign, symbolIcon, symbolTable) {
        const overlay = resolveSymbolOverlay(symbolTable);
        return `
            <img class="map-station-aprs-icon" src="${escapeHtml(symbolIcon)}" alt="">
            ${overlay ? `<span class="map-station-aprs-overlay" aria-hidden="true">${escapeHtml(overlay)}</span>` : ""}
            <span class="map-station-label">${escapeHtml(displayCallsign)}</span>
        `;
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

    function parseTrackPoints(value) {
        if (!value) {
            return [];
        }
        try {
            const parsed = JSON.parse(value);
            if (!Array.isArray(parsed)) {
                return [];
            }
            return parsed.filter((item) => (
                item
                && Number.isFinite(Number(item.latitude))
                && Number.isFinite(Number(item.longitude))
            )).map((item) => ({
                latitude: Number(item.latitude),
                longitude: Number(item.longitude),
                heard_at: String(item.heard_at || ""),
            }));
        } catch (_error) {
            return [];
        }
    }

    function resolveMaskOpacity() {
        const storedOpacity = Number.parseInt(window.localStorage.getItem(maskOpacityStorageKey()) || "", 10);
        if (Number.isInteger(storedOpacity) && storedOpacity >= 0 && storedOpacity <= 100 && storedOpacity % 10 === 0) {
            return storedOpacity;
        }
        const legacyOpacity = Number.parseInt(window.localStorage.getItem(legacyMaskOpacityStorageKey) || "", 10);
        if (Number.isInteger(legacyOpacity) && legacyOpacity >= 0 && legacyOpacity <= 100 && legacyOpacity % 10 === 0) {
            return legacyOpacity;
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

    function applyMaskOpacity() {
        if (!mapCanvas) return;
        const opacityPercent = resolveMaskOpacity();
        const maskLayerOpacity = maskLayerOpacityForMaskOpacity(opacityPercent);
        if (!mapMaskLayer && map) {
            mapMaskLayer = ensureMapMaskLayer(map, mapCanvas);
        }
        if (mapMaskLayer) {
            mapMaskLayer.style.opacity = String(maskLayerOpacity);
        }
        mapCanvas.style.setProperty("--map-mask-layer-opacity", String(maskLayerOpacity));
    }

    function renderTrack(station, stationTrack) {
        if (!map) {
            return;
        }

        if (trackPolyline) {
            map.removeLayer(trackPolyline);
            trackPolyline = null;
        }
        for (const dot of trackDots) {
            map.removeLayer(dot);
        }
        trackDots = [];

        const points = Array.isArray(stationTrack?.points) ? stationTrack.points : [];
        if (points.length < 2) {
            return;
        }

        const trackColor = colorForCallsign(station.display_callsign || "");
        trackPolyline = window.L.polyline(
            points.map((point) => ([Number(point.latitude), Number(point.longitude)])),
            {
                color: trackColor,
                weight: 3,
                opacity: 0.85,
                lineJoin: "round",
                lineCap: "round",
                interactive: false,
            }
        ).addTo(map);

        for (const point of points.slice(0, -1)) {
            const dot = window.L.circleMarker([Number(point.latitude), Number(point.longitude)], {
                radius: 3,
                color: trackColor,
                fillColor: trackColor,
                fillOpacity: 0.65,
                opacity: 0.95,
                weight: 1,
                interactive: false,
            }).addTo(map);
            trackDots.push(dot);
        }
    }

    function parseTileSubdomains(value) {
        return String(value || "")
            .split(/[,\s]+/)
            .map((token) => token.trim())
            .filter((token) => token.length > 0);
    }

    function normalizeTileConfig(mapConfig) {
        return {
            tile_url: String(mapConfig.tile_url || ""),
            tile_attribution: String(mapConfig.tile_attribution || ""),
            tile_min_zoom: Number.parseInt(String(mapConfig.tile_min_zoom || ""), 10),
            tile_max_zoom: Number.parseInt(String(mapConfig.tile_max_zoom || ""), 10),
            tile_subdomains: parseTileSubdomains(mapConfig.tile_subdomains || ""),
        };
    }

    function tileConfigMatches(layer, tileConfig) {
        if (!layer) {
            return false;
        }
        const currentMinZoom = Number.isFinite(Number(layer.options.minZoom)) ? Number(layer.options.minZoom) : null;
        const currentMaxZoom = Number.isFinite(Number(layer.options.maxZoom)) ? Number(layer.options.maxZoom) : null;
        const nextMinZoom = Number.isFinite(Number(tileConfig.tile_min_zoom)) ? Number(tileConfig.tile_min_zoom) : null;
        const nextMaxZoom = Number.isFinite(Number(tileConfig.tile_max_zoom)) ? Number(tileConfig.tile_max_zoom) : null;
        const currentSubdomains = Array.isArray(layer.options.subdomains)
            ? layer.options.subdomains
            : parseTileSubdomains(layer.options.subdomains || "");
        return (
            String(layer._url || "") === tileConfig.tile_url
            && String(layer.options.attribution || "") === tileConfig.tile_attribution
            && currentMinZoom === nextMinZoom
            && currentMaxZoom === nextMaxZoom
            && JSON.stringify(currentSubdomains) === JSON.stringify(tileConfig.tile_subdomains)
        );
    }

    function createTileLayer(tileConfig) {
        const options = {
            attribution: tileConfig.tile_attribution,
        };
        if (Number.isInteger(tileConfig.tile_min_zoom)) {
            options.minZoom = tileConfig.tile_min_zoom;
        }
        if (Number.isInteger(tileConfig.tile_max_zoom)) {
            options.maxZoom = tileConfig.tile_max_zoom;
        }
        if (Array.isArray(tileConfig.tile_subdomains) && tileConfig.tile_subdomains.length > 0) {
            options.subdomains = tileConfig.tile_subdomains;
        }
        return window.L.tileLayer(tileConfig.tile_url, options);
    }

    function syncMapMaskLayerViewport() {
        if (!mapMaskPane || !map) {
            return;
        }
        const size = map.getSize();
        mapMaskPane.style.width = `${size.x}px`;
        mapMaskPane.style.height = `${size.y}px`;
    }

    function ensureMapMaskLayer(mapInstance, mapCanvasElement) {
        mapMaskPane = mapInstance.getPane(mapMaskPaneName);
        if (!mapMaskPane) {
            mapMaskPane = mapInstance.createPane(mapMaskPaneName);
        }
        mapMaskPane.classList.add("map-mask-pane");
        mapMaskPane.style.zIndex = "300";
        mapMaskPane.style.pointerEvents = "none";
        if (mapCanvasElement && !mapCanvasElement.contains(mapMaskPane)) {
            mapCanvasElement.appendChild(mapMaskPane);
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

    function ensureMap(station, mapConfig, stationTrack) {
        const hasCoordinates = Number.isFinite(Number(station.latitude_float)) && Number.isFinite(Number(station.longitude_float));
        if (!hasCoordinates) {
            if (mapRoot) {
                mapRoot.hidden = true;
            }
            if (mapPlaceholder) {
                mapPlaceholder.hidden = false;
            }
            return;
        }

        if (!mapRoot || !mapCanvas || typeof window.L === "undefined") {
            return;
        }

        if (mapPlaceholder) {
            mapPlaceholder.hidden = true;
        }
        mapRoot.hidden = false;
        mapRoot.dataset.latitude = String(station.latitude_float);
        mapRoot.dataset.longitude = String(station.longitude_float);
        mapRoot.dataset.displayCallsign = station.display_callsign || "";
        mapRoot.dataset.symbolIcon = mapConfig.symbol_icon || "";
        mapRoot.dataset.symbolTable = mapConfig.symbol_table || "";
        mapRoot.dataset.symbolCode = mapConfig.symbol_code || "";
        mapRoot.dataset.tileUrl = mapConfig.tile_url || "";
        mapRoot.dataset.tileAttribution = mapConfig.tile_attribution || "";
        mapRoot.dataset.tileMinZoom = String(mapConfig.tile_min_zoom || "");
        mapRoot.dataset.tileMaxZoom = String(mapConfig.tile_max_zoom || "");
        mapRoot.dataset.tileSubdomains = String(mapConfig.tile_subdomains || "");

        const latLng = [Number(station.latitude_float), Number(station.longitude_float)];
        const symbolIcon = mapConfig.symbol_icon ? `${staticRoot}${mapConfig.symbol_icon}` : `${staticRoot}icons/verG/x.gif`;
        const symbolTable = mapConfig.symbol_table || station.symbol_table || "";
        const tileConfig = normalizeTileConfig(mapConfig);
        const icon = window.L.divIcon({
            className: "map-station-icon",
            html: buildIconHtml(station.display_callsign || "", symbolIcon, symbolTable),
            iconSize: aprsIconSize,
            iconAnchor: aprsIconAnchor,
        });

        if (!map) {
            map = window.L.map(mapCanvas, {
                center: latLng,
                zoom: Number.isInteger(mapConfig.zoom) ? mapConfig.zoom : 14,
                zoomControl: true,
                attributionControl: true,
            });
            map.on("resize zoom move", syncMapMaskLayerViewport);
            mapMaskLayer = ensureMapMaskLayer(map, mapCanvas);
            applyMaskOpacity();
            tileLayer = createTileLayer(tileConfig).addTo(map);
            renderTrack(station, stationTrack);
            marker = window.L.marker(latLng, { icon, keyboard: false }).addTo(map);
            map.whenReady(function () {
                window.setTimeout(function () {
                    map.invalidateSize();
                }, 0);
            });
            return;
        }

        marker.setLatLng(latLng);
        marker.setIcon(icon);
        renderTrack(station, stationTrack);
        map.setView(latLng, map.getZoom(), { animate: false });
        if (!tileConfigMatches(tileLayer, tileConfig)) {
            if (tileLayer) {
                map.removeLayer(tileLayer);
            }
            tileLayer = createTileLayer(tileConfig).addTo(map);
        }
        if (!mapMaskLayer) {
            mapMaskLayer = ensureMapMaskLayer(map, mapCanvas);
        }
    }

    async function refreshStation() {
        if (!stationEndpoint) return;
        try {
            const response = await fetch(stationEndpoint, { headers: { Accept: "application/json" } });
            if (!response.ok) return;
            const payload = await response.json();
            const station = payload.station || {};
            const mapConfig = payload.station_map_config || {};
            const stationTrack = payload.station_track || { points: [] };
            if (title) {
                title.textContent = station.display_callsign || "";
            }
            renderMeta(station);
            renderFields(station);
            renderAprsDevice(station.aprs_device || null);
            renderRecentPackets(payload.recent_packets || []);
            renderRelatedSsids(station, payload.related_ssids || []);
            ensureMap(station, mapConfig, stationTrack);
        } catch (_error) {
        }
    }

    const initialStation = mapRoot ? {
        display_callsign: mapRoot.dataset.displayCallsign || "",
        latitude_float: Number.parseFloat(mapRoot.dataset.latitude || ""),
        longitude_float: Number.parseFloat(mapRoot.dataset.longitude || ""),
    } : { latitude_float: NaN, longitude_float: NaN };
    const initialMapConfig = mapRoot ? {
        zoom: Number.parseInt(mapRoot.dataset.zoom || "14", 10),
        tile_url: mapRoot.dataset.tileUrl || "",
        tile_attribution: mapRoot.dataset.tileAttribution || "",
        tile_min_zoom: Number.parseInt(mapRoot.dataset.tileMinZoom || "", 10),
        tile_max_zoom: Number.parseInt(mapRoot.dataset.tileMaxZoom || "", 10),
        tile_subdomains: mapRoot.dataset.tileSubdomains || "",
        symbol_icon: mapRoot.dataset.symbolIcon || "",
        symbol_table: mapRoot.dataset.symbolTable || "",
        symbol_code: mapRoot.dataset.symbolCode || "",
        track_points: parseTrackPoints(mapRoot.dataset.trackPoints || ""),
    } : {};
    const initialStationTrack = { points: initialMapConfig.track_points || [] };

    applyMaskOpacity();
    ensureMap(initialStation, initialMapConfig, initialStationTrack);
    const themeObserver = new window.MutationObserver(function (mutations) {
        for (const mutation of mutations) {
            if (mutation.type === "attributes" && mutation.attributeName === "data-theme") {
                applyMaskOpacity();
                break;
            }
        }
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    if (Number.isInteger(refreshMs) && refreshMs > 0) {
        window.setInterval(refreshStation, refreshMs);
    }
})();
