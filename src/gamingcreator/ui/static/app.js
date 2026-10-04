"use strict";

(() => {
    const byId = (id) => document.getElementById(id);
    const ui = Object.fromEntries([
        "notice", "project-select", "project-path", "project-form", "refresh-projects",
        "run-select", "refresh-runs", "refresh-view", "run-state", "source-name",
        "source-duration", "event-count", "transcript-count", "cost-known", "cost-detail",
        "stage-summary", "stage-list", "source-video", "video-empty", "preview-badge",
        "current-time", "total-time", "play-selection", "add-active", "active-title",
        "active-range", "active-facts", "evidence-tab", "transcript-tab", "evidence-panel",
        "transcript-panel", "evidence-count", "evidence-list", "transcript-tab-count",
        "transcript-list", "search-form", "query", "mode", "top", "search-button",
        "candidate-count", "search-context", "candidate-list", "selection-count",
        "selection-list", "selection-warning", "clear-selection", "export-json",
        "export-csv", "timeline-count", "timeline-filter", "tag-filter", "timeline-map",
        "timeline-end", "video-scrubber", "timeline-list", "filter-summary",
        "evidence-dialog", "evidence-dialog-title", "close-evidence", "evidence-full",
        "evidence-dialog-detail",
    ].map((id) => [id, byId(id)]));
    const state = {
        project: "", run: "", revision: 0, runs: [], view: null, active: null,
        selections: [], basketMediaId: null, inspectController: null, runsController: null,
        projectsController: null, busy: false, playbackEndUs: null, pendingSeekUs: null,
        frameRequest: null, sourceUrl: "", storageWarningShown: false,
    };
    const statusLabels = {
        pending: "等待分析", running: "分析中", completed: "已完成", failed: "失败",
        cancelled: "已取消", interrupted: "已中断",
    };

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = String(text);
        return node;
    }

    function empty(container, text) {
        container.replaceChildren(element("p", "empty-state", text));
    }

    function notice(text, success = false) {
        ui.notice.textContent = text;
        ui.notice.className = success ? "notice success" : "notice";
        ui.notice.hidden = !text;
    }

    function timecode(us) {
        if (!Number.isSafeInteger(us) || us < 0) return "—";
        const ms = Math.floor(us / 1000);
        const seconds = Math.floor(ms / 1000);
        return `${String(Math.floor(seconds / 3600)).padStart(2, "0")}:${String(Math.floor(seconds / 60) % 60).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}.${String(ms % 1000).padStart(3, "0")}`;
    }

    function intervalLabel(row) {
        return `${row.startTimecode || timecode(row.startUs)} – ${row.endTimecode || timecode(row.endUs)}`;
    }

    function facts(row) {
        const texts = Array.isArray(row.displayFacts) ? row.displayFacts : row.observableFacts;
        return Array.isArray(texts) ? texts.filter((text) => typeof text === "string").map(cleanObservationText) : [];
    }

    function cleanObservationText(text) {
        // Legacy aliases refer to model windows. Their source times cannot be
        // recovered from the smaller evidence subset belonging to an event.
        return text.replace(/(?<![A-Za-z0-9_:/.-])f[0-8](?:\s*(?:[-–—→~～至到、，,/与和])\s*f[0-8])*(?!(?:[A-Za-z0-9_:/]|[.-][A-Za-z0-9_]))/g,
            (aliases) => (aliases.match(/f[0-8]/g).length > 1 ? "对应画面序列" : "对应画面"));
    }

    function uncertaintyOf(row) {
        return typeof row?.uncertainty === "string" && row.uncertainty.trim()
            ? cleanObservationText(row.uncertainty) : "";
    }

    function appendUncertainty(container, row) {
        const uncertainty = uncertaintyOf(row);
        if (uncertainty) container.append(element("p", "warning small", `待核对 · ${uncertainty}`));
    }

    function validInterval(row, durationUs = state.view?.media?.durationUs) {
        return row && Number.isSafeInteger(row.startUs) && Number.isSafeInteger(row.endUs)
            && row.startUs >= 0 && row.endUs > row.startUs
            && Number.isSafeInteger(durationUs) && row.endUs <= durationUs;
    }

    function safeMediaUrl(raw, endpoint, evidenceId = null) {
        if (typeof raw !== "string" || !raw) return null;
        try {
            const url = new URL(raw, window.location.origin);
            if (url.origin !== window.location.origin || url.pathname !== endpoint
                || url.username || url.password || url.hash
                || url.searchParams.get("project") !== state.project
                || url.searchParams.get("run") !== state.run
                || (evidenceId !== null && url.searchParams.get("id") !== evidenceId)) return null;
            return url.href;
        } catch {
            return null;
        }
    }

    async function request(endpoint, parameters, signal) {
        const url = new URL(endpoint, window.location.origin);
        for (const [name, value] of Object.entries(parameters)) url.searchParams.set(name, String(value));
        const response = await fetch(url, { signal, cache: "no-store", credentials: "same-origin" });
        let payload;
        try {
            payload = await response.json();
        } catch {
            throw new Error(`服务没有返回有效数据（HTTP ${response.status}）。`);
        }
        if (!response.ok) throw new Error(typeof payload.message === "string" ? payload.message : `请求失败（HTTP ${response.status}）。`);
        return payload;
    }

    function storageKey() {
        return `gamingcreator.selection.v1:${encodeURIComponent(state.project)}:${encodeURIComponent(state.run)}`;
    }

    function storageWarning() {
        if (!state.storageWarningShown) {
            state.storageWarningShown = true;
            notice("浏览器未允许保存片段篮。本次选择仍可下载，关闭页面后不会保留。");
        }
    }

    function loadSelections() {
        state.selections = [];
        state.basketMediaId = null;
        if (!state.project || !state.run) return;
        try {
            const text = localStorage.getItem(storageKey());
            if (!text) return;
            if (text.length > 2000000) throw new Error("oversized selection");
            const stored = JSON.parse(text);
            if (stored.schemaVersion !== 1 || stored.project !== state.project || stored.runId !== state.run
                || typeof stored.mediaId !== "string" || !Array.isArray(stored.entries) || stored.entries.length > 500) throw new Error("invalid selection");
            state.basketMediaId = stored.mediaId;
            state.selections = stored.entries.filter((entry) => entry && ["event", "candidate"].includes(entry.kind)
                && entry.clip && typeof entry.key === "string" && entry.source
                && Number.isSafeInteger(entry.clip.startUs) && Number.isSafeInteger(entry.clip.endUs)
                && entry.clip.startUs >= 0 && entry.clip.endUs > entry.clip.startUs
                && Array.isArray(entry.clip.evidenceIds) && entry.clip.evidenceIds.every((id) => typeof id === "string")
                && Array.isArray(entry.clip.observableFacts) && entry.clip.observableFacts.every((text) => typeof text === "string"));
            state.selections = [...new Map(state.selections.map((entry) => [entry.key, entry])).values()];
        } catch (error) {
            if (error.name === "SecurityError") storageWarning();
            else notice("此运行的已保存片段篮无法读取，请重新选择片段。");
        }
    }

    function persistSelections() {
        if (!state.project || !state.run) return;
        try {
            if (!state.selections.length) localStorage.removeItem(storageKey());
            else localStorage.setItem(storageKey(), JSON.stringify({
                schemaVersion: 1, project: state.project, runId: state.run,
                mediaId: state.basketMediaId, entries: orderedSelections(),
            }));
        } catch {
            storageWarning();
        }
    }

    function selectionKey(row) {
        return JSON.stringify([row.eventId ?? row.candidateId, row.startUs, row.endUs]);
    }

    function orderedSelections() {
        return [...state.selections].sort((a, b) => a.clip.startUs - b.clip.startUs
            || a.clip.endUs - b.clip.endUs || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
    }

    function clipMatches(saved, current) {
        return validInterval(current) && saved.startUs === current.startUs && saved.endUs === current.endUs
            && saved.eventId === current.eventId
            && JSON.stringify(saved.evidenceIds) === JSON.stringify(current.evidenceIds)
            && JSON.stringify(saved.observableFacts) === JSON.stringify(current.observableFacts);
    }

    function validateSelection(entry) {
        if (!state.view || state.view.media.id !== state.basketMediaId) return null;
        if (entry.kind === "candidate") {
            const current = state.view.candidates.find((row) => row.candidateId === entry.clip.candidateId);
            if (current && clipMatches(entry.clip, current)
                && entry.source.query === state.view.query && entry.source.mode === state.view.mode
                && entry.source.retrievalVersion === state.view.retrievalVersion) {
                return { clip: current, against: "candidates" };
            }
        }
        if (entry.clip.eventId) {
            const current = state.view.timeline.find((row) => row.eventId === entry.clip.eventId);
            if (current && clipMatches(entry.clip, current)) {
                return { clip: entry.kind === "event" ? current : {
                    ...entry.clip, displayFacts: current.displayFacts, uncertainty: current.uncertainty,
                }, against: "timeline" };
            }
        }
        return null;
    }

    function selectionButton(kind, row) {
        const selected = state.selections.some((entry) => entry.key === selectionKey(row));
        const button = element("button", `select-clip${selected ? " selected" : ""}`, selected ? "✓" : "+");
        button.type = "button";
        button.setAttribute("aria-label", selected ? "从片段篮移除" : "加入片段篮");
        button.setAttribute("aria-pressed", String(selected));
        button.disabled = !validInterval(row);
        button.addEventListener("click", () => toggleSelection(kind, row));
        return button;
    }

    function toggleSelection(kind, row) {
        if (!validInterval(row) || !state.view) return;
        const key = selectionKey(row);
        const index = state.selections.findIndex((entry) => entry.key === key);
        if (index >= 0) state.selections.splice(index, 1);
        else {
            if (state.selections.length >= 500) return notice("片段篮已达到 500 条，请先移除一些片段。");
            if (state.selections.length && state.basketMediaId !== state.view.media.id) return notice("已保存的片段来自不同素材，请先清空片段篮。");
            state.basketMediaId = state.view.media.id;
            state.selections.push({
                key, kind, clip: JSON.parse(JSON.stringify(row)),
                source: {
                    query: kind === "candidate" ? state.view.query : null,
                    mode: kind === "candidate" ? state.view.mode : null,
                    retrievalVersion: kind === "candidate" ? state.view.retrievalVersion : null,
                },
            });
        }
        persistSelections();
        renderSelections();
        renderCandidates();
        renderTimeline();
        updateActiveButton();
    }

    function renderSelections() {
        const scrollTop = ui["selection-list"].scrollTop;
        ui["selection-count"].textContent = state.selections.length;
        ui["selection-list"].replaceChildren();
        let stale = 0;
        for (const entry of orderedSelections()) {
            const validated = validateSelection(entry);
            if (!validated) stale += 1;
            const item = element("li", validated ? "" : "stale");
            const copy = element("div");
            const preview = element("button", "clip-preview", intervalLabel(entry.clip));
            preview.type = "button";
            preview.disabled = !validated;
            preview.addEventListener("click", () => previewClip(entry.kind, validated.clip));
            copy.append(preview, element("p", "", validated ? facts(validated.clip).join("；") : "待重新核对：此区间尚未在当前结果中匹配"));
            if (validated) appendUncertainty(copy, validated.clip);
            const remove = element("button", "remove-selection", "×");
            remove.type = "button";
            remove.setAttribute("aria-label", `移除 ${intervalLabel(entry.clip)}`);
            remove.addEventListener("click", () => {
                state.selections = state.selections.filter((row) => row.key !== entry.key);
                persistSelections();
                renderSelections();
                renderCandidates();
                renderTimeline();
                updateActiveButton();
            });
            item.append(copy, remove);
            ui["selection-list"].append(item);
        }
        ui["selection-list"].scrollTop = scrollTop;
        ui["clear-selection"].disabled = !state.selections.length;
        ui["export-json"].disabled = !state.selections.length || stale > 0 || state.busy;
        ui["export-csv"].disabled = ui["export-json"].disabled;
        ui["selection-warning"].hidden = stale === 0;
        ui["selection-warning"].textContent = stale ? `${stale} 条片段尚未匹配当前源事件或检索候选，请重查原查询或移除后下载。` : "";
    }

    function exportDocument() {
        if (!state.view || !state.selections.length || state.busy) throw new Error("请先读取素材并选择片段。");
        const selectedClips = orderedSelections().map((entry) => {
            const validated = validateSelection(entry);
            if (!validated) throw new Error("片段篮中有尚未匹配当前结果的区间，请核对后再下载。");
            return {
                ...JSON.parse(JSON.stringify(validated.clip)),
                observableFacts: facts(validated.clip),
                displayFacts: facts(validated.clip),
                uncertainty: uncertaintyOf(validated.clip) || null,
                selectionOrigin: { kind: entry.kind, ...entry.source },
                validatedAgainst: validated.against,
            };
        });
        return {
            schemaVersion: 1, project: state.project, runId: state.run, mediaId: state.view.media.id,
            factsProjectionVersion: state.view.factsProjectionVersion ?? "legacy-frame-alias-neutral-v1",
            mediaSha256: state.view.media.sha256 ?? null, configHash: state.view.configHash ?? null,
            retrievalVersion: state.view.retrievalVersion, query: state.view.query,
            mode: state.view.mode, selectedClips,
        };
    }

    function csvCell(value) {
        let text = value === null || value === undefined ? "" : String(value);
        if (/^[\s\u0000-\u001f]*[=+\-@]|^[\t\r\n]/u.test(text)) text = `'${text}`;
        return `"${text.replaceAll('"', '""')}"`;
    }

    function exportCsv(doc) {
        const headers = ["project", "runId", "mediaId", "selectionKind", "candidateId", "eventId", "startUs", "endUs", "startTimecode", "endTimecode", "rank", "score", "scoreKind", "evidenceIds", "observableFacts", "mechanicTags", "retrievalVersion", "query", "mode", "validatedAgainst", "uncertainty", "factsProjectionVersion"];
        const rows = doc.selectedClips.map((clip) => [
            doc.project, doc.runId, doc.mediaId, clip.selectionOrigin.kind, clip.candidateId,
            clip.eventId, clip.startUs, clip.endUs, clip.startTimecode, clip.endTimecode,
            clip.rank, clip.score, clip.scoreKind, JSON.stringify(clip.evidenceIds),
            JSON.stringify(clip.observableFacts), JSON.stringify(clip.mechanicTags ?? []),
            clip.selectionOrigin.retrievalVersion, clip.selectionOrigin.query,
            clip.selectionOrigin.mode, clip.validatedAgainst, clip.uncertainty, doc.factsProjectionVersion,
        ]);
        return `\uFEFF${[headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n")}\r\n`;
    }

    function download(type) {
        try {
            const doc = exportDocument();
            const blob = new Blob([type === "json" ? `${JSON.stringify(doc, null, 2)}\n` : exportCsv(doc)], { type: type === "json" ? "application/json;charset=utf-8" : "text/csv;charset=utf-8" });
            const link = element("a");
            const url = URL.createObjectURL(blob);
            link.href = url;
            link.download = `selected-clips-${state.run.replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 40)}.${type}`;
            document.body.append(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
            notice(`已下载 ${doc.selectedClips.length} 个片段的 ${type.toUpperCase()} 清单。`, true);
        } catch (error) {
            notice(error.message);
        }
    }

    function setBusy(busy, searching = false) {
        state.busy = busy;
        const completed = state.view?.runStatus === "completed";
        ui["search-button"].disabled = busy || !completed;
        ui["search-button"].textContent = busy ? (searching ? "正在本地检索…" : "正在读取…") : "查找片段 ↗";
        ui["refresh-view"].disabled = busy || !state.run;
        for (const id of ["query", "mode", "top"]) ui[id].disabled = !completed;
        ui["timeline-filter"].disabled = !state.view;
        ui["tag-filter"].disabled = !state.view;
        renderSelections();
    }

    function resetView() {
        state.view = null;
        state.active = null;
        state.playbackEndUs = null;
        state.pendingSeekUs = null;
        state.sourceUrl = "";
        ui["source-video"].pause();
        ui["source-video"].removeAttribute("src");
        ui["source-video"].load();
        ui["video-empty"].hidden = false;
        ui["video-empty"].querySelector("h3").textContent = "从左侧打开分析结果";
        ui["video-empty"].querySelector("p").textContent = "点选事件或检索候选，回看原视频中的对应区间。";
        ui["source-name"].textContent = "选择一份分析结果";
        ui["source-duration"].textContent = "源视频保留在本机";
        ui["run-state"].className = "run-state muted";
        ui["run-state"].textContent = "尚未选择运行";
        for (const id of ["event-count", "transcript-count", "stage-summary"]) ui[id].textContent = "—";
        for (const id of ["candidate-count", "timeline-count", "evidence-count", "transcript-tab-count"]) ui[id].textContent = "0";
        ui["cost-known"].textContent = "未读取";
        ui["cost-detail"].textContent = "估价与账单确认分开记录";
        ui["stage-list"].replaceChildren();
        ui["preview-badge"].textContent = "等待素材";
        ui["active-title"].textContent = "尚未选中片段";
        ui["active-range"].textContent = "选择事件或候选后显示源时间区间";
        ui["active-facts"].textContent = "模型观察、原始证据与视频可以在这里对照查看。";
        ui["play-selection"].disabled = true;
        ui["add-active"].disabled = true;
        ui["current-time"].textContent = "00:00:00.000";
        ui["total-time"].textContent = " / —";
        ui["timeline-end"].textContent = "—";
        ui["video-scrubber"].value = "0";
        ui["video-scrubber"].disabled = true;
        ui["timeline-filter"].value = "";
        ui["tag-filter"].replaceChildren(element("option", "", "全部玩法标签"));
        ui["tag-filter"].firstChild.value = "";
        empty(ui["timeline-list"], "正在等待分析结果…");
        empty(ui["candidate-list"], "输入你需要的动作、玩法或画面。");
        empty(ui["evidence-list"], "选中片段后查看对应证据。");
        empty(ui["transcript-list"], "尚未读取转录。");
        ui["search-context"].textContent = "打开已完成的运行后即可查询。";
        ui["filter-summary"].textContent = "0 个事件";
        if (ui["evidence-dialog"].open) ui["evidence-dialog"].close();
        ui["evidence-full"].removeAttribute("src");
        setBusy(false);
        drawTimeline();
    }

    function switchRun(run) {
        state.revision += 1;
        state.inspectController?.abort();
        state.run = run;
        resetView();
        loadSelections();
        renderSelections();
        const metadata = state.runs.find((item) => item.id === run);
        ui["source-name"].textContent = metadata?.sourceName || "选择一份分析结果";
        ui["source-duration"].textContent = metadata ? `源时长 ${timecode(metadata.durationUs)}` : "源视频保留在本机";
        ui["run-state"].className = `run-state ${metadata?.status || "muted"}`;
        ui["run-state"].textContent = metadata ? `${statusLabels[metadata.status] || metadata.status} · ${run}${metadata.errorCode ? ` · ${metadata.errorCode}` : ""}` : "尚未选择运行";
        if (run) void inspect("");
    }

    async function loadRuns(project, preferredRun = "") {
        state.runsController?.abort();
        state.inspectController?.abort();
        state.revision += 1;
        const revision = state.revision;
        const controller = new AbortController();
        state.runsController = controller;
        state.project = project;
        state.run = "";
        state.runs = [];
        resetView();
        state.selections = [];
        state.basketMediaId = null;
        renderSelections();
        ui["project-path"].value = project;
        ui["refresh-runs"].disabled = !project;
        ui["run-select"].disabled = true;
        ui["run-select"].replaceChildren(element("option", "", project ? "正在读取运行…" : "先选择项目"));
        if (!project) return;
        try {
            const payload = await request("/api/runs", { project }, controller.signal);
            if (state.revision !== revision || state.project !== project) return;
            if (!Array.isArray(payload.runs)) throw new Error("运行列表数据无效。");
            state.runs = payload.runs.filter((run) => typeof run.id === "string" && typeof run.status === "string");
            ui["run-select"].replaceChildren();
            for (const run of state.runs) {
                const analysis = run.analysisProfile === "detailed" ? "细节动作（试验）"
                    : run.analysisKind === "temporal" ? "连续动作（试验）" : "画面观察";
                const option = element("option", "", `${statusLabels[run.status] || run.status} · ${analysis} · ${run.sourceName || run.id}`);
                option.value = run.id;
                ui["run-select"].append(option);
            }
            if (!state.runs.length) {
                ui["run-select"].append(element("option", "", "此项目还没有分析运行"));
                empty(ui["timeline-list"], "项目中没有分析结果。先用分析命令处理本地素材。");
                ui["source-name"].textContent = "此项目暂无素材";
                return;
            }
            ui["run-select"].disabled = false;
            const selected = state.runs.find((run) => run.id === preferredRun)
                || state.runs.find((run) => run.status === "completed" && run.analysisProfile === "detailed")
                || state.runs.find((run) => run.status === "completed" && run.analysisKind === "temporal")
                || state.runs.find((run) => run.status === "completed") || state.runs[0];
            ui["run-select"].value = selected.id;
            switchRun(selected.id);
        } catch (error) {
            if (error.name === "AbortError" || state.revision !== revision) return;
            ui["run-select"].replaceChildren(element("option", "", "无法读取运行"));
            empty(ui["timeline-list"], error.message);
            notice(error.message);
        }
    }

    async function loadProjects() {
        state.projectsController?.abort();
        const controller = new AbortController();
        state.projectsController = controller;
        const initialRevision = state.revision;
        ui["refresh-projects"].disabled = true;
        try {
            const payload = await request("/api/projects", {}, controller.signal);
            if (state.projectsController !== controller) return;
            if (!Array.isArray(payload.projects)) throw new Error("项目列表数据无效。");
            const projects = payload.projects.filter((project) => typeof project.path === "string");
            ui["project-select"].replaceChildren();
            for (const project of projects) {
                const option = element("option", "", `${project.name || project.path} · ${project.path}`);
                option.value = project.path;
                ui["project-select"].append(option);
            }
            if (!projects.length) {
                ui["project-select"].append(element("option", "", "尚未发现已分析项目"));
                empty(ui["timeline-list"], "没有发现已有数据库。可打开仓库内项目目录，或先分析一段视频。");
                return;
            }
            const chosen = projects.find((project) => project.path === state.project)
                || projects.find((project) => project.path === "artifacts/demo-phase0") || projects[0];
            if (state.project && !projects.some((project) => project.path === state.project)) {
                const manual = element("option", "", state.project);
                manual.value = state.project;
                ui["project-select"].append(manual);
            }
            ui["project-select"].value = state.project || chosen.path;
            if (state.revision !== initialRevision) return;
            if (state.project !== chosen.path || !state.run) await loadRuns(chosen.path);
        } catch (error) {
            if (error.name !== "AbortError") {
                ui["project-select"].replaceChildren(element("option", "", "无法读取项目"));
                notice(error.message);
            }
        } finally {
            if (state.projectsController === controller) ui["refresh-projects"].disabled = false;
        }
    }

    async function inspect(query) {
        if (!state.project || !state.run) return;
        state.inspectController?.abort();
        const controller = new AbortController();
        state.inspectController = controller;
        const revision = state.revision;
        const top = Number(ui.top.value);
        if (!Number.isInteger(top) || top < 1 || top > 100) return notice("候选条数需要是 1 到 100 的整数。");
        notice("");
        setBusy(true, Boolean(query));
        try {
            const payload = await request("/api/inspect", {
                project: state.project, run: state.run, query, mode: ui.mode.value, top,
            }, controller.signal);
            if (state.revision !== revision || state.inspectController !== controller) return;
            if (payload.runId !== state.run || !Array.isArray(payload.timeline) || !Array.isArray(payload.candidates)
                || !payload.media || typeof payload.media.id !== "string"
                || !Number.isSafeInteger(payload.media.durationUs) || payload.media.durationUs <= 0) throw new Error("分析视图的素材或运行身份不一致。");
            state.view = payload;
            state.active = null;
            state.playbackEndUs = null;
            renderView();
        } catch (error) {
            if (error.name === "AbortError" || state.revision !== revision || state.inspectController !== controller) return;
            notice(error.message);
            if (query) {
                if (state.view) state.view = { ...state.view, candidates: [] };
                state.active = null;
                state.playbackEndUs = null;
                updateActive();
                renderEvidence();
                empty(ui["candidate-list"], "检索失败，请查看提示后重试。");
                ui["candidate-count"].textContent = "0";
                ui["search-context"].textContent = `查询未完成：${query}`;
            } else if (!state.view) empty(ui["timeline-list"], error.message);
        } finally {
            if (state.revision === revision && state.inspectController === controller) setBusy(false);
        }
    }

    function renderView() {
        const view = state.view;
        ui["source-name"].textContent = view.media.name || "源视频";
        ui["source-duration"].textContent = `源时长 ${timecode(view.media.durationUs)}`;
        ui["run-state"].className = `run-state ${view.runStatus}`;
        const analysis = view.analysisProfile === "detailed" ? "细节动作分析（试验）"
            : view.analysisKind === "temporal" ? "连续动作分析（试验）" : "旧画面观察";
        ui["run-state"].textContent = `${statusLabels[view.runStatus] || view.runStatus} · ${analysis} · ${state.run}`;
        ui["event-count"].textContent = view.timeline.length;
        const transcripts = Array.isArray(view.transcripts) ? view.transcripts : [];
        ui["transcript-count"].textContent = transcripts.length;
        ui["transcript-tab-count"].textContent = transcripts.length;
        ui["total-time"].textContent = ` / ${timecode(view.media.durationUs)}`;
        ui["timeline-end"].textContent = timecode(view.media.durationUs).split(".")[0];
        ui["video-scrubber"].max = String(view.media.durationUs / 1000000);
        const mediaUrl = safeMediaUrl(view.media.videoUrl, "/api/media");
        if (mediaUrl) {
            if (state.sourceUrl !== mediaUrl) {
                state.sourceUrl = mediaUrl;
                ui["source-video"].src = mediaUrl;
                ui["source-video"].load();
            }
            ui["video-empty"].hidden = true;
            ui["video-scrubber"].disabled = false;
            ui["preview-badge"].textContent = "原始素材";
        } else {
            ui["video-empty"].hidden = false;
            ui["video-empty"].querySelector("h3").textContent = "视频地址未通过校验";
            ui["video-empty"].querySelector("p").textContent = "时间轴仍可查看，请刷新素材后重试。";
            ui["preview-badge"].textContent = "暂不可播放";
        }
        const known = view.cost?.knownCny;
        const unknown = Number.isSafeInteger(view.cost?.unknownAttempts) && view.cost.unknownAttempts >= 0 ? view.cost.unknownAttempts : null;
        ui["cost-known"].textContent = typeof known === "string" && /^\d+(?:\.\d+)?$/.test(known) ? `¥${known}` : "费用未知";
        ui["cost-detail"].textContent = unknown === null ? "未知调用数量未确认；估价非账单。"
            : unknown > 0 ? `另有 ${unknown} 次调用费用待确认；已知估价非总额。`
                : "已有记录的费用估算，未核对账单。";
        const stages = Array.isArray(view.stages) ? view.stages : [];
        ui["stage-summary"].textContent = stages.length ? `${stages.filter((stage) => stage.status === "completed").length}/${stages.length} 已完成` : "未登记";
        ui["stage-list"].replaceChildren();
        for (const stage of stages) {
            const row = element("li");
            row.append(element("span", "", `${stage.id}${stage.errorCode ? ` · ${stage.errorCode}` : ""}`), element("span", stage.status, statusLabels[stage.status] || stage.status));
            ui["stage-list"].append(row);
        }
        const oldTag = ui["tag-filter"].value;
        const tags = [...new Set(view.timeline.flatMap((row) => Array.isArray(row.mechanicTags) ? row.mechanicTags.filter((tag) => typeof tag === "string") : []))].sort();
        const all = element("option", "", "全部玩法标签");
        all.value = "";
        ui["tag-filter"].replaceChildren(all);
        for (const tag of tags) {
            const option = element("option", "", tag);
            option.value = tag;
            ui["tag-filter"].append(option);
        }
        ui["tag-filter"].value = tags.includes(oldTag) ? oldTag : "";
        renderCandidates();
        renderTimeline();
        renderTranscripts();
        renderEvidence();
        renderSelections();
        updateActive();
    }

    function renderCandidates() {
        const view = state.view;
        if (!view) return;
        const scrollTop = ui["candidate-list"].scrollTop;
        ui["candidate-count"].textContent = view.candidates.length;
        ui["candidate-list"].replaceChildren();
        ui["search-context"].textContent = view.query ? `“${view.query}” · ${view.mode} · 分数是排序信号` : "输入你需要的动作、玩法或画面。";
        if (!view.candidates.length) {
            empty(ui["candidate-list"], view.runStatus !== "completed" ? "分析尚未完成，可以先查看已保存时间轴。"
                : view.query ? (view.abstentionReason ? `没有合适候选（${view.abstentionReason}）。可以换一种描述。` : "没有匹配候选。可以换一种描述。") : "输入查询后查找片段，或直接从时间轴选片。");
            return;
        }
        for (const row of view.candidates) {
            const card = element("article", `candidate-card${state.active?.kind === "candidate" && state.active.row.candidateId === row.candidateId ? " active" : ""}`);
            const top = element("div", "candidate-card-top");
            const preview = element("button", "clip-preview", intervalLabel(row));
            preview.type = "button";
            preview.disabled = !validInterval(row) || !state.sourceUrl;
            preview.setAttribute("aria-label", `播放候选 ${row.rank}，${intervalLabel(row)}`);
            preview.addEventListener("click", () => previewClip("candidate", row));
            top.append(element("span", "rank", row.rank), preview, selectionButton("candidate", row));
            const copy = element("p", "candidate-facts", facts(row).join("；"));
            const meta = element("div", "candidate-meta");
            meta.append(element("span", "", `${Array.isArray(row.evidenceIds) ? row.evidenceIds.length : 0} 份证据`), element("span", "", `${row.scoreKind || "score"} · ${typeof row.score === "number" && Number.isFinite(row.score) ? row.score.toFixed(4) : "—"}`));
            card.append(top, copy, meta);
            appendUncertainty(card, row);
            ui["candidate-list"].append(card);
        }
        ui["candidate-list"].scrollTop = scrollTop;
    }

    function filteredTimeline() {
        const needle = ui["timeline-filter"].value.trim().toLocaleLowerCase();
        const tag = ui["tag-filter"].value;
        return (state.view?.timeline || []).filter((row) => (!needle || facts(row).join(" ").toLocaleLowerCase().includes(needle))
            && (!tag || (Array.isArray(row.mechanicTags) && row.mechanicTags.includes(tag))));
    }

    function renderTimeline() {
        const scrollTop = ui["timeline-list"].scrollTop;
        const rows = filteredTimeline();
        ui["timeline-count"].textContent = state.view?.timeline.length || 0;
        ui["filter-summary"].textContent = `${rows.length} / ${state.view?.timeline.length || 0} 个事件 · 按源时间排列`;
        ui["timeline-list"].replaceChildren();
        if (!rows.length) empty(ui["timeline-list"], state.view ? (state.view.timeline.length ? "没有符合筛选条件的事件。" : "此运行尚未保存视觉事件。") : "请选择一份分析结果。");
        for (const row of rows) {
            const item = element("div", `timeline-row${state.active?.row.eventId === row.eventId ? " active" : ""}`);
            const preview = element("button", "clip-preview", intervalLabel(row));
            preview.type = "button";
            preview.disabled = !validInterval(row) || !state.sourceUrl;
            preview.setAttribute("aria-label", `播放事件，${intervalLabel(row)}`);
            preview.addEventListener("click", () => previewClip("event", row));
            const copy = element("div", "timeline-facts", facts(row).join("；"));
            appendUncertainty(copy, row);
            if (Array.isArray(row.mechanicTags) && row.mechanicTags.length) {
                const tags = element("div", "tag-list");
                for (const tag of row.mechanicTags) if (typeof tag === "string") tags.append(element("span", "tag", tag));
                copy.append(tags);
            }
            item.append(preview, copy, selectionButton("event", row));
            ui["timeline-list"].append(item);
        }
        ui["timeline-list"].scrollTop = scrollTop;
        drawTimeline();
    }

    function drawTimeline() {
        const canvas = ui["timeline-map"];
        const context = canvas.getContext("2d");
        if (!context) return;
        const width = canvas.clientWidth;
        if (!width) return;
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        const height = canvas.clientHeight || 40;
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
        context.scale(ratio, ratio * height / 40);
        context.clearRect(0, 0, width, 40);
        const duration = state.view?.media?.durationUs;
        if (!duration) return;
        const colors = getComputedStyle(canvas);
        context.strokeStyle = colors.getPropertyValue("--line").trim() || "#33444b";
        context.lineWidth = 1;
        for (let index = 0; index <= 10; index += 1) {
            const x = width * index / 10;
            context.beginPath(); context.moveTo(x, 30); context.lineTo(x, 38); context.stroke();
        }
        context.fillStyle = colors.getPropertyValue("--accent").trim() || "#789f67";
        for (const row of filteredTimeline()) {
            if (validInterval(row)) context.fillRect(width * row.startUs / duration, 9, Math.max(2, width * (row.endUs - row.startUs) / duration), 16);
        }
        context.fillStyle = colors.getPropertyValue("--text").trim() || "#e8efdc";
        const position = Math.max(0, Math.min(duration, Math.round(ui["source-video"].currentTime * 1000000)));
        context.fillRect(width * position / duration, 3, 2, 32);
    }

    function seek(us) {
        if (!state.sourceUrl || !state.view) return;
        const position = Math.max(0, Math.min(state.view.media.durationUs, us));
        state.pendingSeekUs = position;
        if (ui["source-video"].readyState >= 1) {
            ui["source-video"].currentTime = position / 1000000;
            state.pendingSeekUs = null;
        }
        ui["video-scrubber"].value = String(position / 1000000);
        ui["current-time"].textContent = timecode(Math.round(position));
    }

    async function previewClip(kind, row) {
        if (!validInterval(row) || !state.sourceUrl) return notice("这个区间目前无法播放，请刷新素材。");
        state.active = { kind, row };
        state.playbackEndUs = row.endUs;
        seek(row.startUs);
        updateActive();
        renderCandidates();
        renderTimeline();
        renderEvidence();
        const revision = state.revision;
        const selected = state.active;
        try {
            await ui["source-video"].play();
        } catch (error) {
            if (error.name === "AbortError") return;
            if (state.revision === revision && state.active === selected) notice("浏览器暂未开始播放，请使用视频播放按钮。若视频无法解码，请检查原视频格式。");
        }
    }

    function updateActiveButton() {
        ui["add-active"].disabled = !state.active;
        const selected = state.active && state.selections.some((entry) => entry.key === selectionKey(state.active.row));
        ui["add-active"].textContent = selected ? "✓ 已加入（点击移除）" : "＋ 加入片段篮";
    }

    function updateActive() {
        const row = state.active?.row;
        ui["active-title"].textContent = row ? (state.active.kind === "candidate" ? `候选 #${row.rank}` : "时间轴事件") : "尚未选中片段";
        ui["active-range"].textContent = row ? intervalLabel(row) : "选择事件或候选后显示源时间区间";
        ui["active-facts"].textContent = row ? facts(row).join("；") : "模型观察、原始证据与视频可以在这里对照查看。";
        const uncertainty = uncertaintyOf(row);
        if (uncertainty) ui["active-facts"].append(element("br"), element("span", "warning small", `待核对 · ${uncertainty}`));
        ui["play-selection"].disabled = !row || !state.sourceUrl;
        updateActiveButton();
    }

    function renderEvidence() {
        const ids = state.active?.row.evidenceIds || [];
        const evidence = (Array.isArray(state.view?.evidence) ? state.view.evidence : []).filter((item) => ids.includes(item.id));
        ui["evidence-count"].textContent = evidence.length;
        ui["evidence-list"].replaceChildren();
        if (!evidence.length) return empty(ui["evidence-list"], state.active ? "此区间没有可显示的证据。" : "选中片段后查看对应证据。");
        for (const item of evidence) {
            const url = safeMediaUrl(item.url, "/api/evidence", item.id);
            if (!url) {
                ui["evidence-list"].append(element("p", "empty-state", "证据地址未通过校验，请刷新后重试。"));
                continue;
            }
            if (item.kind === "image") {
                const button = element("button", "evidence-card");
                button.type = "button";
                button.setAttribute("aria-label", `查看 ${timecode(item.startUs)} 的源帧证据`);
                const image = element("img");
                image.src = url;
                image.alt = `源帧 ${timecode(item.startUs)}`;
                image.loading = "lazy";
                image.addEventListener("error", () => { image.alt = "源帧无法读取，请检查证据文件"; });
                button.append(image, element("span", "evidence-caption", timecode(item.startUs)));
                button.addEventListener("click", () => {
                    ui["evidence-dialog-title"].textContent = `源帧 · ${timecode(item.startUs)}`;
                    ui["evidence-full"].src = url;
                    ui["evidence-dialog-detail"].textContent = `证据 ${item.id} · 来源 ${state.view.media.name}`;
                    ui["evidence-dialog"].showModal();
                });
                ui["evidence-list"].append(button);
            } else if (item.kind === "audio") {
                const card = element("div", "evidence-card audio-card");
                const audio = element("audio");
                audio.controls = true;
                audio.preload = "none";
                audio.src = url;
                audio.setAttribute("aria-label", `源音频证据 ${timecode(item.startUs)} 至 ${timecode(item.endUs)}`);
                card.append(element("span", "small", `音频证据 · ${timecode(item.startUs)} – ${timecode(item.endUs)}`), audio);
                ui["evidence-list"].append(card);
            }
        }
    }

    function renderTranscripts() {
        const transcripts = Array.isArray(state.view?.transcripts) ? state.view.transcripts : [];
        ui["transcript-list"].replaceChildren();
        if (!transcripts.length) return empty(ui["transcript-list"], "此运行没有语音转录片段。");
        for (const row of transcripts) {
            const item = element("div", "transcript-row");
            const preview = element("button", "", `${timecode(row.startUs)}\n${timecode(row.endUs)}`);
            preview.type = "button";
            preview.disabled = !validInterval(row) || !state.sourceUrl;
            preview.addEventListener("click", () => {
                state.playbackEndUs = row.endUs;
                seek(row.startUs);
                ui["source-video"].play().catch(() => notice("请使用视频播放按钮开始播放。"));
            });
            const copy = element("div");
            copy.append(element("p", "", row.text));
            if (row.uncertainty !== null && row.uncertainty !== undefined && row.uncertainty !== false && row.uncertainty !== "") copy.append(element("span", "uncertain", `转录待核对 · ${typeof row.uncertainty === "string" ? row.uncertainty : JSON.stringify(row.uncertainty)}`));
            item.append(preview, copy);
            ui["transcript-list"].append(item);
        }
    }

    function updatePlayback() {
        const video = ui["source-video"];
        const us = Math.round(video.currentTime * 1000000);
        if (state.pendingSeekUs === null && state.playbackEndUs !== null && us >= state.playbackEndUs) {
            video.pause();
            video.currentTime = state.playbackEndUs / 1000000;
            state.playbackEndUs = null;
        }
        ui["current-time"].textContent = timecode(Math.round(video.currentTime * 1000000));
        ui["video-scrubber"].value = String(video.currentTime);
        drawTimeline();
    }

    function playbackFrame() {
        updatePlayback();
        state.frameRequest = ui["source-video"].paused ? null : requestAnimationFrame(playbackFrame);
    }

    function setTab(showTranscripts) {
        for (const [id, active] of [["evidence-tab", !showTranscripts], ["transcript-tab", showTranscripts]]) {
            ui[id].className = active ? "tab active" : "tab";
            ui[id].setAttribute("aria-selected", String(active));
            ui[id].tabIndex = active ? 0 : -1;
        }
        ui["evidence-panel"].hidden = showTranscripts;
        ui["transcript-panel"].hidden = !showTranscripts;
    }

    ui["project-select"].addEventListener("change", () => { void loadRuns(ui["project-select"].value); });
    ui["project-form"].addEventListener("submit", (event) => {
        event.preventDefault();
        const project = ui["project-path"].value.trim().replaceAll("\\", "/").replace(/^\.\//, "").replace(/\/$/, "");
        if (!project) return notice("请填写已有项目目录。");
        let option = [...ui["project-select"].options].find((item) => item.value === project);
        if (!option) {
            option = element("option", "", project);
            option.value = project;
            ui["project-select"].append(option);
        }
        ui["project-select"].value = project;
        void loadRuns(project);
    });
    ui["run-select"].addEventListener("change", () => switchRun(ui["run-select"].value));
    ui["refresh-projects"].addEventListener("click", () => { void loadProjects(); });
    ui["refresh-runs"].addEventListener("click", () => { void loadRuns(state.project, state.run); });
    ui["refresh-view"].addEventListener("click", () => { void inspect(""); });
    ui["search-form"].addEventListener("submit", (event) => {
        event.preventDefault();
        if (state.view?.runStatus !== "completed" || state.busy) return;
        const query = ui.query.value.trim();
        if (!query) return notice("写一句你想寻找的动作或画面，再查找片段。");
        if (query.length > 4096) return notice("查询最多 4096 个字符，请缩短描述。");
        void inspect(query);
    });
    ui.query.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); ui["search-form"].requestSubmit(); }
    });
    function filterTimeline() {
        ui["timeline-list"].scrollTop = 0;
        renderTimeline();
    }
    ui["timeline-filter"].addEventListener("input", filterTimeline);
    ui["tag-filter"].addEventListener("change", filterTimeline);
    ui["add-active"].addEventListener("click", () => { if (state.active) toggleSelection(state.active.kind, state.active.row); });
    ui["play-selection"].addEventListener("click", () => { if (state.active) void previewClip(state.active.kind, state.active.row); });
    ui["clear-selection"].addEventListener("click", () => {
        state.selections = [];
        persistSelections(); renderSelections(); renderCandidates(); renderTimeline(); updateActiveButton();
    });
    ui["export-json"].addEventListener("click", () => download("json"));
    ui["export-csv"].addEventListener("click", () => download("csv"));
    ui["evidence-tab"].addEventListener("click", () => setTab(false));
    ui["transcript-tab"].addEventListener("click", () => setTab(true));
    for (const id of ["evidence-tab", "transcript-tab"]) ui[id].addEventListener("keydown", (event) => {
        if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
            event.preventDefault();
            const transcripts = event.key === "End" || (event.key !== "Home" && id === "evidence-tab");
            setTab(transcripts);
            ui[transcripts ? "transcript-tab" : "evidence-tab"].focus();
        }
    });
    ui["close-evidence"].addEventListener("click", () => ui["evidence-dialog"].close());
    ui["evidence-dialog"].addEventListener("click", (event) => {
        const box = ui["evidence-dialog"].getBoundingClientRect();
        if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) ui["evidence-dialog"].close();
    });
    ui["evidence-dialog"].addEventListener("close", () => ui["evidence-full"].removeAttribute("src"));
    ui["source-video"].addEventListener("loadedmetadata", () => {
        if (state.pendingSeekUs !== null) seek(state.pendingSeekUs);
        updatePlayback();
    });
    ui["source-video"].addEventListener("timeupdate", updatePlayback);
    ui["source-video"].addEventListener("play", () => {
        if (state.frameRequest === null) state.frameRequest = requestAnimationFrame(playbackFrame);
    });
    ui["source-video"].addEventListener("pause", () => {
        if (state.frameRequest !== null) cancelAnimationFrame(state.frameRequest);
        state.frameRequest = null;
    });
    ui["source-video"].addEventListener("error", () => {
        if (!state.sourceUrl) return;
        ui["video-empty"].hidden = false;
        ui["video-empty"].querySelector("h3").textContent = "原视频暂时无法播放";
        ui["video-empty"].querySelector("p").textContent = "请确认素材仍在原处且浏览器支持其编码。时间轴和片段清单仍可使用。";
        ui["preview-badge"].textContent = "播放失败";
    });
    ui["video-scrubber"].addEventListener("input", () => { state.playbackEndUs = null; seek(Math.round(Number(ui["video-scrubber"].value) * 1000000)); });
    ui["timeline-map"].addEventListener("click", (event) => {
        if (!state.view || !state.sourceUrl) return;
        const bounds = ui["timeline-map"].getBoundingClientRect();
        if (!bounds.width) return;
        state.playbackEndUs = null;
        seek(Math.round(Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)) * state.view.media.durationUs));
    });
    window.addEventListener("resize", drawTimeline);
    resetView();
    void loadProjects();
})();
