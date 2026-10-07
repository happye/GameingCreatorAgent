"use strict";

(() => {
    const byId = (id) => document.getElementById(id);
    const ui = Object.fromEntries([
        "notice", "project-select", "project-path", "project-form", "refresh-projects",
        "run-select", "refresh-runs", "refresh-view", "run-state", "source-name",
        "source-duration", "event-count", "transcript-count", "cost-known", "cost-detail",
        "stage-summary", "stage-list", "source-video", "video-empty", "preview-badge",
        "current-time", "total-time", "play-selection", "play-context", "playback-range", "add-active", "active-title",
        "active-range", "active-facts", "evidence-tab", "transcript-tab", "evidence-panel",
        "transcript-panel", "evidence-count", "evidence-list", "transcript-tab-count",
        "transcript-list", "search-form", "query", "mode", "top", "search-button",
        "candidate-count", "search-context", "candidate-list", "selection-count",
        "selection-list", "selection-warning", "clear-selection", "export-json",
        "export-csv", "timeline-count", "timeline-filter", "tag-filter", "timeline-map",
        "timeline-end", "video-scrubber", "timeline-list", "filter-summary",
        "evidence-dialog", "evidence-dialog-title", "close-evidence", "evidence-full",
        "evidence-dialog-detail", "detail-status", "actor-details", "actor-detail-list",
        "detail-profile", "open-detail-query", "detail-query-dialog", "close-detail-query",
        "detail-query-target", "detail-query-form", "detail-conditions", "add-detail-condition",
        "match-detail-query", "detail-match-result", "open-project-detail-query", "project-detail-controls",
        "project-detail-filter", "project-detail-summary", "project-detail-previous", "project-detail-next", "project-detail-download",
        "open-search-detail-query", "search-detail-controls", "search-detail-summary", "download-search-details",
        "detail-draft-text", "generate-detail-draft", "detail-draft-status",
        "detail-draft-gaps", "detail-draft-confirmation", "detail-draft-subset",
        "open-detail-costs", "detail-cost-dialog", "close-detail-costs", "detail-cost-content",
        "open-retrieval-diagnostics", "retrieval-diagnostics-dialog", "close-retrieval-diagnostics",
        "retrieval-diagnostics-summary", "retrieval-diagnostics-slots", "download-retrieval-diagnostics",
        "open-tasks", "tasks-dialog", "close-tasks", "tasks-list", "tasks-page-summary",
        "tasks-previous", "tasks-next", "refresh-tasks",
        "open-search-sources", "single-search-source", "search-scope-label", "search-sources-dialog",
        "close-search-sources", "search-sources-list", "search-sources-summary", "apply-search-sources", "download-project-search",
        "open-preparation", "preparation-dialog", "close-preparation", "preparation-form", "preparation-project",
        "preparation-paths", "preparation-profile", "preparation-budget", "preparation-timeout", "start-preparation", "stop-preparation",
        "preparation-status", "preparation-summary", "preparation-items", "open-prepared-tasks", "download-preparation",
        "refresh-preparation", "preparation-history-summary", "preparation-batches", "preparation-previous", "preparation-next",
    ].map((id) => [id, byId(id)]));
    const state = {
        project: "", run: "", revision: 0, runs: [], view: null, active: null,
        selections: [], basketMediaId: null, inspectController: null, runsController: null,
        projectsController: null, busy: false, playbackEndUs: null, pendingSeekUs: null,
        frameRequest: null, sourceUrl: "", storageWarningShown: false,
        matchController: null, matchRevision: 0, matching: false,
        costController: null, costRevision: 0,
        draftController: null, draftRevision: 0, drafting: false, draftScope: "manual",
        diagnosticsContext: null,
        tasksController: null, tasksRevision: 0, tasksOffset: 0,
        searchRuns: [], projectSearch: null, projectSearchController: null,
        detailProjectScope: false, projectDetail: null, projectDetailAvailable: false,
        detailSearchScope: false, searchDetail: null, searchDetailAvailable: false,
        preparationController: null, preparationRevision: 0, preparationTimer: null,
        preparationJob: null, preparationSubmitting: false, preparationOffset: 0, preparationCatalog: null,
    };
    const statusLabels = {
        pending: "等待分析", running: "分析中", completed: "已完成", failed: "失败",
        cancelled: "已取消", interrupted: "已中断",
    };
    const TASK_PAGE_SIZE = 20;

    const preparationLabels = {
        queued: "等待准备", running: "正在准备", cancelling: "正在停止…", finished: "本批次检查已完成",
        partial: "部分素材尚未准备好", failed: "本次准备停止", cancelled: "本次准备已停止",
        pending: "等待处理", prepared: "本地素材已准备，等待另行分析",
        coverage_blocked: "素材已保存，分析配置覆盖不足", analysis_started: "已进入分析，沿原任务处理", stopped: "已保存停止状态",
    };

    function stopPreparationObservation() {
        state.preparationController?.abort();
        ui["refresh-preparation"].disabled = false;
        state.preparationController = null;
        state.preparationRevision += 1;
        if (state.preparationTimer !== null) clearTimeout(state.preparationTimer);
        state.preparationTimer = null;
    }

    function preparationTarget() { return ui["preparation-project"].value.trim().replaceAll("\\", "/"); }

    function rememberPreparationTarget(project) {
        try { localStorage.setItem("gamingcreator:preparation-project", project); } catch { storageWarning(); }
    }

    function validPreparationJob(job, project) {
        return job?.schemaVersion === "media-preparation-job-v1" && job.project === project
            && /^[a-f0-9]{32}$/.test(job.jobId) && typeof job.live === "boolean" && typeof job.cancellationRequested === "boolean"
            && ["queued", "running", "cancelling", "finished", "partial", "failed", "cancelled"].includes(job.status)
            && (job.batchId === null || /^[a-f0-9]{32}$/.test(job.batchId))
            && (job.progress === null || (job.progress.batchId === job.batchId && Array.isArray(job.progress.items)
                && job.progress.items.length <= 100 && job.progress.items.every((row) => row && typeof row.id === "string" && typeof row.runId === "string"
                    && typeof row.sourceName === "string" && typeof row.verifiedThisInvocation === "boolean" && typeof preparationLabels[row.status] === "string")));
    }

    function renderPreparationJob() {
        const job = state.preparationJob;
        const active = Boolean(job?.live && ["queued", "running", "cancelling"].includes(job.status));
        for (const id of ["preparation-project", "preparation-paths", "preparation-profile", "preparation-budget", "preparation-timeout", "start-preparation"]) ui[id].disabled = active || state.preparationSubmitting;
        ui["start-preparation"].textContent = state.preparationSubmitting ? "正在提交…" : "开始本地准备";
        ui["stop-preparation"].disabled = !active || job.cancellationRequested || state.preparationSubmitting;
        ui["open-prepared-tasks"].disabled = !job?.progress;
        ui["download-preparation"].disabled = !job?.result || active;
        ui["preparation-status"].textContent = job ? preparationLabels[job.status] : "尚未开始新批次";
        const rows = job?.progress?.items || [];
        ui["preparation-summary"].textContent = rows.length ? `已检查 ${rows.filter((row) => row.verifiedThisInvocation).length}/${rows.length} 段 · 已准备 ${rows.filter((row) => row.status === "prepared").length} 段`
            : job ? (job.error?.message || "正在登记原清单，请稍候。") : "提交录像清单后，在这里查看每段进度。";
        if (job?.error?.message && rows.length) ui["preparation-summary"].textContent += ` · ${job.error.message}`;
        ui["preparation-items"].replaceChildren();
        for (const row of rows) {
            const card = element("article", `preparation-item ${row.status}`);
            card.dataset.run = row.runId;
            card.append(element("h4", "", `${row.id} · ${row.sourceName}`), element("p", "small", row.status === "failed" ? "这段录像准备失败" : preparationLabels[row.status]));
            if (row.result && Number.isSafeInteger(row.result.imageCount)) card.append(element("p", "muted small", `${row.result.imageCount} 张画面 · ${row.result.audioAvailable ? "已保存音轨" : "没有音轨"}`));
            if (typeof row.message === "string") card.append(element("p", "warning small", row.message));
            if (!row.verifiedThisInvocation && !["running", "pending"].includes(row.status)) card.append(element("p", "muted small", "这是上次保存的状态，本次尚未重新核对。"));
            ui["preparation-items"].append(card);
        }
        for (const button of ui["preparation-batches"].querySelectorAll("button")) button.disabled = active || state.preparationSubmitting || button.dataset.unreadable === "true";
    }

    function observePreparation(job, revision) {
        state.preparationJob = job;
        renderPreparationJob();
        if (!job.live) return;
        state.preparationTimer = setTimeout(() => { void pollPreparation(job, revision); }, 750);
    }

    async function pollPreparation(job, revision) {
        if (state.preparationRevision !== revision || !ui["preparation-dialog"].open || job.project !== preparationTarget()) return;
        const controller = new AbortController();
        state.preparationController = controller;
        try {
            const current = await request("/api/media-preparation", { project: job.project, job: job.jobId }, controller.signal);
            if (controller.signal.aborted || revision !== state.preparationRevision || state.preparationController !== controller) return;
            if (!validPreparationJob(current, job.project) || current.jobId !== job.jobId) throw new Error("准备任务身份或进度不一致，请重新读取批次。");
            observePreparation(current, revision);
            if (!current.live && current.batchId) void readPreparationBatches(state.preparationOffset, true);
        } catch (error) {
            if (controller.signal.aborted || revision !== state.preparationRevision) return;
            notice(`${error.message} 请重新读取批次；不会自动重新提交。`);
            ui["preparation-summary"].textContent = "暂时无法确认本次任务状态，请重新读取；已保存资料保留。";
        }
    }

    async function readPreparationBatches(offset = 0, keepJob = false) {
        stopPreparationObservation();
        const project = preparationTarget();
        if (!project) return notice("请填写仓库artifacts目录内的准备项目。");
        const revision = state.preparationRevision;
        const controller = new AbortController();
        state.preparationController = controller;
        if (!keepJob) state.preparationJob = null;
        renderPreparationJob();
        ui["refresh-preparation"].disabled = true;
        try {
            const catalog = await request("/api/media-batches", { project, limit: 20, offset }, controller.signal);
            if (controller.signal.aborted || revision !== state.preparationRevision || project !== preparationTarget()) return;
            if (catalog.schemaVersion !== "media-preparation-catalog-v1" || catalog.project !== project || catalog.offset !== offset
                || catalog.limit !== 20 || !Number.isSafeInteger(catalog.total) || !Array.isArray(catalog.batches)
                || catalog.batches.length > 20 || catalog.batches.some((batch) => !/^[a-f0-9]{32}$/.test(batch.batchId) || typeof batch.readable !== "boolean")
                || (catalog.activeJob && !validPreparationJob(catalog.activeJob, project))) throw new Error("已保存批次身份或分页不一致。");
            rememberPreparationTarget(project);
            state.preparationCatalog = catalog;
            state.preparationOffset = offset;
            ui["preparation-history-summary"].textContent = catalog.total ? `${offset + 1}–${Math.min(offset + 20, catalog.total)} / ${catalog.total} 个批次 · 以下为保存记录` : "此项目还没有准备批次。";
            ui["preparation-previous"].disabled = offset === 0;
            ui["preparation-next"].disabled = offset + 20 >= catalog.total;
            ui["preparation-batches"].replaceChildren();
            for (const batch of catalog.batches) {
                const card = element("article", "preparation-batch");
                card.dataset.batch = batch.batchId;
                card.append(element("h4", "", `批次 ${batch.batchId.slice(0, 8)}`));
                card.append(element("p", "muted small", batch.readable ? `${batch.items.length} 段 · ${preparationLabels[batch.status] || "已保存状态"} · 非实时任务状态`
                    : batch.message || "资料无法核对，请保留原批次后检查。"));
                if (batch.readable) card.append(element("p", "muted small", `原每段后续分析上限：¥${batch.maxCostCnyPerTask}，继续不会替换原方案或额度。`));
                const resume = element("button", "button secondary compact", "继续本地准备");
                resume.type = "button";
                resume.dataset.unreadable = String(!batch.readable);
                resume.disabled = !batch.readable;
                resume.addEventListener("click", () => { void submitPreparation(batch.batchId); });
                card.append(resume);
                ui["preparation-batches"].append(card);
            }
            if (catalog.activeJob) observePreparation(catalog.activeJob, revision);
            else renderPreparationJob();
        } catch (error) {
            if (controller.signal.aborted || revision !== state.preparationRevision) return;
            notice(error.message);
            empty(ui["preparation-batches"], "批次清单未读取完成，请查看提示后重新读取。");
        } finally {
            if (revision === state.preparationRevision) ui["refresh-preparation"].disabled = false;
        }
    }

    async function submitPreparation(resume = null) {
        if (state.preparationSubmitting || (state.preparationJob?.live && ["queued", "running", "cancelling"].includes(state.preparationJob.status))) return;
        const project = preparationTarget();
        const timeoutSeconds = Number(ui["preparation-timeout"].value);
        if (!project || !Number.isFinite(timeoutSeconds) || timeoutSeconds < 1 || timeoutSeconds > 86400) return notice("请填写准备项目和1–86400秒的每段期限。");
        let body = { project, resume, timeoutSeconds };
        if (resume === null) {
            const paths = ui["preparation-paths"].value.split(/\r?\n/).map((line) => line.trim().replace(/^"(.*)"$/, "$1")).filter(Boolean);
            const maxCostCny = ui["preparation-budget"].value.trim();
            if (paths.length < 1 || paths.length > 100 || !maxCostCny || !Number.isFinite(Number(maxCostCny)) || Number(maxCostCny) <= 0) return notice("请填写1–100段录像路径及以后每段分析的正数上限。");
            body = { project, paths, profile: ui["preparation-profile"].value, maxCostCny, timeoutSeconds };
        }
        stopPreparationObservation();
        const revision = state.preparationRevision;
        const controller = new AbortController();
        state.preparationController = controller;
        state.preparationSubmitting = true;
        notice("");
        renderPreparationJob();
        try {
            const job = await request("/api/prepare-media-batch", {}, controller.signal, body);
            if (controller.signal.aborted || revision !== state.preparationRevision || project !== preparationTarget()) return;
            if (!validPreparationJob(job, project)) throw new Error("准备任务来源不一致，请重新读取批次确认。");
            rememberPreparationTarget(project);
            observePreparation(job, revision);
        } catch (error) {
            if (controller.signal.aborted || revision !== state.preparationRevision) return;
            notice(`${error.message} 先重新读取批次确认，不会自动重试提交。`);
        } finally {
            if (revision === state.preparationRevision) {
                state.preparationSubmitting = false;
                renderPreparationJob();
            }
        }
    }

    async function cancelPreparation() {
        const job = state.preparationJob;
        if (!job?.live || job.cancellationRequested) return;
        stopPreparationObservation();
        const revision = state.preparationRevision;
        const controller = new AbortController();
        state.preparationController = controller;
        try {
            const result = await request("/api/cancel-media-preparation", {}, controller.signal, { project: job.project, job: job.jobId });
            if (controller.signal.aborted || revision !== state.preparationRevision) return;
            if (!validPreparationJob(result, job.project) || result.jobId !== job.jobId) throw new Error("停止任务的身份不一致，请重新读取。");
            observePreparation(result, revision);
        } catch (error) {
            if (controller.signal.aborted || revision !== state.preparationRevision) return;
            notice(`${error.message} 请重新读取确认任务状态。`);
        }
    }

    async function openPreparedTasks() {
        const job = state.preparationJob;
        if (!job?.progress) return;
        const project = job.project;
        ui["preparation-dialog"].close();
        if (![...ui["project-select"].options].some((option) => option.value === project)) {
            const option = element("option", "", project);
            option.value = project;
            ui["project-select"].append(option);
        }
        ui["project-select"].value = project;
        await loadRuns(project);
        if (state.project === project) void loadTasks();
    }

    function updateSearchScope() {
        ui["open-search-detail-query"].hidden = !state.searchDetailAvailable || !state.projectSearch;
        ui["open-search-detail-query"].disabled = state.busy || !currentSearchDetailScope();
        ui["open-project-detail-query"].hidden = !state.projectDetailAvailable || !state.searchRuns.length;
        ui["open-project-detail-query"].disabled = state.busy || !state.searchRuns.length || !state.view?.detailQueryOptions;
        ui["open-search-sources"].textContent = state.searchRuns.length ? `已选 ${state.searchRuns.length} 段 · 更改录像` : "选择多段录像";
        ui["search-scope-label"].textContent = state.searchRuns.length ? `搜索已选的 ${state.searchRuns.length} 段录像 · 回看时可切换来源` : "搜索当前录像";
        ui["single-search-source"].hidden = !state.searchRuns.length;
        ui["open-search-sources"].disabled = state.busy || !state.runs.some((run) => run.status === "completed");
        ui["download-project-search"].hidden = !state.searchRuns.length;
        ui["download-project-search"].disabled = state.busy || !state.projectSearch;
        ui["open-retrieval-diagnostics"].hidden = Boolean(state.searchRuns.length);
    }

    function clearProjectSearch() {
        clearSearchDetailEvidence();
        state.projectSearchController?.abort();
        state.projectSearchController = null;
        state.projectSearch = null;
        clearRetrievalDiagnostics();
        updateSearchScope();
    }

    function openSearchSources() {
        ui["search-sources-list"].replaceChildren();
        const ready = state.runs.filter((run) => run.status === "completed" && /^[a-f0-9]{64}$/.test(run.sourceSha256));
        for (const run of ready) {
            const label = element("label", "search-source-option");
            const checkbox = element("input");
            checkbox.type = "checkbox";
            checkbox.value = run.id;
            checkbox.dataset.sha = run.sourceSha256;
            checkbox.dataset.media = run.mediaId;
            checkbox.checked = state.searchRuns.includes(run.id);
            const copy = element("span", "", run.sourceName || "未命名录像");
            const profile = run.analysisProfile === "detailed" ? "细节动作分析" : run.analysisKind === "temporal" ? "连续动作分析" : "画面观察";
            copy.append(element("small", "", `${profile} · ${timecode(run.durationUs)} · 版本 ${run.id.slice(0, 8)}`));
            label.append(checkbox, copy);
            ui["search-sources-list"].append(label);
            checkbox.addEventListener("change", () => {
                if (checkbox.checked) {
                    for (const other of ui["search-sources-list"].querySelectorAll("input")) {
                        if (other !== checkbox && (other.dataset.sha === checkbox.dataset.sha || other.dataset.media === checkbox.dataset.media)) other.checked = false;
                    }
                }
                updateSourceChoice();
            });
        }
        if (!ready.length) empty(ui["search-sources-list"], "还没有已完成且来源明确的录像。");
        updateSourceChoice();
        ui["search-sources-dialog"].showModal();
    }

    function updateSourceChoice() {
        const count = ui["search-sources-list"].querySelectorAll("input:checked").length;
        ui["search-sources-summary"].textContent = `已选择 ${count} 段 · 关闭窗口会保留原来的搜索范围`;
        ui["apply-search-sources"].disabled = count < 1 || count > 100;
    }

    function jointRowsForView(payload) {
        const result = state.projectSearch;
        if (!result) return payload;
        const source = result.sources.find((item) => item.runId === payload.runId);
        if (!source) return payload;
        if (payload.media.id !== source.mediaId || payload.media.sha256 !== source.sourceSha256
            || payload.media.durationUs !== source.durationUs || payload.configHash !== source.configHash) throw new Error("候选来源已变化，请重新搜索后回看。");
        const candidates = result.candidates.filter((row) => row.runId === payload.runId).map((row) => {
            const event = payload.timeline.find((item) => item.eventId === row.eventId);
            return { ...row, detailRefinement: event?.detailRefinement };
        });
        return { ...payload, candidates, query: result.query, mode: result.mode, retrievalVersion: result.retrievalVersion, retrievalDiagnostics: null };
    }

    async function searchProject(query) {
        const top = Number(ui.top.value);
        if (!Number.isInteger(top) || top < 1 || top > 100) return notice("候选条数需要是1到100的整数。");
        state.inspectController?.abort();
        clearProjectSearch();
        state.active = null;
        state.playbackEndUs = null;
        ui["source-video"].pause();
        updateActive();
        renderEvidence();
        const controller = new AbortController();
        state.projectSearchController = controller;
        const revision = state.revision;
        const runs = [...state.searchRuns];
        const mode = ui.mode.value;
        notice("");
        setBusy(true, true);
        empty(ui["candidate-list"], "正在搜索选中的录像…");
        ui["candidate-count"].textContent = "0";
        try {
            const result = await request("/api/search-project", {}, controller.signal, { project: state.project, runs, query, mode, top });
            if (controller.signal.aborted || revision !== state.revision || state.projectSearchController !== controller) return;
            if (result.schemaVersion !== "project-search-v1" || result.project !== state.project || result.query !== query
                || result.mode !== mode || result.topK !== top || !Array.isArray(result.sources) || result.sources.length !== runs.length
                || !Array.isArray(result.candidates) || result.candidates.length > top
                || new Set(result.sources.map((source) => source.runId)).size !== runs.length
                || result.sources.some((source) => {
                    const known = state.runs.find((run) => run.id === source.runId);
                    return !runs.includes(source.runId) || !known || known.sourceSha256 !== source.sourceSha256 || known.mediaId !== source.mediaId || known.durationUs !== source.durationUs;
                }) || result.candidates.some((row, index) => {
                    const source = result.sources.find((item) => item.runId === row.runId);
                    return !source || row.rank !== index + 1 || row.mediaId !== source.mediaId || row.sourceSha256 !== source.sourceSha256
                        || row.sourceName !== source.sourceName || !validInterval(row, source.durationUs)
                        || typeof row.candidateId !== "string" || !Array.isArray(row.evidenceIds) || !row.evidenceIds.every((id) => typeof id === "string")
                        || !Array.isArray(row.observableFacts) || !row.observableFacts.every((fact) => typeof fact === "string");
                })) throw new Error("多录像结果的来源或排名不一致，请重新搜索。");
            state.projectSearch = result;
            if (state.view) state.view = jointRowsForView(state.view);
            renderCandidates();
            renderSelections();
        } catch (error) {
            if (controller.signal.aborted || revision !== state.revision || state.projectSearchController !== controller) return;
            notice(error.message);
            empty(ui["candidate-list"], "搜索未完成，请查看提示后重试。");
            ui["candidate-count"].textContent = "0";
        } finally {
            if (revision === state.revision && state.projectSearchController === controller) setBusy(false);
        }
    }

    async function openJointCandidate(row, select = false) {
        const result = state.projectSearch;
        if (!result || state.busy || !result.candidates.includes(row)) return;
        if (state.run !== row.runId || !state.view?.candidates.some((item) => item.candidateId === row.candidateId)) {
            ui["run-select"].value = row.runId;
            const loaded = await switchRun(row.runId, true);
            if (!loaded || state.projectSearch !== result || state.run !== row.runId) return;
        }
        const current = state.view?.candidates.find((item) => item.candidateId === row.candidateId);
        if (!current || state.projectSearch !== result || state.run !== row.runId) return;
        if (select) toggleSelection("candidate", current);
        else await previewClip("candidate", current);
    }

    function downloadProjectSearch() {
        if (!state.projectSearch || state.busy) return;
        const url = URL.createObjectURL(new Blob([JSON.stringify(state.projectSearch, null, 2) + "\n"], { type: "application/json;charset=utf-8" }));
        const link = element("a");
        link.href = url;
        link.download = `project-search-${state.projectSearch.searchId}.json`;
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        notice("已下载这次搜索的原排名、录像来源和证据清单。", true);
    }

    function clearTasks() {
        state.tasksController?.abort();
        state.tasksController = null;
        state.tasksRevision += 1;
        state.tasksOffset = 0;
        if (ui["tasks-dialog"].open) ui["tasks-dialog"].close();
        ui["tasks-list"].replaceChildren();
        ui["tasks-page-summary"].textContent = "";
        ui["tasks-previous"].disabled = true;
        ui["tasks-next"].disabled = true;
    }

    function taskMoney(value) { return typeof value === "string" ? `¥${value}` : "未知"; }

    function renderTasks(payload, project, revision) {
        ui["tasks-list"].replaceChildren();
        const start = payload.tasks.length ? payload.offset + 1 : 0;
        ui["tasks-page-summary"].textContent = `${start}–${payload.offset + payload.tasks.length} / ${payload.total} 个任务`;
        ui["tasks-previous"].disabled = payload.offset === 0;
        ui["tasks-next"].disabled = !payload.hasMore;
        if (!payload.tasks.length) { empty(ui["tasks-list"], "这一页没有已保存任务。"); return; }
        const blockerLabels = {
            material_integrity: "原文件或证据有问题，先核对素材。",
            explicit_retry_required: "旧调用未提交或费用未确认，需明确选择重试；原预留保留。",
            legacy_stopped: "旧分析流程已停止，不能直接重放。",
            coverage_limit: "原配置不足以覆盖全部窗口，调整配置后准备新任务。",
            unsupported_cli_provider: "该配置需要对应的分析入口。",
        };
        for (const task of payload.tasks) {
            if (typeof task.runId !== "string" || !task.runId) throw new Error("任务身份无效。");
            const card = element("section", "task-card");
            card.append(element("h3", "", task.sourceName || "未命名素材"));
            card.append(element("p", "task-phase", task.phaseLabel || "进度未确认"));
            const savedStatus = task.runStatus === "running" ? "处理中（保存记录）" : statusLabels[task.runStatus] || task.runStatus;
            card.append(element("p", "muted small", `${savedStatus} · ${timecode(task.durationUs)} · ${task.imageCount} 张画面 · ${task.eventCount} 条事件`));
            const progress = task.progress || {};
            card.append(element("p", "small", `阶段 ${progress.requiredCompleted}/${progress.requiredTotal} 已完成；视觉窗口 ${progress.completedVisionWindows}/${progress.plannedWindows ?? "尚未准备"}`));
            const config = task.configuration?.analysis || {};
            card.append(element("p", "muted small", `保存的配置：${config.model || "模型未知"}，每 ${(config.sampling_interval_ms || 0) / 1000} 秒取样，${config.window_frames || "?"} 张一组，重叠 ${config.window_overlap ?? "?"} 张。`));
            const cost = task.cost || {};
            card.append(element("p", "small", `基础分析已知估价 ${taskMoney(cost.knownCny)}；${cost.unknownAttempts ?? "?"} 次费用未确认；未知预留 ${taskMoney(cost.unknownReservationCny)}。`));
            card.append(element("p", "muted small", `保存的分析上限 ${taskMoney(task.configuration?.maxCostCny)}；含未知预留的承诺 ${taskMoney(cost.committedCny)}。精分析费用另行查看。`));
            const blockers = Array.isArray(task.continuationBlockers) ? task.continuationBlockers : [];
            const next = task.phase === "completed" ? "可以打开回看与检索。" : task.nextAction === "prepare_media" ? "下一步：按原任务ID续准备素材。" : "下一步：明确启动分析，接着已保存进度运行。";
            card.append(element("p", "task-next small", blockers.length ? blockers.map((item) => blockerLabels[item] || "接续条件尚未满足。").join(" ") : next));
            if (task.errorCode) card.append(element("p", "muted small", `已保存的停止原因：${task.errorCode}`));
            card.append(element("p", "task-id muted small", `任务 ${task.runId}`));
            const open = element("button", "button secondary compact", "打开此任务");
            open.type = "button";
            open.addEventListener("click", () => {
                if (state.project !== project || state.tasksRevision !== revision) return;
                clearTasks();
                if (state.runs.some((run) => run.id === task.runId)) {
                    ui["run-select"].value = task.runId;
                    switchRun(task.runId);
                } else { void loadRuns(project, task.runId); }
            });
            card.append(open);
            ui["tasks-list"].append(card);
        }
    }

    async function loadTasks(offset = 0) {
        if (!state.project) return;
        state.tasksController?.abort();
        const controller = new AbortController();
        state.tasksController = controller;
        const revision = ++state.tasksRevision;
        const project = state.project;
        state.tasksOffset = offset;
        ui["tasks-previous"].disabled = true;
        ui["tasks-next"].disabled = true;
        ui["tasks-page-summary"].textContent = "正在读取保存进度…";
        empty(ui["tasks-list"], "正在读取素材任务…");
        if (!ui["tasks-dialog"].open) ui["tasks-dialog"].showModal();
        try {
            const payload = await request("/api/tasks", { project, limit: TASK_PAGE_SIZE, offset }, controller.signal);
            if (state.project !== project || state.tasksRevision !== revision || state.tasksController !== controller) return;
            if (payload.schemaVersion !== "material-tasks-v1" || payload.project !== project || payload.offset !== offset
                || !Array.isArray(payload.tasks) || !Number.isSafeInteger(payload.total) || payload.total < 0
                || payload.limit !== TASK_PAGE_SIZE || typeof payload.hasMore !== "boolean") throw new Error("任务清单来源或页码无效。");
            renderTasks(payload, project, revision);
        } catch (error) {
            if (error.name !== "AbortError" && state.project === project && state.tasksRevision === revision) {
                empty(ui["tasks-list"], error.message);
                ui["tasks-page-summary"].textContent = "未读取，不能据此判断没有任务。";
                ui["tasks-previous"].disabled = true;
                ui["tasks-next"].disabled = true;
            }
        }
    }

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

    async function request(endpoint, parameters, signal, body = null) {
        const url = new URL(endpoint, window.location.origin);
        for (const [name, value] of Object.entries(parameters)) url.searchParams.set(name, String(value));
        const response = await fetch(url, {
            signal, cache: "no-store", credentials: "same-origin",
            ...(body === null ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
        });
        let payload;
        try {
            payload = await response.json();
        } catch {
            throw new Error(`服务没有返回有效数据（HTTP ${response.status}）。`);
        }
        if (!response.ok) throw new Error(typeof payload.message === "string" ? payload.message : `请求失败（HTTP ${response.status}）。`);
        return payload;
    }

    function canMatchDetails() {
        if (state.detailSearchScope) return !state.busy && currentSearchDetailScope() && Boolean(state.view?.detailQueryOptions);
        if (state.detailProjectScope) return state.projectDetailAvailable && !state.busy && state.searchRuns.length > 0 && Boolean(state.view?.detailQueryOptions);
        return !state.busy && state.view?.runStatus === "completed" && Boolean(state.active?.row.eventId)
            && state.view?.detailRefinementProfile?.profile === ui["detail-profile"].value;
    }

    function updateDetailQueryButton() {
        const available = canMatchDetails();
        ui["open-detail-query"].disabled = !available;
        ui["match-detail-query"].disabled = !available || state.matching || !draftScopeConfirmed();
        ui["match-detail-query"].textContent = state.matching ? "正在本地核对…" : "核对已保存结果";
        ui["add-detail-condition"].disabled = !available || ui["detail-conditions"].children.length >= 16;
        ui["generate-detail-draft"].disabled = !available || state.drafting || !ui["detail-draft-text"].value.trim();
        ui["generate-detail-draft"].textContent = state.drafting ? "正在整理条件…" : "生成可编辑条件";
        ui["detail-draft-subset"].disabled = state.drafting;
        ui["detail-query-target"].textContent = state.detailSearchScope
            ? `“${state.projectSearch?.query || ""}” · 只核对原搜索的 ${state.projectSearch?.candidates.length || 0} 个候选 · 精分析 ${ui["detail-profile"].value}` : state.detailProjectScope
            ? `核对已选 ${state.searchRuns.length} 段录像的全部已有事件 · 精分析 ${ui["detail-profile"].value}` : state.active
            ? `${intervalLabel(state.active.row)} · 精分析 ${ui["detail-profile"].value}` : "先选择一个已完成运行中的片段。";
    }

    function clearDetailMatch() {
        state.matchController?.abort();
        state.matchController = null;
        state.matchRevision += 1;
        state.matching = false;
        state.projectDetail = null;
        ui["project-detail-filter"].disabled = false;
        ui["project-detail-controls"].hidden = !state.detailProjectScope;
        ui["search-detail-controls"].hidden = !state.detailSearchScope;
        ui["project-detail-summary"].textContent = "先明确条件并核对；缺少精分析不能当作没有符合条件的画面。";
        for (const id of ["project-detail-previous", "project-detail-next", "project-detail-download"]) ui[id].disabled = true;
        empty(ui["detail-match-result"], state.detailProjectScope ? "选择条件后，统一核对已选录像的已保存结果。" : "选择条件后，核对当前片段的已保存结果。");
        updateDetailQueryButton();
    }

    function conditionGroups(kind) {
        if (kind.startsWith("clothing_")) return Array.from({ length: 16 }, (_, i) => [`clothing${i + 1}`, `衣物 ${i + 1}`]);
        if (kind.startsWith("held_")) return Array.from({ length: 16 }, (_, i) => [`held${i + 1}`, `持有物 ${i + 1}`]);
        return [[kind === "hair_color" ? "hair" : kind, { hair_color: "头发", action: "动作", effect: "效果", environment: "环境" }[kind]]];
    }

    function addDetailCondition(kind = "hair_color", value = "white", partGroup = null) {
        const options = state.view?.detailQueryOptions?.kinds;
        if (!Array.isArray(options) || ui["detail-conditions"].children.length >= 16) return;
        const row = element("div", "detail-condition");
        const field = (text, className) => {
            const label = element("label", "", text);
            const select = element("select", className);
            label.append(select);
            row.append(label);
            return select;
        };
        const kinds = field("属性", "condition-kind");
        const values = field("值", "condition-value");
        const groups = field("部件组", "condition-group");
        const fill = (select, entries) => {
            select.replaceChildren();
            for (const [token, label] of entries) {
                const option = element("option", "", label);
                option.value = token;
                select.append(option);
            }
        };
        fill(kinds, options.map((item) => [item.kind, item.label]));
        kinds.value = kind;
        const updateValues = () => {
            const definition = options.find((item) => item.kind === kinds.value);
            fill(values, definition.values.map((item) => [item.value, item.label]));
            fill(groups, conditionGroups(kinds.value));
        };
        updateValues();
        if ([...values.options].some((item) => item.value === value)) values.value = value;
        if (partGroup !== null) groups.value = partGroup;
        kinds.addEventListener("change", () => { updateValues(); detailConditionsChanged(); });
        values.addEventListener("change", detailConditionsChanged);
        groups.addEventListener("change", detailConditionsChanged);
        const remove = element("button", "icon-button", "×");
        remove.type = "button";
        remove.setAttribute("aria-label", "移除此条件");
        remove.addEventListener("click", () => { row.remove(); detailConditionsChanged(); });
        row.append(remove);
        ui["detail-conditions"].append(row);
        detailConditionsChanged();
    }

    function draftScopeConfirmed() {
        return !state.drafting && (["manual", "ready"].includes(state.draftScope) || ui["detail-draft-subset"].checked);
    }

    function invalidateDetailDraft(reset = false) {
        state.draftController?.abort();
        state.draftController = null;
        state.draftRevision += 1;
        state.drafting = false;
        if (reset) ui["detail-draft-text"].value = "";
        state.draftScope = ui["detail-draft-text"].value.trim() ? "pending" : "manual";
        ui["detail-draft-subset"].checked = false;
        ui["detail-draft-confirmation"].hidden = state.draftScope === "manual";
        ui["detail-draft-gaps"].replaceChildren();
        ui["detail-draft-status"].textContent = state.draftScope === "manual"
            ? "可以直接编辑条件，也可以填写描述后生成草稿。"
            : "描述已修改，尚未整理。生成草稿后检查遗漏，或明确只核对下方手动条件。";
        updateDetailQueryButton();
    }

    function detailConditionsChanged() {
        if (state.detailSearchScope) clearSearchDetailEvidence();
        if (state.drafting) invalidateDetailDraft();
        clearDetailMatch();
    }

    function validateDetailDraft(report, originalText) {
        if (report.schemaVersion !== "actor-detail-query-draft-v1" || report.originalText !== originalText
            || report.spanOffsetUnit !== "unicode-code-point" || !["ready", "needs_review", "unsupported"].includes(report.status)
            || !Array.isArray(report.spans) || !Array.isArray(report.unparsed)
            || report.spans.some((span) => typeof span.text !== "string" || typeof span.reason !== "string")
            || report.spans.map((span) => span.text).join("") !== originalText
            || report.unparsed.some((span) => span.kind !== "unparsed" || typeof span.text !== "string" || typeof span.reason !== "string")) {
            throw new Error("草稿与当前描述不一致，请重新生成。");
        }
        const constraint = report.constraint;
        if (constraint === null) {
            if (report.status === "ready") throw new Error("完整草稿缺少条件。");
            return [];
        }
        const options = state.view.detailQueryOptions;
        if (report.status === "unsupported" || constraint.schemaVersion !== options.schemaVersion
            || constraint.version !== options.version || constraint.vocabularyVersion !== options.vocabularyVersion
            || !Array.isArray(constraint.actorAll) || !Array.isArray(constraint.environmentAll) || !constraint.actorAll.length) {
            throw new Error("草稿条件版本无效。");
        }
        const conditions = [...constraint.actorAll, ...constraint.environmentAll];
        if (conditions.length > 16 || conditions.some((condition) => {
            const definition = options.kinds.find((item) => item.kind === condition.kind);
            return !definition?.values.some((item) => item.value === condition.value)
                || !conditionGroups(condition.kind).some(([group]) => group === condition.partGroup);
        }) || (report.status === "ready" && report.unparsed.length)) throw new Error("草稿含有无法编辑的条件。");
        return conditions;
    }

    async function generateDetailDraft() {
        if (!canMatchDetails() || state.drafting) return;
        const originalText = ui["detail-draft-text"].value;
        if (!originalText.trim()) return;
        invalidateDetailDraft();
        clearDetailMatch();
        const controller = new AbortController();
        state.draftController = controller;
        const revision = state.draftRevision;
        state.drafting = true;
        updateDetailQueryButton();
        try {
            const report = await request("/api/draft-detail-query", {}, controller.signal, { text: originalText });
            if (revision !== state.draftRevision || state.draftController !== controller || ui["detail-draft-text"].value !== originalText) return;
            const conditions = validateDetailDraft(report, originalText);
            state.drafting = false;
            state.draftScope = report.status === "ready" ? "ready" : "subset";
            ui["detail-draft-subset"].checked = false;
            if (report.constraint !== null) {
                ui["detail-conditions"].replaceChildren();
                for (const condition of conditions) addDetailCondition(condition.kind, condition.value, condition.partGroup);
            }
            ui["detail-draft-status"].textContent = report.status === "ready"
                ? "已生成可编辑条件。请检查后点击核对；结果只针对下方当前条件。"
                : report.status === "unsupported"
                    ? "这段描述含有暂不支持的要求，未自动转换；已保留原先的手动条件。可以修改描述，或编辑条件并明确确认核对范围。"
                    : "还有要求未能处理，请查看下方原文。你可以修改描述，或明确只核对已列出的条件。";
            ui["detail-draft-confirmation"].hidden = report.status === "ready";
            ui["detail-draft-gaps"].replaceChildren();
            for (const span of report.unparsed) {
                ui["detail-draft-gaps"].append(element("li", "warning small", `未核对：${span.text} · ${span.reason}`));
            }
        } catch (error) {
            if (error.name !== "AbortError" && revision === state.draftRevision) ui["detail-draft-status"].textContent = error.message;
        } finally {
            if (revision === state.draftRevision) { state.drafting = false; updateDetailQueryButton(); }
        }
    }

    function detailConstraint() {
        const options = state.view.detailQueryOptions;
        const constraint = {
            schemaVersion: options.schemaVersion, version: options.version, vocabularyVersion: options.vocabularyVersion,
            actorAll: [], environmentAll: [],
        };
        for (const row of ui["detail-conditions"].children) {
            const condition = {
                kind: row.querySelector(".condition-kind").value,
                value: row.querySelector(".condition-value").value,
                partGroup: row.querySelector(".condition-group").value,
            };
            constraint[condition.kind === "environment" ? "environmentAll" : "actorAll"].push(condition);
        }
        if (!constraint.actorAll.length) throw new Error("至少选择一个主体属性条件。");
        return constraint;
    }

    function conditionLabel(condition) {
        const definition = state.view?.detailQueryOptions?.kinds.find((item) => item.kind === condition.kind);
        const value = definition?.values.find((item) => item.value === condition.value);
        const group = conditionGroups(condition.kind).find(([token]) => token === condition.partGroup);
        return `${definition?.label || condition.kind}：${value?.label || condition.value} · ${group?.[1] || condition.partGroup}`;
    }

    function appendSupportFrames(container, ids, label = "支持帧") {
        const list = element("div", "detail-support-frames");
        for (const id of ids || []) {
            const item = state.view.evidence.find((frame) => frame.id === id && frame.kind === "image");
            if (!item || !state.active?.row.evidenceIds.includes(id)) continue;
            const url = safeMediaUrl(item.url, "/api/evidence", id);
            if (!url) continue;
            const button = element("button", "text-button", `${label} ${timecode(item.startUs)}`);
            button.type = "button";
            button.addEventListener("click", () => {
                ui["evidence-dialog-title"].textContent = `源帧 · ${timecode(item.startUs)}`;
                ui["evidence-full"].src = url;
                ui["evidence-dialog-detail"].textContent = `证据 ${item.id} · 来源 ${state.view.media.name}`;
                ui["evidence-dialog"].showModal();
            });
            list.append(button);
        }
        container.append(list);
    }

    function renderDetailMatch(report) {
        const result = report.result;
        const labels = { full: "全部条件有共同支持 · 待人工核对", partial: "部分条件有支持", no_match: "已有证据排除条件", unverified: "条件未验证" };
        if (state.draftScope !== "manual") labels.full = "当前条件有共同支持 · 待人工核对";
        ui["detail-match-result"].replaceChildren(element("h3", result.status === "full" ? "accent" : "warning", labels[result.status]));
        if (state.draftScope !== "manual") ui["detail-match-result"].append(element("p", "warning small",
            state.draftScope === "ready" ? "仅核对下方当前条件；生成后可编辑，结果不代表原描述的所有要求。"
                : "仅核对下方当前条件。原描述的其他要求尚未核对，不能确认整句满足。"));
        if (!result.matches.length) ui["detail-match-result"].append(element("p", "muted small", "所选版本尚无可匹配的主体结构。未发起精分析。"));
        const detail = state.active.row.detailRefinement?.detail;
        for (const match of result.matches) {
            const actor = detail?.shots.find((shot) => shot.shotId === match.shotId)?.actors.find((item) => item.actorId === match.actorId);
            const section = element("section", "detail-match-actor");
            section.append(element("p", "", actor ? cleanObservationText(actor.description) : "已保存主体"));
            if (actor) appendDescriptionReview(section, match.shotId, match.actorId);
            const list = element("ul");
            for (const [key, text] of [["satisfied", "有支持"], ["uncertain", "不确定"], ["opposed", "有相反证据"]]) {
                for (const support of match[key]) {
                    const entry = element("li", key === "satisfied" ? "" : "warning", `${text} · ${conditionLabel(support.condition)}`);
                    appendSupportFrames(entry, support.evidenceIds);
                    list.append(entry);
                }
            }
            for (const condition of match.missing) list.append(element("li", "muted", `缺少支持 · ${conditionLabel(condition)}`));
            section.append(list);
            if (match.conflicts.length) section.append(element("p", "warning small", "同一部件的观察属性有冲突，不能确认全部条件。"));
            if (match.sharedEvidenceIds.length) appendSupportFrames(section, match.sharedEvidenceIds, "上方有支持条件的共同帧");
            else section.append(element("p", "muted small", "没有共同支持全部条件的源帧。"));
            if (match.counterEvidence.length) {
                section.append(element("p", "warning small", "此主体存在排除条件的证据："));
                appendSupportFrames(section, [...new Set(match.counterEvidence.flatMap((item) => item.evidenceIds))], "排除证据");
            }
            ui["detail-match-result"].append(section);
        }
        const notes = { detail_missing: "缺少已保存的主体详情。", unassigned_evidence: "部分帧尚未归属镜头。", observed_attribute_conflict: "观察属性存在冲突。", unresolved_entity: "还有实体、持有关系或画面连续性未确定，不能据此排除所有人物。" };
        for (const note of result.notes) ui["detail-match-result"].append(element("p", "warning small", notes[note] || cleanObservationText(note)));
    }

    function currentSearchDetailScope() {
        const search = state.projectSearch;
        return Boolean(state.searchDetailAvailable && search && /^[a-f0-9]{64}$/.test(search.searchSha256)
            && search.query === ui.query.value.trim() && search.mode === ui.mode.value && search.topK === Number(ui.top.value));
    }

    function clearSearchDetailEvidence() {
        state.searchDetail = null;
        ui["download-search-details"].disabled = true;
        ui["search-detail-summary"].textContent = "确认条件后，为这次搜索的原候选补依据；不重排，不剔除未知结果。";
        if (state.projectSearch) renderCandidates();
    }

    function stableJson(value) {
        const sorted = (item) => Array.isArray(item) ? item.map(sorted)
            : item && typeof item === "object" ? Object.fromEntries(Object.keys(item).sort().map(key => [key, sorted(item[key])])) : item;
        return JSON.stringify(sorted(value));
    }

    function conditionIdentity(constraint) {
        return stableJson({schemaVersion:constraint.schemaVersion,version:constraint.version,vocabularyVersion:constraint.vocabularyVersion,
            actorAll:constraint.actorAll.map(row=>`${row.partGroup}\n${row.kind}\n${row.value}`).sort(),
            environmentAll:constraint.environmentAll.map(row=>`${row.partGroup}\n${row.kind}\n${row.value}`).sort()});
    }

    async function matchSearchDetails() {
        if (!state.detailSearchScope || !canMatchDetails() || state.matching || !draftScopeConfirmed()) return;
        let constraint;
        try {constraint=detailConstraint();} catch(error){return empty(ui["detail-match-result"],error.message);}
        const search=state.projectSearch, project=state.project, profile=ui["detail-profile"].value;
        clearDetailMatch();clearSearchDetailEvidence();
        const controller=new AbortController(), revision=state.matchRevision;
        state.matchController=controller;state.matching=true;updateDetailQueryButton();
        try {
            const report=await request("/api/match-search-details",{},controller.signal,{project,searchId:search.searchId,searchSha256:search.searchSha256,profile,constraint});
            if(revision!==state.matchRevision || state.matchController!==controller || project!==state.project || state.projectSearch!==search || !state.detailSearchScope || !currentSearchDetailScope() || profile!==ui["detail-profile"].value)return;
            const {project:unusedProject,searchSha256:unusedDigest,...original}=search;
            if(report.schemaVersion!=="search-detail-query-v1" || report.project!==project || report.searchSha256!==search.searchSha256
                || report.refinementProfile!==profile || stableJson(report.search)!==stableJson(original)
                || conditionIdentity(JSON.parse(report.constraintJson))!==conditionIdentity(constraint)
                || !Array.isArray(report.matches) || report.matches.length!==search.candidates.length
                || !/^[a-f0-9]{64}$/.test(report.snapshotId) || report.matches.some((row,index)=>{
                    const expected=search.candidates[index];
                    return row.rank!==expected.rank || row.runId!==expected.runId || row.candidateId!==expected.candidateId || row.eventId!==expected.eventId
                        || !["full","partial","no_match","unverified"].includes(row.status)
                        || (expected.eventId===null ? row.status!=="unverified" || row.match!==null || row.availability!=="transcript_only"
                            : row.availability!=="visual_event" || !row.match || row.match.runId!==row.runId || row.match.eventId!==row.eventId || row.match.refinementProfile!==profile || row.match.constraintJson!==report.constraintJson || row.match.result?.status!==row.status || !Array.isArray(row.match.result.matches));
                }))throw new Error("条件依据与原搜索、候选或条件版本不一致，请重新核对。");
            state.searchDetail=report;
            const count=report.counts;
            ui["search-detail-summary"].textContent=`已核对原排名 ${report.matches.length} 个候选：全部满足 ${count.full}，部分满足 ${count.partial}，尚未验证 ${count.unverified}，有证据不符 ${count.no_match}。原顺序与分数保留；关闭窗口可在候选旁看依据。`;
            ui["download-search-details"].disabled=false;
            empty(ui["detail-match-result"],"条件状态和依据已显示在原搜索候选旁；缺资料仍需回看原片。");
            renderCandidates();
        } catch(error){if(error.name!=="AbortError" && revision===state.matchRevision)empty(ui["detail-match-result"],error.message);}
        finally{if(revision===state.matchRevision){state.matching=false;updateDetailQueryButton();}}
    }

    function appendSearchConditionProof(card,row) {
        const report=state.searchDetail;
        if(!report || report.searchSha256!==state.projectSearch?.searchSha256 || report.refinementProfile!==ui["detail-profile"].value)return;
        const match=report.matches.find(item=>item.runId===row.runId && item.candidateId===row.candidateId);
        if(!match)return;
        const labels={full:"条件全部满足",partial:"条件部分满足",unverified:"尚未验证",no_match:"有证据不符"};
        const details=element("details","candidate-condition-proof"), list=element("ul");
        details.dataset.status=match.status;
        details.append(element("summary",match.status==="full"?"accent":"warning",`${labels[match.status]} · 条件依据（精分析 ${report.refinementProfile}）`));
        const query=JSON.parse(report.constraintJson);
        list.append(element("li","","只核对以下条件，原搜索的其他要求仍需回看。"));
        list.append(element("li","",`核对条件：${[...query.actorAll,...query.environmentAll].map(conditionLabel).join("；")}`));
        if(match.availability==="transcript_only")list.append(element("li","","该候选来自语音，缺少可核对的视觉主体，尚未验证。"));
        else if(!match.match.result.matches.length)list.append(element("li","","该准确版本缺少足够的主体细节；不代表原片没有。"));
        for(const actor of match.match?.result.matches || []){
            list.append(element("li","","同一镜头内的一个主体："));
            for(const [key,label] of [["satisfied","有支持"],["uncertain","不确定"],["opposed","有相反证据"]])for(const support of actor[key])list.append(element("li","",`${label} · ${conditionLabel(support.condition)} · ${support.evidenceIds.length} 张画面`));
            for(const missing of actor.missing)list.append(element("li","",`缺少支持 · ${conditionLabel(missing)}`));
            list.append(element("li","",`共同支持画面 ${actor.sharedEvidenceIds.length} 张`));
        }
        details.append(list);card.append(details);
    }

    async function matchProjectDetails(offset = 0, snapshot = null) {
        if (!state.detailProjectScope || !canMatchDetails() || state.matching || !draftScopeConfirmed()) return;
        let constraint;
        try { constraint = detailConstraint(); } catch (error) { return empty(ui["detail-match-result"], error.message); }
        const project=state.project, runs=[...state.searchRuns].sort(), profile=ui["detail-profile"].value, filter=ui["project-detail-filter"].value;
        clearDetailMatch();
        const controller=new AbortController(), revision=state.matchRevision;
        state.matchController=controller;state.matching=true;updateDetailQueryButton();
        ui["project-detail-filter"].disabled=true;
        try {
            const report=await request("/api/match-project-details",{},controller.signal,{project,runs,profile,constraint,limit:20,offset,status:filter,snapshot});
            if (revision!==state.matchRevision || state.matchController!==controller || project!==state.project || runs.join("\n")!==[...state.searchRuns].sort().join("\n") || !state.detailProjectScope) return;
            if(report.schemaVersion!=="project-detail-query-v1" || report.project!==project || report.refinementProfile!==profile || report.status!==filter || report.offset!==offset || report.sources.map(row=>row.runId).sort().join("\n")!==runs.join("\n") || !/^[a-f0-9]{64}$/.test(report.snapshotId) || (snapshot && report.snapshotId!==snapshot) || !Array.isArray(report.results)) throw new Error("结果与当前录像、条件版本或页面身份不一致，请重新核对。");
            const labels={full:"条件全部满足",partial:"条件部分满足",unverified:"尚未验证",no_match:"有证据不符"};
            state.projectDetail=report;
            ui["project-detail-summary"].textContent=`已核对 ${report.sources.length} 段录像、${report.totalEvents} 个事件：全部满足 ${report.counts.full}，部分满足 ${report.counts.partial}，尚未验证 ${report.counts.unverified}，有证据不符 ${report.counts.no_match}。本筛选共 ${report.totalSelected} 项，按素材与原片时间显示。`;
            ui["detail-match-result"].replaceChildren();
            if(!report.results.length) empty(ui["detail-match-result"],"当前筛选没有条目；请结合上方尚未验证数量判断，缺资料不等于原片没有。");
            for(const row of report.results){
                const section=element("section","detail-match-actor project-detail-row");
                section.append(element("h3","",`${row.sourceName} · ${timecode(row.startUs)}–${timecode(row.endUs)}`),element("p",row.match.result.status==="full"?"accent":"warning",labels[row.match.result.status]),element("p","small",row.displayFacts.join("；")));
                const proof=element("details"), list=element("ul");proof.append(element("summary","","查看条件依据"));
                for(const match of row.match.result.matches){
                    list.append(element("li","small","同一镜头内的一个主体："));
                    for(const [key,label] of [["satisfied","有支持"],["uncertain","不确定"],["opposed","有相反证据"]])for(const support of match[key])list.append(element("li","small",`${label} · ${conditionLabel(support.condition)} · ${support.evidenceIds.length} 张画面`));
                    for(const condition of match.missing)list.append(element("li","muted small",`缺少支持 · ${conditionLabel(condition)}`));
                    list.append(element("li","small",`共同支持画面 ${match.sharedEvidenceIds.length} 张`));
                }
                if(!row.match.result.matches.length)list.append(element("li","muted small","所选版本没有足够的已保存主体结构，尚未验证。"));
                proof.append(list);section.append(proof);
                const open=element("button","text-button","回看此片段");open.type="button";open.addEventListener("click",()=>void openProjectDetail(row));section.append(open);ui["detail-match-result"].append(section);
            }
            ui["project-detail-previous"].disabled=offset===0;
            ui["project-detail-next"].disabled=!report.hasNext;
            ui["project-detail-download"].disabled=false;
        } catch(error){if(error.name!=="AbortError" && revision===state.matchRevision)empty(ui["detail-match-result"],error.message);}
        finally{if(revision===state.matchRevision){state.matching=false;ui["project-detail-filter"].disabled=false;updateDetailQueryButton();}}
    }

    async function openProjectDetail(row) {
        const report=state.projectDetail, project=state.project;
        if(!report || !report.results.includes(row) || state.busy) return;
        ui["detail-query-dialog"].close();
        if(state.run!==row.runId){ui["run-select"].value=row.runId;await switchRun(row.runId,true);}
        if(state.project!==project || state.run!==row.runId) return;
        const event=state.view?.timeline.find(item=>item.eventId===row.eventId && item.startUs===row.startUs && item.endUs===row.endUs);
        if(!event)return notice("原片事件已变化，请重新读取核对。");
        await previewClip("event",event);
    }

    async function matchDetailQuery() {
        if (!canMatchDetails() || state.matching || !draftScopeConfirmed()) return;
        let constraint;
        try { constraint = detailConstraint(); } catch (error) { return empty(ui["detail-match-result"], error.message); }
        clearDetailMatch();
        const controller = new AbortController();
        state.matchController = controller;
        const revision = state.matchRevision;
        const eventId = state.active.row.eventId;
        const profile = ui["detail-profile"].value;
        const digest = state.active.row.detailRefinement?.requestHash;
        const detailDigest = state.active.row.detailRefinement?.payloadHash || null;
        state.matching = true;
        updateDetailQueryButton();
        try {
            const report = await request("/api/match-details", {}, controller.signal, {
                project: state.project, run: state.run, event: eventId, profile, constraint,
            });
            if (revision !== state.matchRevision || state.matchController !== controller) return;
            if (report.runId !== state.run || report.eventId !== eventId || report.refinementProfile !== profile
                || report.refinementRequestHash !== digest || !["full", "partial", "no_match", "unverified"].includes(report.result?.status)
                || report.refinementPayloadHash !== detailDigest
                || !Array.isArray(report.result.matches)) throw new Error("条件结果与当前片段的身份不一致，请刷新后重试。");
            renderDetailMatch(report);
        } catch (error) {
            if (error.name !== "AbortError" && revision === state.matchRevision) empty(ui["detail-match-result"], error.message);
        } finally {
            if (revision === state.matchRevision) { state.matching = false; updateDetailQueryButton(); }
        }
    }

    function money(value) {
        return typeof value === "string" && /^\d+(?:\.\d+)?$/.test(value) ? `¥${value}` : "未知";
    }

    function clearDetailCosts() {
        state.costController?.abort();
        state.costController = null;
        state.costRevision += 1;
        if (ui["detail-cost-dialog"].open) ui["detail-cost-dialog"].close();
        ui["detail-cost-content"].replaceChildren();
    }

    function renderDetailCosts(history) {
        const container = ui["detail-cost-content"];
        container.replaceChildren();
        const summary = (title, data) => {
            const section = element("section", "detail-cost-summary");
            section.append(element("h3", "", title));
            section.append(element("p", "", `已知估价 ${money(data.knownEstimatedCostCny)} · ${data.attemptCount} 次尝试`));
            section.append(element("p", data.unknownCostCount ? "warning" : "muted small", `未知费用 ${data.unknownCostCount} 次 · 保留预留 ${money(data.unknownReservedCny)}`));
            section.append(element("p", "accent", `承诺金额 ${money(data.commitmentCny)}`));
            container.append(section);
        };
        summary("当前运行的精分析", history.summary);
        summary("本项目全部精分析（含其他运行）", history.sharedCommitment);
        container.append(element("p", "muted small", "这里只汇总精分析。基础分析与其他项目的费用不包含在内。"));
        if (!history.attempts.length) container.append(element("p", "muted", "当前运行尚无已登记的精分析尝试。"));
        if (history.attemptsTruncated) container.append(element("p", "warning small", `共 ${history.totalAttemptCount} 次尝试，仅展示 ${history.attempts.length} 条；上方金额已包含全部记录。`));
        const labels = { planned: "已计划，发送状态待核对", completed: "已完成", failed: "失败", cancelled: "已取消", recorded: "已登记历史" };
        for (const attempt of history.attempts) {
            const section = element("details", "detail-cost-attempt");
            section.append(element("summary", "", `${labels[attempt.status] || "状态待核对"} · 尝试 ${attempt.attemptNo} · 估价 ${money(attempt.estimatedCostCny)}`));
            section.append(element("p", "muted small", `预算 ${attempt.budgetId} · 原预留 ${money(attempt.reservationCny)}`));
            if (attempt.errorCode) section.append(element("p", "warning small", `错误 ${attempt.errorCode}`));
            if (attempt.settlementPending) section.append(element("p", "warning small", "已返回用量但账本尚未结算，继续保留未知费用预留。"));
            const metadata = attempt.metadata;
            if (metadata) {
                const usage = metadata.usage;
                section.append(element("p", "small", `模型 ${metadata.actualModel || "未知"} · 请求模型 ${metadata.requestedModel} · 修订 ${metadata.modelRevision || "未知"}`));
                section.append(element("p", "muted small", `提示词 ${metadata.promptVersion} · 计价版本 ${metadata.priceVersion || "未知"}`));
                section.append(element("p", "muted small", `输入 ${usage.inputTokens ?? "未知"} / 缓存 ${usage.cachedInputTokens ?? "未知"} / 输出 ${usage.outputTokens ?? "未知"} tokens`));
                section.append(element("p", "muted small", `耗时 ${metadata.elapsedMs === null ? "未知" : `${metadata.elapsedMs} ms`} · 请求时间 ${metadata.requestedAtUtc || "未记录"}`));
                if (metadata.requestId) section.append(element("p", "muted small", `请求编号 ${metadata.requestId}`));
            } else section.append(element("p", "muted small", "历史记录未包含完整调用信息，缺失字段保持未知。"));
            section.append(element("p", "muted small", `请求指纹 ${attempt.requestHash}`));
            container.append(section);
        }
    }

    async function openDetailCosts() {
        if (!state.run || state.busy) return;
        clearDetailCosts();
        const controller = new AbortController();
        state.costController = controller;
        const revision = state.costRevision;
        const run = state.run;
        empty(ui["detail-cost-content"], "正在读取已有精分析记录…");
        ui["detail-cost-dialog"].showModal();
        try {
            const history = await request("/api/detail-cost-history", { project: state.project, run }, controller.signal);
            if (revision !== state.costRevision || state.costController !== controller) return;
            if (history.schemaVersion !== "detail-refinement-cost-history-v1" || history.runId !== run
                || !history.summary || !history.sharedCommitment || !Array.isArray(history.attempts)) throw new Error("费用记录与当前运行不一致。");
            renderDetailCosts(history);
        } catch (error) {
            if (error.name !== "AbortError" && revision === state.costRevision) empty(ui["detail-cost-content"], error.message);
        }
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
                    detailRefinement: current.detailRefinement,
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
            const clip = JSON.parse(JSON.stringify(row));
            delete clip.detailRefinement;
            state.selections.push({
                key, kind, clip,
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
            const clip = JSON.parse(JSON.stringify(validated.clip));
            delete clip.detailRefinement;
            return {
                ...clip,
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

    function currentDiagnostics() {
        if (state.searchRuns.length) return null;
        const view = state.view;
        const doc = view?.retrievalDiagnostics;
        if (state.busy || view?.runStatus !== "completed" || !doc
            || doc.schemaVersion !== "retrieval-diagnostics-v2"
            || doc.project !== state.project || doc.runId !== state.run
            || doc.mediaId !== view.media.id || doc.mediaSha256 !== view.media.sha256
            || doc.durationUs !== view.media.durationUs || doc.configHash !== view.configHash
            || doc.retrievalVersion !== view.retrievalVersion
            || !doc.query.trim() || doc.query !== view.query || doc.query !== ui.query.value.trim()
            || doc.mode !== view.mode || doc.mode !== ui.mode.value
            || doc.requestedTopK !== Number(ui.top.value)
            || !Array.isArray(doc.slots) || doc.slots.length !== 10) return null;
        for (const [index, slot] of doc.slots.entries()) {
            const row = view.candidates[index];
            if (slot.position !== index + 1) return null;
            if (!row) {
                if (slot.status !== "missing" || slot.candidate !== null) return null;
            } else if (!validInterval(row) || !slot.candidate
                || !["candidate", "known_duplicate"].includes(slot.status)
                || ["rank", "candidateId", "eventId", "startUs", "endUs"].some((key) => slot.candidate[key] !== row[key])
                || JSON.stringify(slot.candidate.evidenceIds) !== JSON.stringify(row.evidenceIds)) return null;
        }
        return doc;
    }

    function updateDiagnosticsButton() {
        ui["open-retrieval-diagnostics"].disabled = !currentDiagnostics();
    }

    function clearRetrievalDiagnostics() {
        state.diagnosticsContext = null;
        if (ui["retrieval-diagnostics-dialog"].open) ui["retrieval-diagnostics-dialog"].close();
        ui["retrieval-diagnostics-slots"].replaceChildren();
        ui["retrieval-diagnostics-summary"].textContent = "";
        ui["download-retrieval-diagnostics"].disabled = true;
    }

    function diagnosticsStillCurrent(context) {
        return context && context === state.diagnosticsContext && context.view === state.view
            && context.revision === state.revision && context.doc === currentDiagnostics();
    }

    function evidenceSummaryText(summary) {
        if (!summary || summary.status === "unavailable") return "登记证据不完整，无法列出画面对照。";
        if (summary.status === "registered_audio_only") return "只登记了音频，没有登记画面；请核对原片和音频证据。";
        if (summary.status === "registered_single_frame") return "已登记 1 张画面，只有一个时刻；不能据此确认动作过程。";
        const count = summary.registeredImageCount;
        const times = summary.distinctImageSourceTimeCount;
        const seconds = Number.isFinite(summary.imageSpanUs) ? (summary.imageSpanUs / 1000000).toFixed(3) : "未知";
        const prefix = `已登记 ${count} 张画面，来自 ${times} 个时刻，跨 ${seconds} 秒。`;
        if (summary.status === "registered_same_instant") return `${prefix}这些画面属于同一时刻，无法对照动作变化。`;
        if (summary.status === "registered_repeated_content") return `${prefix}画面文件内容相同，不能作为动作变化依据。`;
        return `${prefix}多图不等于动作成立，请回看主体和镜头变化。`;
    }

    function openRetrievalDiagnostics() {
        const doc = currentDiagnostics();
        if (!doc) return notice("请先完成当前查询，再查看检索诊断。");
        clearRetrievalDiagnostics();
        const context = { doc, view: state.view, revision: state.revision };
        state.diagnosticsContext = context;
        const mode = { lexical: "词法检索", semantic: "语义检索", hybrid: "混合检索" }[doc.mode] || doc.mode;
        const summary = [`“${doc.query}” · ${mode} · 返回 ${doc.returnedCount} 条，前十位缺 ${doc.missingCount} 位，已知重复 ${doc.knownDuplicateCount} 位。`];
        if (doc.limitedByRequestedTopK) summary.push(`本次只请求 ${doc.requestedTopK} 条，缺位包含条数限制。请设置至少 10 条后重新检索，再检查召回。`);
        if (doc.abstentionReason) summary.push(`检索保留的未返回原因：${doc.abstentionReason}`);
        ui["retrieval-diagnostics-summary"].textContent = summary.join(" ");
        for (const slot of doc.slots) {
            const item = element("li", `diagnostics-slot ${slot.status}`);
            item.append(element("h3", "", `第 ${slot.position} 位 · ${slot.status === "missing" ? "缺位" : slot.status === "known_duplicate" ? `已知重复第 ${slot.duplicateOfPosition} 位` : "待人工核对"}`));
            if (slot.candidate) {
                const row = context.view.candidates[slot.position - 1];
                item.append(element("p", "accent small", `原排名 #${row.rank} · ${intervalLabel(row)}`));
                item.append(element("p", "diagnostics-facts", facts(row).join(" ") || "没有保存可观察描述。"));
                item.append(element("p", "muted small diagnostics-evidence", evidenceSummaryText(slot.candidate.evidenceSummary)));
                const preview = element("button", "button secondary compact diagnostics-preview", "回看这个片段");
                preview.type = "button";
                preview.addEventListener("click", () => {
                    if (!diagnosticsStillCurrent(context)) {
                        clearRetrievalDiagnostics();
                        return notice("查询已经变化，请重新打开当前诊断。");
                    }
                    clearRetrievalDiagnostics();
                    void previewClip("candidate", row);
                });
                item.append(preview);
            } else item.append(element("p", "muted small", "这个位置没有候选。"));
            ui["retrieval-diagnostics-slots"].append(item);
        }
        ui["download-retrieval-diagnostics"].disabled = false;
        ui["retrieval-diagnostics-dialog"].showModal();
    }

    function downloadRetrievalDiagnostics() {
        const context = state.diagnosticsContext;
        if (!diagnosticsStillCurrent(context)) {
            clearRetrievalDiagnostics();
            return notice("查询已经变化，请重新打开当前诊断。");
        }
        const blob = new Blob([`${JSON.stringify(context.doc, null, 2)}\n`], { type: "application/json;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = element("a");
        link.href = url;
        link.download = `retrieval-diagnostics-${state.run.replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 40)}.json`;
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        notice("已下载本次检索诊断，人工评分仍为空。", true);
    }

    function setBusy(busy, searching = false) {
        state.busy = busy;
        if (busy) clearRetrievalDiagnostics();
        updateDiagnosticsButton();
        const completed = state.searchRuns.length > 0 || state.view?.runStatus === "completed";
        ui["search-button"].disabled = busy || !completed;
        ui["search-button"].textContent = busy ? (searching ? "正在本地检索…" : "正在读取…") : "查找片段 ↗";
        ui["refresh-view"].disabled = busy || !state.run;
        for (const id of ["query", "mode", "top"]) ui[id].disabled = !completed;
        ui["timeline-filter"].disabled = !state.view;
        ui["tag-filter"].disabled = !state.view;
        ui["detail-profile"].disabled = busy || !state.view;
        ui["open-detail-costs"].disabled = busy || !state.run;
        updateDetailQueryButton();
        renderSelections();
        updateSearchScope();
        if (state.projectSearch) renderCandidates();
    }

    function resetView() {
        clearTasks();
        ui["open-tasks"].disabled = !state.project;
        clearRetrievalDiagnostics();
        invalidateDetailDraft(true);
        clearDetailCosts();
        clearDetailMatch();
        if (ui["detail-query-dialog"].open) ui["detail-query-dialog"].close();
        state.view = null;
        state.active = null;
        renderActorDetails();
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
        ui["play-context"].disabled = true;
        ui["playback-range"].textContent = "";
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

    async function switchRun(run, keepProjectSearch = false) {
        if (!keepProjectSearch) clearProjectSearch();
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
        if (run) return await inspect("");
        return false;
    }

    async function loadRuns(project, preferredRun = "") {
        clearProjectSearch();
        state.searchRuns = [];
        if (ui["search-sources-dialog"].open) ui["search-sources-dialog"].close();
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

    async function inspect(query, preserveActive = false) {
        if (!state.project || !state.run) return;
        state.inspectController?.abort();
        invalidateDetailDraft(true);
        clearDetailMatch();
        const previousActive = preserveActive ? state.active : null;
        const controller = new AbortController();
        state.inspectController = controller;
        const revision = state.revision;
        const top = Number(ui.top.value);
        if (!Number.isInteger(top) || top < 1 || top > 100) return notice("候选条数需要是 1 到 100 的整数。");
        notice("");
        setBusy(true, Boolean(query));
        try {
            const payload = await request("/api/inspect", {
                project: state.project, run: state.run, query, mode: ui.mode.value, top, detailProfile: ui["detail-profile"].value,
            }, controller.signal);
            if (controller.signal.aborted || state.revision !== revision || state.inspectController !== controller) return;
            if (payload.runId !== state.run || !Array.isArray(payload.timeline) || !Array.isArray(payload.candidates)
                || !payload.media || typeof payload.media.id !== "string"
                || !Number.isSafeInteger(payload.media.durationUs) || payload.media.durationUs <= 0) throw new Error("分析视图的素材或运行身份不一致。");
            state.view = jointRowsForView(payload);
            const activeRow = previousActive && (previousActive.kind === "candidate" ? state.view.candidates : state.view.timeline)
                .find((row) => selectionKey(row) === selectionKey(previousActive.row));
            state.active = activeRow ? { kind: previousActive.kind, row: activeRow } : null;
            state.playbackEndUs = null;
            renderView();
            return true;
        } catch (error) {
            if (error.name === "AbortError" || state.revision !== revision || state.inspectController !== controller) return;
            notice(error.message);
            if (query) {
                if (state.view) state.view = { ...state.view, candidates: [], retrievalDiagnostics: null };
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
        return false;
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
        const joint = state.projectSearch;
        if (!view && !joint) return;
        const rows = joint ? joint.candidates : view.candidates;
        const scrollTop = ui["candidate-list"].scrollTop;
        ui["candidate-count"].textContent = rows.length;
        ui["candidate-list"].replaceChildren();
        ui["search-context"].textContent = joint ? `“${joint.query}” · ${joint.sources.length} 段录像共同排名 · 分数是排序信号`
            : view.query ? `“${view.query}” · ${view.mode} · 分数是排序信号` : "输入你需要的动作、玩法或画面。";
        if (!rows.length) {
            if (joint) return empty(ui["candidate-list"], "选中的录像中没有匹配候选，可以换一种描述。");
            empty(ui["candidate-list"], view.runStatus !== "completed" ? "分析尚未完成，可以先查看已保存时间轴。"
                : view.query ? (view.abstentionReason ? `没有合适候选（${view.abstentionReason}）。可以换一种描述。` : "没有匹配候选。可以换一种描述。") : "输入查询后查找片段，或直接从时间轴选片。");
            return;
        }
        for (const row of rows) {
            const card = element("article", `candidate-card${state.active?.kind === "candidate" && state.active.row.candidateId === row.candidateId ? " active" : ""}`);
            const top = element("div", "candidate-card-top");
            const preview = element("button", "clip-preview", intervalLabel(row));
            preview.type = "button";
            preview.disabled = joint ? state.busy || !validInterval(row, joint.sources.find((source) => source.runId === row.runId)?.durationUs) : !validInterval(row) || !state.sourceUrl;
            preview.setAttribute("aria-label", `播放候选 ${row.rank}，${intervalLabel(row)}`);
            preview.addEventListener("click", () => joint ? void openJointCandidate(row) : void previewClip("candidate", row));
            let selection;
            if (joint) {
                const selected = state.run === row.runId && state.selections.some((entry) => entry.key === selectionKey(row));
                selection = element("button", `select-clip${selected ? " selected" : ""}`, selected ? "✓" : "+");
                selection.type = "button";
                selection.setAttribute("aria-label", selected ? "从来源录像的片段篮移除" : "加入来源录像的片段篮");
                selection.setAttribute("aria-pressed", String(selected));
                selection.disabled = state.busy;
                selection.addEventListener("click", () => { void openJointCandidate(row, true); });
            } else selection = selectionButton("candidate", row);
            top.append(element("span", "rank", row.rank), preview, selection);
            const copy = element("p", "candidate-facts", facts(row).join("；"));
            const meta = element("div", "candidate-meta");
            meta.append(element("span", "", `${Array.isArray(row.evidenceIds) ? row.evidenceIds.length : 0} 份证据`), element("span", "", `${row.scoreKind || "score"} · ${typeof row.score === "number" && Number.isFinite(row.score) ? row.score.toFixed(4) : "—"}`));
            card.append(top, copy, meta);
            if (joint) {
                card.dataset.run = row.runId;
                card.insertBefore(element("p", "candidate-source", `来源 · ${row.sourceName}`), copy);
            }
            appendUncertainty(card, row);
            if (joint) appendSearchConditionProof(card,row);
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

    async function previewClip(kind, row, withContext = false) {
        if (!validInterval(row) || !state.sourceUrl) return notice("这个区间目前无法播放，请刷新素材。");
        invalidateDetailDraft(true);
        clearDetailMatch();
        state.active = { kind, row };
        const startUs = withContext ? Math.max(0, row.startUs - 1000000) : row.startUs;
        const endUs = withContext ? Math.min(state.view.media.durationUs, row.endUs + 1000000) : row.endUs;
        state.playbackEndUs = endUs;
        seek(startUs);
        updateActive();
        ui["playback-range"].textContent = `${withContext ? "前后文" : "原区间"} · ${timecode(startUs)} – ${timecode(endUs)}`;
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
        ui["play-context"].disabled = !validInterval(row) || !state.sourceUrl;
        ui["playback-range"].textContent = row ? `原区间 · ${intervalLabel(row)}` : "";
        updateActiveButton();
        updateDetailQueryButton();
    }

    function renderEvidence() {
        renderActorDetails();
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

    function appendDescriptionReview(container, shotId, actorId) {
        const row = state.active?.row;
        const refinement = row?.detailRefinement;
        const feedback = refinement?.descriptionFeedback;
        const marker = element("div", "detail-description-review");
        if (!feedback) {
            marker.append(element("p", "muted small", "描述待人工核对 · 尚无已登记反馈"));
            container.append(marker);
            return;
        }
        const targets = new Set((refinement.detail?.shots || []).flatMap((shot) => shot.actors.map((actor) => `${shot.shotId}/${actor.actorId}`)));
        const seen = new Set();
        const valid = feedback.schemaVersion === "actor-description-feedback-inspection-v1"
            && feedback.scope === "actor-description" && feedback.phase0QualityGate === null
            && feedback.runId === state.run && feedback.eventId === row.eventId
            && feedback.requestHash === refinement.requestHash
            && feedback.refinementPayloadHash === refinement.payloadHash
            && typeof feedback.pilotReportSha256 === "string" && /^[0-9a-f]{64}$/.test(feedback.pilotReportSha256)
            && Array.isArray(feedback.reviews)
            && feedback.status === (feedback.reviews.length ? "reviewed" : "unreviewed")
            && feedback.reviews.every((review) => {
                if (!review || typeof review !== "object") return false;
                const target = `${review.shotId}/${review.actorId}`;
                if (!targets.has(target) || seen.has(target) || review.scope !== "actor-description"
                    || review.source !== "direct-project-user-feedback" || !["accepted", "rejected"].includes(review.verdict)
                    || typeof review.statement !== "string" || !review.statement.trim()
                    || typeof review.recordedOn !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(review.recordedOn)) return false;
                seen.add(target);
                return true;
            });
        if (!valid) {
            marker.append(element("p", "warning small", "人工反馈与当前结果不一致，未应用；描述仍待核对。"));
        } else {
            const review = feedback.reviews.find((item) => item.shotId === shotId && item.actorId === actorId);
            if (review) {
                marker.append(element("p", review.verdict === "accepted" ? "accent small" : "warning small",
                    review.verdict === "accepted" ? "用户已确认此描述" : "用户已指出此描述有误"));
                marker.append(element("p", "small", review.statement));
                marker.append(element("p", "muted small", `用户反馈 · ${review.recordedOn} · 仅针对描述，属性和检索质量仍须独立核对。`));
            } else marker.append(element("p", "muted small", "此描述尚未人工核对；不从其他条目推断通过。"));
        }
        container.append(marker);
    }

    function renderActorDetails() {
        const row = state.active?.row;
        const refinement = row?.detailRefinement;
        const details = refinement?.detail;
        ui["detail-status"].hidden = !row;
        ui["actor-details"].hidden = true;
        ui["actor-details"].open = false;
        ui["actor-detail-list"].replaceChildren();
        if (!row) return;
        const unavailable = {
            missing: "主体详情未验证：尚无已保存的精分析结果。",
            unsupported: "主体详情未验证：此片段缺少可用的视觉事件证据或版本身份。",
            run_incomplete: "主体详情未验证：分析运行尚未完成。",
        };
        ui["detail-status"].textContent = unavailable[refinement?.availability]
            || "主体详情未验证：尚无可用结构。";
        if (refinement?.availability !== "reused" || refinement.status !== "unverified"
            || !details || details.runId !== state.run || details.eventId !== row.eventId
            || details.sourceRange?.startUs !== row.startUs || details.sourceRange?.endUs !== row.endUs
            || !Array.isArray(details.shots)) return;
        ui["detail-status"].textContent = "已读取保存的主体详情；复合条件匹配未验证。";
        ui["actor-details"].hidden = false;
        const kinds = {
            hair_color: "发色", clothing_color: "衣着颜色", clothing_shape: "衣着形状",
            held_shape: "持有物形状", held_class: "持有物类别", action: "动作",
            effect: "可见效果", environment: "环境",
        };
        const values = {
            white: "白色", black: "黑色", red: "红色", blue: "蓝色", brown: "棕色",
            orange: "橙色", gray: "灰色", green: "绿色", yellow: "黄色", purple: "紫色",
            light: "浅色", dark: "深色", upper_garment: "上装", coat: "外套", scarf: "围巾",
            shorts: "短裤", trousers: "长裤", armor: "盔甲", gloves: "手套",
            flat_object: "扁平物体", blue_flat_object: "蓝色扁平物体", long_rod: "长杆",
            curved_object: "弯曲物体", weapon: "武器", staff: "权杖", tool: "工具",
            look_up: "抬头", move: "移动", run: "奔跑", jump: "跳跃", raise_item: "举起持有物",
            shoot: "射击", light_arc: "光弧", light_ring: "光环", projectile: "投射物",
            water: "水面", stone_platform: "石块平台", sandy_ground: "沙地",
            indoors: "室内", outdoors: "室外",
        };
        const evidence = new Map((state.view.evidence || []).map((item) => [item.id, item]));
        const addAttributes = (container, attributes, entityUncertain = false) => {
            for (const attribute of attributes) {
                const pending = entityUncertain || attribute.status !== "observed";
                const status = entityUncertain ? "实体未确定 · 模型观察待核对" : pending ? "待核对" : "已观察";
                const label = `${status} · ${kinds[attribute.kind] || attribute.kind}：${values[attribute.value] || attribute.value}`;
                const item = element("li", pending ? "warning" : "", label);
                const frames = (attribute.evidenceIds || []).map((id) => evidence.get(id))
                    .filter(Boolean).map((frame) => timecode(frame.startUs));
                item.append(element("span", "muted detail-support", `支持源帧 · ${frames.join(" / ")}`));
                container.append(item);
            }
        };
        const scene = details.temporalScene;
        if (scene?.schemaVersion === "temporal-scene-v1") {
            const proof = element("details", "detail-temporal");
            proof.append(element("summary", "", "角色、物品和画面变化的判断依据（待核对）"));
            proof.append(element("p", "muted small", "以下为模型的视觉判断。引用和时间已校验，识别是否正确仍需回看画面；遮挡区域不会自动补出人物特征。"));
            const entityKinds = { actor: "角色", object: "物品", unknown: "无法判断的实体" };
            const visibility = { visible: "可见", partially_occluded: "部分被遮挡", occluded: "被完全遮挡", unknown: "可见性无法判断" };
            const basis = { character_structure: "可见角色结构", independent_agency: "独立行为", carried_object: "可见被持有的物品", rigid_object: "物体结构", insufficient_evidence: "依据不足", visual_continuity: "连续画面依据", scene_change: "场景变化依据" };
            const names = new Map(scene.entities.map((entity, index) => [entity.entityId, `${entityKinds[entity.classification.kind]} ${index + 1}`]));
            for (const entity of scene.entities) {
                const section = element("section", "detail-shot");
                const classification = entity.classification;
                section.append(element("h4", "", `${names.get(entity.entityId)} · ${classification.status === "observed" ? "模型判断" : "尚未确定"}`));
                section.append(element("p", "", cleanObservationText(entity.description)));
                section.append(element("p", "small", `${basis[classification.basis]}：${cleanObservationText(classification.reason)}`));
                appendSupportFrames(section, classification.evidenceIds, "分类依据");
                const observations = element("ul");
                for (const observation of entity.observations) {
                    const frame = evidence.get(observation.evidenceId);
                    const item = element("li", "small", `${frame ? timecode(frame.startUs) : "源帧"} · ${visibility[observation.visibility]} · ${cleanObservationText(observation.location)}`);
                    appendSupportFrames(item, [observation.evidenceId], "回看");
                    observations.append(item);
                }
                section.append(observations);
                for (const part of entity.parts) {
                    const attributes = element("ul");
                    addAttributes(attributes, part.attributes, classification.status !== "observed");
                    section.append(attributes);
                }
                proof.append(section);
            }
            for (const relation of scene.owners) {
                const section = element("section", "detail-shot");
                section.append(element("h4", "", `${names.get(relation.actorId)} 与 ${names.get(relation.objectId)} · ${relation.status === "observed" ? "模型判断有持有关系" : "持有关系未确定"}`));
                section.append(element("p", "small", cleanObservationText(relation.reason)));
                appendSupportFrames(section, relation.evidenceIds, "关系依据");
                proof.append(section);
            }
            const transitionLabels = { continuous: "画面连续", cut: "发生切镜", unknown: "连续性未确定" };
            for (const transition of scene.transitions) {
                const section = element("section", "detail-shot");
                const before = evidence.get(transition.beforeId);
                const after = evidence.get(transition.afterId);
                section.append(element("h4", "", `${before ? timecode(before.startUs) : "前一帧"} → ${after ? timecode(after.startUs) : "后一帧"} · ${transitionLabels[transition.state]}`));
                section.append(element("p", "small", `${basis[transition.basis]}：${cleanObservationText(transition.reason)}`));
                appendSupportFrames(section, [transition.beforeId, transition.afterId], "两侧画面");
                proof.append(section);
            }
            ui["actor-detail-list"].append(proof);
        }
        for (const [shotIndex, shot] of details.shots.entries()) {
            const section = element("section", "detail-shot");
            section.append(element("h4", "", `镜头 ${shotIndex + 1} · ${timecode(shot.sourceRange.startUs)} – ${timecode(shot.sourceRange.endUs)}`));
            for (const [actorIndex, actor] of shot.actors.entries()) {
                section.append(element("p", "", `主体 ${actorIndex + 1} · ${cleanObservationText(actor.description)}`));
                appendDescriptionReview(section, shot.shotId, actor.actorId);
                const parts = new Map();
                for (const attribute of actor.attributes) {
                    if (!parts.has(attribute.partId)) parts.set(attribute.partId, []);
                    parts.get(attribute.partId).push(attribute);
                }
                for (const [index, attributes] of [...parts.values()].entries()) {
                    section.append(element("p", "muted", `部件 ${index + 1}`));
                    const list = element("ul");
                    addAttributes(list, attributes);
                    section.append(list);
                }
                if (!actor.attributes.length) section.append(element("p", "muted", "此主体尚无可核对属性。"));
            }
            if (shot.environment.length) {
                section.append(element("p", "", "当前镜头环境"));
                const list = element("ul");
                addAttributes(list, shot.environment);
                section.append(list);
            }
            ui["actor-detail-list"].append(section);
        }
        if (!details.shots.length) ui["actor-detail-list"].append(element("p", "muted", "没有已确认的镜头和主体结构。"));
        for (const note of details.notes || []) ui["actor-detail-list"].append(element("p", "warning", `待核对 · ${cleanObservationText(note)}`));
        if (details.unassignedEvidenceIds?.length) ui["actor-detail-list"].append(element("p", "warning", "部分源帧尚未归属镜头，不能合并主体属性。"));
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
                ui["playback-range"].textContent = `转录区间 · ${timecode(row.startUs)} – ${timecode(row.endUs)}`;
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
    ui["run-select"].addEventListener("change", () => { void switchRun(ui["run-select"].value); });
    ui["open-search-sources"].addEventListener("click", openSearchSources);
    ui["close-search-sources"].addEventListener("click", () => ui["search-sources-dialog"].close());
    ui["apply-search-sources"].addEventListener("click", () => {
        const runs = [...ui["search-sources-list"].querySelectorAll("input:checked")].map((input) => input.value);
        if (!runs.length || runs.length > 100) return;
        clearProjectSearch();
        state.searchRuns = runs;
        ui["search-sources-dialog"].close();
        updateSearchScope();
        void inspect("");
    });
    ui["single-search-source"].addEventListener("click", () => {
        clearProjectSearch();
        state.searchRuns = [];
        updateSearchScope();
        void inspect("");
    });
    ui["download-project-search"].addEventListener("click", downloadProjectSearch);
    ui["detail-profile"].addEventListener("change", () => { clearSearchDetailEvidence();void inspect(state.projectSearch ? "" : state.view?.query || "", true); });
    ui["open-detail-query"].addEventListener("click", () => {
        state.detailSearchScope=false;
        state.detailProjectScope=false;
        if (!canMatchDetails()) return;
        clearDetailMatch();
        if (!ui["detail-conditions"].children.length) addDetailCondition();
        ui["detail-query-dialog"].showModal();
    });
    ui["open-project-detail-query"].addEventListener("click",()=>{
        if(!state.projectDetailAvailable || !state.searchRuns.length || state.busy)return;
        state.detailSearchScope=false;state.detailProjectScope=true;ui["project-detail-filter"].value="all";clearDetailMatch();
        if(!ui["detail-conditions"].children.length)addDetailCondition();
        ui["detail-query-dialog"].showModal();
    });
    ui["open-search-detail-query"].addEventListener("click",()=>{
        if(state.busy || !currentSearchDetailScope())return;
        state.detailSearchScope=true;state.detailProjectScope=false;clearDetailMatch();
        if(!ui["detail-conditions"].children.length)addDetailCondition();
        ui["detail-query-dialog"].showModal();
    });
    ui["download-search-details"].addEventListener("click",()=>{
        if(!state.searchDetail || state.matching)return;
        const url=URL.createObjectURL(new Blob([JSON.stringify(state.searchDetail,null,2)+"\n"],{type:"application/json;charset=utf-8"})),link=element("a");
        link.href=url;link.download=`search-conditions-${state.searchDetail.search.searchId}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    });
    ui["project-detail-filter"].addEventListener("change",()=>void matchProjectDetails(0,state.projectDetail?.snapshotId || null));
    ui["project-detail-previous"].addEventListener("click",()=>{const report=state.projectDetail;if(report)void matchProjectDetails(Math.max(0,report.offset-report.limit),report.snapshotId);});
    ui["project-detail-next"].addEventListener("click",()=>{const report=state.projectDetail;if(report?.hasNext)void matchProjectDetails(report.offset+report.limit,report.snapshotId);});
    ui["project-detail-download"].addEventListener("click",()=>{
        if(!state.projectDetail || state.matching)return;
        const url=URL.createObjectURL(new Blob([JSON.stringify(state.projectDetail,null,2)+"\n"],{type:"application/json;charset=utf-8"})),link=element("a");
        link.href=url;link.download=`compound-results-page-${state.projectDetail.offset+1}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    });
    ui["close-detail-query"].addEventListener("click", () => ui["detail-query-dialog"].close());
    ui["detail-query-dialog"].addEventListener("close", () => { state.detailSearchScope=false;state.detailProjectScope=false;invalidateDetailDraft(true); clearDetailMatch(); });
    ui["detail-draft-text"].addEventListener("input", () => { if(state.detailSearchScope)clearSearchDetailEvidence();invalidateDetailDraft(); clearDetailMatch(); });
    ui["generate-detail-draft"].addEventListener("click", () => { void generateDetailDraft(); });
    ui["detail-draft-subset"].addEventListener("change", clearDetailMatch);
    ui["add-detail-condition"].addEventListener("click", () => addDetailCondition());
    ui["detail-query-form"].addEventListener("submit", (event) => { event.preventDefault(); void (state.detailSearchScope ? matchSearchDetails() : state.detailProjectScope ? matchProjectDetails() : matchDetailQuery()); });
    ui["open-detail-costs"].addEventListener("click", () => { void openDetailCosts(); });
    ui["open-tasks"].addEventListener("click", () => { void loadTasks(); });
    ui["open-preparation"].addEventListener("click", () => {
        if (!ui["preparation-project"].value) {
            let saved = "";
            try { saved = localStorage.getItem("gamingcreator:preparation-project") || ""; } catch { storageWarning(); }
            ui["preparation-project"].value = saved.length <= 8192 ? saved || state.project || "artifacts/my-recordings" : state.project || "artifacts/my-recordings";
        }
        ui["preparation-dialog"].showModal();
        void readPreparationBatches();
    });
    ui["close-preparation"].addEventListener("click", () => ui["preparation-dialog"].close());
    ui["preparation-dialog"].addEventListener("close", () => { stopPreparationObservation(); state.preparationSubmitting = false; });
    ui["preparation-project"].addEventListener("input", () => {
        stopPreparationObservation();
        state.preparationJob = null;
        state.preparationCatalog = null;
        state.preparationOffset = 0;
        ui["preparation-batches"].replaceChildren();
        ui["preparation-history-summary"].textContent = "项目已变化，请重新读取批次。";
        ui["preparation-previous"].disabled = true;
        ui["preparation-next"].disabled = true;
        renderPreparationJob();
    });
    ui["preparation-form"].addEventListener("submit", (event) => { event.preventDefault(); void submitPreparation(); });
    ui["stop-preparation"].addEventListener("click", () => { void cancelPreparation(); });
    ui["refresh-preparation"].addEventListener("click", () => { void readPreparationBatches(); });
    ui["preparation-previous"].addEventListener("click", () => { void readPreparationBatches(Math.max(0, state.preparationOffset - 20)); });
    ui["preparation-next"].addEventListener("click", () => { void readPreparationBatches(state.preparationOffset + 20); });
    ui["open-prepared-tasks"].addEventListener("click", () => { void openPreparedTasks(); });
    ui["download-preparation"].addEventListener("click", () => {
        if (!state.preparationJob?.result) return;
        const url = URL.createObjectURL(new Blob([JSON.stringify(state.preparationJob.result, null, 2) + "\n"], { type: "application/json;charset=utf-8" }));
        const link = element("a");
        link.href = url;
        link.download = `media-batch-${state.preparationJob.batchId}.json`;
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    ui["close-tasks"].addEventListener("click", clearTasks);
    ui["tasks-previous"].addEventListener("click", () => { void loadTasks(Math.max(0, state.tasksOffset - TASK_PAGE_SIZE)); });
    ui["tasks-next"].addEventListener("click", () => { void loadTasks(state.tasksOffset + TASK_PAGE_SIZE); });
    ui["refresh-tasks"].addEventListener("click", () => { void loadTasks(state.tasksOffset); });
    ui["tasks-dialog"].addEventListener("close", () => { state.tasksController?.abort(); state.tasksController = null; state.tasksRevision += 1; });
    ui["close-detail-costs"].addEventListener("click", () => ui["detail-cost-dialog"].close());
    ui["open-retrieval-diagnostics"].addEventListener("click", openRetrievalDiagnostics);
    ui["close-retrieval-diagnostics"].addEventListener("click", clearRetrievalDiagnostics);
    ui["download-retrieval-diagnostics"].addEventListener("click", downloadRetrievalDiagnostics);
    ui["retrieval-diagnostics-dialog"].addEventListener("close", () => { state.diagnosticsContext = null; });
    for (const id of ["query", "mode", "top"]) {
        ui[id].addEventListener(id === "mode" ? "change" : "input", () => {
            clearSearchDetailEvidence();
            if(state.detailSearchScope)clearDetailMatch();
            updateSearchScope();
            state.inspectController?.abort();
            if (state.projectSearchController && !state.projectSearch) {
                state.projectSearchController.abort();
                state.projectSearchController = null;
                setBusy(false);
                empty(ui["candidate-list"], "查询已变化，请重新查找片段。");
            }
            if (state.view) state.view = { ...state.view, retrievalDiagnostics: null };
            clearRetrievalDiagnostics();
            updateDiagnosticsButton();
        });
    }
    ui["detail-cost-dialog"].addEventListener("close", () => { state.costController?.abort(); state.costRevision += 1; });
    ui["refresh-projects"].addEventListener("click", () => { void loadProjects(); });
    ui["refresh-runs"].addEventListener("click", () => { void loadRuns(state.project, state.run); });
    ui["refresh-view"].addEventListener("click", () => { void inspect(""); });
    ui["search-form"].addEventListener("submit", (event) => {
        event.preventDefault();
        if ((!state.searchRuns.length && state.view?.runStatus !== "completed") || state.busy) return;
        const query = ui.query.value.trim();
        if (!query) return notice("写一句你想寻找的动作或画面，再查找片段。");
        if (query.length > 4096) return notice("查询最多 4096 个字符，请缩短描述。");
        if (state.searchRuns.length) void searchProject(query);
        else void inspect(query);
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
    ui["play-context"].addEventListener("click", () => { if (state.active) void previewClip(state.active.kind, state.active.row, true); });
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
    ui["video-scrubber"].addEventListener("input", () => { state.playbackEndUs = null; ui["playback-range"].textContent = "自由回看"; seek(Math.round(Number(ui["video-scrubber"].value) * 1000000)); });
    ui["timeline-map"].addEventListener("click", (event) => {
        if (!state.view || !state.sourceUrl) return;
        const bounds = ui["timeline-map"].getBoundingClientRect();
        if (!bounds.width) return;
        state.playbackEndUs = null;
        ui["playback-range"].textContent = "自由回看";
        seek(Math.round(Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)) * state.view.media.durationUs));
    });
    window.addEventListener("resize", drawTimeline);
    resetView();
    void (async () => {
        try {
            const health = await request("/api/health", {});
            state.projectDetailAvailable=health.application==="gamingcreator-workspace" && health.capabilities?.includes("project-detail-query-v1");updateSearchScope();
            state.searchDetailAvailable=health.application==="gamingcreator-workspace" && health.capabilities?.includes("search-detail-query-v1");updateSearchScope();
            document.getElementById("open-acceptance").hidden = !(health.application === "gamingcreator-workspace"
                && health.capabilities?.includes("benchmark-workflow-v1"));
            ui["open-preparation"].hidden = !(health.application === "gamingcreator-workspace"
                && health.capabilities?.includes("media-preparation-v1"));
        } catch { /* Keep the preparation entry hidden until its service is available. */ }
    })();
    void loadProjects();
})();
