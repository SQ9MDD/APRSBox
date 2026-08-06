(function () {
    const root = document.getElementById("map-root");
    const overlay = document.getElementById("map-scroller-overlay");
    if (!root || !overlay) {
        return;
    }

    const streamEndpoint = String(root.dataset.trafficStreamEndpoint || "").trim();
    const toggleButton = document.getElementById("map-toggle-scroller");
    const toggleIcon = document.getElementById("map-toggle-scroller-icon");
    const staticRoot = root.dataset.staticRoot || "/static/";
    const aprsSymbolIconFallback = window.APRSBOX_APRS_SYMBOL_ICON_FALLBACK || "icons/verG/x.gif";
    const scrollerVisibleStorageKey = "aprsbox-map-scroller-visible";
    const stationsRefreshEventName = "aprsbox:map-stations-refreshed";
    const mapViewRefreshEventName = "aprsbox:map-view-refreshed";
    const trafficSnapshotEventName = "aprsbox:traffic-snapshot";
    const fallbackStationIconPath = `${staticRoot}${aprsSymbolIconFallback}`;
    const maxEntries = 120;
    const stationSourceKey = normalizeCallsignKey(root.dataset.stationSourceKey || "");
    const stationSourceCallsign = baseCallsignKey(stationSourceKey);

    const i18n = Object.freeze({
        show: root.dataset.i18nShow || "Show",
        hide: root.dataset.i18nHide || "Hide",
        trafficMonitor: root.dataset.i18nTrafficMonitor || "Traffic Monitor",
        noFrames: root.dataset.i18nNoFrames || "No frames received yet.",
    });

    const tnc2Regex = /^(?<source>[^>]+?)\s*>\s*(?<destination>[^,:]+?)(?:\s*,\s*(?<path>[^:]+))?\s*:(?<info>.*)$/;
    const stationByCallsignKey = new Map();
    let scrollerVisible = true;
    let lastSnapshotSignature = "";
    let lastSnapshotPayload = null;
    let eventSource = null;
    let mapViewState = {
        centerLatitude: NaN,
        centerLongitude: NaN,
        visibleRadiusKm: NaN,
    };

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
    }

    function resolveScrollerVisible() {
        const storedValue = String(window.localStorage.getItem(scrollerVisibleStorageKey) || "").trim().toLowerCase();
        if (storedValue === "0" || storedValue === "false") {
            return false;
        }
        if (storedValue === "1" || storedValue === "true") {
            return true;
        }
        return true;
    }

    function applyScrollerToggleState(visible) {
        scrollerVisible = Boolean(visible);
        window.localStorage.setItem(scrollerVisibleStorageKey, scrollerVisible ? "1" : "0");
        overlay.hidden = !scrollerVisible;
        if (toggleIcon) {
            toggleIcon.setAttribute("src", `${staticRoot}icons/${scrollerVisible ? "format-list-bulleted.svg" : "format-list-bulleted-square.svg"}`);
        }
        if (toggleButton) {
            const label = `${scrollerVisible ? i18n.hide : i18n.show} ${i18n.trafficMonitor}`;
            toggleButton.setAttribute("title", label);
            toggleButton.setAttribute("aria-label", label);
        }
    }

    function shortTimestamp(value) {
        const text = String(value || "").trim();
        if (!text) {
            return "--";
        }
        const match = text.match(/(\d{2}:\d{2}(?::\d{2})?)/);
        return match ? match[1] : text;
    }

    function normalizeCallsignKey(value) {
        return String(value || "").trim().toUpperCase();
    }

    function baseCallsignKey(value) {
        const normalized = normalizeCallsignKey(value);
        if (!normalized) {
            return "";
        }
        const dashIndex = normalized.indexOf("-");
        if (dashIndex <= 0) {
            return normalized;
        }
        const suffix = normalized.slice(dashIndex + 1);
        if (/^[A-Z0-9]{1,2}$/.test(suffix)) {
            return normalized.slice(0, dashIndex);
        }
        return normalized;
    }

    function registerStationLookupEntry(callsign, stationInfo) {
        const normalized = normalizeCallsignKey(callsign);
        if (!normalized) {
            return;
        }
        stationByCallsignKey.set(normalized, stationInfo);
    }

    function updateStationLookup(stations) {
        stationByCallsignKey.clear();
        const resolvedStations = Array.isArray(stations) ? stations : [];
        for (const station of resolvedStations) {
            const symbolIcon = String((station && station.symbol_icon) || "").trim();
            const stationInfo = {
                iconPath: symbolIcon ? `${staticRoot}${symbolIcon}` : fallbackStationIconPath,
                symbolOverlay: resolveSymbolOverlay(station && station.symbol_table),
                latitude: Number((station && station.latitude)),
                longitude: Number((station && station.longitude)),
            };
            registerStationLookupEntry(station && station.display_callsign, stationInfo);
            if (!String((station && station.display_callsign) || "").trim()) {
                registerStationLookupEntry(station && station.callsign, stationInfo);
            }
        }
    }

    function resolveSymbolOverlay(symbolTable) {
        const normalized = String(symbolTable || "").trim();
        if (!normalized || normalized === "/" || normalized === "\\") {
            return "";
        }
        return normalized.charAt(0);
    }

    function updateMapViewState(detail) {
        const resolved = detail && typeof detail === "object" ? detail : {};
        mapViewState = {
            centerLatitude: Number(resolved.center_latitude),
            centerLongitude: Number(resolved.center_longitude),
            visibleRadiusKm: Number(resolved.visible_radius_km),
        };
    }

    function parseTnc2Line(line) {
        const text = String(line || "").trim();
        if (!text) {
            return null;
        }
        const match = text.match(tnc2Regex);
        if (!match || !match.groups) {
            return null;
        }
        const source = String(match.groups.source || "").trim();
        const destination = String(match.groups.destination || "").trim();
        if (!source || !destination) {
            return null;
        }
        return {
            source,
            destination,
            path: String(match.groups.path || "").trim(),
            info: String(match.groups.info || ""),
        };
    }

    function tokenizeUsedPath(pathText) {
        const tokens = String(pathText || "")
            .split(",")
            .map((token) => token.trim())
            .filter((token) => token.length > 0);
        if (!tokens.length) {
            return [];
        }
        const starredIndexes = [];
        for (let index = 0; index < tokens.length; index += 1) {
            if (tokens[index].endsWith("*")) {
                starredIndexes.push(index);
            }
        }
        if (!starredIndexes.length) {
            return [];
        }
        // Standard monitor output may mark only the last used hop with "*".
        // In that case, every token up to that hop is treated as used.
        if (starredIndexes.length === 1) {
            const usedTokens = [];
            const usedEndIndex = starredIndexes[0];
            for (let index = 0; index <= usedEndIndex; index += 1) {
                const cleaned = tokens[index].endsWith("*")
                    ? tokens[index].slice(0, -1).trim()
                    : tokens[index];
                if (cleaned) {
                    usedTokens.push(cleaned);
                }
            }
            return usedTokens;
        }
        return tokens
            .filter((token) => token.endsWith("*"))
            .map((token) => token.slice(0, -1).trim())
            .filter((token) => token.length > 0);
    }

    function isQConstructToken(token) {
        return /^q[A-Z]/i.test(String(token || "").trim());
    }

    function isGenericAliasToken(token) {
        const normalized = normalizeCallsignKey(token);
        if (!normalized) {
            return false;
        }
        if (isQConstructToken(normalized)) {
            return true;
        }
        if (/^(?:WIDE|TRACE|RELAY|GATE)(?:\d+)?(?:-\d+)?$/.test(normalized)) {
            return true;
        }
        if (/^[A-Z]{1,5}\d(?:-\d+)?$/.test(normalized)) {
            return true;
        }
        if (["TCPIP", "TCPXX", "RFONLY", "NOGATE", "NORF"].includes(normalized)) {
            return true;
        }
        return false;
    }

    function formatDigipeaterLabel(value) {
        const normalized = normalizeCallsignKey(value);
        if (!normalized) {
            return "-";
        }
        const dashIndex = normalized.indexOf("-");
        if (dashIndex > 0) {
            const ssid = normalized.slice(dashIndex + 1);
            if (ssid === "0") {
                return `${normalized.slice(0, dashIndex)}*`;
            }
        }
        return `${normalized}*`;
    }

    function resolveLastDigipeater(pathText) {
        const usedTokens = tokenizeUsedPath(pathText);
        if (!usedTokens.length) {
            return "-";
        }
        for (let index = usedTokens.length - 1; index >= 0; index -= 1) {
            const token = usedTokens[index];
            if (isQConstructToken(token) || isGenericAliasToken(token)) {
                continue;
            }
            return formatDigipeaterLabel(token);
        }
        return formatDigipeaterLabel(usedTokens[usedTokens.length - 1]);
    }

    function pathContainsOwnDigipeat(pathText) {
        const usedTokens = tokenizeUsedPath(pathText);
        if (!usedTokens.length) {
            return false;
        }
        for (const token of usedTokens) {
            if (isQConstructToken(token)) {
                continue;
            }
            const full = normalizeCallsignKey(token);
            const base = baseCallsignKey(full);
            if (stationSourceKey && (full === stationSourceKey || base === stationSourceKey)) {
                return true;
            }
            if (stationSourceCallsign && (full === stationSourceCallsign || base === stationSourceCallsign)) {
                return true;
            }
        }
        return false;
    }

    function parseFrameLine(line) {
        const outer = parseTnc2Line(line);
        if (!outer) {
            return null;
        }
        const info = String(outer.info || "");
        const isThirdParty = info.startsWith("}");
        const inner = isThirdParty ? parseTnc2Line(info.slice(1).trimStart()) : null;
        const station = String((inner && inner.source) || outer.source || "").trim();
        if (!station) {
            return null;
        }
        const digipeatedByLocal = pathContainsOwnDigipeat(outer.path);
        let digipeater = resolveLastDigipeater(outer.path);
        if (isThirdParty) {
            digipeater = formatDigipeaterLabel(outer.source);
        }
        const usedPathTokens = tokenizeUsedPath(outer.path);
        return {
            station,
            digipeater,
            isThirdParty,
            digipeatedByLocal,
            isDirectRf: !isThirdParty && usedPathTokens.length === 0,
        };
    }

    function distanceKm(fromLatitude, fromLongitude, toLatitude, toLongitude) {
        const earthRadiusKm = 6371;
        const latRadFrom = (fromLatitude * Math.PI) / 180;
        const lonRadFrom = (fromLongitude * Math.PI) / 180;
        const latRadTo = (toLatitude * Math.PI) / 180;
        const lonRadTo = (toLongitude * Math.PI) / 180;
        const deltaLat = latRadTo - latRadFrom;
        const deltaLon = lonRadTo - lonRadFrom;
        const a = (
            (Math.sin(deltaLat / 2) ** 2)
            + (Math.cos(latRadFrom) * Math.cos(latRadTo) * (Math.sin(deltaLon / 2) ** 2))
        );
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return earthRadiusKm * c;
    }

    function stationTextColor(stationCallsign) {
        const station = stationByCallsignKey.get(normalizeCallsignKey(stationCallsign));
        if (!station || !Number.isFinite(station.latitude) || !Number.isFinite(station.longitude)) {
            return "#000000";
        }
        if (
            !Number.isFinite(mapViewState.centerLatitude)
            || !Number.isFinite(mapViewState.centerLongitude)
            || !Number.isFinite(mapViewState.visibleRadiusKm)
            || mapViewState.visibleRadiusKm <= 0
        ) {
            return "hsl(120 100% 34%)";
        }
        const currentDistanceKm = distanceKm(
            station.latitude,
            station.longitude,
            mapViewState.centerLatitude,
            mapViewState.centerLongitude
        );
        const ratio = Math.max(0, Math.min(1, currentDistanceKm / mapViewState.visibleRadiusKm));
        const hue = Math.round(120 * ratio);
        return `hsl(${hue} 100% 40%)`;
    }

    function ingressMarker(parsedFrame) {
        if (parsedFrame.digipeatedByLocal) {
            return "@";
        }
        if (parsedFrame.isThirdParty) {
            return "#";
        }
        if (parsedFrame.isDirectRf) {
            return "*";
        }
        return "";
    }

    function isOwnStationCallsign(callsign) {
        const full = normalizeCallsignKey(callsign);
        const base = baseCallsignKey(full);
        if (stationSourceKey && (full === stationSourceKey || base === stationSourceKey)) {
            return true;
        }
        if (stationSourceCallsign && (full === stationSourceCallsign || base === stationSourceCallsign)) {
            return true;
        }
        return false;
    }

    function resolveMarker(parsedFrame, direction) {
        if (direction === "TX" && isOwnStationCallsign(parsedFrame.station)) {
            return "@";
        }
        return ingressMarker(parsedFrame);
    }

    function stationIconPath(stationCallsign) {
        const station = stationByCallsignKey.get(normalizeCallsignKey(stationCallsign));
        return (station && station.iconPath) || fallbackStationIconPath;
    }

    function stationIconOverlay(stationCallsign) {
        const station = stationByCallsignKey.get(normalizeCallsignKey(stationCallsign));
        return (station && station.symbolOverlay) || "";
    }

    function frameIconPath(frame, fallbackCallsign) {
        const displayIconPath = String((frame && frame.display_icon_path) || "").trim();
        if (displayIconPath) {
            return `${staticRoot}${displayIconPath}`;
        }
        const displayPacketGroup = String((frame && frame.display_packet_group) || "").trim().toLowerCase();
        if (displayPacketGroup === "object" || displayPacketGroup === "item") {
            return fallbackStationIconPath;
        }
        return stationIconPath(fallbackCallsign);
    }

    function buildScrollerEntries(snapshot) {
        const frames = Array.isArray(snapshot && snapshot.frames) ? snapshot.frames : [];
        const entries = [];
        for (const frame of frames) {
            const direction = String((frame && frame.direction) || "").trim().toUpperCase();
            const parsed = parseFrameLine(frame && frame.line);
            if (!parsed) {
                continue;
            }
            const isOwn = isOwnStationCallsign(parsed.station);
            if (direction !== "RX" && !(direction === "TX" && isOwn)) {
                continue;
            }
            const marker = resolveMarker(parsed, direction);
            const displayCallsign = String((frame && frame.display_callsign) || parsed.station || "").trim() || parsed.station;
            const stationLabel = `${displayCallsign}${marker}`;
            entries.push({
                timestamp: shortTimestamp(frame && frame.timestamp),
                station: displayCallsign,
                stationLabel,
                digipeater: parsed.digipeater,
                stationIconPath: frameIconPath(frame, displayCallsign || parsed.station),
                stationIconOverlay: stationIconOverlay(displayCallsign || parsed.station),
                stationColor: stationTextColor(displayCallsign || parsed.station),
            });
            if (entries.length >= maxEntries) {
                break;
            }
        }
        return entries;
    }

    function renderEntries(entries) {
        if (!entries.length) {
            overlay.innerHTML = `<p class="map-scroller-empty">${escapeHtml(i18n.noFrames)}</p>`;
            return;
        }
        overlay.innerHTML = entries.map((entry) => (
            `<div class="map-scroller-row">`
                + `<span class="map-scroller-icon-wrap" title="${escapeHtml(entry.timestamp)}">`
                    + `<img class="map-scroller-icon" src="${escapeHtml(entry.stationIconPath)}" alt="">`
                    + `${entry.stationIconOverlay ? `<span class="aprs-symbol-overlay" aria-hidden="true">${escapeHtml(entry.stationIconOverlay)}</span>` : ""}`
                + `</span>`
                + `<span class="map-scroller-station" style="color:${escapeHtml(entry.stationColor)}">${escapeHtml(entry.stationLabel)}</span>`
                + `<span class="map-scroller-digi">${escapeHtml(entry.digipeater)}</span>`
            + `</div>`
        )).join("");
    }

    function applySnapshot(snapshot) {
        lastSnapshotPayload = snapshot;
        window.__APRSBOX_TRAFFIC_SNAPSHOT__ = snapshot;
        window.dispatchEvent(new window.CustomEvent(trafficSnapshotEventName, {
            detail: snapshot,
        }));
        root.dispatchEvent(new window.CustomEvent(trafficSnapshotEventName, {
            detail: snapshot,
        }));
        const entries = buildScrollerEntries(snapshot);
        const signature = entries
            .map((entry) => `${entry.timestamp}|${entry.stationLabel}|${entry.digipeater}|${entry.stationIconPath}|${entry.stationIconOverlay}|${entry.stationColor}`)
            .join("||");
        if (signature === lastSnapshotSignature) {
            return;
        }
        lastSnapshotSignature = signature;
        renderEntries(entries);
    }

    function refreshFromLastSnapshot() {
        if (!lastSnapshotPayload) {
            return;
        }
        lastSnapshotSignature = "";
        applySnapshot(lastSnapshotPayload);
    }

    function connectTrafficStream() {
        if (!streamEndpoint) {
            return;
        }
        eventSource = new window.EventSource(streamEndpoint);
        eventSource.onmessage = function (event) {
            try {
                const payload = JSON.parse(event.data || "{}");
                applySnapshot(payload);
            } catch (_error) {
            }
        };
    }

    applyScrollerToggleState(resolveScrollerVisible());
    renderEntries([]);

    if (toggleButton) {
        toggleButton.addEventListener("click", function () {
            applyScrollerToggleState(!scrollerVisible);
        });
    }

    root.addEventListener(stationsRefreshEventName, function (event) {
        const detail = event && event.detail ? event.detail : {};
        updateStationLookup(detail.stations);
        refreshFromLastSnapshot();
    });

    root.addEventListener(mapViewRefreshEventName, function (event) {
        const detail = event && event.detail ? event.detail : {};
        updateMapViewState(detail);
        refreshFromLastSnapshot();
    });

    window.__APRSBOX_TRAFFIC_STREAM_MANAGED__ = true;
    connectTrafficStream();

    window.addEventListener("beforeunload", function () {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
    }, { once: true });
})();
