(function () {
    const root = document.getElementById("station-detail-map-root");
    const canvas = document.getElementById("station-detail-map-canvas");
    if (!root || !canvas || typeof window.L === "undefined") {
        return;
    }

    const latitude = Number.parseFloat(root.dataset.latitude || "");
    const longitude = Number.parseFloat(root.dataset.longitude || "");
    const zoom = Number.parseInt(root.dataset.zoom || "10", 10);
    const tileUrl = root.dataset.tileUrl || "";
    const tileAttribution = root.dataset.tileAttribution || "";
    const displayCallsign = root.dataset.displayCallsign || "";
    const symbolIcon = root.dataset.symbolIcon ? `/static/${root.dataset.symbolIcon}` : "/static/icons/verG/x.gif";

    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
        return;
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll("\"", "&quot;")
            .replaceAll("'", "&#39;");
    }

    const map = window.L.map(canvas, {
        center: [latitude, longitude],
        zoom: Number.isInteger(zoom) ? zoom : 10,
        zoomControl: true,
        attributionControl: true,
    });

    window.L.tileLayer(tileUrl, {
        attribution: tileAttribution,
        maxZoom: 19,
    }).addTo(map);

    const marker = window.L.marker([latitude, longitude], {
        icon: window.L.divIcon({
            className: "map-station-icon",
            html: `
                <img class="map-station-aprs-icon" src="${escapeHtml(symbolIcon)}" alt="">
                <span class="map-station-label">${escapeHtml(displayCallsign)}</span>
            `,
            iconSize: [36, 24],
            iconAnchor: [8, 8],
        }),
        keyboard: false,
    });
    marker.addTo(map);

    map.whenReady(function () {
        window.setTimeout(function () {
            map.invalidateSize();
        }, 0);
    });
})();
