// Dynamic alternatives use the saved brief and candidate basket. Within the monthly AI budget
// (2026-11-11) one click sends; past it the old per-call confirmation applies.
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
            if (!quote.budget?.eligible || !available) return;
            if (!remember(identity, quote)) throw new Error("无法保存结果恢复入口，已阻止发送，请允许浏览器本地存储");
            update({sent: true, busy: "execute"});
            try { update({result: await post({action: "execute_budget", preparedHash: quote.preparedHash, snapshotFingerprint: quote.snapshotFingerprint})}); }
            catch (error) {
                // A 400 can also be a result-write failure after sending. Keep recovery identity.
                throw new Error(`${error.message}。可读取本次结果，不会重复付费。`);
            }
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

export function PlanReasoningPanel({project, jobId, disabled, onAdopt, autoStart = false, onAutoStarted = () => {}}) {
    const flow = usePlanReasoning(project, jobId, disabled, onAdopt);
    const panel = useRef(null);
    // Started by the user's "生成方案" click; runs once per plan job, only when a key is set.
    useEffect(() => {
        if (!autoStart || disabled || !flow.available || flow.quote || flow.busy) return;
        if (panel.current) panel.current.open = true;
        onAutoStarted(); void flow.prepare();
    }, [autoStart, disabled, flow.available]);
    const history = records().filter(r => r.key === flow.identity);
    const response = flow.result?.proposal?.response;
    return html`<details class="group dynamic-planning" aria-label="AI动态策划" ref=${panel}>
        <summary>AI动态策划（预算内自动）</summary>
        <p class="hint">按此任务已保存的需求与候选素材重新策划，不使用尚未生成的表单修改。只发送文字，模型没有观看画面；声音仍用免费本机语音。</p>
        ${disabled ? html`<p class="hint">请先保存或撤销镜头修改，并完成当前任务。</p>` : null}
        <button class="btn ghost" disabled=${disabled || !!flow.busy} onClick=${flow.prepare}>${flow.busy === "execute" ? "AI 正在策划…" : "让 AI 重新策划"}</button>
        ${!flow.available ? html`<p class="hint">未配置 DEEPSEEK_API_KEY，可以准备文字，暂不能发送。</p>` : null}
        ${history.length ? html`<details><summary>已确认策划的结果记录（${history.length}）</summary>
            ${history.map(saved => html`<div><span class="hint">${saved.at}</span><button class="btn ghost" disabled=${disabled || !!flow.busy} onClick=${() => flow.recover(saved)}>读取策划结果（不调用模型）</button></div>`)}
        </details>` : null}
        ${flow.quote ? html`<p class="hint" aria-label="AI预算">${client.budgetText(flow.quote.budget)}${flow.quote.budget && !flow.quote.budget.eligible ? `${flow.quote.budget.reason}，这次需要你确认。` : ""}</p>
            ${flow.quote.knowledge?.length === 0 ? html`<p class="hint">未命中当前同游戏的登记知识；本次未发送知识资料。按主题/目标字面匹配，长中文词可能零命中。</p>` : null}
            ${flow.quote.knowledge ? html`<details><summary>本次登记知识（${flow.quote.knowledge.length} 条）</summary><p class="hint">按游戏及主题/目标字面匹配；长中文词可能零命中。资料与引用未做真实性或语义核验。</p>${flow.quote.knowledge.map(entry => html`<p style="overflow-wrap:anywhere">${entry.title} · ${entry.source.kind} · ${entry.source.label} · ${entry.createdAt} · ${entry.entryId}</p><blockquote>${entry.text}</blockquote>`)}</details>` : null}
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
        <strong>${plan.title}</strong><p class="hint">${plan.structure}</p><${KnowledgeUses} uses=${plan.knowledgeUses} />
        <p>${(plan.actualFrames / preview.fps).toFixed(1)} 秒 / 目标 ${(plan.targetFrames / preview.fps).toFixed(1)} 秒</p>
        ${plan.durationStatus !== "target-met" ? html`<p class="note">${plan.durationStatus === "insufficient-candidate-pool" ? "候选素材不足" : "本案选材不足"}：差 ${(plan.frameGap / preview.fps).toFixed(1)} 秒，不会凭空补镜头。</p>` : null}
        ${plan.gaps?.length ? html`<ul>${plan.gaps.map(gap => html`<li>${gap}</li>`)}</ul>` : null}
        <${TopicCoverage} plan=${plan} />
        <ol>${plan.segments.map(segment => html`<li>${segment.role || "镜头"} · ${(segment.startUs / 1e6).toFixed(1)}–${(segment.endUs / 1e6).toFixed(1)} 秒 <span class="hint">${segment.scriptDraft}</span></li>`)}</ol>
    </section>`)}</div>`;
}

export function KnowledgeUses({uses}) {
    if (!uses?.length) return null;
    return html`<details class="knowledge-uses"><summary>登记知识引用（未核验真实性与语义）</summary>${uses.map(use => html`<div>
        <p>策划原句：${use.structureQuote}</p><blockquote>资料原文：${use.text}</blockquote>
        <p class="hint" style="overflow-wrap:anywhere">登记来源：${use.title} · ${use.source.kind} · ${use.source.label} · ${use.createdAt} · ${use.entryId}</p>
    </div>`)}</details>`;
}

export function TopicCoverage({plan}) {
    if (!plan?.topicCoverage?.length) return null;
    return html`<details class="topic-coverage" aria-label="方案主题安排"><summary>方案主题安排（AI 建议，需预览核对）</summary>
        <p class="hint">以下对应原方案镜头编号；手动改镜头后请重新核对。引用的是已保存的画面描述，不代表已经确认画面能讲清这个主题。</p>
        ${plan.topicCoverage.map(row => html`<div class="field"><div class="k">${row.topic}</div>
            <p>${row.status === "missing" ? "缺少对应画面，可补素材或调整表达" : `建议使用镜头 ${row.shotIndexes.join("、")}`}</p>
            ${row.shotIndexes.map(index => html`<div>${(plan.segments[index - 1]?.topicUses || []).filter(use => use.topic === row.topic).map(use => html`<p>镜头 ${index}：${use.rationale}</p><blockquote>摘要原文：${use.observationQuote}</blockquote>`)}</div>`)}
        </div>`)}
    </details>`;
}
