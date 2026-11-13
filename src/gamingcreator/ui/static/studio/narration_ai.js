import {h} from "../vendor/preact.module.js";
import {useEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import {api, budgetText} from "./api.js";
const html = htm.bind(h);
const post = (body) => api("/api/creation/reasoning", {}, {body});
const initial = () => ({quote: null, script: null, busy: false, sent: false, message: ""});
const records = () => { try { return JSON.parse(localStorage.getItem("studio-narration-ai-v1") || "{}"); } catch { return {}; } };
function remember(scope, quote) {
    const record = {scope, quote: Object.fromEntries(["preparedHash", "snapshotFingerprint", "maxCostCny"].map(k => [k, quote[k]]))};
    try { localStorage.setItem("studio-narration-ai-v1", JSON.stringify({...records(), [scope]: record})); }
    catch { throw new Error("无法保存 AI 恢复入口，已阻止发送；仍可使用本机草稿。"); }
}

export function useNarrationAI({editing, project, text, fallback, adopt}) {
    const scope = JSON.stringify([project, editing.base?.jobId, editing.base?.planId, editing.editor?.expectedParentReceiptSha256]);
    const key = JSON.stringify([scope, editing.dirty, editing.status, editing.clips, text]);
    const live = useRef({key, epoch: 0, mounted: true});
    if (live.current.key !== key) { live.current.key = key; live.current.epoch++; }
    const epoch = live.current.epoch;
    const valid = () => live.current.mounted && live.current.epoch === epoch;
    const [state, setState] = useState(initial);
    const patch = (value) => { if (valid()) setState(s => ({...s, ...value})); };
    useEffect(() => { setState(initial()); }, [key]);
    useEffect(() => () => { live.current.mounted = false; }, []);
    const ready = editing.status === "ready" && !editing.dirty;
    const take = (data) => {
        if (!valid()) return;
        const script = data.status === "completed" && data.purpose === "narration" ? data.script : null;
        patch({script, message: script?.text ? "AI 草稿待预览核对；引文只证明来源，请核对语义。" : "没有有效 AI 输出，可用规则模板继续；本次不会自动重试。"});
    };
    const send = async (quote, explicit = false) => {
        if (!ready || !valid() || state.sent) return;
        remember(scope, quote);
        patch({sent: true});
        take(await post({action: explicit ? "execute" : "execute_budget", preparedHash: quote.preparedHash, snapshotFingerprint: quote.snapshotFingerprint,
            ...(explicit ? {confirmedMaxCny: quote.maxCostCny} : {})}));
    };
    const run = async (task) => {
        patch({busy: true});
        try { await task(); }
        catch (error) { patch({message: `${error.message}。若已发送，仅可读取结果，不会自动重复付费；也可继续本机草稿。`}); }
        finally { patch({busy: false}); }
    };
    const start = () => ready && !state.busy && run(async () => {
        if (records()[scope]) return patch({sent: true, message: "已有 AI 调用恢复入口，请先只读恢复；可继续使用规则模板。"});
        const config = await api("/api/creation/reasoning/config");
        if (!valid()) return;
        if (!config.available) { patch({message: "未配置文本模型，使用规则模板兜底。"}); return fallback(); }
        const quote = await post({action: "prepare_narration", jobId: editing.base.jobId, planId: editing.base.planId});
        if (!valid()) return;
        patch({quote});
        if (quote.budget?.eligible) await send(quote);
        else patch({message: "超出自动 AI 预算，可使用规则模板，或明确确认本次费用上限后发送。"});
    });
    const saved = records()[scope];
    const recover = () => run(async () => {
        patch({sent: true, quote: saved.quote});
        take(await post({action: "result", preparedHash: saved.quote.preparedHash}));
    });
    const view = html`<div aria-label="AI旁白预览">
        ${!ready && html`<p class="hint">请先保存镜头版本，再起草或填入 AI 旁白。</p>`}
        ${state.message && html`<p role="status">${state.message}</p>`}
        ${state.quote && html`<p class="hint">${budgetText(state.quote.budget)}</p>`}
        ${saved && html`<button class="btn ghost" disabled=${state.busy} onClick=${recover}>读取上次 AI 旁白结果（不重新调用）</button>`}
        ${state.quote && !state.quote.budget?.eligible && !state.sent && html`<button class="btn ghost" disabled=${!ready || state.busy} onClick=${() => {
            if (confirm(`确认本次 AI 文字调用最多 ¥${state.quote.maxCostCny}？`)) void run(() => send(state.quote, true));
        }}>确认费用上限 ¥${state.quote.maxCostCny} 并起草</button>`}
        ${(saved || state.quote || state.message) && html`<button class="btn ghost" disabled=${state.busy} onClick=${fallback}>使用规则模板旁白</button>`}
        ${state.script?.text && html`<div class="rules-result"><p>AI 草稿待预览核对</p><p>${state.script.text}</p>
            <p>${[...state.script.text].length} 字 / 上限 ${state.script.budgetCharacters} 字 · 约 ${Number(state.script.estimatedSeconds).toFixed(1)} 秒</p>
            <ul>${(state.script.lines || []).map(line => html`<li>${line.text}<blockquote>镜头原描述：${line.observationQuote}</blockquote>
                ${(line.knowledgeUses || []).map(use => html`<p>知识引文：${use.quote}（${state.script.citations?.find(c => c.entryId === use.entryId)?.title || "登记资料"}）</p>`)}</li>`)}</ul>
            <button class="btn" disabled=${!ready || state.busy} onClick=${() => { if (valid()) adopt(state.script); }}>填入旁白稿</button></div>`}
    </div>`;
    return {start, view, busy: state.busy};
}
