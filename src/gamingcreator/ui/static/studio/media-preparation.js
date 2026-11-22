import {h} from "../vendor/preact.module.js";
import {useEffect, useLayoutEffect, useMemo, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";

const html = htm.bind(h);
const PAGE_SIZE = 20;
const STORE = "gamingcreator:preparation-project";
const STATES = {queued: "排队中", pending: "待准备", running: "准备中", cancelling: "正在停止", finished: "准备完成",
    partial: "部分准备完成", failed: "准备失败", stopped: "已中断", cancelled: "已停止", prepared: "已准备", coverage_blocked: "覆盖不足", analysis_started: "后续分析已开始"};
const ACTIVE = ["queued", "running", "cancelling"];
const isActive = (job) => !!job?.live && ACTIVE.includes(job.status);
const validId = (id) => typeof id === "string" && /^[a-f0-9]{32}$/.test(id);
const knownState = (status) => Object.hasOwn(STATES, status);
const normalized = (project) => project.trim().replaceAll("\\", "/");

function rememberedScope(project) {
    try { return localStorage.getItem(STORE) || project; } catch { return project; }
}

function rememberScope(project) {
    try { localStorage.setItem(STORE, project); } catch { /* The target can also be entered again to recover a batch. */ }
}

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
            rememberScope(project);
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
        rememberScope(project);
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

function ProgressRows({items, saved = false}) {
    return html`<ul>${items.map((row) => html`<li key=${row.id} data-run=${row.runId} data-preparation-state=${row.status}>
        <strong>${row.sourceName}</strong> · ${STATES[row.status]}
        ${Number.isSafeInteger(row.result?.imageCount) ? html`<span> · ${row.result.imageCount} 张画面 · ${row.result.audioAvailable ? "已保存音轨" : "没有音轨"}</span>` : null}
        ${row.message ? html`<p class="hint">${row.message}</p>` : null}
        ${!saved && !row.verifiedThisInvocation && !["pending", "running"].includes(row.status) ? html`<span class="hint"> · 本次尚未重新核对</span>` : null}
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
                <${ProgressRows} items=${batch.items} saved=${true} />
                <button class="btn ghost" type="button" disabled=${disabled} onClick=${() => onResume(batch.batchId)}>继续本地准备</button>`
                : html`<p class="hint">${batch.message || "批次资料无法核对。"}</p>`}
        </details>`)}
        ${total > PAGE_SIZE ? html`<div class="actions-row">
            <button class="btn ghost" type="button" disabled=${disabled || offset === 0} onClick=${() => read(offset - PAGE_SIZE)}>上一页</button>
            <button class="btn ghost" type="button" disabled=${disabled || offset + PAGE_SIZE >= total} onClick=${() => read(offset + PAGE_SIZE)}>下一页</button>
        </div>` : null}
    </section>`;
}

export function ImportRecordings({project, onClose, onOpenProject}) {
    const dialog = useRef(null);
    const [target, setTarget] = useState(() => rememberedScope(project));
    const scope = normalized(target);
    const [paths, setPaths] = useState("");
    const [profile, setProfile] = useState("detailed");
    const [budget, setBudget] = useState("");
    const [timeout, setTimeoutSeconds] = useState("3600");
    const [error, setError] = useState("");
    const [opening, setOpening] = useState(false);
    const {catalog, job, checking, writing, error: stateError, read, write} = usePreparation(scope);
    const locked = !!writing || opening;
    const active = isActive(job);
    const items = job?.progress?.items || [];
    const hasPrepared = (rows) => rows.some((row) => ["prepared", "analysis_started"].includes(row.status));
    const ready = hasPrepared(items) || catalog?.batches.some((batch) => batch.readable && hasPrepared(batch.items));
    useEffect(() => { dialog.current?.showModal(); }, []);

    const submit = (resume = null) => {
        if (!catalog || active || locked) return;
        setError("");
        const timeoutSeconds = Number(timeout);
        if (!timeout || !Number.isFinite(timeoutSeconds) || timeoutSeconds < 1 || timeoutSeconds > 86400) {
            return setError("每段准备时间须为 1–86400 秒。");
        }
        const entries = paths.split(/\r?\n/).map((line) => line.trim().replace(/^"(.*)"$/, "$1")).filter(Boolean);
        const maxCostCny = budget.trim();
        if (!resume && (entries.length < 1 || entries.length > 100 || !Number.isFinite(Number(maxCostCny)) || Number(maxCostCny) <= 0)) {
            return setError("请填写 1–100 段本机录像路径和大于零的后续分析上限。");
        }
        const body = resume ? {project: scope, resume, timeoutSeconds} : {project: scope, paths: entries, profile, maxCostCny, timeoutSeconds};
        void write((signal) => client.prepareMedia(body, signal), null, resume);
    };
    const openProject = async () => {
        setOpening(true); setError("");
        try { await onOpenProject(scope); onClose(); }
        catch (reason) { setError(`打开项目失败。${reason.message}`); setOpening(false); }
    };
    return html`<dialog ref=${dialog} aria-label="导入录像" style=${{width: "min(640px, calc(100vw - 32px))", maxHeight: "calc(100vh - 32px)", padding: "var(--s-4)", border: "1px solid var(--line)", borderRadius: "var(--r-3)", background: "var(--bg-1)"}}
            onCancel=${(e) => { e.preventDefault(); if (!locked) onClose(); }}>
        <div class="entitlement-head"><h2>导入录像</h2><span class="spacer"></span><button class="btn ghost" type="button" disabled=${locked} onClick=${onClose}>关闭</button></div>
        <p class="note">本地准备会提取画面和音轨。录像分析须另行确认费用，分析完成后才可在素材页搜索。</p>
        <form onSubmit=${(event) => { event.preventDefault(); submit(); }}>
            <label class="form-row">准备项目<input class="input" value=${target} maxLength="8192" required disabled=${locked || active}
                onInput=${(e) => { setTarget(e.currentTarget.value); setError(""); }} placeholder="artifacts/my-recordings" /></label>
            <label class="form-row">录像路径（每行一段）<textarea class="input" rows="4" value=${paths} disabled=${locked || active} onInput=${(e) => setPaths(e.currentTarget.value)} /></label>
            <div class="pair even">
                <label class="form-row">准备方案<select class="select" value=${profile} disabled=${locked || active} onChange=${(e) => setProfile(e.currentTarget.value)}>
                    <option value="frames">画面观察</option><option value="temporal">连续动作</option><option value="detailed">细节动作</option>
                </select></label>
                <label class="form-row">以后每段分析上限（元）<input class="input" type="number" min="0" step="any" value=${budget} disabled=${locked || active} onInput=${(e) => setBudget(e.currentTarget.value)} /></label>
            </div>
            <details><summary>准备时间设置</summary><label class="form-row">每段最长准备时间（秒）<input class="input" type="number" min="1" max="86400" step="any" value=${timeout} disabled=${locked || active} onInput=${(e) => setTimeoutSeconds(e.currentTarget.value)} /></label></details>
            <div class="actions-row">
                <button class="btn" type="submit" disabled=${locked || active || !catalog}>开始本地准备</button>
                <button class="btn ghost" type="button" disabled=${locked || checking || !scope} onClick=${() => { setError(""); void read(catalog?.offset || 0); }}>重新读取批次</button>
                <button class="btn ghost" type="button" disabled=${locked || !active || job?.cancellationRequested || !catalog}
                    onClick=${() => { setError(""); void write((signal) => client.cancelPreparation(scope, job.jobId, signal), job.jobId, job.batchId); }}>停止本地准备</button>
            </div>
        </form>
        <p role="status">${writing ? "正在提交…" : checking ? "正在读取准备批次…" : job ? STATES[job.status] : "在这里查看本地准备进度。"}
            ${items.length ? ` · 已准备 ${items.filter((item) => item.status === "prepared").length}/${items.length} 段` : ""}</p>
        ${error || stateError || job?.error?.message ? html`<p role="alert">${error || stateError || job.error.message}</p>` : null}
        ${items.length ? html`<${ProgressRows} items=${items} />` : null}
        ${ready ? html`<button class="btn ghost" type="button" disabled=${locked || active} onClick=${openProject}>打开准备项目</button>` : null}
        <${PreparationHistory} catalog=${catalog} job=${job} disabled=${locked || active || checking} onResume=${submit} read=${read} />
    </dialog>`;
}
