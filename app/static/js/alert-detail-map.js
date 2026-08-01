(function () {
    const mapRoot = document.getElementById("alert-detail-map-root");
    const mapCanvas = document.getElementById("alert-detail-map-canvas");
    const mapPlaceholder = document.getElementById("alert-detail-map-placeholder");

    if (!mapRoot || !mapCanvas || typeof window.L === "undefined") {
        return;
    }

    function parseFeatureCollection(value) {
        try {
            const parsed = JSON.parse(value || "");
            if (parsed?.type === "FeatureCollection" && Array.isArray(parsed.features)) {
                return parsed;
            }
        } catch (_error) {
        }
        return { type: "FeatureCollection", features: [] };
    }

    function parseTileSubdomains(value) {
        return String(value || "")
            .split(/[,\s]+/)
            .map((token) => token.trim())
            .filter(Boolean);
    }

    function alertColorName(feature) {
        const requested = String(feature?.properties?.aprsbox_alert_color || "gray").toLowerCase();
        return ["yellow", "orange", "red", "gray"].includes(requested) ? requested : "gray";
    }

    function themeProperty(name, fallback) {
        const value = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return value || fallback;
    }

    function alertColor(feature) {
        const colorName = alertColorName(feature);
        return themeProperty(`--alert-detail-map-area-${colorName}`, colorName);
    }

    function alertFillOpacity() {
        const value = Number.parseFloat(
            themeProperty("--alert-detail-map-area-fill-opacity", "0.22")
        );
        return Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0.22;
    }

    function areaHaloStyle() {
        return {
            stroke: true,
            color: themeProperty("--alert-detail-map-area-halo", "rgba(0, 0, 0, 0.85)"),
            opacity: 0.96,
            weight: 7,
            lineCap: "round",
            lineJoin: "round",
            fill: false,
        };
    }

    function areaStyle(feature) {
        const color = alertColor(feature);
        return {
            stroke: true,
            color,
            opacity: 1,
            weight: 3,
            lineCap: "round",
            lineJoin: "round",
            fill: true,
            fillColor: color,
            fillOpacity: alertFillOpacity(),
        };
    }

    const featureCollection = parseFeatureCollection(mapRoot.dataset.featureCollection);
    if (!featureCollection.features.length) {
        mapRoot.hidden = true;
        if (mapPlaceholder) {
            mapPlaceholder.hidden = false;
        }
        return;
    }

    mapRoot.hidden = false;
    if (mapPlaceholder) {
        mapPlaceholder.hidden = true;
    }

    const map = window.L.map(mapCanvas, {
        center: [52.1, 19.4],
        zoom: 6,
        zoomControl: true,
        attributionControl: true,
    });

    const tileUrl = String(mapRoot.dataset.tileUrl || "").trim();
    if (tileUrl) {
        const tileOptions = {
            attribution: String(mapRoot.dataset.tileAttribution || ""),
        };
        const minZoom = Number.parseInt(mapRoot.dataset.tileMinZoom || "", 10);
        const maxZoom = Number.parseInt(mapRoot.dataset.tileMaxZoom || "", 10);
        const subdomains = parseTileSubdomains(mapRoot.dataset.tileSubdomains);
        if (Number.isInteger(minZoom)) {
            tileOptions.minZoom = minZoom;
        }
        if (Number.isInteger(maxZoom)) {
            tileOptions.maxZoom = maxZoom;
        }
        if (subdomains.length) {
            tileOptions.subdomains = subdomains;
        }
        window.L.tileLayer(tileUrl, tileOptions).addTo(map);
    }

    const maskPaneName = "alert-detail-map-mask-pane";
    const maskPane = map.createPane(maskPaneName);
    maskPane.classList.add("map-mask-pane");
    maskPane.style.zIndex = "300";
    maskPane.style.pointerEvents = "none";
    const maskLayer = document.createElement("div");
    maskLayer.className = "map-mask-layer";
    maskPane.appendChild(maskLayer);

    function syncMaskViewport() {
        const size = map.getSize();
        const mapPane = map.getPane("mapPane");
        const position = mapPane ? window.L.DomUtil.getPosition(mapPane) : null;
        const offsetX = Number.isFinite(position?.x) ? position.x : 0;
        const offsetY = Number.isFinite(position?.y) ? position.y : 0;
        maskPane.style.transform = "";
        maskPane.style.left = `${-offsetX}px`;
        maskPane.style.top = `${-offsetY}px`;
        maskPane.style.width = `${size.x}px`;
        maskPane.style.height = `${size.y}px`;
    }

    function currentThemeName() {
        return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    }

    function applyMaskOpacity() {
        let opacityPercent = Number.parseInt(
            window.localStorage.getItem(`aprsbox-map-mask-opacity-${currentThemeName()}`) || "",
            10
        );
        if (!Number.isInteger(opacityPercent) || opacityPercent < 0 || opacityPercent > 100) {
            const defaultOpacity = Number.parseFloat(
                window.getComputedStyle(document.documentElement).getPropertyValue("--map-mask-default-opacity") || ""
            );
            opacityPercent = Number.isFinite(defaultOpacity)
                ? Math.max(0, Math.min(100, Math.round(defaultOpacity * 100)))
                : 20;
        }
        const opacity = opacityPercent / 100;
        maskLayer.style.opacity = String(opacity);
        mapCanvas.style.setProperty("--map-mask-layer-opacity", String(opacity));
    }

    map.on("resize zoom move", syncMaskViewport);
    syncMaskViewport();
    applyMaskOpacity();

    const areaHaloPaneName = "alert-detail-area-halo-pane";
    const areaHaloPane = map.createPane(areaHaloPaneName);
    areaHaloPane.style.zIndex = "349";
    areaHaloPane.style.pointerEvents = "none";
    const areaHaloLayer = window.L.geoJSON(featureCollection, {
        pane: areaHaloPaneName,
        interactive: false,
        style: areaHaloStyle,
    }).addTo(map);

    const areasPaneName = "alert-detail-areas-pane";
    const areasPane = map.createPane(areasPaneName);
    areasPane.style.zIndex = "350";
    areasPane.style.pointerEvents = "none";
    const areaLayer = window.L.geoJSON(featureCollection, {
        pane: areasPaneName,
        interactive: false,
        style: areaStyle,
    }).addTo(map);

    const bounds = areaLayer.getBounds();
    if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [24, 24], maxZoom: 10, animate: false });
    }

    const themeObserver = new window.MutationObserver((mutations) => {
        if (mutations.some((mutation) => mutation.attributeName === "data-theme")) {
            applyMaskOpacity();
            areaHaloLayer.setStyle(areaHaloStyle);
            areaLayer.setStyle(areaStyle);
        }
    });
    themeObserver.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["data-theme"],
    });

    map.whenReady(() => {
        window.setTimeout(() => {
            map.invalidateSize();
            syncMaskViewport();
        }, 0);
    });
})();
