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
    const scrollerVisibleStorageKey = "aprsbox-map-scroller-visible";
    const stationsRefreshEventName = "aprsbox:map-stations-refreshed";
    const fallbackStationIconPath = `${staticRoot}icons/verG/x.gif`;
    const maxEntries = 120;

    const i18n = Object.freeze({
        show: root.dataset.i18nShow || "Show",
        hide: root.dataset.i18nHide || "Hide",
        trafficMonitor: root.dataset.i18nTrafficMonitor || "Traffic Monitor",
        noFrames: root.dataset.i18nNoFrames || "No frames received yet.",
    });

    const tnc2Regex = /^(?<source>[^>]+?)\s*>\s*(?<destination>[^,:]+?)(?:\s*,\s*(?<path>[^:]+))?\s*:(?<info>.*)$/;
    const stationIconByCallsignKey = new Map();
    let scrollerVisible = true;
    let lastSnapshotSignature = "";
    let lastSnapshotPayload = null;
    let eventSource = null;

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

    function updateStationIconLookup(stations) {
        stationIconByCallsignKey.clear();
        const resolvedStations = Array.isArray(stations) ? stations : [];
        for (const station of resolvedStations) {
            const symbolIcon = String(station && station.symbol_icon || "").trim();
            if (!symbolIcon) {
                continue;
            }
            const iconPath = `${staticRoot}${symbolIcon}`;
            const displayCallsign = normalizeCallsignKey(station && station.display_callsign);
            const baseCallsign = normalizeCallsignKey(station && station.callsign);
            if (displayCallsign) {
                stationIconByCallsignKey.set(displayCallsign, iconPath);
            }
            if (baseCallsign) {
                stationIconByCallsignKey.set(baseCallsign, iconPath);
            }
        }
    }

    function pathDigipeater(pathText) {
        const rawPath = String(pathText || "").trim();
        if (!rawPath) {
            return "-";
        }
        const starredPathItems = rawPath
            .split(",")
            .map((token) => token.trim())
            .filter((token) => token.endsWith("*"))
            .map((token) => token.slice(0, -1).trim())
            .filter((token) => token.length > 0)
            .filter((token) => !/^q[a-z]/i.test(token));
        if (starredPathItems.length === 0) {
            return "-";
        }
        return starredPathItems[starredPathItems.length - 1];
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
        if (!source) {
            return null;
        }
        const path = String(match.groups.path || "").trim();
        return {
            source,
            digipeater: pathDigipeater(path),
        };
    }

    function buildScrollerEntries(snapshot) {
        const frames = Array.isArray(snapshot && snapshot.frames) ? snapshot.frames : [];
        const entries = [];
        for (const frame of frames) {
            const direction = String(frame && frame.direction || "").trim().toUpperCase();
            if (direction !== "RX") {
                continue;
            }
            const parsed = parseTnc2Line(frame && frame.line);
            if (!parsed) {
                continue;
            }
            entries.push({
                timestamp: shortTimestamp(frame && frame.timestamp),
                station: parsed.source,
                digipeater: parsed.digipeater,
                stationIconPath: stationIconByCallsignKey.get(normalizeCallsignKey(parsed.source)) || fallbackStationIconPath,
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
                + `</span>`
                + `<span class="map-scroller-station">${escapeHtml(entry.station)}</span>`
                + `<span class="map-scroller-digi">${escapeHtml(entry.digipeater)}</span>`
            + `</div>`
        )).join("");
    }

    function applySnapshot(snapshot) {
        lastSnapshotPayload = snapshot;
        const entries = buildScrollerEntries(snapshot);
        const signature = entries.map((entry) => `${entry.timestamp}|${entry.digipeater}|${entry.station}`).join("||");
        if (signature === lastSnapshotSignature) {
            return;
        }
        lastSnapshotSignature = signature;
        renderEntries(entries);
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
        updateStationIconLookup(detail.stations);
        if (lastSnapshotPayload) {
            lastSnapshotSignature = "";
            applySnapshot(lastSnapshotPayload);
        }
    });

    connectTrafficStream();

    window.addEventListener("beforeunload", function () {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
    }, { once: true });
})();
