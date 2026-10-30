"use strict";
(() => {
    const $ = (id) => document.getElementById(id);
    const state = {project: "", job: "", epoch: 0, view: 0, timer: null, selected: null, busy: false, intents: {}};
    const labels = {pending: "等待开始", running: "正在处理", completed: "已完成", failed: "失败", interrupted: "已中断"};
    function node(tag, text) { const el = document.createElement(tag); el.textContent = text; return el; }
    function notice(message) { $("notice").textContent = message; }
    function humanTime(value) { const time = new Date(value); return Number.isNaN(time.getTime()) ? "时间未知" : time.toLocaleString("zh-CN", {hour12: false}); }
    function save() { try { localStorage.setItem("creation-workspace-v1", JSON.stringify({project: state.project, job: state.job})); } catch { /* Storage may be disabled. */ } }
    async function api(url, body) {
        const response = await fetch(url, body ? {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)} : {});
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : data.error?.message || data.message || `请求失败 (${response.status})`);
        return data;
    }
    function requestId(kind, payload) {
        const key = JSON.stringify(payload);
        if (state.intents[kind]?.key !== key) {
            const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), (v) => v.toString(16).padStart(2, "0")).join("");
            state.intents[kind] = {key, id};
        }
        return state.intents[kind].id;
    }
    function controls() {
        $("plan").disabled = state.busy || !state.project || !$("runs").querySelector("input:checked");
        $("render").disabled = state.busy || !state.selected;
    }
    function clearView() { state.selected = null; $("plans").replaceChildren(); $("artifact").replaceChildren(); $("job-status").textContent = "尚未选择任务"; controls(); }
    function showPlans(job) {
        $("plans").replaceChildren(); state.selected = null;
        for (const plan of job.plans || []) {
            const card = node("article", ""); card.className = "plan-card";
            card.append(node("h3", plan.structure), node("p", plan.ready ? "方案可用 · 模板草稿" : "方案有缺口 · 不可选择"), node("p", "脚本：已有描述草稿，待核对"));
            const segments = plan.segments || [];
            card.append(node("p", `${segments.length} 个片段 · ${(segments.reduce((sum, s) => sum + s.outputFrames, 0) / job.fps).toFixed(2)} 秒`));
            const list = node("ol", "");
            for (const segment of segments) list.append(node("li", `${(segment.startUs / 1e6).toFixed(2)}–${(segment.endUs / 1e6).toFixed(2)} 秒：${segment.scriptDraft || "无描述"}`));
            card.append(list);
            for (const gap of plan.gaps || []) card.append(node("p", `缺口：${gap}`));
            const select = node("button", "选择此方案"); select.type = "button"; select.disabled = plan.ready !== true;
            select.addEventListener("click", () => { state.selected = {planJobId: job.jobId, planId: plan.id}; document.querySelectorAll(".plan-card").forEach((c) => c.classList.remove("selected")); card.classList.add("selected"); controls(); });
            card.append(select); $("plans").append(card);
        }
        controls();
    }
    function showArtifact(artifact) {
        const video = document.createElement("video"); video.controls = true; video.preload = "metadata";
        const download = node("a", `下载 MP4（${(artifact.sizeBytes / 1048576).toFixed(2)} MB）`);
        // Only serve artifacts through the workspace's job media endpoint.
        const prefix = `/api/creation/jobs/${encodeURIComponent(state.job)}/video`;
        for (const value of [artifact.previewUrl, artifact.downloadUrl]) {
            const url = new URL(value, location.origin);
            if (url.origin !== location.origin || url.pathname !== prefix) throw new Error("成片地址无效，请刷新任务。");
        }
        video.src = artifact.previewUrl; download.href = artifact.downloadUrl; download.download = "video.mp4";
        $("artifact").append(video, download);
        if (artifact.subtitleUrl) {
            const url = new URL(artifact.subtitleUrl, location.origin);
            if (url.origin !== location.origin || url.pathname !== `/api/creation/jobs/${encodeURIComponent(state.job)}/subtitles` || url.search || url.hash) throw new Error("字幕地址无效，请刷新任务。");
            const link = node("a", "下载 SRT 字幕"); link.id = "download-subtitles"; link.href = artifact.subtitleUrl; link.download = "subtitles.srt";
            $("artifact").append(node("p", artifact.subtitleCueCount === 0 ? "字幕 0 条：所选片段无可用的已保存语音，SRT 为空。" : `字幕 ${artifact.subtitleCueCount} 条 · ${artifact.subtitleMode === "burn" ? "已烧入视频" : "独立导出"}`), link);
        }
    }
    async function openJob(id) {
        clearTimeout(state.timer); const epoch = state.epoch, view = ++state.view;
        state.job = id; save(); clearView();
        async function poll() {
            try {
                const job = await api(`/api/creation/jobs/${encodeURIComponent(id)}`);
                if (epoch !== state.epoch || view !== state.view) return;
                if (job.projectId !== state.project || job.jobId !== id) throw new Error("任务不属于当前项目。");
                $("job-status").textContent = `${job.kind === "plan" ? "方案" : "视频"} · ${labels[job.status] || job.status}${job.error ? `：${job.error.message}（${job.error.code}）` : ""}`;
                if (job.status === "completed") { if (job.kind === "plan") showPlans(job); else if (job.artifact) showArtifact(job.artifact); void history(epoch); }
                else if (["pending", "running"].includes(job.status)) state.timer = setTimeout(poll, 1000);
            } catch (error) { if (epoch === state.epoch && view === state.view) notice(`任务回查失败：${error.message}。可从历史重新打开。`); }
        }
        await poll();
    }
    async function history(epoch = state.epoch) {
        const project = state.project; if (!project) return;
        try {
            const data = await api(`/api/creation/jobs?projectId=${encodeURIComponent(project)}`);
            if (epoch !== state.epoch) return;
            $("history").replaceChildren();
            for (const job of data.jobs.slice(0, 100)) {
                const button = node("button", `${job.kind === "plan" ? "方案" : "视频"} · ${labels[job.status] || job.status} · ${humanTime(job.createdAt)}${job.error ? ` · ${job.error.message}` : ""}`);
                button.type = "button"; button.addEventListener("click", () => { void openJob(job.jobId); }); $("history").append(button);
            }
            if (!data.jobs.length) $("history").append(node("p", "此项目暂无创作任务。"));
        } catch (error) { if (epoch === state.epoch) notice(error.message); }
    }
    async function projectChanged(restoreJob = "") {
        const epoch = ++state.epoch; ++state.view; clearTimeout(state.timer);
        state.project = $("project").value; state.job = restoreJob; state.intents = {}; state.busy = false; save(); clearView(); $("runs").replaceChildren(); $("history").replaceChildren();
        if (!state.project) return;
        notice("正在读取可用素材…");
        try {
            const data = await api(`/api/runs?project=${encodeURIComponent(state.project)}`);
            if (epoch !== state.epoch) return;
            for (const run of data.runs.filter((r) => r.completedEligible === true)) {
                const label = node("label", ""), check = document.createElement("input"); check.type = "checkbox"; check.value = run.id; check.addEventListener("change", controls);
                label.append(check, document.createTextNode(`${run.sourceName} · 版本 ${run.id.slice(0, 8)}`)); $("runs").append(label);
            }
            notice($("runs").childElementCount ? "请选择素材，填写需求后生成方案。" : "此项目没有已完成分析的录像，暂不能生成方案。"); controls();
            await history(epoch); if (restoreJob && epoch === state.epoch) await openJob(restoreJob);
        } catch (error) { if (epoch === state.epoch) notice(error.message); }
    }
    async function submit(kind, payload) {
        if (state.busy) return;
        const epoch = state.epoch, view = state.view; state.busy = true; controls(); notice("正在提交任务…");
        try {
            const result = await api(`/api/creation/${kind === "plan" ? "plans" : "renders"}`, {...payload, requestId: requestId(kind, payload)});
            if (epoch !== state.epoch || view !== state.view) return;
            delete state.intents[kind]; notice("任务已保存，可刷新页面继续查看。"); await openJob(result.jobId); void history(epoch);
        } catch (error) { if (epoch === state.epoch && view === state.view) notice(`${error.message}。再次提交相同内容会复用请求，不重复创建任务。`); }
        finally { if (epoch === state.epoch) { state.busy = false; controls(); } }
    }
    $("brief").addEventListener("submit", (event) => {
        event.preventDefault(); const brief = Object.fromEntries(new FormData(event.target));
        for (const key of ["platforms", "mandatoryTopics", "exclude"]) brief[key] = [...new Set(brief[key].split(/[,，\n]/).map((s) => s.trim()).filter(Boolean))];
        brief.targetDuration = Number(brief.targetDuration);
        void submit("plan", {projectId: state.project, runIds: Array.from($("runs").querySelectorAll("input:checked"), (c) => c.value), brief, fps: Number($("fps").value)});
    });
    $("render-form").addEventListener("submit", (event) => { event.preventDefault(); if (!state.selected) return; const [width, height] = $("size").value.split(",").map(Number); void submit("render", {...state.selected, width, height, subtitleMode: $("subtitles").value}); });
    $("project").addEventListener("change", () => { void projectChanged(); }); $("refresh").addEventListener("click", () => { void history(); if (state.job) void openJob(state.job); });
    void (async () => {
        try {
            let saved = {}; try { saved = JSON.parse(localStorage.getItem("creation-workspace-v1") || "{}"); } catch { /* Ignore an invalid saved selection. */ }
            const data = await api("/api/projects");
            for (const project of data.projects) { const option = node("option", project.name || project.path); option.value = project.path; $("project").append(option); }
            $("project").value = data.projects.some((p) => p.path === saved.project) ? saved.project : (data.projects[0]?.path || "");
            await projectChanged($("project").value === saved.project ? saved.job : "");
            if (!data.projects.length) notice("尚未发现已有项目，请先在素材工作台准备素材。");
        } catch (error) { notice(`无法读取项目：${error.message}`); }
    })();
})();
