(() => {
    const dataNode = document.getElementById("own-alert-page-data");
    if (!dataNode) return;

    let pageData;
    try {
        pageData = JSON.parse(dataNode.textContent || "{}");
    } catch (_) {
        return;
    }

    const rootPath = String(pageData.rootPath || "");
    const compose = pageData.compose || {};
    const i18n = pageData.i18n || {};
    const groups = new Map((compose.groups || []).map((group) => [group.group, group]));
    const format = (template, values = {}) => Object.entries(values).reduce(
        (text, [key, value]) => text.replaceAll(`{${key}}`, String(value)),
        String(template || "")
    );
    const responseError = async (response, fallback) => {
        try {
            const body = await response.json();
            return String(body.detail || fallback);
        } catch (_) {
            return fallback;
        }
    };
    const setModalOpen = (open) => document.body.classList.toggle("modal-open", open);
    const showModal = (modal) => {
        if (!modal) return;
        modal.hidden = false;
        setModalOpen(true);
        modal.querySelector(".own-alert-modal-dialog")?.focus();
    };
    const hideModal = (modal) => {
        if (!modal) return;
        modal.hidden = true;
        setModalOpen(Boolean(document.querySelector(".own-alert-modal:not([hidden])")));
    };

    const cancelModal = document.getElementById("own-alert-cancel-modal");
    const cancelForm = document.getElementById("own-alert-cancel-form");
    const cancelLabel = document.getElementById("own-alert-cancel-label");
    document.querySelectorAll("[data-alert-protocol-cancel]").forEach((button) => {
        button.addEventListener("click", () => {
            const id = button.dataset.alertProtocolCancel || "";
            if (cancelForm) cancelForm.action = `${rootPath}/alerts/${encodeURIComponent(id)}/cancel-protocol`;
            if (cancelLabel) cancelLabel.textContent = button.dataset.alertProtocolLabel || id;
            showModal(cancelModal);
        });
    });
    document.querySelectorAll("[data-close-own-alert-cancel]").forEach((button) => {
        button.addEventListener("click", () => hideModal(cancelModal));
    });

    const form = document.getElementById("own-alert-compose-form");
    if (!form) return;
    const target = document.getElementById("own-alert-target");
    const areaSelect = document.getElementById("own-alert-area");
    const areaStatus = document.getElementById("own-alert-area-status");
    const hazardSelect = document.getElementById("own-alert-hazard");
    const levelSelect = document.getElementById("own-alert-level");
    const validity = document.getElementById("own-alert-validity");
    const comment = document.getElementById("own-alert-comment");
    const repeat = document.getElementById("own-alert-repeat");
    const characterCounter = document.getElementById("own-alert-character-counter");
    const partsCounter = document.getElementById("own-alert-parts-counter");
    const formStatus = document.getElementById("own-alert-form-status");
    const confirmModal = document.getElementById("own-alert-confirm-modal");
    const confirmSend = document.getElementById("own-alert-confirm-send");
    const confirmError = document.getElementById("own-alert-confirm-error");
    const technicalFrames = document.getElementById("own-alert-technical-frames");
    let areas = [];
    let previewTimer = 0;
    let previewSequence = 0;
    let lastPreview = null;
    let pendingPayload = null;

    const collectPayload = () => ({
        target_group: target?.value || "",
        area_code: areaSelect?.value || "",
        event_family: hazardSelect?.value || "",
        severity_level: Number(levelSelect?.value || 0),
        validity_hours: Number(validity?.value || 0),
        comment: comment?.value || "",
        repeat_interval_minutes: Number(repeat?.value || 0),
    });
    const selectedArea = () => areas.find((area) => area.code === areaSelect?.value);
    const areaLabel = (area) => {
        if (!area) return "";
        const parent = area.parent ? ` · ${area.parent}` : "";
        return `${area.name} — ${area.code}${parent}`;
    };
    const renderAreas = () => {
        if (!areaSelect) return;
        const selected = areaSelect.value;
        areaSelect.replaceChildren();
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = i18n.selectArea || "Select an area";
        areaSelect.append(placeholder);
        areas.forEach((area) => {
            const option = document.createElement("option");
            option.value = area.code;
            option.textContent = areaLabel(area);
            areaSelect.append(option);
        });
        if (areas.some((area) => area.code === selected)) areaSelect.value = selected;
    };
    const renderHazards = () => {
        if (!hazardSelect || !target) return;
        const selected = hazardSelect.value;
        const options = groups.get(target.value)?.hazard_options || [];
        hazardSelect.replaceChildren();
        options.forEach((event) => {
            const option = document.createElement("option");
            option.value = event.code;
            option.textContent = event.translated_label || event.label;
            hazardSelect.append(option);
        });
        if (options.some((option) => option.code === selected)) hazardSelect.value = selected;
    };
    const renderLevels = () => {
        if (!levelSelect || !target) return;
        const selected = levelSelect.value || "2";
        const options = groups.get(target.value)?.level_options || [];
        levelSelect.replaceChildren();
        options.forEach((level) => {
            const option = document.createElement("option");
            option.value = level.value;
            option.textContent = level.translated_label || level.label;
            levelSelect.append(option);
        });
        if (options.some((option) => String(option.value) === selected)) levelSelect.value = selected;
    };
    const clearPreview = (message = "") => {
        lastPreview = null;
        if (characterCounter) characterCounter.textContent = message;
        if (partsCounter) partsCounter.textContent = "";
    };
    const requestPreview = async () => {
        const payload = collectPayload();
        if (!payload.target_group || !payload.area_code || !payload.event_family || !payload.severity_level) {
            clearPreview(i18n.selectArea || "Select an area");
            return null;
        }
        const sequence = ++previewSequence;
        try {
            const response = await fetch(`${rootPath}/api/alerts/send/preview`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            if (sequence !== previewSequence) return null;
            if (!response.ok) {
                throw new Error(await responseError(response, i18n.previewError));
            }
            const preview = await response.json();
            lastPreview = preview;
            if (characterCounter) {
                characterCounter.classList.remove("field-validation-error");
                characterCounter.textContent = format(i18n.remainingCharacters, {
                    count: preview.remaining_characters,
                });
            }
            if (partsCounter) {
                partsCounter.textContent = format(i18n.parts, { count: preview.parts_total });
            }
            return preview;
        } catch (error) {
            if (sequence !== previewSequence) return null;
            const message = String(error?.message || i18n.previewError || "");
            clearPreview(message);
            if (characterCounter) characterCounter.classList.add("field-validation-error");
            return null;
        }
    };
    const schedulePreview = () => {
        window.clearTimeout(previewTimer);
        previewTimer = window.setTimeout(() => void requestPreview(), 160);
    };
    const loadAreas = async () => {
        if (!target || !areaSelect) return;
        const requestedGroup = target.value;
        areas = [];
        if (areaStatus) areaStatus.classList.remove("field-validation-error");
        areaSelect.disabled = true;
        areaSelect.replaceChildren(new Option(i18n.loadingAreas || "Loading areas...", ""));
        if (areaStatus) areaStatus.textContent = i18n.loadingAreas || "";
        clearPreview();
        try {
            const response = await fetch(
                `${rootPath}/api/alerts/send/areas?group=${encodeURIComponent(requestedGroup)}`
            );
            if (!response.ok) throw new Error(await responseError(response, i18n.areasUnavailable));
            const payload = await response.json();
            if (target.value !== requestedGroup) return;
            areas = Array.isArray(payload.areas) ? payload.areas : [];
            renderAreas();
            areaSelect.disabled = areas.length === 0;
            const defaultCode = String(payload.default_area_code || "");
            if (defaultCode && areas.some((area) => area.code === defaultCode)) {
                areaSelect.value = defaultCode;
            } else if (areaStatus) {
                areaStatus.textContent = payload.station_position_known
                    ? (i18n.areaNotMatched || "")
                    : (i18n.positionUnknown || "");
            }
            schedulePreview();
        } catch (error) {
            areaSelect.replaceChildren(new Option(i18n.areasUnavailable || "-", ""));
            if (areaStatus) {
                areaStatus.textContent = String(error?.message || i18n.areasUnavailable || "");
                areaStatus.classList.add("field-validation-error");
            }
        }
    };

    target?.addEventListener("change", () => {
        renderHazards();
        renderLevels();
        void loadAreas();
    });
    areaSelect?.addEventListener("change", () => {
        if (areaStatus && areaSelect.value) {
            areaStatus.textContent = areaLabel(selectedArea());
            areaStatus.classList.remove("field-validation-error");
        }
        schedulePreview();
    });
    [hazardSelect, levelSelect, validity, repeat].forEach((field) => field?.addEventListener("change", schedulePreview));
    comment?.addEventListener("input", schedulePreview);

    const populateConfirmation = (preview) => {
        const setField = (name, value) => {
            const node = confirmModal?.querySelector(`[data-confirm-field="${name}"]`);
            if (node) node.textContent = String(value || "-");
        };
        setField("target_group", preview.target_group);
        setField("area", areaLabel(preview.area));
        const hazard = (groups.get(preview.target_group)?.hazard_options || [])
            .find((option) => option.code === preview.event_family);
        const level = (groups.get(preview.target_group)?.level_options || [])
            .find((option) => Number(option.value) === Number(preview.severity_level));
        setField(
            "event_code",
            `${hazard?.translated_label || hazard?.label || preview.event_family} — ${level?.translated_label || level?.label || preview.severity_level}`
        );
        setField("valid_until", new Date(preview.valid_until).toLocaleString());
        setField("repeat", format(i18n.minutes, { count: preview.repeat_interval_minutes }));
        setField("comment", preview.comment || "-");
        setField("parts_total", format(i18n.parts, { count: preview.parts_total }));
        if (technicalFrames) technicalFrames.textContent = (preview.technical_frames || []).join("\n");
        if (confirmError) {
            confirmError.hidden = true;
            confirmError.textContent = "";
        }
    };
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!form.reportValidity()) return;
        pendingPayload = collectPayload();
        if (formStatus) formStatus.textContent = "";
        const preview = await requestPreview();
        if (!preview) {
            if (formStatus) {
                formStatus.textContent = i18n.previewError || "";
                formStatus.classList.add("field-validation-error");
            }
            return;
        }
        populateConfirmation(preview);
        showModal(confirmModal);
    });
    document.querySelectorAll("[data-close-own-alert-confirm]").forEach((button) => {
        button.addEventListener("click", () => hideModal(confirmModal));
    });
    confirmSend?.addEventListener("click", async () => {
        if (!pendingPayload) return;
        confirmSend.disabled = true;
        if (confirmError) {
            confirmError.hidden = false;
            confirmError.textContent = i18n.sending || "";
        }
        try {
            const response = await fetch(`${rootPath}/api/alerts/send`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(pendingPayload),
            });
            if (!response.ok) throw new Error(await responseError(response, i18n.previewError));
            const targetUrl = new URL(`${window.location.origin}${rootPath}/alerts`);
            targetUrl.searchParams.set("flash", i18n.sent || "Alarm queued for transmission.");
            targetUrl.searchParams.set("flash_success", "1");
            window.location.assign(targetUrl.toString());
        } catch (error) {
            if (confirmError) {
                confirmError.hidden = false;
                confirmError.textContent = String(error?.message || i18n.previewError || "");
            }
            confirmSend.disabled = false;
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        [confirmModal, cancelModal].forEach((modal) => {
            if (modal && !modal.hidden) hideModal(modal);
        });
    });

    renderHazards();
    renderLevels();
    void loadAreas();
})();
