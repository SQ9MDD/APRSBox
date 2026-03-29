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
    const maskElement = document.getElementById("map-mask");
    const resetButton = document.getElementById("map-reset-view");
    const maskOpacitySelect = document.getElementById("map-mask-opacity");
    const stationLayer = window.L.layerGroup();
    const maskOpacityStorageKey = "aprsbox-map-mask-opacity";
    let refreshTimer = null;

    const map = window.L.map("map-canvas", {
        center: [defaultView.latitude, defaultView.longitude],
        zoom: defaultView.zoom,
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
        const storedOpacity = Number.parseInt(window.localStorage.getItem(maskOpacityStorageKey) || "", 10);
        if (Number.isInteger(storedOpacity) && storedOpacity >= 0 && storedOpacity <= 100 && storedOpacity % 10 === 0) {
            return storedOpacity;
        }
        return 20;
    }

    function applyMaskOpacity(opacityPercent) {
        const normalizedOpacity = Number.isInteger(opacityPercent) && opacityPercent >= 0 && opacityPercent <= 100
            ? opacityPercent - (opacityPercent % 10)
            : 20;
        if (maskElement) {
            maskElement.style.opacity = String(normalizedOpacity / 100);
        }
        if (maskOpacitySelect) {
            maskOpacitySelect.value = String(normalizedOpacity);
        }
        window.localStorage.setItem(maskOpacityStorageKey, String(normalizedOpacity));
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
        return date.toLocaleString("sv-SE", { hour12: false }).replace("T", " ");
    }

    function formatAge(seconds) {
        if (!Number.isFinite(seconds) || seconds < 0) {
            return "";
        }
        if (seconds < 60) {
            return `${seconds}s ago`;
        }
        if (seconds < 3600) {
            return `${Math.floor(seconds / 60)}m ago`;
        }
        return `${Math.floor(seconds / 3600)}h ago`;
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

    if (resetButton) {
        resetButton.addEventListener("click", function () {
            map.setView([defaultView.latitude, defaultView.longitude], defaultView.zoom);
        });
    }

    if (maskOpacitySelect) {
        applyMaskOpacity(resolveDefaultMaskOpacity());
        maskOpacitySelect.addEventListener("change", function () {
            applyMaskOpacity(Number.parseInt(maskOpacitySelect.value || "", 10));
        });
    }

    function tooltipHtml(station) {
        const lines = [];
        const heardAt = formatTimestamp(station.last_heard_at);
        const heardAge = formatAge(station.last_heard_age_s);
        lines.push(`<strong>${escapeHtml(station.display_callsign || station.callsign || "")}</strong>`);
        if (heardAt || heardAge) {
            const heardLabel = [heardAt, heardAge ? `(${heardAge})` : ""].filter(Boolean).join(" ");
            lines.push(`<span><strong>Last heard:</strong> ${escapeHtml(heardLabel)}</span>`);
        }
        if (station.source) {
            lines.push(`<span><strong>Source:</strong> ${escapeHtml(station.source)}</span>`);
        }
        if (station.path) {
            lines.push(`<span><strong>Path:</strong> ${escapeHtml(station.path)}</span>`);
        }
        if (station.destination) {
            lines.push(`<span><strong>Destination:</strong> ${escapeHtml(station.destination)}</span>`);
        }
        if (station.comment) {
            lines.push(`<span><strong>Comment:</strong> ${escapeHtml(station.comment)}</span>`);
        }
        if (Number.isFinite(station.speed)) {
            lines.push(`<span><strong>Speed:</strong> ${escapeHtml(`${station.speed} km/h`)}</span>`);
        }
        if (Number.isFinite(station.course)) {
            lines.push(`<span><strong>Course:</strong> ${escapeHtml(`${station.course}°`)}</span>`);
        }
        if (Number.isFinite(station.altitude)) {
            lines.push(`<span><strong>Altitude:</strong> ${escapeHtml(`${station.altitude} m`)}</span>`);
        }
        if (station.packet_type) {
            lines.push(`<span><strong>Packet:</strong> ${escapeHtml(station.packet_type)}</span>`);
        }
        return `<div class="map-station-tooltip">${lines.join("")}</div>`;
    }

    function buildStationIcon(station) {
        const staleClass = station.stale ? " map-station-icon-stale" : "";
        const iconPath = station.symbol_icon ? `/static/${station.symbol_icon}` : "/static/icons/verG/x.gif";
        const iconAlt = station.symbol_table || station.symbol_code ? `${station.symbol_table || ""}${station.symbol_code || ""}` : "";
        return window.L.divIcon({
            className: `map-station-icon${staleClass}`,
            html: `
                <img class="map-station-aprs-icon" src="${escapeHtml(iconPath)}" alt="${escapeHtml(iconAlt)}">
                <span class="map-station-label">${escapeHtml(station.display_callsign || station.callsign || "")}</span>
            `,
            iconSize: [36, 24],
            iconAnchor: [8, 8],
            tooltipAnchor: [0, -10],
        });
    }

    function renderStations(stations) {
        stationLayer.clearLayers();
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
            renderStations(payload.stations || []);
        } catch (_error) {
        }
    }

    function startPolling() {
        if (refreshTimer) {
            window.clearInterval(refreshTimer);
        }
        refreshTimer = window.setInterval(refreshStations, 10000);
    }

    map.on("moveend zoomend", syncStatus);
    map.whenReady(function () {
        window.setTimeout(function () {
            map.invalidateSize();
        }, 0);
    });
    refreshStations();
    startPolling();
    syncStatus();
})();
