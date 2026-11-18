import {h} from "../vendor/preact.module.js";
import {useEffect, useLayoutEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import {api} from "./api.js";

const html = htm.bind(h);
const path = "/api/creation/package-batches";
const active = row => ["pending", "running", "cancelling"].includes(row.status);
const names = {pending: "等待", running: "生成中", completed: "完成", interrupted: "等待恢复", cancelled: "已停止后续", cancelling: "正在停止后续", partial: "部分完成", failed: "失败"};
const platforms = {bilibili: "B站", douyin: "抖音", kuaishou: "快手", xiaohongshu: "小红书"};
async function requestId(body) {
    const bytes = new TextEncoder().encode(JSON.stringify(body));
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

export function usePackageBatches({project, pub, profiles, selected, disabled, startBlocked, onChanged}) {
    const key = JSON.stringify([project, pub?.publicationJobId, pub?.publicationReceiptSha256]);
    const [state, setState] = useState({key, batches: [], busy: false, error: ""});
    const latest = useRef(null), refresh = useRef(null), signature = useRef("");
    latest.current = {key, disabled, startBlocked, onChanged};
    useLayoutEffect(() => { signature.current = ""; setState({key, batches: [], busy: false, error: ""}); }, [key]);
    useEffect(() => {
        if (!pub?.publicationJobId) return;
        const controller = new AbortController(); let stopped = false, timer;
        const tick = async () => {
            let running = false;
            try {
                const result = await api(path, {projectId: project, publicationJobId: pub.publicationJobId}, {signal: controller.signal});
                if (stopped || latest.current.key !== key) return;
                setState(s => ({...s, batches: result.batches, error: result.errors?.length ? `${result.errors.length} 条队列记录无法读取，原记录已保留。` : ""}));
                const next = JSON.stringify(result.batches.map(b => [b.batchId, b.status, b.items.map(i => [i.jobId, i.status, i.attempt])]));
                if (signature.current !== next) { signature.current = next; latest.current.onChanged(); }
                running = result.batches.some(active);
            } catch (e) {
                if (!stopped && latest.current.key === key) setState(s => ({...s, error: e.message}));
            } finally { if (!stopped) { clearTimeout(timer); timer = setTimeout(tick, running ? 1200 : 7000); } }
        };
        refresh.current = tick; void tick();
        return () => { stopped = true; clearTimeout(timer); controller.abort(); refresh.current = null; };
    }, [key]);
    const run = async (url, body) => {
        if (latest.current.key !== key || latest.current.disabled || state.busy || (url === path && latest.current.startBlocked)) return;
        setState(s => ({...s, busy: true, error: ""}));
        try {
            await api(url, {}, {body});
            if (latest.current.key === key) await refresh.current?.();
        } catch (e) { if (latest.current.key === key) setState(s => ({...s, error: `${e.message}；可从队列记录恢复，请勿重复创建。`})); }
        finally { if (latest.current.key === key) setState(s => ({...s, busy: false})); }
    };
    const batches = state.key === key ? state.batches : [];
    const start = async () => {
        const body = {projectId: project, publicationJobId: pub.publicationJobId,
            expectedPublicationReceiptSha256: pub.publicationReceiptSha256,
            profiles: profiles.filter(p => selected.includes(p.Platform))};
        const id = await requestId(body);
        await run(path, {requestId: id, ...body});
    };
    const command = (id, action) => run(`${path}/${encodeURIComponent(id)}/${action}`, {projectId: project});
    return {start, busy: state.key === key && state.busy, running: batches.some(active),
        view: html`<${BatchRecords} batches=${batches} error=${state.key === key ? state.error : ""} fps=${pub?.fps?.numerator / pub?.fps?.denominator}
            disabled=${disabled || state.busy} onCommand=${command} />`};
}

function BatchRecords({batches, error, disabled, onCommand, fps}) {
    return html`<section aria-label="持久平台队列">
        <p class="hint">选定平台后一次加入本机队列。关闭页面会继续生成；重启工作台后可继续未完成队列。停止只影响后续平台，当前包会收尾。</p>
        ${error && html`<p role="status">${error}</p>`}
        ${batches.map(batch => html`<div class="pkg-result" data-batch-id=${batch.batchId}>
            <p>平台队列 · ${names[batch.status] || batch.status} · ${batch.items.filter(i => i.status === "completed").length}/${batch.items.length}</p>
            <ul>${batch.items.map(item => {
                const {variant, publicationText} = item.profile.Fields;
                return html`<li>${platforms[item.profile.Platform] || item.profile.Platform}${variant ? ` · 短版 ${(variant.durationFrames / fps).toFixed(2)} 秒` : ""} · ${names[item.status] || item.status}${item.error?.message ? `：${item.error.message}` : ""}
                    ${variant?.startFrame && html`<span> · 原成片 ${(variant.startFrame / fps).toFixed(2)}–${((variant.startFrame + variant.durationFrames) / fps).toFixed(2)} 秒</span>`}
                    ${publicationText?.opening && html`<span> · 开场：${publicationText.opening}</span>`}
                    ${publicationText?.closing && html`<span> · 结尾：${publicationText.closing}</span>`}</li>`;
            })}</ul>
            ${["interrupted", "cancelled"].includes(batch.status) && html`<button class="btn ghost" disabled=${disabled} onClick=${() => onCommand(batch.batchId, "resume")}>继续未完成队列</button>`}
            ${active(batch) && html`<button class="btn ghost" disabled=${disabled} onClick=${() => onCommand(batch.batchId, "cancel")}>停止后续平台</button>`}
        </div>`)}
    </section>`;
}
