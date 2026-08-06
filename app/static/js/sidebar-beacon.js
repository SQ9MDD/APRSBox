(function () {
    const button = document.getElementById("sidebar-send-beacon");
    const modal = document.getElementById("sidebar-beacon-modal");
    const confirmButton = document.getElementById("sidebar-beacon-confirm");
    const statusNode = document.getElementById("sidebar-beacon-status");
    if (
        !(button instanceof HTMLButtonElement)
        || !(modal instanceof HTMLElement)
        || !(confirmButton instanceof HTMLButtonElement)
        || !(statusNode instanceof HTMLElement)
    ) {
        return;
    }

    const dialog = modal.querySelector(".sidebar-beacon-dialog");
    const closeButtons = modal.querySelectorAll("[data-close-sidebar-beacon]");
    const endpoint = String(modal.dataset.endpoint || "").trim();
    const successMessage = String(modal.dataset.successMessage || "Beacon queued for transmission.");
    const errorMessage = String(modal.dataset.errorMessage || "Beacon could not be queued.");
    const baseLabel = String(button.getAttribute("aria-label") || "Send beacon");
    const cooldownStorageKey = "aprsbox-beacon-send-cooldown-until";
    const cooldownMs = 10_000;
    let cooldownTimer = null;
    let closeTimer = null;
    let sending = false;

    const readCooldownUntil = () => {
        try {
            const value = Number.parseInt(window.localStorage.getItem(cooldownStorageKey) || "0", 10);
            return Number.isFinite(value) ? value : 0;
        } catch (_error) {
            return 0;
        }
    };

    const writeCooldownUntil = (value) => {
        try {
            window.localStorage.setItem(cooldownStorageKey, String(value));
        } catch (_error) {
            return;
        }
    };

    const remainingCooldownMs = () => Math.max(0, readCooldownUntil() - Date.now());

    const scheduleCooldownSync = () => {
        if (cooldownTimer !== null) {
            window.clearTimeout(cooldownTimer);
            cooldownTimer = null;
        }
        const remaining = remainingCooldownMs();
        const seconds = Math.ceil(remaining / 1000);
        button.disabled = sending || remaining > 0;
        button.setAttribute("aria-label", seconds > 0 ? `${baseLabel} (${seconds}s)` : baseLabel);
        button.setAttribute("title", seconds > 0 ? `${baseLabel} (${seconds}s)` : baseLabel);
        confirmButton.disabled = sending || remaining > 0;
        if (remaining > 0) {
            cooldownTimer = window.setTimeout(scheduleCooldownSync, Math.min(remaining, 250));
        }
    };

    const showStatus = (message, success) => {
        statusNode.textContent = message;
        statusNode.classList.toggle("tone-success", success);
        statusNode.classList.toggle("tone-error", !success);
        statusNode.hidden = false;
    };

    const clearStatus = () => {
        statusNode.textContent = "";
        statusNode.classList.remove("tone-success", "tone-error");
        statusNode.hidden = true;
    };

    const closeModal = () => {
        if (sending) {
            return;
        }
        modal.hidden = true;
        document.body.style.removeProperty("overflow");
        button.focus();
    };

    const openModal = () => {
        if (remainingCooldownMs() > 0 || sending) {
            scheduleCooldownSync();
            return;
        }
        clearStatus();
        modal.hidden = false;
        document.body.style.overflow = "hidden";
        if (dialog instanceof HTMLElement) {
            dialog.focus();
        }
    };

    button.addEventListener("click", openModal);
    for (const closeButton of closeButtons) {
        closeButton.addEventListener("click", closeModal);
    }

    modal.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            event.preventDefault();
            closeModal();
        }
    });

    confirmButton.addEventListener("click", async () => {
        if (sending || remainingCooldownMs() > 0 || !endpoint) {
            scheduleCooldownSync();
            return;
        }

        sending = true;
        writeCooldownUntil(Date.now() + cooldownMs);
        scheduleCooldownSync();
        clearStatus();

        try {
            const response = await window.fetch(endpoint, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
            });
            const payload = await response.json().catch(() => ({}));
            const ok = response.ok && Boolean(payload.ok);
            showStatus(ok ? successMessage : String(payload.message || errorMessage), ok);
            if (ok) {
                closeTimer = window.setTimeout(() => {
                    sending = false;
                    closeModal();
                    scheduleCooldownSync();
                }, 900);
                return;
            }
        } catch (_error) {
            showStatus(errorMessage, false);
        }

        sending = false;
        scheduleCooldownSync();
    });

    window.addEventListener("storage", (event) => {
        if (event.key === cooldownStorageKey) {
            scheduleCooldownSync();
        }
    });
    window.addEventListener("beforeunload", () => {
        if (cooldownTimer !== null) {
            window.clearTimeout(cooldownTimer);
        }
        if (closeTimer !== null) {
            window.clearTimeout(closeTimer);
        }
    });

    scheduleCooldownSync();
})();
