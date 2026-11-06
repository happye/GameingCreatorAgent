// Dynamic alternatives use the saved brief and candidate basket, with one confirmed send.
import {h} from "../vendor/preact.module.js";
import {useEffect, useLayoutEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";

const html = htm.bind(h);
const STORE = "studio-plan-reasoning-v1";
const empty = () => ({quote: null, result: null, sent: false, confirmed: false, busy: "", message: ""});
const post = body => client.api("/api/creation/reasoning", {}, {body});
function records() {
    try { const value = JSON.parse(localStorage.getItem(STORE) || "[]"); return Array.isArray(value) ? value.filter(r => typeof r?.quote?.preparedHash === "string") : []; }
    catch { return []; }
}
function remember(key, quote) {
    const saved = {key, at: new Date().toISOString(), quote: Object.fromEntries(["preparedHash", "snapshotFingerprint", "maxCostCny", "requestedModel", "purpose"].map(k => [k, quote[k]]))};
    try { localStorage.setItem(STORE, JSON.stringify([saved, ...records().filter(r => r.quote.preparedHash !== quote.preparedHash)].slice(0, 20))); return true; }
    catch { return false; }
}

function usePlanReasoning(project, jobId, disabled, onAdopt) {
    const [state, setState] = useState(empty);
    const [available, setAvailable] = useState(false);
    const identity = JSON.stringify([project, jobId]);
    const key = JSON.stringify([identity, disabled]);
    const live = useRef({key, generation: 0, mounted: true});
    if (live.current.key !== key) { live.current.key = key; live.current.generation += 1; }
    const generation = live.current.generation;
    const valid = () => live.current.mounted && live.current.generation === generation;
    const update = patch => { if (valid()) setState(s => ({...s, ...patch})); };
    useLayoutEffect(() => { setState(empty()); }, [key]);
    useLayoutEffect(() => () => { live.current.mounted = false; }, []);
    useEffect(() => {
        let active = true;
        client.api("/api/creation/reasoning/config").then(data => { if (active) setAvailable(data.available === true); }).catch(() => {});
        return () => { active = false; };
    }, []);
    const run = async (busy, task) => {
        if (disabled || !jobId || state.busy) return;
        update({busy, message: ""});
        try { await task(); } catch (error) { update({message: `${error.message}${busy === "execute" ? "。可读取本次结果，不要重复确认付费。" : ""}`}); }
        finally { update({busy: ""}); }
    };
    return {...state, available, identity, update,
        prepare: () => run("prepare", async () => {
            const quote = await post({action: "prepare_plan", jobId});
            update({quote, result: null, sent: false, confirmed: false});
        }),
        execute: () => state.quote && state.confirmed && !state.sent && available && run("execute", async () => {
            if (!remember(identity, state.quote)) throw new Error("无法保存结果恢复入口，已阻止发送，请允许浏览器本地存储");
            update({sent: true, confirmed: false});
            const result = await post({action: "execute", preparedHash: state.quote.preparedHash, snapshotFingerprint: state.quote.snapshotFingerprint, confirmedMaxCny: state.quote.maxCostCny});
            update({result});
        }),
        recover: saved => run("result", async () => {
            if (saved.key !== identity) return;
            update({quote: saved.quote, result: null, sent: true, confirmed: false});
            const result = await post({action: "result", preparedHash: saved.quote.preparedHash});
            update({result});
        }),
        adopt: () => state.result?.planPreview?.plans?.length > 0 && run("adopt", async () => {
            const accepted = await post({action: "adopt_plan", preparedHash: state.quote.preparedHash});
            if (valid()) await onAdopt(accepted.jobId);
        }),
    };
}

export function PlanReasoningPanel({project, jobId, disabled, onAdopt}) {
    const flow = usePlanReasoning(project, jobId, disabled, onAdopt);
    const history = records().filter(r => r.key === flow.identity);
    const response = flow.result?.proposal?.response;
    return html`<details class="group dynamic-planning" aria-label="AI动态策划">
        <summary>AI动态策划（按次确认）</summary>
        <p class="hint">按此任务已保存的需求与候选素材重新策划，不使用尚未生成的表单修改。只发送文字，模型没有观看画面；声音仍用免费本机语音。</p>
        ${disabled ? html`<p class="hint">请先保存或撤销镜头修改，并完成当前任务。</p>` : null}
        <button class="btn ghost" disabled=${disabled || !!flow.busy} onClick=${flow.prepare}>准备动态策划（不发送）</button>
        ${!flow.available ? html`<p class="hint">未配置 DEEPSEEK_API_KEY，可以准备文字，暂不能发送。</p>` : null}
        ${history.length ? html`<details><summary>已确认策划的结果记录（${history.length}）</summary>
            ${history.map(saved => html`<div><span class="hint">${saved.at}</span><button class="btn ghost" disabled=${disabled || !!flow.busy} onClick=${() => flow.recover(saved)}>读取策划结果（不调用模型）</button></div>`)}
        </details>` : null}
        ${flow.quote ? html`<p class="hint">费用上限 ¥${flow.quote.maxCostCny}，按完整上下文保守预留，非实际费用。</p>
            ${flow.quote.originalRequest ? html`<details><summary>本次已保存需求</summary><pre>${JSON.stringify(flow.quote.originalRequest, null, 2)}</pre></details>` : null}
            ${flow.quote.payloadPreview ? html`<details><summary>本次将发送的文字</summary><pre>${JSON.stringify(flow.quote.payloadPreview, null, 2)}</pre></details>` : null}
            ${!flow.sent ? html`<label class="check"><input type="checkbox" aria-label="同意本次动态策划费用" checked=${flow.confirmed} disabled=${disabled || !!flow.busy} onChange=${e => flow.update({confirmed: e.currentTarget.checked})} />同意发送文字并确认本次费用上限</label>
                <button class="btn" disabled=${disabled || !!flow.busy || !flow.confirmed || !flow.available} onClick=${flow.execute}>确认动态策划（最高 ¥${flow.quote.maxCostCny}）</button>`
                : !flow.result ? html`<button class="btn ghost" disabled=${disabled || !!flow.busy} onClick=${() => flow.recover({key: flow.identity, quote: flow.quote})}>读取本次策划结果（不重新调用）</button>` : null}` : null}
        ${flow.message ? html`<p class="note" role="status">${flow.message}</p>` : null}
        ${response?.questions?.length ? html`<ul>${response.questions.map(q => html`<li>${q}</li>`)}</ul>` : null}
        ${flow.result?.status && flow.result.status !== "completed" ? html`<p class="note">策划未完成（${flow.result.status}），不会自动重试或重新付费。</p>` : null}
        ${flow.result?.billing ? html`<p class="hint">${flow.result.billing.unresolvedAttempts || flow.result.billing.knownCostCny === null
            ? `实际费用未知，保留 ¥${flow.result.billing.reservedCny} 的费用占用。`
            : `按价目估算费用 ¥${flow.result.billing.knownCostCny}，以提供方账单为准。`}</p>` : null}
        ${flow.result?.planPreview?.plans?.length > 0 ? html`<${PlanPreview} preview=${flow.result.planPreview} />
            <button class="btn" disabled=${disabled || !!flow.busy} onClick=${flow.adopt}>采用这些方案（不再调用模型）</button>` : null}
    </details>`;
}

function PlanPreview({preview}) {
    return html`<div class="dynamic-plan-preview" aria-label="动态方案预览">${preview.plans.map(plan => html`<section class="field">
        <strong>${plan.title}</strong><p class="hint">${plan.structure}</p>
        <p>${(plan.actualFrames / preview.fps).toFixed(1)} 秒 / 目标 ${(plan.targetFrames / preview.fps).toFixed(1)} 秒</p>
        ${plan.durationStatus !== "target-met" ? html`<p class="note">${plan.durationStatus === "insufficient-candidate-pool" ? "候选素材不足" : "本案选材不足"}：差 ${(plan.frameGap / preview.fps).toFixed(1)} 秒，不会凭空补镜头。</p>` : null}
        ${plan.gaps?.length ? html`<ul>${plan.gaps.map(gap => html`<li>${gap}</li>`)}</ul>` : null}
        <ol>${plan.segments.map(segment => html`<li>${segment.role || "镜头"} · ${(segment.startUs / 1e6).toFixed(1)}–${(segment.endUs / 1e6).toFixed(1)} 秒 <span class="hint">${segment.scriptDraft}</span></li>`)}</ol>
    </section>`)}</div>`;
}
