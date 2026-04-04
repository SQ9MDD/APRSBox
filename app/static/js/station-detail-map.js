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
    let map = null;
    let marker = null;
    let tileLayer = null;

    function currentThemeName() {
        return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    }

    function maskOpacityStorageKey() {
        return `aprsbox-map-mask-opacity-${currentThemeName()}`;
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll("\"", "&quot;")
            .replaceAll("'", "&#39;");
    }

    function renderMeta(station) {
        if (!meta) return;
        const parts = [];
        if (station.last_heard_date) {
            let heard = `Last heard ${escapeHtml(station.last_heard_date)}`;
            if (station.last_heard_relative) {
                heard += ` <span class="muted">(${escapeHtml(station.last_heard_relative)})</span>`;
            }
            parts.push(heard);
        }
        if (station.source) {
            parts.push(`<span class="muted">• Source ${escapeHtml(station.source)}</span>`);
        }
        if (station.path) {
            parts.push(`<span class="muted">• Path ${escapeHtml(station.path)}</span>`);
        }
        meta.innerHTML = parts.join(" ");
    }

    function renderFields(station) {
        if (!fields) return;
        fields.innerHTML = (station.fields || []).map((field) => `
            <dt>${escapeHtml(field.label)}</dt>
            <dd>${field.label === "Latest raw packet" ? `<code>${escapeHtml(field.value)}</code>` : escapeHtml(field.value)}</dd>
        `).join("");
    }

    function renderAprsDevice(device) {
        if (!devicePanel || !deviceRoot) return;
        if (!device) {
            devicePanel.hidden = true;
            deviceRoot.innerHTML = "";
            return;
        }

        const identifierLabel = device.identifier_kind === "tocall" ? "TOCALL" : "Mic-E";
        const capabilityBlock = Array.isArray(device.features) && device.features.length
            ? `
                <div class="station-device-capabilities">
                    <span class="muted">Capabilities</span>
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
                    <dt>Identified software/device</dt>
                    <dd>${escapeHtml(device.identified_as || device.short_name || "")}</dd>
                    ${device.vendor ? `<dt>Vendor</dt><dd>${escapeHtml(device.vendor)}</dd>` : ""}
                    ${device.model ? `<dt>Model</dt><dd>${escapeHtml(device.model)}</dd>` : ""}
                    ${device.class_label ? `<dt>Class</dt><dd>${escapeHtml(device.class_label)}</dd>` : ""}
                    ${device.class_description ? `<dt>Class description</dt><dd>${escapeHtml(device.class_description)}</dd>` : ""}
                    ${device.os ? `<dt>OS</dt><dd>${escapeHtml(device.os)}</dd>` : ""}
                </dl>
                ${capabilityBlock}
            </div>
        `;
        devicePanel.hidden = false;
    }

    function renderRecentPackets(packets) {
        if (!recentPackets) return;
        if (!packets || !packets.length) {
            recentPackets.innerHTML = '<p class="muted">No stored packet history is available for this station yet.</p>';
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
                            <th>Timestamp</th>
                            <th>Destination</th>
                            <th>Raw packet</th>
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
            relatedSsids.innerHTML = `<p class="muted">No other known SSIDs are currently available for ${escapeHtml(station.base_callsign || "")}.</p>`;
            return;
        }
        relatedSsids.innerHTML = `
            <div class="station-ssid-list">
                ${items.map((item) => `
                    <a href="${escapeHtml(item.detail_href && item.detail_href.startsWith("/") ? `${rootPath}${item.detail_href}` : (item.detail_href || "#"))}" class="station-ssid-chip${item.is_current ? " current" : ""}">
                        <span>${escapeHtml(item.display_callsign || "")}</span>
                        ${item.is_current ? '<span class="muted">current</span>' : ""}
                    </a>
                `).join("")}
            </div>
        `;
    }

    function buildIconHtml(displayCallsign, symbolIcon) {
        return `
            <img class="map-station-aprs-icon" src="${escapeHtml(symbolIcon)}" alt="">
            <span class="map-station-label">${escapeHtml(displayCallsign)}</span>
        `;
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
        return 20;
    }

    function applyMaskOpacity() {
        if (!mapCanvas) return;
        const opacityPercent = resolveMaskOpacity();
        mapCanvas.style.setProperty("--map-pane-opacity", String(1 - (opacityPercent / 100)));
    }

    function ensureMap(station, mapConfig) {
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

        const latLng = [Number(station.latitude_float), Number(station.longitude_float)];
        const symbolIcon = mapConfig.symbol_icon ? `${staticRoot}${mapConfig.symbol_icon}` : `${staticRoot}icons/verG/x.gif`;
        const icon = window.L.divIcon({
            className: "map-station-icon",
            html: buildIconHtml(station.display_callsign || "", symbolIcon),
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
            tileLayer = window.L.tileLayer(mapConfig.tile_url || "", {
                attribution: mapConfig.tile_attribution || "",
                maxZoom: 19,
            }).addTo(map);
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
        map.setView(latLng, map.getZoom(), { animate: false });
        if (tileLayer && tileLayer._url !== (mapConfig.tile_url || "")) {
            tileLayer.setUrl(mapConfig.tile_url || "");
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
            if (title) {
                title.textContent = station.display_callsign || "";
            }
            renderMeta(station);
            renderFields(station);
            renderAprsDevice(station.aprs_device || null);
            renderRecentPackets(payload.recent_packets || []);
            renderRelatedSsids(station, payload.related_ssids || []);
            ensureMap(station, mapConfig);
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
        symbol_icon: mapRoot.dataset.symbolIcon || "",
    } : {};

    applyMaskOpacity();
    ensureMap(initialStation, initialMapConfig);
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
