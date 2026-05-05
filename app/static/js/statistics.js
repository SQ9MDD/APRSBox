(() => {
    const root = document.getElementById("statistics-root");
    const payloadNode = document.getElementById("statistics-data");
    const devicesPayloadNode = document.getElementById("statistics-devices-data");
    const rangeSelect = document.getElementById("statistics-range");
    const backButton = document.getElementById("statistics-back");
    const forwardButton = document.getElementById("statistics-forward");
    const frameCanvas = document.getElementById("statistics-frame-types-chart");
    const heardCanvas = document.getElementById("statistics-heard-chart");
    const actionsCanvas = document.getElementById("statistics-actions-chart");
    const devicesCanvas = document.getElementById("statistics-devices-chart");
    const frameEmptyNode = document.getElementById("statistics-frame-types-empty");
    const heardEmptyNode = document.getElementById("statistics-heard-empty");
    const actionsEmptyNode = document.getElementById("statistics-actions-empty");
    const devicesEmptyNode = document.getElementById("statistics-devices-empty");
    const frameStepNode = document.getElementById("statistics-frame-types-step");
    const heardStepNode = document.getElementById("statistics-heard-step");
    const actionsStepNode = document.getElementById("statistics-actions-step");
    const devicesModeSelect = document.getElementById("statistics-devices-mode");
    const devicesListNode = document.getElementById("statistics-devices-list");

    if (!(root instanceof HTMLElement) || !(payloadNode instanceof HTMLScriptElement)) {
        return;
    }
    if (!(frameCanvas instanceof HTMLCanvasElement) || !(heardCanvas instanceof HTMLCanvasElement) || !(actionsCanvas instanceof HTMLCanvasElement)) {
        return;
    }
    const ChartConstructor = typeof window.Chart === "function"
        ? window.Chart
        : (window.Chart && typeof window.Chart.Chart === "function" ? window.Chart.Chart : null);
    if (!ChartConstructor) {
        return;
    }

    const apiUrl = String(root.dataset.apiUrl || "").trim();
    const devicesApiUrl = String(root.dataset.devicesApiUrl || "").trim();
    const noDataText = String(root.dataset.noDataText || "No data for selected range.");
    const aggregationLabel = String(root.dataset.aggregationLabel || "aggregation");
    const devicesCountStationsLabel = String(root.dataset.devicesCountStationsLabel || "Unique CALLSIGN-SSID stations");
    const devicesCountFramesLabel = String(root.dataset.devicesCountFramesLabel || "Frames");
    const devicesLabelOther = String(root.dataset.devicesLabelOther || "Other");
    const devicesLabelUnknown = String(root.dataset.devicesLabelUnknown || "Unknown");
    const devicesLabelMixedUnknown = String(root.dataset.devicesLabelMixedUnknown || "Mixed / Unknown");
    const supportedRanges = new Set(["24h", "7d", "30d"]);
    const supportedDeviceModes = new Set(["stations", "frames"]);
    const defaultRange = "24h";
    const defaultDeviceMode = supportedDeviceModes.has(String(root.dataset.devicesDefaultMode || "").trim().toLowerCase())
        ? String(root.dataset.devicesDefaultMode || "").trim().toLowerCase()
        : "stations";
    const storageKey = "aprsbox-statistics-range";

    let frameChart = null;
    let heardChart = null;
    let actionsChart = null;
    let devicesChart = null;

    const readChartPalette = () => {
        const isLightTheme = document.documentElement.getAttribute("data-theme") === "light";
        const rootStyle = window.getComputedStyle(document.documentElement);
        const trafficColorDefaultFromCss = rootStyle.getPropertyValue("--traffic-color-default").trim();
        const trafficColorDefault = trafficColorDefaultFromCss || (isLightTheme ? "#000000" : "#ffffff");
        const trafficColorOwnBeaconTx = rootStyle.getPropertyValue("--traffic-color-own-beacon-tx").trim() || "#4f8dff";
        const trafficColorOwnWxTx = rootStyle.getPropertyValue("--traffic-color-own-wx-tx").trim() || "#46a85f";
        const trafficColorOwnMessageTx = rootStyle.getPropertyValue("--traffic-color-own-message-tx").trim() || "#e8913a";
        const trafficColorRepeatedTx = rootStyle.getPropertyValue("--traffic-color-repeated-tx").trim() || "#d24b4b";
        const trafficColorProxyTx = rootStyle.getPropertyValue("--traffic-color-proxy-tx").trim() || "#a65fc1";
        return {
            trafficColorDefault,
            trafficColorOwnBeaconTx,
            trafficColorOwnWxTx,
            trafficColorOwnMessageTx,
            trafficColorRepeatedTx,
            trafficColorProxyTx,
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

    const normalizeDeviceMode = (value) => {
        const normalizedValue = String(value || "").trim().toLowerCase();
        return supportedDeviceModes.has(normalizedValue) ? normalizedValue : defaultDeviceMode;
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

    const normalizeShift = (value) => {
        const parsed = Number.parseInt(String(value || "0"), 10);
        if (!Number.isFinite(parsed) || parsed < 0) {
            return 0;
        }
        return parsed;
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

    const buildBarDatasets = (seriesMapValue, definitions, labelsCount) => {
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

    const createCommonOptions = (palette, options = {}) => {
        const stacked = Boolean(options.stacked);
        return ({
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
    };

    const parseJsonPayload = (node) => {
        if (!(node instanceof HTMLScriptElement)) {
            return {};
        }
        try {
            return JSON.parse(node.textContent || "{}");
        } catch (_) {
            return {};
        }
    };

    const normalizeDeviceItems = (rawItems, total) => {
        const items = Array.isArray(rawItems) ? rawItems : [];
        const normalizedTotal = Math.max(0, Number(total) || 0);
        const result = [];
        for (const item of items) {
            const key = String(item && item.key ? item.key : "").trim();
            const count = Math.max(0, Number(item && item.count) || 0);
            if (!key || count <= 0) {
                continue;
            }
            let percent = Number(item && item.percent);
            if (!Number.isFinite(percent)) {
                percent = normalizedTotal > 0 ? (count * 100.0) / normalizedTotal : 0;
            }
            result.push({
                key,
                label: String(item && item.label ? item.label : key),
                count,
                percent,
            });
        }
        return result;
    };

    const resolveDeviceLabel = (item) => {
        if (!item || !item.key) {
            return devicesLabelUnknown;
        }
        const key = String(item.key).trim().toLowerCase();
        if (key === "other") {
            return devicesLabelOther;
        }
        if (key === "unknown") {
            return devicesLabelUnknown;
        }
        if (key === "mixed_unknown") {
            return devicesLabelMixedUnknown;
        }
        return String(item.label || item.key);
    };

    const renderDeviceList = (items) => {
        if (!(devicesListNode instanceof HTMLElement)) {
            return;
        }
        devicesListNode.textContent = "";
        for (const item of items) {
            const row = document.createElement("li");
            row.className = "statistics-devices-list-item";

            const labelNode = document.createElement("span");
            labelNode.textContent = resolveDeviceLabel(item);

            const valueNode = document.createElement("span");
            valueNode.className = "statistics-devices-list-value";
            valueNode.textContent = `${Math.round(item.count)} (${Number(item.percent).toFixed(1)}%)`;

            row.appendChild(labelNode);
            row.appendChild(valueNode);
            devicesListNode.appendChild(row);
        }
    };

    const renderCharts = (payload) => {
        const labels = Array.isArray(payload && payload.labels) ? payload.labels : [];
        const labelsCount = labels.length;
        const bucketMinutes = Number(payload && payload.bucket_minutes) || 5;
        const palette = readChartPalette();
        const bucketLabel = bucketMinutes >= 1440 && bucketMinutes % 1440 === 0
            ? `${aggregationLabel} ${Math.floor(bucketMinutes / 1440)}d`
            : `${aggregationLabel} ${bucketMinutes}min`;

        if (frameStepNode instanceof HTMLElement) {
            frameStepNode.textContent = bucketLabel;
        }
        if (heardStepNode instanceof HTMLElement) {
            heardStepNode.textContent = bucketLabel;
        }
        if (actionsStepNode instanceof HTMLElement) {
            actionsStepNode.textContent = bucketLabel;
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

        const heardDatasets = buildBarDatasets(
            heardSeries,
            [
                { key: "direct_heard", label: "Direct heard", color: palette.trafficColorOwnBeaconTx },
                { key: "all_heard", label: "All heard", color: palette.trafficColorDefault },
            ],
            labelsCount,
        );

        const actionsDatasets = buildBarDatasets(
            actionsSeries,
            [
                { key: "rx", label: "RX", color: palette.trafficColorDefault },
                { key: "tx", label: "TX", color: palette.trafficColorOwnBeaconTx },
                { key: "digipeated", label: "Digipeated", color: palette.trafficColorRepeatedTx },
                { key: "gated_to_aprsis", label: "Gated to APRS-IS", color: palette.trafficColorProxyTx },
                { key: "filtered_dropped", label: "Filtered / dropped to APRS-IS", color: palette.trafficColorOwnMessageTx },
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
            frameChart = new ChartConstructor(frameContext, {
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
            heardChart = new ChartConstructor(heardContext, {
                type: "bar",
                data: {
                    labels,
                    datasets: heardDatasets,
                },
                options: createCommonOptions(palette, { stacked: false }),
            });
        }

        const actionsContext = actionsCanvas.getContext("2d");
        if (actionsContext) {
            actionsChart = new ChartConstructor(actionsContext, {
                type: "bar",
                data: {
                    labels,
                    datasets: actionsDatasets,
                },
                options: createCommonOptions(palette, { stacked: false }),
            });
        }
    };

    const buildDeviceColors = (count, palette) => {
        const base = [
            palette.trafficColorOwnBeaconTx,
            palette.trafficColorOwnWxTx,
            palette.trafficColorOwnMessageTx,
            palette.trafficColorRepeatedTx,
            palette.trafficColorProxyTx,
            "#53c8ce",
            "#c2a34e",
            "#bc6fff",
            "#7f8d99",
            "#d26e6e",
            "#8a8a8a",
        ];
        const colors = [];
        for (let index = 0; index < count; index += 1) {
            colors.push(base[index % base.length]);
        }
        return colors;
    };

    const renderDevices = (payloadValue) => {
        if (!(devicesCanvas instanceof HTMLCanvasElement)) {
            return;
        }
        const mode = normalizeDeviceMode(payloadValue && payloadValue.mode);
        const total = Math.max(0, Number(payloadValue && payloadValue.total) || 0);
        const items = normalizeDeviceItems(payloadValue && payloadValue.items, total);
        const hasData = total > 0 && items.length > 0;

        toggleEmptyState(devicesEmptyNode, !hasData);
        renderDeviceList(hasData ? items : []);

        if (devicesChart) {
            devicesChart.destroy();
            devicesChart = null;
        }

        if (!hasData) {
            return;
        }

        const palette = readChartPalette();
        const labels = items.map((item) => resolveDeviceLabel(item));
        const counts = items.map((item) => Number(item.count) || 0);
        const colors = buildDeviceColors(counts.length, palette);
        const countBasisLabel = mode === "frames" ? devicesCountFramesLabel : devicesCountStationsLabel;

        const context = devicesCanvas.getContext("2d");
        if (!context) {
            return;
        }

        devicesChart = new ChartConstructor(context, {
            type: "doughnut",
            data: {
                labels,
                datasets: [
                    {
                        data: counts,
                        backgroundColor: colors,
                        borderColor: withAlpha(palette.colorBorder, 0.7),
                        borderWidth: 1,
                        hoverOffset: 4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "62%",
                plugins: {
                    legend: {
                        display: false,
                    },
                    tooltip: {
                        displayColors: true,
                        callbacks: {
                            label: (contextValue) => {
                                const item = items[contextValue.dataIndex] || { count: 0, percent: 0, label: "" };
                                const label = resolveDeviceLabel(item);
                                const count = Math.max(0, Number(item.count) || 0);
                                const percent = Number(item.percent) || 0;
                                return `${label}: ${count} (${percent.toFixed(1)}%) • ${countBasisLabel}`;
                            },
                        },
                    },
                },
            },
        });
    };

    let payload = parseJsonPayload(payloadNode);
    let devicesPayload = parseJsonPayload(devicesPayloadNode);

    let activeRange = normalizeRange(payload && payload.range);
    let activeShift = normalizeShift(payload && payload.shift_windows);
    const storedRange = readStoredRange();
    if (storedRange) {
        activeRange = storedRange;
        activeShift = 0;
    }

    let activeDeviceMode = normalizeDeviceMode(
        (devicesPayload && devicesPayload.mode)
        || (devicesModeSelect instanceof HTMLSelectElement ? devicesModeSelect.value : "")
        || defaultDeviceMode,
    );

    const setControlsDisabled = (disabled) => {
        if (rangeSelect instanceof HTMLSelectElement) {
            rangeSelect.disabled = disabled;
        }
        if (backButton instanceof HTMLButtonElement) {
            backButton.disabled = disabled;
        }
        if (forwardButton instanceof HTMLButtonElement) {
            forwardButton.disabled = disabled || activeShift <= 0;
        }
    };

    const loadDevicesPayload = async (rangeValue, shiftValue, modeValue, options = {}) => {
        const disableModeControl = Boolean(options.disableModeControl);
        if (!(devicesCanvas instanceof HTMLCanvasElement) || !devicesApiUrl) {
            return;
        }
        const normalizedMode = normalizeDeviceMode(modeValue);
        const normalizedRange = normalizeRange(rangeValue);
        const normalizedShift = normalizeShift(shiftValue);

        if (devicesModeSelect instanceof HTMLSelectElement) {
            devicesModeSelect.value = normalizedMode;
            if (disableModeControl) {
                devicesModeSelect.disabled = true;
            }
        }

        try {
            const response = await fetch(
                `${devicesApiUrl}?range=${encodeURIComponent(normalizedRange)}&shift=${encodeURIComponent(String(normalizedShift))}&mode=${encodeURIComponent(normalizedMode)}`,
                {
                    method: "GET",
                    headers: { "Accept": "application/json" },
                },
            );
            if (!response.ok) {
                return;
            }
            const nextPayload = await response.json();
            devicesPayload = nextPayload;
            activeDeviceMode = normalizeDeviceMode(nextPayload && nextPayload.mode);
            if (devicesModeSelect instanceof HTMLSelectElement) {
                devicesModeSelect.value = activeDeviceMode;
            }
            renderDevices(nextPayload);
        } catch (_) {
            return;
        } finally {
            if (devicesModeSelect instanceof HTMLSelectElement && disableModeControl) {
                devicesModeSelect.disabled = false;
            }
        }
    };

    const loadRangePayload = async (rangeValue, shiftValue) => {
        const normalizedRange = normalizeRange(rangeValue);
        const normalizedShift = normalizeShift(shiftValue);
        if (!apiUrl) {
            return;
        }
        setControlsDisabled(true);
        try {
            const response = await fetch(
                `${apiUrl}?range=${encodeURIComponent(normalizedRange)}&shift=${encodeURIComponent(String(normalizedShift))}`,
                {
                    method: "GET",
                    headers: { "Accept": "application/json" },
                },
            );
            if (!response.ok) {
                return;
            }
            const nextPayload = await response.json();
            payload = nextPayload;
            activeRange = normalizeRange(nextPayload && nextPayload.range);
            activeShift = normalizeShift(nextPayload && nextPayload.shift_windows);
            persistRange(activeRange);
            if (rangeSelect instanceof HTMLSelectElement) {
                rangeSelect.value = activeRange;
            }
            renderCharts(nextPayload);
            await loadDevicesPayload(activeRange, activeShift, activeDeviceMode);
        } catch (_) {
            return;
        } finally {
            setControlsDisabled(false);
        }
    };

    if (rangeSelect instanceof HTMLSelectElement) {
        rangeSelect.value = activeRange;
        rangeSelect.addEventListener("change", () => {
            activeShift = 0;
            void loadRangePayload(rangeSelect.value, activeShift);
        });
    }
    if (backButton instanceof HTMLButtonElement) {
        backButton.addEventListener("click", () => {
            void loadRangePayload(activeRange, activeShift + 1);
        });
    }
    if (forwardButton instanceof HTMLButtonElement) {
        forwardButton.addEventListener("click", () => {
            if (activeShift <= 0) {
                return;
            }
            void loadRangePayload(activeRange, activeShift - 1);
        });
    }
    if (devicesModeSelect instanceof HTMLSelectElement) {
        devicesModeSelect.value = activeDeviceMode;
        devicesModeSelect.addEventListener("change", () => {
            const nextMode = normalizeDeviceMode(devicesModeSelect.value);
            activeDeviceMode = nextMode;
            void loadDevicesPayload(activeRange, activeShift, nextMode, { disableModeControl: true });
        });
    }

    renderCharts(payload);
    renderDevices(devicesPayload);
    setControlsDisabled(false);

    if (activeRange !== normalizeRange(payload && payload.range)) {
        void loadRangePayload(activeRange, activeShift);
    } else if (!(devicesPayload && Array.isArray(devicesPayload.items) && devicesPayload.range === activeRange)) {
        void loadDevicesPayload(activeRange, activeShift, activeDeviceMode);
    }
})();
