// Text-model proposals are prepared locally, explicitly confirmed, previewed, then validated.
import {h} from "../vendor/preact.module.js";
import {useEffect, useLayoutEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";

const html = htm.bind(h);
const empty = () => ({quote: null, result: null, busy: "", message: "", confirmed: false, sent: false});
const post = (body) => client.api("/api/creation/reasoning", {}, {body});
const STORE = "studio-reasoning-attempts-v1";
const parentKey = (editing) => JSON.stringify([editing.project, editing.base?.jobId, editing.base?.planId, editing.editor?.expectedParentReceiptSha256]);
const attempts = () => { try { const data = JSON.parse(localStorage.getItem(STORE) || "[]"); return Array.isArray(data) ? data : []; } catch { return []; } };
function remember(editing, quote, text) {
    const saved = {parentKey: parentKey(editing), text, at: new Date().toISOString(), quote: Object.fromEntries(["preparedHash", "snapshotFingerprint", "maxCostCny", "requestedModel", "priceVersion"].map((k) => [k, quote[k]]))};
    try { localStorage.setItem(STORE, JSON.stringify([saved, ...attempts().filter((a) => a.quote.preparedHash !== quote.preparedHash)].slice(0, 20))); return true; }
    catch { return false; }
}

function useReasoning(editing, text, onPreview) {
    const [state, setState] = useState(empty);
    const [available, setAvailable] = useState(false);
    const key = JSON.stringify([editing.project, editing.base, editing.editor?.expectedParentReceiptSha256, editing.dirty, editing.rows(), text]);
    const live = useRef({key, generation: 0, mounted: true});
    if (live.current.key !== key) { live.current.key = key; live.current.generation += 1; }
    const generation = live.current.generation;
    useLayoutEffect(() => { setState(empty()); onPreview(null); }, [key]);
    useLayoutEffect(() => () => { live.current.mounted = false; onPreview(null); }, []);
    useEffect(() => {
        let active = true;
        client.api("/api/creation/reasoning/config").then((data) => { if (active) setAvailable(data.available === true); }).catch(() => {});
        return () => { active = false; };
    }, []);
    const valid = () => live.current.mounted && live.current.generation === generation;
    const update = (patch) => { if (valid()) setState((s) => ({...s, ...patch})); };
    return {...state, available, valid, update, key};
}

function reasoningActions(flow, editing, text, onPreview) {
    const identity = {jobId: editing.base?.jobId, planId: editing.base?.planId};
    const ready = editing.status === "ready" && !editing.dirty;
    const show = (data) => {
        if (!flow.valid()) return;
        const response = data.proposal?.response;
        flow.update({result: data, message: response?.message || "调用未产生可用建议；失败或未知费用不会自动重试。"});
        onPreview(response?.kind === "edit_proposal" ? response.clips : null);
    };
    const run = async (kind, task) => {
        flow.update({busy: kind, message: ""});
        try { await task(); } catch (error) { flow.update({message: `${error.message}${kind === "execute" ? "。结果可能尚未取回，请读取本次结果，勿重复付费。" : ""}`}); }
        finally { flow.update({busy: ""}); }
    };
    return {
        prepare: () => ready && text.trim() && run("prepare", async () => {
            const quote = await post({action: "prepare", ...identity, instruction: text.trim()});
            flow.update({quote, result: null, confirmed: false, sent: false}); if (flow.valid()) onPreview(null);
        }),
        execute: () => {
            if (!ready || !flow.quote || !flow.confirmed || flow.sent || !flow.available) return;
            if (!remember(editing, flow.quote, text)) return flow.update({message: "无法保存本次结果的恢复入口，已阻止发送。请允许浏览器本地存储后再试"});
            return run("execute", async () => {
                flow.update({sent: true, confirmed: false});
                show(await post({action: "execute", preparedHash: flow.quote.preparedHash, snapshotFingerprint: flow.quote.snapshotFingerprint, confirmedMaxCny: flow.quote.maxCostCny}));
            });
        },
        recover: () => flow.quote && run("result", async () => show(await post({action: "result", preparedHash: flow.quote.preparedHash}))),
        restore: (saved) => ready && saved.parentKey === parentKey(editing) && run("result", async () => {
            flow.update({quote: saved.quote, result: null, sent: true, confirmed: false}); onPreview(null);
            show(await post({action: "result", preparedHash: saved.quote.preparedHash}));
        }),
        apply: () => ready && flow.result?.proposal?.response.kind === "edit_proposal" && run("validate", async () => {
            const data = await post({action: "validate", preparedHash: flow.quote.preparedHash, ...identity, expectedParentReceiptSha256: editing.editor.expectedParentReceiptSha256});
            if (!flow.valid()) return;
            onPreview(null); editing.ops.apply(data.clips);
        }),
        discard: () => { flow.update(empty()); onPreview(null); },
    };
}

export function ReasoningDock({editing, onPreview}) {
    const [text, setText] = useState("");
    const [restoring, setRestoring] = useState(null);
    const flow = useReasoning(editing, text, onPreview);
    const actions = reasoningActions(flow, editing, text, onPreview);
    const ready = editing.status === "ready" && !editing.dirty;
    const identity = parentKey(editing);
    useEffect(() => {
        if (!restoring || text !== restoring.text) return;
        setRestoring(null);
        if (restoring.parentKey === identity) void actions.restore(restoring);
    }, [restoring, text, identity]);
    const history = attempts().filter((a) => a.parentKey === identity);
    const response = flow.result?.proposal?.response;
    return html`<section class="dock reasoning" aria-label="AI创作对话">
        <form class="reasoning-input" onSubmit=${(e) => { e.preventDefault(); if (!flow.busy) void actions.prepare(); }}>
            <strong>AI创作对话</strong><input class="input" aria-label="创作对话需求" value=${text} disabled=${!ready || !!flow.busy}
                placeholder="描述想改变的节奏或镜头；不清楚时会先询问" onInput=${(e) => setText(e.currentTarget.value)} />
            <button class="btn ghost" disabled=${!ready || !text.trim() || !!flow.busy}>准备请求（不发送）</button>
        </form>
        <p class="hint">${!ready ? "请先保存当前镜头和声音修改，再请求模型建议。" : "仅发送已保存镜头的文字和时间；模型没有观看画面。旁白仍用免费本机语音。"}
            ${!flow.available ? " 文本模型尚未配置 DEEPSEEK_API_KEY，不能发送；可先查看请求。" : ""}</p>
        ${history.length ? html`<details class="reasoning-history"><summary>已确认请求的结果记录（${history.length}）</summary>
            ${history.map((saved) => html`<div class="actions-row"><span>${saved.at} · ${saved.text.slice(0, 50)}</span>
                <button type="button" class="btn ghost" disabled=${!ready || !!flow.busy} onClick=${() => { setText(saved.text); setRestoring(saved); }}>读取已确认结果（不调用模型）</button></div>`)}
            <p class="hint">切换模式或修改镜头不会清除已发送记录；回到对应的已保存版本后可恢复。未完成或失败的请求不会自动重发。</p>
        </details>` : null}
        ${flow.quote && html`<div class="reasoning-quote">
            <p>DeepSeek 文本模型 · 本次费用上限 ¥${flow.quote.maxCostCny}（完整上下文的保守上界，非实际费用）</p>
            <details><summary>查看将发送的文字</summary><pre>${flow.quote.payloadPreview ? JSON.stringify(flow.quote.payloadPreview, null, 2) : JSON.stringify({instruction: text, clips: editing.clips.map((c) => ({clipId: c.clipId, startUs: c.startUs, endUs: c.endUs, scriptDraft: c.scriptDraft}))}, null, 2)}</pre></details>
            ${!flow.sent && html`<label class="check"><input type="checkbox" aria-label="同意本次文字发送和费用上限" checked=${flow.confirmed} disabled=${!!flow.busy}
                onChange=${(e) => flow.update({confirmed: e.currentTarget.checked})} />我同意发送以上文字，并确认本次费用上限。</label>
                <button type="button" class="btn" disabled=${!ready || !flow.confirmed || !flow.available || !!flow.busy} onClick=${actions.execute}>确认本次调用（最高 ¥${flow.quote.maxCostCny}）</button>`}
            ${flow.sent && !flow.result && html`<button type="button" class="btn ghost" disabled=${!!flow.busy} onClick=${actions.recover}>读取本次结果（不重新调用）</button>`}
        </div>`}
        ${flow.message && html`<p class="reasoning-message" role="status">${flow.message}</p>`}
        ${flow.result?.billing && html`<p class="hint" aria-label="本次文本模型费用">${flow.result.billing.unresolvedAttempts || flow.result.billing.knownCostCny === null
            ? `实际费用未知，仍保留 ¥${flow.result.billing.reservedCny} 的费用占用；不会自动重试。`
            : `${flow.result.metadata?.usage?.cost_status === "confirmed" ? "已确认费用" : "按价目估算费用"} ¥${flow.result.billing.knownCostCny}，以提供方账单为准。`}</p>`}
        ${response?.questions?.length ? html`<ul>${response.questions.map((q) => html`<li>${q}</li>`)}</ul>` : null}
        ${response?.kind === "edit_proposal" && html`<div class="actions-row"><span>改动预览：${flow.result.proposal.before_seconds.toFixed(1)} → ${flow.result.proposal.after_seconds.toFixed(1)} 秒；尚未应用。</span>
            <button type="button" class="btn" disabled=${!ready || !!flow.busy} onClick=${actions.apply}>应用AI建议</button></div>`}
        ${flow.quote && html`<button type="button" class="btn ghost" disabled=${!!flow.busy} onClick=${actions.discard}>关闭本次建议</button>`}
    </section>`;
}
