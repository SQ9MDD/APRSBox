(() => {
    const statusPanel = document.querySelector("[data-aprsis-interface-status]");
    if (!statusPanel) {
        return;
    }

    const diagnosticsUrl = statusPanel.dataset.diagnosticsUrl || "";
    const staticRoot = statusPanel.dataset.staticRoot || "/static/";
    const pollingIntervalMs = 3000;
    let timerId = null;

    const renderStatusLabel = (value) => {
        const normalized = String(value || "").trim();
        if (!normalized) return "-";
        return normalized.charAt(0).toUpperCase() + normalized.slice(1);
    };

    const renderDateTime = (value) => {
        const normalized = String(value || "").trim();
        if (!normalized) return "-";
        const parsed = /(?:[zZ]|[+-]\d{2}:\d{2})$/.test(normalized)
            ? new Date(normalized)
            : new Date(`${normalized}Z`);
        if (Number.isNaN(parsed.getTime())) return normalized;
        const year = parsed.getUTCFullYear();
        const month = String(parsed.getUTCMonth() + 1).padStart(2, "0");
        const day = String(parsed.getUTCDate()).padStart(2, "0");
        const hour = String(parsed.getUTCHours()).padStart(2, "0");
        const minute = String(parsed.getUTCMinutes()).padStart(2, "0");
        return `${year}.${month}.${day} ${hour}:${minute} UTC`;
    };

    const setText = (id, value) => {
        const element = document.getElementById(id);
        if (!element) return;
        if (value === null || value === undefined || String(value).length === 0) {
            element.textContent = "-";
            return;
        }
        element.textContent = String(value);
    };

    const setCounterTriple = (id, first, second, third) => {
        setText(id, `${Number(first || 0)} / ${Number(second || 0)} / ${Number(third || 0)}`);
    };

    const applyRuntime = (runtime, runtimeBadge, config) => {
        const badge = document.getElementById("igate-runtime-badge");
        const icon = document.getElementById("igate-runtime-icon");
        const label = document.getElementById("igate-runtime-label");
        if (!badge || !icon || !label) {
            return;
        }

        badge.classList.remove("tnc-badge-enabled", "tnc-badge-disabled", "status-pill", "status-unknown");
        if (runtimeBadge === "enabled") {
            badge.classList.add("tnc-badge-enabled");
        } else if (runtimeBadge === "warning") {
            badge.classList.add("status-pill", "status-unknown");
        } else {
            badge.classList.add("tnc-badge-disabled");
        }

        const status = String((runtime || {}).status || "").trim().toLowerCase();
        const iconFile = status === "connected"
            ? "check-circle.svg"
            : (status === "connecting" ? "progress-clock.svg" : "close-circle.svg");
        icon.src = `${staticRoot}icons/${iconFile}`;
        label.textContent = renderStatusLabel(status);

        setText("igate-runtime-detail", (runtime || {}).status_detail || "-");
        const runtimeServer = String((runtime || {}).server || "").trim();
        const runtimePort = Number((runtime || {}).port || 0);
        const configServer = String((config || {}).server || "").trim();
        const configPort = Number((config || {}).port || 0);
        const server = runtimeServer || configServer;
        const port = runtimePort || configPort;
        setText("igate-runtime-server", server ? `${server}${port ? `:${port}` : ""}` : "-");
        setText("igate-runtime-login", String((runtime || {}).login || "").trim() || String((config || {}).login || "").trim() || "-");
        setText("igate-runtime-connected-at", renderDateTime((runtime || {}).connected_at));
        setText("igate-runtime-last-error", (runtime || {}).last_error || "-");
    };

    const applyDiagnostics = (diagnostics) => {
        const diag = diagnostics || {};
        const tx = diag.tx || {};
        const strictRejects = diag.strict_rejects || {};
        setText("igate-diag-active-flow-count", Number(diag.active_flow_count || 0));
        setText(
            "igate-diag-active-flow-names",
            Array.isArray(diag.active_flow_names) && diag.active_flow_names.length
                ? diag.active_flow_names.join(", ")
                : "-",
        );
        setText("igate-diag-last-activity", renderDateTime(diag.last_activity_at));
        setCounterTriple("igate-diag-tx-sent", tx.sent_total, tx.sent_1h, tx.sent_24h);
        setCounterTriple("igate-diag-tx-drop", tx.drop_total, tx.drop_1h, tx.drop_24h);
        setCounterTriple("igate-diag-strict-total", strictRejects.total, strictRejects.last_1h, strictRejects.last_24h);
    };

    const refreshDiagnostics = async () => {
        if (!diagnosticsUrl || statusPanel.hidden) {
            return;
        }
        try {
            const response = await fetch(diagnosticsUrl, { headers: { Accept: "application/json" } });
            if (!response.ok) return;
            const payload = await response.json();
            applyRuntime(payload.runtime || {}, payload.runtime_badge || "disabled", payload.config || {});
            applyDiagnostics(payload.diagnostics || {});
        } catch (_error) {
        }
    };

    timerId = window.setInterval(refreshDiagnostics, pollingIntervalMs);
    void refreshDiagnostics();
    window.addEventListener("beforeunload", () => {
        if (timerId !== null) {
            window.clearInterval(timerId);
        }
    });
})();
