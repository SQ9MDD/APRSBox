(function () {
    const root = document.getElementById("aprs-emergency-root");
    const modal = document.getElementById("aprs-emergency-modal");
    if (!root || !modal) {
        return;
    }

    const eventName = "aprsbox:traffic-snapshot";
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
    const openAlertLink = document.getElementById("aprs-emergency-open-alert");
    const rootPath = String(root.dataset.rootPath || "");
    const streamEndpoint = String(root.dataset.trafficStreamEndpoint || "").trim();
    const emergencyFrameReceivedText = String(root.dataset.i18nEmergencyFrameReceived || "Emergency frame received");
    const activeEmergencyText = String(root.dataset.i18nActiveEmergency || "Active emergency");
    const alertMutedText = String(root.dataset.i18nAlertMuted || "Alert muted");
    const handledAlertsStorageKey = "aprsbox-emergency-alerts-shown";

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
    let eventSource = null;
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
            frame.alert_id || "",
            emergencyData.timestamp_utc || frame.timestamp || "",
            emergencyData.raw_frame || frame.line || "",
        ].join("|");
    }

    function emergencyFrameSortValue(frame) {
        const emergencyData = frame && typeof frame === "object" ? (frame.emergency_data || {}) : {};
        const rawTimestamp = String(emergencyData.timestamp_utc || frame.timestamp || "").trim();
        const parsedTimestamp = Date.parse(rawTimestamp);
        return Number.isFinite(parsedTimestamp) ? parsedTimestamp : -Infinity;
    }

    function readHandledAlertIds() {
        try {
            const parsed = JSON.parse(window.sessionStorage.getItem(handledAlertsStorageKey) || "[]");
            if (!Array.isArray(parsed)) {
                return new Set();
            }
            return new Set(parsed.map((value) => String(value || "")).filter(Boolean));
        } catch (_error) {
            return new Set();
        }
    }

    function isAlertHandled(frame) {
        const alertId = String(frame && frame.alert_id ? frame.alert_id : "").trim();
        return Boolean(alertId) && readHandledAlertIds().has(alertId);
    }

    function markAlertHandled(frame) {
        const alertId = String(frame && frame.alert_id ? frame.alert_id : "").trim();
        if (!alertId) {
            return;
        }
        const handledIds = readHandledAlertIds();
        handledIds.add(alertId);
        try {
            window.sessionStorage.setItem(
                handledAlertsStorageKey,
                JSON.stringify(Array.from(handledIds).slice(-200))
            );
        } catch (_error) {
        }
    }

    function selectNewestEmergencyFrame(frames) {
        if (!Array.isArray(frames) || frames.length === 0) {
            return null;
        }
        const candidates = frames.filter((frame) =>
            frame
            && frame.emergency
            && frame.alert_should_notify
            && !frame.alert_muted
            && !isAlertHandled(frame)
        );
        candidates.sort((left, right) => emergencyFrameSortValue(right) - emergencyFrameSortValue(left));
        return candidates[0] || null;
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
        openMapButton.disabled = !hasCoordinates;
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

    function showModal({ playSound = false } = {}) {
        if (isVisible) {
            return;
        }
        isVisible = true;
        modal.hidden = false;
        document.body.classList.add("modal-open");
        if (dialog instanceof HTMLElement) {
            dialog.focus();
        }
        if (playSound) {
            playOpenBeep();
        }
    }

    function renderEmergencyFrame(frame, { playSound = false, remember = false } = {}) {
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
            title.textContent = emergencyFrameReceivedText;
        }
        if (callsign) {
            callsign.textContent = call;
        }
        if (status) {
            status.textContent = frame.alert_muted ? alertMutedText : activeEmergencyText;
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
        if (openAlertLink) {
            if (frame.alert_href) {
                openAlertLink.href = `${rootPath}${frame.alert_href}`;
                openAlertLink.hidden = false;
            } else {
                openAlertLink.hidden = true;
            }
        }

        renderMiniMap(latitude, longitude);
        updateOpenMapButton(latitude, longitude);
        if (remember) {
            markAlertHandled(frame);
        }
        showModal({ playSound });
    }

    function handleSnapshot(snapshot) {
        const frames = Array.isArray(snapshot && snapshot.frames) ? snapshot.frames : [];
        const emergencyFrame = selectNewestEmergencyFrame(frames);
        if (!emergencyFrame) {
            return;
        }

        const nextSignature = emergencySignature(emergencyFrame);
        if (nextSignature && nextSignature === currentSignature && isVisible) {
            return;
        }
        if (!isVisible && nextSignature && nextSignature === dismissedSignature) {
            return;
        }

        if (isVisible && currentSignature && nextSignature !== currentSignature) {
            showNewerNotice();
        }
        dismissedSignature = "";
        renderEmergencyFrame(emergencyFrame, { playSound: true, remember: true });
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
            if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
                return;
            }
            if (typeof window.aprsboxCenterMapOn === "function") {
                window.aprsboxCenterMapOn(latitude, longitude);
                return;
            }
            const mapUrl = new URL(`${rootPath}/map`, window.location.origin);
            mapUrl.searchParams.set("lat", String(latitude));
            mapUrl.searchParams.set("lon", String(longitude));
            mapUrl.searchParams.set("zoom", "15");
            window.location.href = mapUrl.toString();
        });
    }

    const audioUnlockEvents = ["pointerdown", "keydown", "touchstart"];
    for (const eventType of audioUnlockEvents) {
        window.addEventListener(eventType, function () {
            primeEmergencyAlarmAudio();
        }, { once: true, passive: true });
    }

    window.addEventListener(eventName, function (event) {
        handleSnapshot(event && event.detail ? event.detail : {});
    });

    window.aprsboxOpenEmergencyModal = function (frame) {
        if (!frame || typeof frame !== "object" || !frame.emergency) {
            return false;
        }
        dismissedSignature = "";
        renderEmergencyFrame(frame, { playSound: false, remember: false });
        return true;
    };

    if (window.__APRSBOX_TRAFFIC_SNAPSHOT__) {
        handleSnapshot(window.__APRSBOX_TRAFFIC_SNAPSHOT__);
    }

    if (!window.__APRSBOX_TRAFFIC_STREAM_MANAGED__ && streamEndpoint) {
        window.__APRSBOX_TRAFFIC_STREAM_MANAGED__ = true;
        eventSource = new window.EventSource(streamEndpoint);
        eventSource.onmessage = function (event) {
            try {
                const snapshot = JSON.parse(event.data || "{}");
                window.__APRSBOX_TRAFFIC_SNAPSHOT__ = snapshot;
                window.dispatchEvent(new window.CustomEvent(eventName, {
                    detail: snapshot,
                }));
            } catch (_error) {
            }
        };
    }

    window.addEventListener("beforeunload", function () {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
    }, { once: true });
})();
