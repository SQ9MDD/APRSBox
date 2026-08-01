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

    function alertColor(feature) {
        const requested = String(feature?.properties?.aprsbox_alert_color || "gray").toLowerCase();
        return ["yellow", "orange", "red", "gray"].includes(requested) ? requested : "gray";
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

    const areasPaneName = "alert-detail-areas-pane";
    const areasPane = map.createPane(areasPaneName);
    areasPane.style.zIndex = "350";
    const areaLayer = window.L.geoJSON(featureCollection, {
        pane: areasPaneName,
        interactive: false,
        style: (feature) => {
            const color = alertColor(feature);
            return {
                stroke: true,
                color,
                opacity: 1,
                weight: 3,
                fill: true,
                fillColor: color,
                fillOpacity: 0.22,
            };
        },
    }).addTo(map);

    const bounds = areaLayer.getBounds();
    if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [24, 24], maxZoom: 10, animate: false });
    }

    const themeObserver = new window.MutationObserver((mutations) => {
        if (mutations.some((mutation) => mutation.attributeName === "data-theme")) {
            applyMaskOpacity();
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
