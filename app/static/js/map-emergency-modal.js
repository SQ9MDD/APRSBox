(function () {
    const root = document.getElementById("map-root");
    const modal = document.getElementById("aprs-emergency-modal");
    if (!root || !modal) {
        return;
    }

    const eventName = "aprsbox:traffic-snapshot";
    const mapViewRefreshEventName = "aprsbox:map-view-refreshed";
    const dialog = modal.querySelector(".aprs-emergency-dialog");
    const title = document.getElementById("aprs-emergency-title");
    const callsign = document.getElementById("aprs-emergency-callsign");
    const status = document.getElementById("aprs-emergency-status");
    const newerNotice = document.getElementById("aprs-emergency-newer");
    const timestamp = document.getElementById("aprs-emergency-timestamp");
    const source = document.getElementById("aprs-emergency-source");
    const path = document.getElementById("aprs-emergency-path");
    const summary = document.getElementById("aprs-emergency-summary");
    const raw = document.getElementById("aprs-emergency-raw");
    const noPosition = document.getElementById("aprs-emergency-no-position");
    const mapContainer = document.getElementById("aprs-emergency-map");
    const closeButton = document.getElementById("aprs-emergency-close");
    const copyButton = document.getElementById("aprs-emergency-copy");
    const openMapButton = document.getElementById("aprs-emergency-open-map");

    const mapTileUrl = String(root.dataset.tileUrl || "").trim();
    const mapTileAttribution = String(root.dataset.tileAttribution || "").trim();
    const mapTileMinZoom = Number.parseInt(root.dataset.tileMinZoom || "", 10);
    const mapTileMaxZoom = Number.parseInt(root.dataset.tileMaxZoom || "", 10);
    const mapTileSubdomains = String(root.dataset.tileSubdomains || "")
        .split(/[,\s]+/)
        .map((token) => token.trim())
        .filter((token) => token.length > 0);

    let currentSignature = "";
    let dismissedSignature = "";
    let isVisible = false;
    let miniMap = null;
    let miniMapMarker = null;
    let newEmergencyTimer = null;
    let currentEmergencyFrame = null;
    const emergencyAlarmSrc = `${String(root.dataset.staticRoot || "/static/")}audio/aprs-audio-alert.mp3`;
    const emergencyAlarmAudio = new Audio(emergencyAlarmSrc);
    emergencyAlarmAudio.preload = "auto";
    emergencyAlarmAudio.playsInline = true;
    emergencyAlarmAudio.loop = true;
    emergencyAlarmAudio.volume = 1;
    emergencyAlarmAudio.load();

    function textOrDash(value) {
        const text = String(value ?? "").trim();
        return text || "-";
    }

    function parseCoordinate(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : null;
    }

    function formatUtcTimestamp(value) {
        const text = String(value || "").trim();
        if (!text) {
            return "-";
        }
        const date = new Date(text);
        if (Number.isNaN(date.getTime())) {
            return text;
        }
        return date.toISOString().replace("T", " ").replace(/\.\d{3}Z$/, " UTC");
    }

    function emergencySignature(frame) {
        const emergencyData = frame && typeof frame === "object" ? (frame.emergency_data || {}) : {};
        return [
            emergencyData.timestamp_utc || frame.timestamp || "",
            emergencyData.raw_frame || frame.line || "",
            emergencyData.callsign || frame.display_callsign || frame.source || "",
        ].join("|");
    }

    function emergencyFrameSortValue(frame) {
        const emergencyData = frame && typeof frame === "object" ? (frame.emergency_data || {}) : {};
        const rawTimestamp = String(emergencyData.timestamp_utc || frame.timestamp || "").trim();
        const parsedTimestamp = Date.parse(rawTimestamp);
        return Number.isFinite(parsedTimestamp) ? parsedTimestamp : -Infinity;
    }

    function selectNewestEmergencyFrame(frames) {
        if (!Array.isArray(frames) || frames.length === 0) {
            return null;
        }
        const newestFrame = frames[0];
        if (!newestFrame || !newestFrame.emergency) {
            return null;
        }
        return newestFrame;
    }

    function destroyMiniMap() {
        if (miniMap && typeof miniMap.remove === "function") {
            miniMap.remove();
        }
        miniMap = null;
        miniMapMarker = null;
        if (mapContainer) {
            mapContainer.innerHTML = "";
        }
    }

    function renderMiniMap(latitude, longitude) {
        const hasCoordinates = Number.isFinite(latitude) && Number.isFinite(longitude);
        if (!mapContainer || !noPosition) {
            return;
        }
        if (!hasCoordinates || typeof window.L === "undefined") {
            destroyMiniMap();
            mapContainer.hidden = true;
            noPosition.hidden = false;
            return;
        }

        noPosition.hidden = true;
        mapContainer.hidden = false;

        if (!miniMap) {
            mapContainer.textContent = "";
            miniMap = window.L.map(mapContainer, {
                center: [latitude, longitude],
                zoom: 13,
                zoomControl: false,
                attributionControl: false,
                scrollWheelZoom: false,
                dragging: false,
                doubleClickZoom: false,
                boxZoom: false,
                keyboard: false,
                tap: false,
                touchZoom: false,
            });

            if (mapTileUrl) {
                const tileOptions = {
                    attribution: mapTileAttribution,
                };
                if (Number.isInteger(mapTileMinZoom)) {
                    tileOptions.minZoom = mapTileMinZoom;
                }
                if (Number.isInteger(mapTileMaxZoom)) {
                    tileOptions.maxZoom = mapTileMaxZoom;
                }
                if (mapTileSubdomains.length > 0) {
                    tileOptions.subdomains = mapTileSubdomains;
                }
                window.L.tileLayer(mapTileUrl, tileOptions).addTo(miniMap);
            }

            miniMapMarker = window.L.marker([latitude, longitude]).addTo(miniMap);
            window.setTimeout(() => {
                if (miniMap) {
                    miniMap.invalidateSize();
                }
            }, 0);
            return;
        }

        miniMap.setView([latitude, longitude], 13);
        if (miniMapMarker) {
            miniMapMarker.setLatLng([latitude, longitude]);
        } else {
            miniMapMarker = window.L.marker([latitude, longitude]).addTo(miniMap);
        }
        miniMap.invalidateSize();
    }

    function primeEmergencyAlarmAudio() {
        try {
            emergencyAlarmAudio.muted = true;
            const primePromise = emergencyAlarmAudio.play();
            if (primePromise && typeof primePromise.then === "function") {
                primePromise.then(() => {
                    emergencyAlarmAudio.pause();
                    emergencyAlarmAudio.currentTime = 0;
                    emergencyAlarmAudio.muted = false;
                }).catch(() => {
                    emergencyAlarmAudio.muted = false;
                });
                return;
            }
        } catch (_error) {
        }
        emergencyAlarmAudio.muted = false;
    }

    function playOpenBeep() {
        try {
            emergencyAlarmAudio.pause();
            emergencyAlarmAudio.currentTime = 0;
            const playPromise = emergencyAlarmAudio.play();
            if (playPromise && typeof playPromise.catch === "function") {
                playPromise.catch(() => {});
            }
        } catch (_error) {
        }
        try {
            if (navigator.vibrate) {
                navigator.vibrate([150, 60, 150, 60, 300]);
            }
        } catch (_error) {
        }
    }

    function applyCopyFrame() {
        const frameText = String(raw?.textContent || "");
        if (!frameText) {
            return;
        }
        try {
            if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
                void navigator.clipboard.writeText(frameText);
                return;
            }
        } catch (_error) {
        }

        try {
            const textarea = document.createElement("textarea");
            textarea.value = frameText;
            textarea.setAttribute("readonly", "readonly");
            textarea.style.position = "fixed";
            textarea.style.left = "-9999px";
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand("copy");
            textarea.remove();
        } catch (_error) {
        }
    }

    function updateOpenMapButton(latitude, longitude) {
        if (!openMapButton) {
            return;
        }
        const hasCoordinates = Number.isFinite(latitude) && Number.isFinite(longitude);
        const canCenterMap = typeof window.aprsboxCenterMapOn === "function";
        openMapButton.disabled = !(hasCoordinates && canCenterMap);
    }

    function hideNewerNotice() {
        if (newEmergencyTimer) {
            window.clearTimeout(newEmergencyTimer);
            newEmergencyTimer = null;
        }
        if (newerNotice) {
            newerNotice.hidden = true;
        }
    }

    function showNewerNotice() {
        if (!newerNotice) {
            return;
        }
        newerNotice.hidden = false;
        if (newEmergencyTimer) {
            window.clearTimeout(newEmergencyTimer);
        }
        newEmergencyTimer = window.setTimeout(() => {
            newerNotice.hidden = true;
            newEmergencyTimer = null;
        }, 3000);
    }

    function hideModal() {
        isVisible = false;
        emergencyAlarmAudio.pause();
        emergencyAlarmAudio.currentTime = 0;
        modal.hidden = true;
        document.body.classList.remove("modal-open");
        dismissedSignature = currentSignature;
        hideNewerNotice();
        destroyMiniMap();
    }

    function showModal() {
        if (isVisible) {
            return;
        }
        isVisible = true;
        modal.hidden = false;
        document.body.classList.add("modal-open");
        if (dialog instanceof HTMLElement) {
            dialog.focus();
        }
        playOpenBeep();
    }

    function renderEmergencyFrame(frame) {
        const emergencyData = frame && typeof frame === "object" ? (frame.emergency_data || {}) : {};
        const call = textOrDash(emergencyData.callsign || frame.display_callsign || frame.source);
        const sourceLabel = textOrDash(
            [emergencyData.source_interface || frame.source, emergencyData.source_port].filter(Boolean).join(" · ")
        );
        const pathLabel = textOrDash(emergencyData.path);
        const summaryLabel = textOrDash(emergencyData.summary || emergencyData.comment);
        const timestampLabel = formatUtcTimestamp(emergencyData.timestamp_utc || frame.timestamp);
        const rawFrame = String(emergencyData.raw_frame || frame.line || "").trim();
        const latitude = parseCoordinate(emergencyData.latitude);
        const longitude = parseCoordinate(emergencyData.longitude);

        currentEmergencyFrame = frame;
        currentSignature = emergencySignature(frame);
        if (title) {
            title.textContent = "EMERGENCY FRAME RECEIVED";
        }
        if (callsign) {
            callsign.textContent = call;
        }
        if (status) {
            status.textContent = "ACTIVE EMERGENCY";
        }
        if (timestamp) {
            timestamp.textContent = timestampLabel;
        }
        if (source) {
            source.textContent = sourceLabel;
        }
        if (path) {
            path.textContent = pathLabel;
        }
        if (summary) {
            summary.textContent = summaryLabel;
        }
        if (raw) {
            raw.textContent = rawFrame;
        }

        renderMiniMap(latitude, longitude);
        updateOpenMapButton(latitude, longitude);
        showModal();
    }

    function handleSnapshot(snapshot) {
        const frames = Array.isArray(snapshot && snapshot.frames) ? snapshot.frames : [];
        const emergencyFrame = selectNewestEmergencyFrame(frames);
        if (!emergencyFrame) {
            return;
        }

        const nextSignature = emergencySignature(emergencyFrame);
        if (nextSignature && nextSignature === currentSignature && isVisible) {
            if (emergencyAlarmAudio.paused) {
                playOpenBeep();
            }
            return;
        }
        if (!isVisible && nextSignature && nextSignature === dismissedSignature) {
            return;
        }

        if (isVisible && currentSignature && nextSignature !== currentSignature) {
            showNewerNotice();
        }
        dismissedSignature = "";
        renderEmergencyFrame(emergencyFrame);
    }

    if (closeButton) {
        closeButton.addEventListener("click", hideModal);
    }

    if (copyButton) {
        copyButton.addEventListener("click", applyCopyFrame);
    }

    if (openMapButton) {
        openMapButton.addEventListener("click", function () {
            const emergencyData = currentEmergencyFrame && currentEmergencyFrame.emergency_data ? currentEmergencyFrame.emergency_data : {};
            const latitude = parseCoordinate(emergencyData.latitude);
            const longitude = parseCoordinate(emergencyData.longitude);
            if (Number.isFinite(latitude) && Number.isFinite(longitude) && typeof window.aprsboxCenterMapOn === "function") {
                window.aprsboxCenterMapOn(latitude, longitude);
            }
        });
    }

    const audioUnlockEvents = ["pointerdown", "keydown", "touchstart"];
    for (const eventType of audioUnlockEvents) {
        window.addEventListener(eventType, function () {
            primeEmergencyAlarmAudio();
        }, { once: true, passive: true });
    }

    root.addEventListener(eventName, function (event) {
        handleSnapshot(event && event.detail ? event.detail : {});
    });

    root.addEventListener(mapViewRefreshEventName, function () {
        if (isVisible && currentEmergencyFrame && emergencyAlarmAudio.paused) {
            playOpenBeep();
        }
    });

    if (window.__APRSBOX_TRAFFIC_SNAPSHOT__) {
        handleSnapshot(window.__APRSBOX_TRAFFIC_SNAPSHOT__);
    }
})();
