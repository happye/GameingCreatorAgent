import {h} from "../vendor/preact.module.js";
import {useEffect, useLayoutEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import {api, JOB_STATUS, studioJobLink} from "./api.js";

const html = htm.bind(h);
const path = "/api/creation/ad-batches";
const maxVariants = 6;
const planLabels = {"ad-evidence-hook": "卖点版", "ad-evidence-demo": "演示版"};
const styles = {standard: "标准字幕", large: "大字字幕", boxed: "底框字幕", none: "无字幕"};
const platforms = {bilibili: "B站", douyin: "抖音", kuaishou: "快手", xiaohongshu: "小红书"};
const stages = {render: "成片", publication: "发布稿", package: "平台包"};
const labels = {...JOB_STATUS, interrupted: "等待恢复", cancelled: "已停止后续", cancelling: "正在停止", partial: "部分完成"};
const active = ({status}) => ["pending", "running", "cancelling"].includes(status);
const receipt = value => typeof value === "string" && /^[0-9a-f]{64}$/.test(value);

export function adBatchPlan(job, project) {
    return job?.kind === "plan" && job.status === "completed" && job.projectId === project
        && job.brief?.contentType === "ad" && receipt(job.resultReceiptSha256);
}

export function adBatchRevision(editing, planJob, planId) {
    const {base, editor, status, dirty} = editing;
    if (status !== "ready" || dirty || base?.kind !== "revision" || base.planId !== planId
        || editor?.rootReceiptSha256 !== planJob.resultReceiptSha256 || !receipt(editor.expectedParentReceiptSha256)
        || !editor.ancestry?.some(parent => parent.kind === "plan" && parent.jobId === planJob.jobId)) return null;
    return {planId, revisionJobId: base.jobId, revisionReceiptSha256: editor.expectedParentReceiptSha256};
}

function useProfiles(preferred) {
    const [state, setState] = useState({profiles: [], message: "正在读取本机平台配置…"});
    useEffect(() => {
        const controller = new AbortController();
        api("/api/creation/platform-profiles", {}, {signal: controller.signal}).then(({profiles}) => {
            if (controller.signal.aborted) return;
            const selected = profiles.find(p => p.Platform === preferred) || profiles[0];
            setState({profiles, selected: selected?.Platform, message: profiles.length ? "" : "没有可用的本机平台配置。"});
        }).catch(error => {
            if (!controller.signal.aborted) setState({profiles: [], message: error.message});
        });
        return () => controller.abort();
    }, [preferred]);
    return state;
}

function useQueue(projectId, planJobId, onChanged) {
    const [rows, setRows] = useState({batches: [], message: ""});
    const [refresh, setRefresh] = useState(0);
    const signature = useRef("[]"), notify = useRef(onChanged);
    notify.current = onChanged;
    useEffect(() => {
        const controller = new AbortController();
        let timer;
        const tick = async () => {
            let delay = 7000;
            try {
                const {batches, errors} = await api(path, {projectId, planJobId}, {signal: controller.signal});
                if (controller.signal.aborted) return;
                setRows({batches, message: errors?.length ? `${errors.length} 条队列记录无法读取。` : ""});
                const next = JSON.stringify(batches.map(batch => [batch.batchId, batch.status,
                    batch.items.map(item => Object.keys(stages).map(kind => {
                        const stage = item.stages[kind];
                        return [stage?.jobId, stage?.status];
                    }))]));
                if (signature.current !== next) { signature.current = next; notify.current(); }
                if (batches.some(active)) delay = 1200;
            } catch (error) {
                if (!controller.signal.aborted) setRows(current => ({...current, message: error.message}));
            } finally {
                if (!controller.signal.aborted) timer = setTimeout(tick, delay);
            }
        };
        void tick();
        return () => { clearTimeout(timer); controller.abort(); };
    }, [projectId, planJobId, refresh]);
    return {...rows, reload: () => setRefresh(n => n + 1)};
}

async function requestId(body) {
    const bytes = new TextEncoder().encode(body);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

function useQueueActions(queue, payload, blocked) {
    const [state, setState] = useState({busy: false, message: ""});
    const live = useRef(false), pending = useRef(false), latest = useRef(null);
    const body = JSON.stringify(payload);
    latest.current = {body, blocked};
    useLayoutEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
    const run = async (batchId, action) => {
        const start = !action;
        if (!live.current || pending.current || (start && latest.current.blocked)) return;
        pending.current = true;
        setState({busy: true, message: ""});
        try {
            if (start) {
                const id = await requestId(body);
                if (!live.current || latest.current.blocked || latest.current.body !== body) return;
                await api(path, {}, {body: {requestId: id, ...payload}});
            } else {
                await api(`${path}/${encodeURIComponent(batchId)}/${action}`, {}, {body: {projectId: payload.projectId}});
            }
            if (live.current) queue.reload();
        } catch (error) {
            if (live.current) setState({busy: true, message: error.message});
        } finally {
            pending.current = false;
            if (live.current) setState(current => ({...current, busy: false}));
        }
    };
    return {...state, start: () => run(), command: run};
}

const toggle = (rows, value, checked) => checked ? [...rows, value] : rows.filter(row => row !== value);

export function AdBatches({project, planJob, selectedPlanId, revision, dirty, disabled, onChanged}) {
    const plans = planJob.plans.filter(p => p.ready && Object.hasOwn(planLabels, p.id));
    const [planIds, setPlanIds] = useState(() => [plans.find(p => p.id === selectedPlanId)?.id || plans[0]?.id].filter(Boolean));
    const [styleIds, setStyleIds] = useState(["standard"]);
    const [platform, setPlatform] = useState("");
    const revisionKey = revision ? JSON.stringify(revision) : "";
    const [useRevision, setUseRevision] = useState("");
    useLayoutEffect(() => { setUseRevision(""); }, [revisionKey]);
    const local = useProfiles(planJob.brief.platforms?.[0]);
    const profile = local.profiles.find(p => p.Platform === (platform || local.selected));
    const variants = plans.filter(p => planIds.includes(p.id)).flatMap(({id}) =>
        Object.keys(styles).filter(style => styleIds.includes(style)).map(subtitleStyle => {
            const variant = {planId: id, subtitleStyle};
            if (revision?.planId === id && useRevision === revisionKey) {
                variant.revisionJobId = revision.revisionJobId;
                variant.revisionReceiptSha256 = revision.revisionReceiptSha256;
            }
            return variant;
        }));
    const queue = useQueue(project, planJob.jobId, onChanged);
    const blocked = disabled || dirty || !profile || !variants.length || variants.length > maxVariants;
    const actions = useQueueActions(queue, {
        projectId: project, planJobId: planJob.jobId, expectedPlanReceiptSha256: planJob.resultReceiptSha256, profile, variants,
    }, blocked);
    return html`<section aria-label="广告批量导出">
        <div class="section-label">广告批量导出</div>
        <p class="note">在本机生成所选画面和字幕的组合。关闭页面后，队列会继续生成。</p>
        <div role="group" aria-label="画面方案">
            ${plans.length ? plans.map(plan => html`<label class="check" key=${plan.id}>
                <input type="checkbox" checked=${planIds.includes(plan.id)} disabled=${actions.busy}
                    onChange=${event => setPlanIds(toggle(planIds, plan.id, event.currentTarget.checked))} />${planLabels[plan.id]}
            </label>`) : html`<p class="note">当前没有可批量导出的广告方案。</p>`}
        </div>
        ${revision && planIds.includes(revision.planId) && Object.hasOwn(planLabels, revision.planId) && html`<label class="check">
            <input type="checkbox" checked=${useRevision === revisionKey} disabled=${actions.busy}
                onChange=${event => setUseRevision(event.currentTarget.checked ? revisionKey : "")} />
            ${planLabels[revision.planId]}使用当前已保存的剪辑版本
        </label>`}
        <div role="group" aria-label="字幕样式">
            ${Object.entries(styles).map(([id, label]) => html`<label class="check" key=${id}>
                <input type="checkbox" checked=${styleIds.includes(id)} disabled=${actions.busy}
                    onChange=${event => setStyleIds(toggle(styleIds, id, event.currentTarget.checked))} />${label}
            </label>`)}
        </div>
        ${local.message ? html`<p class="note" role="status">${local.message}</p>` : html`<label class="form-row">目标平台
            <select class="select" value=${profile?.Platform || ""} disabled=${actions.busy} onChange=${event => setPlatform(event.currentTarget.value)}>
                ${local.profiles.map(row => html`<option key=${row.Platform} value=${row.Platform}>${platforms[row.Platform] || row.Platform}</option>`)}
            </select>
        </label>`}
        <p class="note" role="status">已选 ${variants.length} 个组合，每批最多 ${maxVariants} 个。${dirty ? "请先保存剪辑或取消未保存的修改。" : ""}</p>
        <button class="btn" disabled=${blocked || actions.busy} onClick=${actions.start}>加入本机队列</button>
        ${actions.message && html`<p role="status">${actions.message}</p>`}
        ${queue.message && html`<p role="status">${queue.message}</p>`}
        ${queue.batches.map(batch => html`<${BatchRecord} key=${batch.batchId} batch=${batch} project=${project}
            busy=${actions.busy} onCommand=${actions.command} />`)}
    </section>`;
}

function BatchRecord({batch, project, busy, onCommand}) {
    const platform = batch.profile.Platform;
    const done = batch.items.filter(item => item.status === "completed").length;
    return html`<div class="pkg-result" data-batch-id=${batch.batchId}>
        <p>${platforms[platform] || platform} · ${labels[batch.status] || batch.status} · ${done}/${batch.items.length}</p>
        ${batch.error?.message && html`<p class="note">${batch.error.message}</p>`}
        <ul>${batch.items.map(item => html`<${BatchItem} key=${JSON.stringify([item.planId, item.subtitleStyle, item.revisionJobId])}
            item=${item} project=${project} />`)}</ul>
        ${["interrupted", "cancelled"].includes(batch.status) && html`<button class="btn ghost" disabled=${busy} onClick=${() => onCommand(batch.batchId, "resume")}>继续未完成队列</button>`}
        ${batch.status === "failed" && html`<button class="btn ghost" disabled=${busy} onClick=${() => onCommand(batch.batchId, "resume")}>重试失败步骤</button>`}
        ${active(batch) && html`<button class="btn ghost" disabled=${busy} onClick=${() => onCommand(batch.batchId, "cancel")}>停止后续步骤</button>`}
    </div>`;
}

function BatchItem({item, project}) {
    const render = item.stages.render;
    const pkg = item.stages.package;
    return html`<li>
        <div>${planLabels[item.planId]} · ${styles[item.subtitleStyle]}${item.revisionJobId ? " · 已保存剪辑" : ""} · ${labels[item.status] || item.status}</div>
        <div class="note">${Object.entries(stages).map(([kind, label]) => {
            const status = item.stages[kind]?.status;
            return `${label} ${labels[status] || status || "待开始"}`;
        }).join(" / ")}</div>
        ${item.error?.message && html`<p class="note">${item.error.message}</p>`}
        <div class="actions-row">
            ${render?.status === "completed" && render.jobId && html`<a class="btn ghost" href=${studioJobLink(project, render.jobId)} target="_blank" rel="noopener">打开成片</a>`}
            ${pkg?.status === "completed" && pkg.jobId && html`
                <a class="btn ghost" href=${studioJobLink(project, pkg.jobId)} target="_blank" rel="noopener">打开平台包</a>
                <a class="btn ghost" href=${`/api/creation/jobs/${encodeURIComponent(pkg.jobId)}/package-files/package.zip?download=1`} download>下载 ZIP</a>`}
        </div>
    </li>`;
}
