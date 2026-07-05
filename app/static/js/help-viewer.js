(function () {
    const modal = document.getElementById("help-viewer-modal");
    const titleNode = document.getElementById("help-viewer-title");
    const contentNode = document.getElementById("help-viewer-content");
    if (!(modal instanceof HTMLElement) || !(titleNode instanceof HTMLElement) || !(contentNode instanceof HTMLElement)) {
        return;
    }

    const dialog = modal.querySelector(".help-viewer-dialog");
    const closeButtons = modal.querySelectorAll("[data-close-help-viewer]");
    const rootPath = String(modal.dataset.rootPath || "");
    const apiUrl = `${rootPath}/api/help`;
    const titleText = String(modal.dataset.titleText || "Help");
    const loadingText = String(modal.dataset.loadingText || "Loading help...");
    const notFoundText = String(modal.dataset.notFoundText || "Help file not found.");
    const errorText = String(modal.dataset.errorText || "Unable to load help.");

    let currentPath = "";
    let activeRequestId = 0;
    let lastTrigger = null;

    const escapeHtml = (value) => String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll("\"", "&quot;")
        .replaceAll("'", "&#39;");

    const currentLanguage = () => {
        const language = String(document.documentElement.lang || "").trim().toLowerCase();
        return language || "en";
    };

    const renderInline = (value) => {
        let html = escapeHtml(value);
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label, href) => (
            `<a href="${escapeHtml(String(href || "").trim())}" data-help-link="1">${label}</a>`
        ));
        html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
        html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
        html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
        return html;
    };

    const renderMarkdown = (source) => {
        const lines = String(source || "").replaceAll("\r\n", "\n").split("\n");
        const html = [];
        let paragraphLines = [];
        let listItems = [];
        let codeLines = [];
        let inCodeBlock = false;

        const flushParagraph = () => {
            if (!paragraphLines.length) return;
            html.push(`<p>${renderInline(paragraphLines.join(" "))}</p>`);
            paragraphLines = [];
        };

        const flushList = () => {
            if (!listItems.length) return;
            html.push("<ul>");
            for (const item of listItems) {
                html.push(`<li>${renderInline(item)}</li>`);
            }
            html.push("</ul>");
            listItems = [];
        };

        const flushCodeBlock = () => {
            html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
            codeLines = [];
        };

        for (const rawLine of lines) {
            const trimmed = rawLine.trim();

            if (rawLine.trimStart().startsWith("```")) {
                if (inCodeBlock) {
                    flushCodeBlock();
                    inCodeBlock = false;
                } else {
                    flushParagraph();
                    flushList();
                    inCodeBlock = true;
                    codeLines = [];
                }
                continue;
            }

            if (inCodeBlock) {
                codeLines.push(rawLine);
                continue;
            }

            if (!trimmed) {
                flushParagraph();
                flushList();
                continue;
            }

            const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
            if (headingMatch) {
                flushParagraph();
                flushList();
                const level = headingMatch[1].length;
                html.push(`<h${level}>${renderInline(headingMatch[2].trim())}</h${level}>`);
                continue;
            }

            const listMatch = trimmed.match(/^-\s+(.+)$/);
            if (listMatch) {
                flushParagraph();
                listItems.push(listMatch[1].trim());
                continue;
            }

            paragraphLines.push(trimmed);
        }

        flushParagraph();
        flushList();

        if (inCodeBlock) {
            flushCodeBlock();
        }

        if (!html.length) {
            return `<p class="muted">${escapeHtml(notFoundText)}</p>`;
        }

        return html.join("\n");
    };

    const setLoading = () => {
        titleNode.textContent = titleText;
        contentNode.innerHTML = `<p class="muted">${escapeHtml(loadingText)}</p>`;
    };

    const setError = (message) => {
        titleNode.textContent = titleText;
        contentNode.innerHTML = `<p class="muted">${escapeHtml(message || errorText)}</p>`;
    };

    const openModal = (trigger) => {
        lastTrigger = trigger instanceof HTMLElement ? trigger : lastTrigger;
        modal.hidden = false;
        document.body.classList.add("modal-open");
        if (dialog instanceof HTMLElement) {
            dialog.focus();
        }
    };

    const closeModal = () => {
        modal.hidden = true;
        document.body.classList.remove("modal-open");
        if (lastTrigger instanceof HTMLElement) {
            lastTrigger.focus();
        }
    };

    const resolveMarkdownHelpPath = (href) => {
        const rawHref = String(href || "").trim();
        if (!rawHref || !currentPath) {
            return null;
        }
        try {
            const baseUrl = new URL(`/help/${currentPath}`, window.location.origin);
            const targetUrl = new URL(rawHref, baseUrl);
            const normalizedPath = decodeURIComponent(targetUrl.pathname || "");
            if (!normalizedPath.startsWith("/help/")) {
                return null;
            }
            const relativePath = normalizedPath.slice("/help/".length);
            if (!relativePath.toLowerCase().endsWith(".md")) {
                return null;
            }
            if (relativePath.split("/").some((segment) => !segment || segment === "." || segment === "..")) {
                return null;
            }
            return relativePath;
        } catch (_error) {
            return null;
        }
    };

    const fetchHelp = async (params) => {
        const requestUrl = new URL(apiUrl, window.location.origin);
        for (const [key, value] of Object.entries(params)) {
            if (value) {
                requestUrl.searchParams.set(key, String(value));
            }
        }
        const response = await fetch(requestUrl.toString(), {
            method: "GET",
            headers: { "Accept": "application/json" },
        });
        let payload = null;
        try {
            payload = await response.json();
        } catch (_error) {
            payload = null;
        }
        if (!response.ok || !payload || payload.ok !== true) {
            throw new Error(payload && payload.error ? payload.error : (response.status === 404 ? notFoundText : errorText));
        }
        return payload;
    };

    const loadHelp = async (params, trigger) => {
        activeRequestId += 1;
        const requestId = activeRequestId;
        openModal(trigger);
        setLoading();
        try {
            const payload = await fetchHelp(params);
            if (requestId !== activeRequestId) {
                return;
            }
            currentPath = String(payload.path || "");
            titleNode.textContent = String(payload.title || titleText);
            contentNode.innerHTML = renderMarkdown(payload.markdown || "");
        } catch (error) {
            if (requestId !== activeRequestId) {
                return;
            }
            currentPath = "";
            setError(error instanceof Error ? error.message : errorText);
        }
    };

    for (const button of closeButtons) {
        button.addEventListener("click", () => {
            closeModal();
        });
    }

    document.addEventListener("click", (event) => {
        const target = event.target instanceof Element ? event.target.closest("[data-help-page]") : null;
        if (!(target instanceof HTMLElement)) {
            return;
        }
        const page = String(target.getAttribute("data-help-page") || "").trim();
        if (!page) {
            return;
        }
        event.preventDefault();
        void loadHelp({ page, language: currentLanguage() }, target);
    });

    modal.addEventListener("click", (event) => {
        if (event.target instanceof HTMLElement && event.target.hasAttribute("data-close-help-viewer")) {
            closeModal();
        }
    });

    contentNode.addEventListener("click", (event) => {
        const target = event.target instanceof Element ? event.target.closest("a[data-help-link]") : null;
        if (!(target instanceof HTMLAnchorElement)) {
            return;
        }
        event.preventDefault();
        const relativePath = resolveMarkdownHelpPath(target.getAttribute("href"));
        if (!relativePath) {
            return;
        }
        void loadHelp({ path: relativePath }, lastTrigger);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !modal.hidden) {
            closeModal();
        }
    });
})();
