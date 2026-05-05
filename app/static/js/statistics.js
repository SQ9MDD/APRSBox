(() => {
    const root = document.getElementById("statistics-root");
    const payloadNode = document.getElementById("statistics-data");
    const rangeSelect = document.getElementById("statistics-range");
    const frameCanvas = document.getElementById("statistics-frame-types-chart");
    const heardCanvas = document.getElementById("statistics-heard-chart");
    const actionsCanvas = document.getElementById("statistics-actions-chart");
    const frameEmptyNode = document.getElementById("statistics-frame-types-empty");
    const heardEmptyNode = document.getElementById("statistics-heard-empty");
    const actionsEmptyNode = document.getElementById("statistics-actions-empty");
    const frameStepNode = document.getElementById("statistics-frame-types-step");
    const heardStepNode = document.getElementById("statistics-heard-step");
    const actionsStepNode = document.getElementById("statistics-actions-step");

    if (!(root instanceof HTMLElement) || !(payloadNode instanceof HTMLScriptElement)) {
        return;
    }
    if (!(frameCanvas instanceof HTMLCanvasElement) || !(heardCanvas instanceof HTMLCanvasElement) || !(actionsCanvas instanceof HTMLCanvasElement)) {
        return;
    }
    if (!window.Chart || typeof window.Chart !== "function") {
        return;
    }

    const apiUrl = String(root.dataset.apiUrl || "").trim();
    const noDataText = String(root.dataset.noDataText || "No data for selected range.");
    const minStepText = String(root.dataset.minStepText || "min step");
    const supportedRanges = new Set(["6h", "24h", "7d"]);
    const defaultRange = "24h";
    const storageKey = "aprsbox-statistics-range";

    let frameChart = null;
    let heardChart = null;
    let actionsChart = null;

    const readChartPalette = () => {
        const isLightTheme = document.documentElement.getAttribute("data-theme") === "light";
        const rootStyle = window.getComputedStyle(document.documentElement);
        const trafficColorDefaultFromCss = rootStyle.getPropertyValue("--traffic-color-default").trim();
        const trafficColorDefault = trafficColorDefaultFromCss || (isLightTheme ? "#000000" : "#ffffff");
        const trafficColorOwnBeaconTx = rootStyle.getPropertyValue("--traffic-color-own-beacon-tx").trim() || "#4f8dff";
        const trafficColorOwnWxTx = rootStyle.getPropertyValue("--traffic-color-own-wx-tx").trim() || "#46a85f";
        const trafficColorOwnMessageTx = rootStyle.getPropertyValue("--traffic-color-own-message-tx").trim() || "#e8913a";
        const trafficColorRepeatedTx = rootStyle.getPropertyValue("--traffic-color-repeated-tx").trim() || "#d24b4b";
        return {
            trafficColorDefault,
            trafficColorOwnBeaconTx,
            trafficColorOwnWxTx,
            trafficColorOwnMessageTx,
            trafficColorRepeatedTx,
            colorText: rootStyle.getPropertyValue("--text").trim() || "#e6efe8",
            colorMuted: rootStyle.getPropertyValue("--muted").trim() || "#9cb0a2",
            colorBorder: rootStyle.getPropertyValue("--border").trim() || "rgba(255, 255, 255, 0.18)",
        };
    };

    const withAlpha = (color, alpha) => {
        const safeColor = String(color || "").trim();
        if (safeColor.startsWith("#") && (safeColor.length === 7 || safeColor.length === 4)) {
            let hex = safeColor.slice(1);
            if (hex.length === 3) {
                hex = `${hex[0]}${hex[0]}${hex[1]}${hex[1]}${hex[2]}${hex[2]}`;
            }
            const red = Number.parseInt(hex.slice(0, 2), 16);
            const green = Number.parseInt(hex.slice(2, 4), 16);
            const blue = Number.parseInt(hex.slice(4, 6), 16);
            if (Number.isFinite(red) && Number.isFinite(green) && Number.isFinite(blue)) {
                return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
            }
        }
        return safeColor;
    };

    const normalizeRange = (value) => {
        const normalizedValue = String(value || "").trim().toLowerCase();
        return supportedRanges.has(normalizedValue) ? normalizedValue : defaultRange;
    };

    const readStoredRange = () => {
        try {
            return normalizeRange(window.localStorage.getItem(storageKey) || defaultRange);
        } catch (_) {
            return defaultRange;
        }
    };

    const persistRange = (value) => {
        try {
            window.localStorage.setItem(storageKey, normalizeRange(value));
        } catch (_) {
            return;
        }
    };

    const normalizeSeriesData = (value, expectedLength) => {
        const raw = Array.isArray(value) ? value : [];
        const normalized = raw.slice(0, expectedLength).map((item) => Number(item) || 0);
        while (normalized.length < expectedLength) {
            normalized.push(0);
        }
        return normalized;
    };

    const seriesMap = (payload, chartKey) => {
        const list = payload && payload.charts && payload.charts[chartKey] && Array.isArray(payload.charts[chartKey].series)
            ? payload.charts[chartKey].series
            : [];
        const map = {};
        for (const item of list) {
            const key = String((item && item.key) || "").trim();
            if (!key) {
                continue;
            }
            map[key] = {
                label: String(item.label || key),
                data: item.data,
            };
        }
        return map;
    };

    const buildStackedBarDatasets = (seriesMapValue, definitions, labelsCount) => {
        return definitions.map((definition) => {
            const source = seriesMapValue[definition.key] || { label: definition.label, data: [] };
            return {
                label: source.label || definition.label,
                data: normalizeSeriesData(source.data, labelsCount),
                borderColor: definition.color,
                backgroundColor: withAlpha(definition.color, 0.18),
                borderWidth: 1,
                borderRadius: 3,
                borderSkipped: false,
                pointRadius: 0,
                stack: "stats",
            };
        });
    };

    const buildLineDatasets = (seriesMapValue, definitions, labelsCount) => {
        return definitions.map((definition) => {
            const source = seriesMapValue[definition.key] || { label: definition.label, data: [] };
            return {
                label: source.label || definition.label,
                data: normalizeSeriesData(source.data, labelsCount),
                borderColor: definition.color,
                backgroundColor: withAlpha(definition.color, 0.16),
                borderWidth: 2,
                fill: false,
                tension: 0.25,
                pointRadius: 0,
                pointHoverRadius: 3,
            };
        });
    };

    const hasAnyData = (datasets) => datasets.some((dataset) => Array.isArray(dataset.data) && dataset.data.some((value) => Number(value) > 0));

    const toggleEmptyState = (node, showEmpty) => {
        if (!(node instanceof HTMLElement)) {
            return;
        }
        node.textContent = noDataText;
        node.hidden = !showEmpty;
    };

    const createCommonOptions = (palette, *, stacked) => ({
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
            x: {
                stacked,
                ticks: { color: palette.colorMuted, maxRotation: 0, autoSkip: true, maxTicksLimit: 16 },
                grid: { color: withAlpha(palette.colorBorder, 0.65) },
            },
            y: {
                beginAtZero: true,
                stacked,
                ticks: { color: palette.colorMuted, precision: 0 },
                grid: { color: withAlpha(palette.colorBorder, 0.7) },
            },
        },
        plugins: {
            legend: {
                labels: {
                    color: palette.colorText,
                    usePointStyle: true,
                    boxWidth: 10,
                },
            },
            tooltip: {
                displayColors: true,
                mode: "index",
                intersect: false,
            },
        },
    });

    const renderCharts = (payload) => {
        const labels = Array.isArray(payload && payload.labels) ? payload.labels : [];
        const labelsCount = labels.length;
        const bucketMinutes = Number(payload && payload.bucket_minutes) || 5;
        const palette = readChartPalette();

        if (frameStepNode instanceof HTMLElement) {
            frameStepNode.textContent = `${bucketMinutes} ${minStepText}`;
        }
        if (heardStepNode instanceof HTMLElement) {
            heardStepNode.textContent = `${bucketMinutes} ${minStepText}`;
        }
        if (actionsStepNode instanceof HTMLElement) {
            actionsStepNode.textContent = `${bucketMinutes} ${minStepText}`;
        }

        const frameSeries = seriesMap(payload, "frame_types");
        const heardSeries = seriesMap(payload, "heard");
        const actionsSeries = seriesMap(payload, "actions");

        const frameDatasets = buildStackedBarDatasets(
            frameSeries,
            [
                { key: "position", label: "Position", color: palette.trafficColorDefault },
                { key: "weather", label: "Weather", color: palette.trafficColorOwnWxTx },
                { key: "message", label: "Message", color: palette.trafficColorOwnMessageTx },
                { key: "object_item", label: "Object / Item", color: palette.trafficColorOwnBeaconTx },
                { key: "status", label: "Status", color: "#7f8d99" },
                { key: "telemetry", label: "Telemetry", color: "#bc6fff" },
                { key: "query", label: "Query", color: "#53c8ce" },
                { key: "user_defined", label: "User-defined", color: "#c2a34e" },
                { key: "third_party", label: "Third-party", color: "#d26e6e" },
                { key: "other_unknown", label: "Other / Unknown", color: "#8a8a8a" },
            ],
            labelsCount,
        );

        const heardDatasets = buildLineDatasets(
            heardSeries,
            [
                { key: "direct_heard", label: "Direct heard", color: palette.trafficColorOwnBeaconTx },
                { key: "all_heard", label: "All heard", color: palette.trafficColorDefault },
            ],
            labelsCount,
        );

        const actionsDatasets = buildStackedBarDatasets(
            actionsSeries,
            [
                { key: "rx", label: "RX", color: palette.trafficColorDefault },
                { key: "tx", label: "TX", color: palette.trafficColorOwnBeaconTx },
                { key: "digipeated", label: "Digipeated", color: palette.trafficColorRepeatedTx },
                { key: "gated_to_aprsis", label: "Gated to APRS-IS", color: palette.trafficColorOwnWxTx },
                { key: "filtered_dropped", label: "Filtered / Dropped", color: palette.trafficColorOwnMessageTx },
                { key: "duplicate_ignored", label: "Duplicate ignored", color: "#8a8a8a" },
            ],
            labelsCount,
        );

        toggleEmptyState(frameEmptyNode, !hasAnyData(frameDatasets));
        toggleEmptyState(heardEmptyNode, !hasAnyData(heardDatasets));
        toggleEmptyState(actionsEmptyNode, !hasAnyData(actionsDatasets));

        if (frameChart) {
            frameChart.destroy();
            frameChart = null;
        }
        if (heardChart) {
            heardChart.destroy();
            heardChart = null;
        }
        if (actionsChart) {
            actionsChart.destroy();
            actionsChart = null;
        }

        const frameContext = frameCanvas.getContext("2d");
        if (frameContext) {
            frameChart = new window.Chart(frameContext, {
                type: "bar",
                data: {
                    labels,
                    datasets: frameDatasets,
                },
                options: createCommonOptions(palette, { stacked: true }),
            });
        }

        const heardContext = heardCanvas.getContext("2d");
        if (heardContext) {
            heardChart = new window.Chart(heardContext, {
                type: "line",
                data: {
                    labels,
                    datasets: heardDatasets,
                },
                options: createCommonOptions(palette, { stacked: false }),
            });
        }

        const actionsContext = actionsCanvas.getContext("2d");
        if (actionsContext) {
            actionsChart = new window.Chart(actionsContext, {
                type: "bar",
                data: {
                    labels,
                    datasets: actionsDatasets,
                },
                options: createCommonOptions(palette, { stacked: true }),
            });
        }
    };

    let payload = {};
    try {
        payload = JSON.parse(payloadNode.textContent || "{}");
    } catch (_) {
        payload = {};
    }

    let activeRange = normalizeRange(payload && payload.range);
    const storedRange = readStoredRange();
    if (storedRange) {
        activeRange = storedRange;
    }

    const loadRangePayload = async (rangeValue) => {
        const normalizedRange = normalizeRange(rangeValue);
        if (!(rangeSelect instanceof HTMLSelectElement) || !apiUrl) {
            return;
        }
        rangeSelect.disabled = true;
        try {
            const response = await fetch(`${apiUrl}?range=${encodeURIComponent(normalizedRange)}`, {
                method: "GET",
                headers: { "Accept": "application/json" },
            });
            if (!response.ok) {
                return;
            }
            const nextPayload = await response.json();
            payload = nextPayload;
            activeRange = normalizeRange(nextPayload && nextPayload.range);
            persistRange(activeRange);
            rangeSelect.value = activeRange;
            renderCharts(nextPayload);
        } catch (_) {
            return;
        } finally {
            rangeSelect.disabled = false;
        }
    };

    if (rangeSelect instanceof HTMLSelectElement) {
        rangeSelect.value = activeRange;
        rangeSelect.addEventListener("change", () => {
            void loadRangePayload(rangeSelect.value);
        });
    }

    renderCharts(payload);

    if (activeRange !== normalizeRange(payload && payload.range)) {
        void loadRangePayload(activeRange);
    }
})();
