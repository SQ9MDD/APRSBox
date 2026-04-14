(function () {
    const root = document.getElementById("map-root");
    const overlay = document.getElementById("map-latest-overlay");
    if (!root || !overlay) {
        return;
    }

    const toggleButton = document.getElementById("map-toggle-latest-overlay");
    const toggleIcon = document.getElementById("map-toggle-latest-overlay-icon");
    const staticRoot = root.dataset.staticRoot || "/static/";
    const overlayVisibleStorageKey = "aprsbox-map-latest-overlay-visible";
    const stationsRefreshEventName = "aprsbox:map-stations-refreshed";

    const i18n = Object.freeze({
        callsign: root.dataset.i18nCallsign || "Callsign",
        latestPacket: root.dataset.i18nLatestPacket || "Latest packet",
        distanceAzimuth: root.dataset.i18nDistanceAzimuth || "Distance and azimuth",
        description: root.dataset.i18nDescription || "Description",
        qsy: root.dataset.i18nQsy || "QSY",
        noStations: root.dataset.i18nNoStations || "No decoded APRS stations available yet.",
        showOverlay: root.dataset.i18nShowLatestOverlay || "Show latest packet widget",
        hideOverlay: root.dataset.i18nHideLatestOverlay || "Hide latest packet widget",
    });

    let overlayVisible = true;
    let stationReferenceLatitude = Number.parseFloat(root.dataset.stationLatitude || "");
    let stationReferenceLongitude = Number.parseFloat(root.dataset.stationLongitude || "");

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
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

    function resolveOverlayVisible() {
        const storedValue = String(window.localStorage.getItem(overlayVisibleStorageKey) || "").trim().toLowerCase();
        if (storedValue === "0" || storedValue === "false") {
            return false;
        }
        if (storedValue === "1" || storedValue === "true") {
            return true;
        }
        return true;
    }

    function applyOverlayToggleState(visible) {
        overlayVisible = Boolean(visible);
        window.localStorage.setItem(overlayVisibleStorageKey, overlayVisible ? "1" : "0");
        overlay.hidden = !overlayVisible;
        if (toggleIcon) {
            toggleIcon.setAttribute("src", `${staticRoot}icons/${overlayVisible ? "message-alert.svg" : "message-off.svg"}`);
        }
        if (toggleButton) {
            const label = overlayVisible ? i18n.hideOverlay : i18n.showOverlay;
            toggleButton.setAttribute("title", label);
            toggleButton.setAttribute("aria-label", label);
        }
    }

    function formatDistanceAndAzimuth(station) {
        const parts = [];
        if (Number.isFinite(station.distance_km)) {
            parts.push(`${station.distance_km} km`);
        }

        if (
            Number.isFinite(stationReferenceLatitude)
            && Number.isFinite(stationReferenceLongitude)
            && Number.isFinite(station.latitude)
            && Number.isFinite(station.longitude)
        ) {
            const azimuth = Math.round(
                bearingBetweenPoints(
                    { lat: stationReferenceLatitude, lng: stationReferenceLongitude },
                    { lat: station.latitude, lng: station.longitude }
                )
            );
            parts.push(`${azimuth}\u00b0`);
        }

        return parts.length ? parts.join(", ") : "-";
    }

    function formatQsy(station) {
        if (!Number.isFinite(station.qsy_frequency_mhz)) {
            return "-";
        }
        const parts = [`${Number(station.qsy_frequency_mhz).toFixed(3)} MHz`];
        const qsyTone = String(station.qsy_tone || "").trim();
        if (qsyTone) {
            parts.push(qsyTone);
        }
        if (Number.isFinite(station.qsy_offset_khz)) {
            const qsyOffset = Number(station.qsy_offset_khz);
            const sign = qsyOffset > 0 ? "+" : "";
            parts.push(`${sign}${qsyOffset} kHz`);
        }
        const qsyCallsign = String(station.qsy_callsign || "").trim();
        if (qsyCallsign) {
            parts.push(qsyCallsign);
        }
        return parts.join(" ");
    }

    function selectLatestStation(stations) {
        if (!Array.isArray(stations) || stations.length === 0) {
            return null;
        }
        for (const station of stations) {
            if (Number.isFinite(station.latitude) && Number.isFinite(station.longitude)) {
                return station;
            }
        }
        return null;
    }

    function renderOverlay(station) {
        if (!station) {
            overlay.innerHTML = `
                <div class="map-latest-overlay-empty">${escapeHtml(i18n.noStations)}</div>
            `;
            return;
        }

        const displayCallsign = String(station.display_callsign || station.callsign || "-").trim() || "-";
        const description = String(station.comment || "").trim() || "-";

        overlay.innerHTML = `
            <h3 class="map-latest-overlay-title">${escapeHtml(i18n.latestPacket)}</h3>
            <dl class="map-latest-overlay-grid">
                <div class="map-latest-overlay-row">
                    <dt>${escapeHtml(i18n.callsign)}</dt>
                    <dd>${escapeHtml(displayCallsign)}</dd>
                </div>
                <div class="map-latest-overlay-row">
                    <dt>${escapeHtml(i18n.distanceAzimuth)}</dt>
                    <dd>${escapeHtml(formatDistanceAndAzimuth(station))}</dd>
                </div>
                <div class="map-latest-overlay-row">
                    <dt>${escapeHtml(i18n.description)}</dt>
                    <dd>${escapeHtml(description)}</dd>
                </div>
                <div class="map-latest-overlay-row">
                    <dt>${escapeHtml(i18n.qsy)}</dt>
                    <dd>${escapeHtml(formatQsy(station))}</dd>
                </div>
            </dl>
        `;
    }

    root.addEventListener(stationsRefreshEventName, function (event) {
        const detail = event && event.detail ? event.detail : {};
        const stations = Array.isArray(detail.stations) ? detail.stations : [];

        const referenceLatitude = Number(detail.stationLatitude);
        const referenceLongitude = Number(detail.stationLongitude);
        if (Number.isFinite(referenceLatitude) && Number.isFinite(referenceLongitude)) {
            stationReferenceLatitude = referenceLatitude;
            stationReferenceLongitude = referenceLongitude;
        }

        renderOverlay(selectLatestStation(stations));
    });

    applyOverlayToggleState(resolveOverlayVisible());
    renderOverlay(null);

    if (toggleButton) {
        toggleButton.addEventListener("click", function () {
            applyOverlayToggleState(!overlayVisible);
        });
    }
})();
