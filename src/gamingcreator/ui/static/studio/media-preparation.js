import {h} from "../vendor/preact.module.js";
import {useEffect, useLayoutEffect, useMemo, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";

const html = htm.bind(h);
const PAGE_SIZE = 20;
const STATES = {queued: "排队中", pending: "待准备", running: "准备中", cancelling: "正在停止", finished: "准备完成",
    partial: "部分准备完成", failed: "准备失败", stopped: "已中断", cancelled: "已停止", prepared: "已准备", coverage_blocked: "覆盖不足", analysis_started: "后续分析已开始"};
const ACTIVE = ["queued", "running", "cancelling"];
const isActive = (job) => !!job?.live && ACTIVE.includes(job.status);
const validId = (id) => typeof id === "string" && /^[a-f0-9]{32}$/.test(id);
const knownState = (status) => Object.hasOwn(STATES, status);

function validItems(items) {
    return Array.isArray(items) && items.length <= 100 && items.every((row) => row && typeof row.id === "string"
        && typeof row.sourceName === "string" && typeof row.runId === "string" && knownState(row.status)
        && typeof row.verifiedThisInvocation === "boolean");
}

function checkedJob(job, project, id, batch) {
    if (job?.schemaVersion !== "media-preparation-job-v1" || job.project !== project || !validId(job.jobId)
        || (id && job.jobId !== id) || (batch && job.batchId !== batch) || !knownState(job.status) || typeof job.live !== "boolean"
        || typeof job.cancellationRequested !== "boolean" || (job.batchId !== null && !validId(job.batchId))
        || (job.progress !== null && (job.progress?.batchId !== job.batchId || !validItems(job.progress.items)))) {
        throw new Error("准备任务的项目、批次或进度无法核对。");
    }
    return job;
}

function checkedCatalog(catalog, project, offset) {
    if (catalog?.schemaVersion !== "media-preparation-catalog-v1" || catalog.project !== project || catalog.limit !== PAGE_SIZE
        || catalog.offset !== offset || !Number.isSafeInteger(catalog.total) || catalog.total < 0 || !Array.isArray(catalog.batches)
        || catalog.batches.length > PAGE_SIZE || catalog.batches.some((row) => !validId(row?.batchId) || typeof row.readable !== "boolean"
            || (row.readable && (!knownState(row.status) || !validItems(row.items))))) {
        throw new Error("保存的批次清单无法核对。");
    }
    if (catalog.activeJob) checkedJob(catalog.activeJob, project);
    return catalog;
}

function usePreparation(project) {
    const scope = useMemo(() => ({project}), [project]);
    const slot = useRef({});
    const writing = useRef(false);
    const [state, setState] = useState({});
    const current = state.scope === scope ? state : {};
    const update = (values) => setState((previous) => ({...(previous.scope === scope ? previous : {}), ...values, scope}));
    const stop = () => { slot.current.controller?.abort(); clearTimeout(slot.current.timer); };
    const begin = () => {
        stop();
        const controller = new AbortController();
        slot.current = {controller};
        return controller.signal;
    };
    const watch = (job, signal, offset) => {
        if (!isActive(job)) return;
        slot.current.timer = setTimeout(async () => {
            try {
                const next = checkedJob(await client.preparationJob(project, job.jobId, signal), project, job.jobId, job.batchId);
                if (signal.aborted) return;
                if (isActive(next)) { update({job: next}); watch(next, signal, offset); }
                else void read(offset, next);
            } catch (error) {
                if (!signal.aborted) void read(offset, null, {jobId: job.jobId, message: error.message});
            }
        }, 750);
    };
    const read = async (offset = 0, keep = null, failed = null) => {
        const signal = begin();
        update({checking: true, error: "", catalog: null, job: keep});
        try {
            const catalog = checkedCatalog(await client.preparationBatches(project, PAGE_SIZE, offset, signal), project, offset);
            if (signal.aborted) return;
            const job = catalog.activeJob || keep;
            const paused = isActive(job) && failed?.jobId === job.jobId;
            update({checking: false, catalog, job, error: paused ? `暂时无法读取实时进度。${failed.message} 请点击“重新读取批次”。` : ""});
            if (!paused) watch(job, signal, offset);
        } catch (error) {
            if (!signal.aborted) update({checking: false, error: `${error.message} 请重新读取批次。`});
        }
    };
    const write = async (send, expectedId, expectedBatch) => {
        if (writing.current || !current.catalog) return;
        writing.current = true;
        const signal = begin();
        const offset = current.catalog.offset;
        update({writing: true, error: ""});
        try {
            const job = checkedJob(await send(signal), project, expectedId, expectedBatch);
            if (signal.aborted) return;
            if (isActive(job)) { update({job}); watch(job, signal, offset); }
            else void read(offset, job);
        } catch (error) {
            if (!signal.aborted) update({catalog: null, job: null, error: `${error.message} 请先重新读取批次，确认任务状态。`});
        } finally {
            writing.current = false;
            // A terminal job may have started a fresh catalog read already.
            update({writing: false});
        }
    };
    useLayoutEffect(() => {
        if (project) slot.current.timer = setTimeout(() => void read(), 250);
        return stop;
    }, [scope]);
    return {...current, read, write};
}

function localWindowsPath(path) {
    return typeof path === "string" && /^[A-Za-z]:[\\/]/.test(path) && !/[\p{Cc}\p{Cf}\p{Zl}\p{Zp}"<>|?*]/u.test(path)
        && path.slice(3).split(/[\\/]/).every((part) => part && !part.includes(":") && !/[. ]$/.test(part));
}

function quotePowerShell(word) {
    // PowerShell recognizes typographic single quotes as delimiters, too.
    return `'${word.replace(/['\u2018-\u201B]/gu, "$&$&")}'`;
}

function checkedHandoff(document, project, row) {
    if (document?.schemaVersion !== "material-tasks-v2" || document.project !== project || document.limit !== 1
        || document.offset !== 0 || document.total !== 1 || document.hasMore !== false || document.snapshotOnly !== true
        || !Array.isArray(document.tasks) || document.tasks.length !== 1 || document.tasks[0]?.runId !== row.runId) {
        throw new Error("返回的项目或任务身份无法核对，请重新读取批次。");
    }
    const [task] = document.tasks;
    if (task.phase === "completed") throw new Error("此任务的分析已完成，可在项目中打开回看。");
    const {result} = row;
    const {stages, cost, progress, nextCommand: args} = task;
    if (task.phase !== "media_prepared" || task.runStatus !== "pending" || task.nextAction !== "analyze" || task.errorCode !== null
        || !Array.isArray(task.continuationBlockers) || task.continuationBlockers.length || task.requiresRetryConfirmation !== false
        || !Array.isArray(stages) || stages.length !== 1 || stages[0]?.id !== "media" || stages[0]?.status !== "completed"
        || task.eventCount !== 0 || task.transcriptCount !== 0 || cost?.remoteRequests !== 0 || cost?.unknownAttempts !== 0
        || cost?.knownCny !== "0" || progress?.completedVisionWindows !== 0 || progress?.coverageFits !== true) {
        throw new Error("当前任务还不能交接分析，请先核对最新任务状态。");
    }
    const cap = result.savedMaxCostCny;
    const digest = (value) => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
    const positive = (value) => Number.isSafeInteger(value) && value > 0;
    if (!validId(row.runId) || result.runId !== row.runId || result.runStatus !== "pending" || result.modelInvocations !== 0
        || !digest(result.sourceSha256) || result.sourceSha256 !== row.sourceSha256 || result.sourceSha256 !== task.sourceSha256
        || !digest(result.configHash) || result.configHash !== task.configHash || row.sourceName !== task.sourceName
        || !positive(result.durationUs) || result.durationUs !== task.durationUs || !positive(result.imageCount) || result.imageCount !== task.imageCount
        || typeof cap !== "string" || !/^\+?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(cap)
        || !Number.isFinite(Number(cap)) || Number(cap) <= 0 || cap !== task.configuration?.maxCostCny
        || !positive(result.plannedWindows) || result.plannedWindows !== progress.plannedWindows
        || !positive(result.plannedUploadFrames) || result.plannedUploadFrames !== progress.plannedUploadFrames) {
        throw new Error("冻结的素材、分析配置或费用上限与当前任务不一致，请重新读取批次。");
    }
    const frozen = result.nextCommand;
    if (!Array.isArray(args) || !Array.isArray(frozen) || args.length !== 7 || frozen.length !== args.length
        || args.some((arg, index) => typeof arg !== "string" || arg !== frozen[index])
        || args[0] !== "gamingcreator" || args[1] !== "analyze" || args[3] !== "--project" || args[5] !== "--resume"
        || args[6] !== row.runId || !localWindowsPath(args[2]) || !localWindowsPath(args[4]) || args[2].split(/[\\/]/).at(-1) !== row.sourceName) {
        throw new Error("冻结的分析命令无法核对，请重新读取批次。");
    }
    const command = String.raw`& {
    $ErrorActionPreference = 'Stop'
    . '.\scripts\env.ps1'
    & '.\.venv\Scripts\python.exe' -B -m gamingcreator analyze ${quotePowerShell(args[2])} --project ${quotePowerShell(args[4])} --resume ${quotePowerShell(args[6])}
}`;
    return {command, cap, windows: progress.plannedWindows, frames: progress.plannedUploadFrames};
}

function AnalysisHandoff({project, row}) {
    const active = useRef(null);
    const [state, setState] = useState({});
    useLayoutEffect(() => () => active.current?.abort(), []);
    const check = async () => {
        active.current?.abort();
        const controller = new AbortController();
        active.current = controller;
        setState({checking: true});
        try {
            const document = await client.preparedAnalysisTask(project, row.runId, controller.signal);
            if (!controller.signal.aborted) setState(checkedHandoff(document, project, row));
        } catch (error) {
            if (!controller.signal.aborted) setState({error: `核对分析任务失败。${error.message}`});
        }
    };
    const copy = () => {
        const {signal} = active.current;
        const notice = (message) => { if (!signal.aborted) setState((value) => ({...value, notice: message})); };
        void client.copyText(state.command, () => notice("已复制分析命令。"), () => notice("无法自动复制，请手动选中下方命令复制。"));
    };
    return html`<div class="actions-row">
        <button type="button" class="btn ghost" disabled=${state.checking} onClick=${check}>核对分析任务</button>
        ${state.checking ? html`<p role="status">正在核对分析任务…</p>` : null}
        ${state.error ? html`<p role="alert">${state.error}</p>` : null}
        ${state.command ? html`<div>
            <p class="hint">保存的分析上限 ¥${state.cap}（实际费用以账单为准） · 计划 ${state.windows} 个窗口、${state.frames} 张上传帧。</p>
            <p class="hint">先单独确认分析与费用授权，再在应用根目录的 PowerShell 运行命令。</p>
            <button type="button" class="btn ghost" onClick=${copy}>复制分析命令</button>
            <textarea class="input" aria-label="分析命令（PowerShell）" readonly rows="5" value=${state.command}></textarea>
            ${state.notice ? html`<p role="status">${state.notice}</p>` : null}
        </div>` : null}
    </div>`;
}

function ProgressRows({project, items, saved = false}) {
    return html`<ul>${items.map((row) => html`<li key=${row.id} data-run=${row.runId} data-preparation-state=${row.status}>
        <strong>${row.sourceName}</strong> · ${STATES[row.status]}
        ${Number.isSafeInteger(row.result?.imageCount) ? html`<span> · ${row.result.imageCount} 张画面 · ${row.result.audioAvailable ? "已保存音轨" : "没有音轨"}</span>` : null}
        ${row.message ? html`<p class="hint">${row.message}</p>` : null}
        ${!saved && !row.verifiedThisInvocation && !["pending", "running"].includes(row.status) ? html`<span class="hint"> · 本次尚未重新核对</span>` : null}
        ${row.status === "prepared" && row.result?.coverageFits === true && row.result.nextCommand
            ? html`<${AnalysisHandoff} key=${JSON.stringify([project, row.runId, row.sourceSha256, row.sourceName, row.result])} project=${project} row=${row} />` : null}
    </li>`)}</ul>`;
}

function PreparationHistory({catalog, job, disabled, onResume, read}) {
    if (!catalog) return null;
    const {batches, total, offset} = catalog;
    return html`<section aria-label="保存的准备批次">
        <h3>保存的准备批次</h3>
        <p class="hint">${total ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} / ${total} 个批次 · 保存状态` : "该项目还没有保存的批次。"}</p>
        ${batches.map((batch) => html`<details class="group" key=${batch.batchId} data-batch=${batch.batchId} open=${batches.length === 1 && !job}>
            <summary>批次 ${batch.batchId.slice(0, 8)} · ${batch.readable ? `${batch.items.length} 段 · ${STATES[batch.status]}` : "无法读取"}</summary>
            ${batch.readable ? html`<p class="hint">原每段后续分析上限 ¥${batch.maxCostCnyPerTask}。</p>
                <${ProgressRows} project=${catalog.project} items=${batch.items} saved=${true} />
                <button class="btn ghost" type="button" disabled=${disabled} onClick=${() => onResume(batch.batchId)}>继续本地准备</button>`
                : html`<p class="hint">${batch.message || "批次资料无法核对。"}</p>`}
        </details>`)}
        ${total > PAGE_SIZE ? html`<div class="actions-row">
            <button class="btn ghost" type="button" disabled=${disabled || offset === 0} onClick=${() => read(offset - PAGE_SIZE)}>上一页</button>
            <button class="btn ghost" type="button" disabled=${disabled || offset + PAGE_SIZE >= total} onClick=${() => read(offset + PAGE_SIZE)}>下一页</button>
        </div>` : null}
    </section>`;
}


function ProjectDialog({title, onClose, closeDisabled, children}) {
    const dialog = useRef(null);
    useEffect(() => { dialog.current?.showModal(); }, []);
    return html`<dialog class="project-dialog" ref=${dialog} aria-label=${title}
        onCancel=${(event) => { event.preventDefault(); if (!closeDisabled) onClose(); }}>
        <header class="entitlement-head"><h2>${title}</h2><span class="spacer"></span>
            <button class="btn ghost" type="button" disabled=${closeDisabled} onClick=${onClose}>关闭</button>
        </header>
        ${children}
    </dialog>`;
}

function ProjectLocations({start = "artifacts", selectFolder, openProject, onHistory, busy}) {
    const [folder, setFolder] = useState(start);
    const [listing, setListing] = useState(null);
    const [error, setError] = useState("");
    const [retry, setRetry] = useState(0);
    const [filter, setFilter] = useState("");
    const navigate = (path) => { setFilter(""); setFolder(path); };
    const current = listing?.folder === folder ? listing : null;
    useEffect(() => {
        const controller = new AbortController();
        setError(""); setListing(null);
        client.projectLocations(folder, controller.signal).then((data) => {
            if (!controller.signal.aborted) setListing(data);
        }).catch((e) => { if (!controller.signal.aborted) setError(e.message); });
        return () => controller.abort();
    }, [folder, retry]);
    const folders = current?.folders.filter(({name}) => name.toLowerCase().includes(filter.trim().toLowerCase())) || [];
    const folderList = current?.folders.length ? html`
        ${current.folders.length > 12 && html`<label class="form-row">查找文件夹<input class="input" type="search"
            value=${filter} onInput=${e => setFilter(e.currentTarget.value)} /></label>`}
        ${folders.length ? html`<ul class="project-list" aria-label="子目录">
            ${folders.map(({path, name}) => html`<li key=${path}>
                <button class="project-choice" type="button" disabled=${busy} onClick=${() => navigate(path)}>
                    <strong>${name}</strong><span>浏览文件夹</span>
                </button>
            </li>`)}
        </ul>` : html`<p class="hint">没有匹配的文件夹。</p>`}
    ` : null;
    return html`<section class="project-locations" aria-label="项目目录">
        <div class="actions-row">
            ${folder !== "artifacts" && html`<button class="btn ghost" type="button"
                onClick=${() => navigate(folder.slice(0, folder.lastIndexOf("/")))}>上一级</button>`}
            <span class="project-path">${folder}</span>
            ${selectFolder && html`<button class="btn ghost" type="button" disabled=${busy || !current}
                onClick=${() => selectFolder(current.folder)}>使用这个目录</button>`}
        </div>
        ${error ? html`<p role="alert">${error} <button class="btn ghost" type="button" onClick=${() => setRetry(retry + 1)}>重试</button></p>`
            : !current ? html`<p role="status">正在读取目录…</p>`
            : html`
                ${openProject && current.projects.length > 0 && html`<ul class="project-list" aria-label="可打开的项目">
                    ${current.projects.map(({path, name}) => html`<li key=${path}>
                        <button class="project-choice" type="button" disabled=${busy} onClick=${() => openProject(path)}>
                            <strong>${name}</strong><span>${path}</span>
                        </button>
                        <button class="btn ghost" type="button" disabled=${busy} aria-label=${`查看 ${name} 的导入记录`}
                            onClick=${() => onHistory(path)}>导入记录</button>
                    </li>`)}
                </ul>`}
                ${openProject && current.histories?.length > 0 && html`<ul class="project-list" aria-label="未完成的导入">
                    ${current.histories.map(({path, name}) => html`<li key=${path}>
                        <button class="project-choice" type="button" disabled=${busy} onClick=${() => onHistory(path)}>
                            <strong>${name}</strong><span>${path} · 导入记录</span>
                        </button>
                    </li>`)}
                </ul>`}
                ${openProject && (current.projects.length || current.histories?.length) && folderList
                    ? html`<details><summary>浏览其他目录</summary>${folderList}</details>`
                    : folderList || html`<p class="hint">${openProject && !(current.projects.length || current.histories?.length)
                        ? "这里没有已保存的项目。" : "没有子目录。"}</p>`}            `}
    </section>`;
}

export function OpenStudioProject({onClose, onOpenProject, onHistory}) {
    const opening = useRef(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    useEffect(() => () => opening.current?.abort(), []);
    const open = async (path) => {
        if (opening.current) return;
        const controller = new AbortController();
        opening.current = controller;
        setBusy(true); setError("");
        try { if (await onOpenProject(path, "edit", controller.signal)) onClose(); }
        catch (e) { if (!controller.signal.aborted) setError(`打开项目失败。${e.message}`); }
        finally { opening.current = null; if (!controller.signal.aborted) setBusy(false); }
    };
    return html`<${ProjectDialog} title="打开已有项目" onClose=${onClose}>
        <p>点击项目名称进入剪辑。项目下方显示保存位置。</p>
        ${busy && html`<p role="status">正在打开项目…</p>`}
        ${error && html`<p role="alert">${error}</p>`}
        <${ProjectLocations} openProject=${open} onHistory=${onHistory} busy=${busy} />
    <//>`;
}

export function ImportRecordings({historyProject = "", onClose, onOpenProject}) {
    const [name, setName] = useState("");
    const [folder, setFolder] = useState("artifacts");
    const [showFolders, setShowFolders] = useState(false);
    const [paths, setPaths] = useState("");
    const [profile, setProfile] = useState("detailed");
    const [budget, setBudget] = useState("5");
    const [timeout, setTimeoutSeconds] = useState("3600");
    const [error, setError] = useState("");
    const [opening, setOpening] = useState(false);
    const [picking, setPicking] = useState(false);
    const cleanName = name.trim();
    const validName = !!cleanName && !/[\\/:*?"<>|]/u.test(cleanName) && !cleanName.endsWith(".");
    const scope = historyProject || (validName ? `${folder}/${cleanName}` : "");
    const {catalog, job, checking, writing, error: stateError, read, write} = usePreparation(scope);
    const active = isActive(job);
    const locked = !!writing || opening || active;
    const entries = paths.split(/\r?\n/).map((line) => line.trim().replace(/^"(.*)"$/, "$1")).filter(Boolean);
    const items = job?.progress?.items || [];
    const hasPrepared = rows => rows.some(row => ["prepared", "analysis_started"].includes(row.status));
    const ready = hasPrepared(items) || catalog?.batches.some(batch => batch.readable && hasPrepared(batch.items));
    const existing = catalog?.projectExists === true;
    const canSubmit = !locked && !picking && !!catalog && (historyProject || !existing) && entries.length > 0;

    const submit = (resume = null) => {
        if (resume ? locked || !catalog : !canSubmit) return;
        setError("");
        const timeoutSeconds = Number(timeout);
        if (!timeout || !Number.isFinite(timeoutSeconds) || timeoutSeconds < 1 || timeoutSeconds > 86400) {
            setError("每段准备时间须为 1–86400 秒。"); return;
        }
        const maxCostCny = budget.trim();
        if (!resume && (entries.length > 100 || !Number.isFinite(Number(maxCostCny)) || Number(maxCostCny) <= 0)) {
            setError("每次最多添加 100 段视频，后续分析上限须大于零。"); return;
        }
        const body = resume ? {project: scope, resume, timeoutSeconds} : {project: scope, paths: entries, profile, maxCostCny, timeoutSeconds};
        void write(signal => client.prepareMedia(body, signal), null, resume);
    };
    const pick = async () => {
        setPicking(true); setError("");
        try {
            const {paths: selected} = await client.pickLocalVideos();
            if (!Array.isArray(selected) || !selected.every(path => typeof path === "string")) throw new Error("无法读取所选视频。");
            if (selected.length) setPaths(selected.join("\n"));
        } catch (e) { setError(e.message); }
        finally { setPicking(false); }
    };
    const open = async () => {
        setOpening(true); setError("");
        try { if (await onOpenProject(scope, "assets")) onClose(); }
        catch (e) { setError(`打开素材页失败。${e.message}`); }
        finally { setOpening(false); }
    };
    return html`<${ProjectDialog} title=${historyProject ? "导入记录" : "新建剪辑项目"} onClose=${onClose} closeDisabled=${writing || opening}>
        ${historyProject ? html`<p class="project-path">${historyProject}</p>`
            : html`<p>给项目起个名字、添加视频，再点击「创建项目」。</p>`}
        <form class="project-form" onSubmit=${(event) => { event.preventDefault(); submit(); }}>
            ${!historyProject && html`
                <label class="form-row">项目名称<input class="input" autofocus maxLength="80" value=${name} disabled=${locked}
                    placeholder="例如：蓝色星原玩法展示" onInput=${e => { setName(e.currentTarget.value); setError(""); }} /></label>
                <div class="project-destination">
                    <span class="project-path">保存到 ${scope || folder}</span>
                    <button class="btn ghost" type="button" disabled=${locked} aria-expanded=${showFolders}
                        onClick=${() => setShowFolders(!showFolders)}>${showFolders ? "收起目录" : "更改工作目录"}</button>
                </div>
                ${showFolders && html`<${ProjectLocations} start=${folder} busy=${locked} selectFolder=${path => { setFolder(path); setShowFolders(false); }} />`}
                ${name && !validName && html`<p class="hint">请输入一个有效的目录名称。</p>`}
                ${existing && !job && html`<p class="hint">这个目录已有项目。请换个名字，或从顶栏打开已有项目。</p>`}
            `}
            <div class="actions-row">
                <button class="btn ghost" type="button" disabled=${locked || picking} onClick=${() => void pick()}>${picking ? "等待 Windows 选择…" : "选择视频"}</button>
                <span class="hint">${entries.length ? `已选 ${entries.length} 段` : "可以一次选择多段视频"}</span>
            </div>
            ${entries.length > 0 && html`<ul class="project-videos" aria-label="已选视频">
                ${entries.map(path => html`<li title=${path}>${path.split(/[\\\\/]/).at(-1)}</li>`)}
            </ul>`}
            <details>
                <summary>高级选项</summary>
                <label class="form-row">录像路径（每行一段）<textarea class="input" rows="3" value=${paths} disabled=${locked}
                    onInput=${e => setPaths(e.currentTarget.value)} /></label>
                <div class="pair even">
                    <label class="form-row">准备方案<select class="select" value=${profile} disabled=${locked}
                        onChange=${e => setProfile(e.currentTarget.value)}>
                        <option value="frames">画面观察</option><option value="temporal">连续动作</option><option value="detailed">细节动作</option>
                    </select></label>
                    <label class="form-row">以后每段分析上限（元）<input class="input" type="number" min="0" step="any" value=${budget}
                        disabled=${locked} onInput=${e => setBudget(e.currentTarget.value)} /></label>
                </div>
                <label class="form-row">每段最长准备时间（秒）<input class="input" type="number" min="1" max="86400" step="any" value=${timeout}
                    disabled=${locked} onInput=${e => setTimeoutSeconds(e.currentTarget.value)} /></label>
            </details>
            <p class="hint">${ready ? "视频已准备，可打开素材页。也可在下方核对分析任务。" : "视频先在本机准备，之后可以核对素材分析任务。"}</p>
            <div class="actions-row">
                ${(historyProject || !ready) && html`<button class="btn" type="submit" disabled=${!canSubmit}>${historyProject ? "添加到此项目" : "创建项目"}</button>`}
                ${active && html`<button class="btn ghost" type="button" disabled=${writing || job.cancellationRequested || !catalog}
                    onClick=${() => void write(signal => client.cancelPreparation(scope, job.jobId, signal), job.jobId, job.batchId)}>停止本地准备</button>`}
                ${ready && html`<button class="btn ghost" type="button" disabled=${locked} onClick=${() => void open()}>打开素材页</button>`}
            </div>
        </form>
        ${(writing || job || (checking && scope)) && html`<p role="status">${writing ? "正在提交…" : checking ? "正在读取导入记录…" : STATES[job.status]}
            ${items.length ? ` · 已准备 ${items.filter(item => item.status === "prepared").length}/${items.length} 段` : ""}</p>`}
        ${error || stateError || job?.error?.message ? html`<p role="alert">${error || stateError || job.error.message}</p>` : null}
        ${stateError && html`<button class="btn ghost" type="button" disabled=${checking || writing}
            onClick=${() => void read(catalog?.offset || 0)}>重新读取</button>`}
        ${items.length ? html`<${ProgressRows} project=${scope} items=${items} />` : null}
        ${(historyProject || catalog?.total > 0) && html`<${PreparationHistory} catalog=${catalog} job=${job}
            disabled=${locked || checking} onResume=${submit} read=${read} />`}
    <//>`;
}
