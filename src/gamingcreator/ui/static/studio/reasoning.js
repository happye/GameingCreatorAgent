// Text-model proposals: prepared locally, sent within the monthly AI budget (2026-11-11) or
// explicitly confirmed past it, previewed, then validated.
import {h} from "../vendor/preact.module.js";
import {useEffect, useLayoutEffect, useMemo, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";

import {clipFrames} from "./preview.js";
import {projectCompanions} from "./timeline_companions.js";

const html = htm.bind(h);
export function overlayProposalItems(editing, patch) {
    if (!patch || Object.keys(patch).sort().join() !== "endFrame,fadeOutFrames,overlayId") throw new Error("图层建议格式无效");
    const item = editing.overlays.find((row) => row.overlayId === patch.overlayId);
    const total = editing.clips.reduce((n, row) => n + clipFrames(row, editing.editor.fps) - (row.transitionIn?.frames || 0), 0);
    if (!item || !editing.overlayAssets.some((a) => a.assetId === item.assetId && a.assetReceiptSha256 === item.assetReceiptSha256)
        || !Number.isSafeInteger(patch.endFrame) || patch.endFrame <= item.startFrame || patch.endFrame > total
        || !Number.isSafeInteger(patch.fadeOutFrames) || patch.fadeOutFrames < 0
        || item.fadeInFrames + patch.fadeOutFrames > patch.endFrame - item.startFrame) throw new Error("图层建议超出当前图层范围");
    return editing.overlays.map((row) => row === item ? {...row, endFrame: patch.endFrame, fadeOutFrames: patch.fadeOutFrames} : row);
}
const noop = () => {};
const empty = () => ({quote: null, result: null, busy: "", message: "", confirmed: false, sent: false, projection: null});
const post = (body) => client.api("/api/creation/reasoning", {}, {body});
const STORE = "studio-reasoning-attempts-v1";
const parentKey = (editing) => JSON.stringify([editing.project, editing.base?.jobId, editing.base?.planId, editing.editor?.expectedParentReceiptSha256]);
const attempts = () => { try { const data = JSON.parse(localStorage.getItem(STORE) || "[]"); return Array.isArray(data) ? data : []; } catch { return []; } };
function remember(editing, quote, text) {
    const saved = {parentKey: parentKey(editing), text, at: new Date().toISOString(), quote: Object.fromEntries(["preparedHash", "snapshotFingerprint", "maxCostCny", "requestedModel", "priceVersion"].map((k) => [k, quote[k]]))};
    try { localStorage.setItem(STORE, JSON.stringify([saved, ...attempts().filter((a) => a.quote.preparedHash !== quote.preparedHash)].slice(0, 20))); return true; }
    catch { return false; }
}

function useReasoning(editing, text, onPreview, onOverlayPreview, mode) {
    const [state, setState] = useState(empty);
    const [available, setAvailable] = useState(false);
    const key = JSON.stringify([mode, editing.insertions, editing.project, editing.base, editing.editor?.expectedParentReceiptSha256, editing.status, editing.dirty, editing.rows(), editing.subtitleOverrides, editing.overlays, editing.audio, editing.replacements, editing.editEpoch, text]);
    const live = useRef({key, generation: 0, mounted: true});
    if (live.current.key !== key) { live.current.key = key; live.current.generation += 1; }
    const generation = live.current.generation;
    useLayoutEffect(() => { setState(empty()); onPreview(null); onOverlayPreview(null); }, [key]);
    useLayoutEffect(() => () => { live.current.mounted = false; onPreview(null); onOverlayPreview(null); }, []);
    useEffect(() => {
        let active = true;
        client.api("/api/creation/reasoning/config").then((data) => { if (active) setAvailable(data.available === true); }).catch(() => {});
        return () => { active = false; };
    }, []);
    const valid = () => live.current.mounted && live.current.generation === generation;
    const update = (patch) => { if (valid()) setState((s) => ({...s, ...patch})); };
    return {...state, available, valid, update, key};
}

function withCompanions(editing, projection, follow) {
    const replaced = projection.replacements?.map(row => row.targetClipId);
    return {...projection, ...projectCompanions(editing, projection.clips, follow, replaced)};
}

function reasoningActions(flow, editing, text, onPreview, onOverlayPreview, mode, follow) {
    const identity = {jobId: editing.base?.jobId, planId: editing.base?.planId};
    const ready = editing.status === "ready" && !editing.dirty;
    const show = async (data) => {
        if (!flow.valid()) return;
        const selection = data.mixed || data.insertion || data.replacement;
        if (selection) {
            const message = data.failureStage === "validate_timeline"
                ? "组合建议未通过时间线校验。请检查变速后的旁白、图层时长和镜头范围。"
                : selection.message;
            flow.update({result: data, projection: null, message});
            onOverlayPreview(null); onPreview(null);
            let projection = null;
            if (data.status === "completed" && ["mixed_edit", "replacement", "insertion"].includes(selection.kind)) {
                projection = await post({action: "validate", preparedHash: data.preparedHash, ...identity, expectedParentReceiptSha256: editing.editor.expectedParentReceiptSha256});
                if (!flow.valid()) return;
            }
            flow.update({projection}); return;
        }
        if (!flow.valid()) return;
        const response = data.proposal?.response;
        const overlays = response?.kind === "overlay_edit_proposal" ? overlayProposalItems(editing, response.overlayEdit) : null;
        onOverlayPreview(overlays);
        flow.update({result: data, projection: null, message: response?.message || "调用未产生可用建议；失败或未知费用不会自动重试。"});
    };
    const run = async (kind, task) => {
        flow.update({busy: kind, message: ""});
        try { await task(); } catch (error) { flow.update({message: `${error.message}${kind === "execute" ? "。结果可能尚未取回，请读取本次结果，勿重复付费。" : ""}`}); }
        finally { flow.update({busy: ""}); }
    };
    return {
        prepare: () => ready && text.trim() && run("prepare", async () => {
            const action = {mixed: "prepare_mixed", insertion: "prepare_insertion", replacement: "prepare_replacement"}[mode] || "prepare";
            const quote = await post({action, ...identity, instruction: text.trim()});
            if (!flow.valid()) return;
            flow.update({quote, result: null, projection: null, confirmed: false, sent: false}); if (flow.valid()) { onPreview(null); onOverlayPreview(null); }
            if (!quote.budget?.eligible || !flow.available) return;
            if (!remember(editing, quote, text)) throw new Error("无法保存本次结果的恢复入口，已阻止发送。请允许浏览器本地存储后再试");
            flow.update({sent: true, busy: "execute"});
            let result;
            try { result = await post({action: "execute_budget", preparedHash: quote.preparedHash, snapshotFingerprint: quote.snapshotFingerprint}); }
            catch (error) {
                // A refusal (4xx) happens before anything is sent: fall back to explicit confirmation.
                if (error.status >= 400 && error.status < 500) { flow.update({sent: false}); throw new Error(`${error.message}（本次未发送）`); }
                throw new Error(`${error.message}。结果可能尚未取回，请读取本次结果，不会重复付费。`);
            }
            await show(result);
        }),
        execute: () => {
            if (!ready || !flow.quote || !flow.confirmed || flow.sent || !flow.available) return;
            if (!remember(editing, flow.quote, text)) return flow.update({message: "无法保存本次结果的恢复入口，已阻止发送。请允许浏览器本地存储后再试"});
            return run("execute", async () => {
                flow.update({sent: true, confirmed: false});
                await show(await post({action: "execute", preparedHash: flow.quote.preparedHash, snapshotFingerprint: flow.quote.snapshotFingerprint, confirmedMaxCny: flow.quote.maxCostCny}));
            });
        },
        recover: () => flow.quote && run("result", async () => await show(await post({action: "result", preparedHash: flow.quote.preparedHash}))),
        restore: (saved) => ready && saved.parentKey === parentKey(editing) && run("result", async () => {
            flow.update({quote: saved.quote, result: null, projection: null, sent: true, confirmed: false}); onPreview(null); onOverlayPreview(null);
            await show(await post({action: "result", preparedHash: saved.quote.preparedHash}));
        }),
        apply: () => ready && (flow.result?.mixed?.kind === "mixed_edit" || flow.result?.replacement?.kind === "replacement" || flow.result?.insertion?.kind === "insertion" || ["edit_proposal", "overlay_edit_proposal"].includes(flow.result?.proposal?.response.kind)) && run("validate", async () => {
            const data = await post({action: "validate", preparedHash: flow.quote.preparedHash, ...identity, expectedParentReceiptSha256: editing.editor.expectedParentReceiptSha256});
            if (!flow.valid()) return;
            const response = flow.result.proposal?.response || {};
            if (response.kind === "overlay_edit_proposal") {
                const expected = overlayProposalItems(editing, response.overlayEdit), items = data.overlays?.items;
                if (!Array.isArray(items) || items.length !== expected.length || expected.some((item, i) =>
                    Object.keys(item).length !== Object.keys(items[i]).length || Object.entries(item).some(([k, v]) => items[i][k] !== v))) throw new Error("图层验证结果与预览不一致");
            }
            const proposal = response.kind === "overlay_edit_proposal" ? data : withCompanions(editing, data, follow);
            onPreview(null); onOverlayPreview(null); editing.ops.applyProposal(proposal, editing.editEpoch);
        }),
        discard: () => { flow.update(empty()); onPreview(null); onOverlayPreview(null); },
    };
}

function mixedActionLabels(proposal, projection, original, fps) {
    const steps = proposal.actions || [{action: "replace", ...proposal.replacement}, proposal.edit];
    let insertionIndex = 0;
    return steps.map(step => {
        if (step.action === "insert_after") {
            const identity = projection.insertions?.[insertionIndex++]?.newClipId;
            const clip = projection.clips.find(c => c.clipId === identity);
            return `在原第 ${step.after.slice(1)} 镜之后插入 ${step.durationMs / 1000} 秒：${clip?.scriptDraft || "候选镜头"}`;
        }
        const shot = Number(step.target.slice(1));
        if (step.action === "set_speed") return `原第 ${shot} 镜设为 ${step.speed} 播放`;
        if (step.action === "move_before" || step.action === "move_after") {
            return `将原第 ${shot} 镜移到原第 ${step.anchor.slice(1)} 镜${step.action === "move_after" ? "之后" : "之前"}`;
        }
        if (step.action === "replace") {
            const clip = projection.clips.find(c => c.clipId === original[shot - 1]?.clipId);
            return `替换原第 ${shot} 镜：${clip?.scriptDraft || "候选镜头"}`;
        }
        if (step.action === "delete") return `删除原第 ${shot} 镜`;
        if (["creation-mixed-edit-v3", "creation-mixed-edit-v4"].includes(proposal.schemaVersion)) {
            const clip = projection.clips.find(c => c.clipId === original[shot - 1]?.clipId);
            if (clip) return `裁短原第 ${shot} 镜，最终时长 ${(clipFrames(clip, fps) / fps).toFixed(2)} 秒`;
        }
        return `原第 ${shot} 镜保留开头 ${step.keepMs / 1000} 秒`;
    });
}

export function ReasoningDock({editing, onPreview, onOverlayPreview = noop, mode = "edit", follow}) {
    const [text, setText] = useState("");
    const [restoring, setRestoring] = useState(null);
    const flow = useReasoning(editing, text, onPreview, onOverlayPreview, mode);
    const actions = reasoningActions(flow, editing, text, onPreview, onOverlayPreview, mode, follow);
    const ready = editing.status === "ready" && !editing.dirty;
    const identity = parentKey(editing);
    useEffect(() => {
        if (!restoring || text !== restoring.text) return;
        setRestoring(null);
        if (restoring.parentKey === identity) void actions.restore(restoring);
    }, [restoring, text, identity]);
    const history = attempts().filter((a) => a.parentKey === identity);
    const response = flow.result?.proposal?.response;
    const mixed = flow.result?.mixed;
    const preview = useMemo(() => {
        const projection = flow.projection ?? (response?.kind === "edit_proposal" ? {clips: response.clips} : null);
        try { return projection ? {projection: withCompanions(editing, projection, follow)} : {}; }
        catch (error) { return {problem: error.message}; }
    }, [flow.projection, response, editing.editEpoch, follow]);
    useLayoutEffect(() => onPreview(preview.projection?.clips || null, preview.projection), [preview, onPreview]);
    return html`<section class="dock reasoning" aria-label="AI创作对话">
        <form class="reasoning-input" onSubmit=${(e) => { e.preventDefault(); if (!flow.busy) void actions.prepare(); }}>
            <strong>AI创作对话</strong><input class="input" aria-label="创作对话需求" value=${text} disabled=${!ready || !!flow.busy}
                placeholder="描述想改变的节奏或镜头；不清楚时会先询问" onInput=${(e) => setText(e.currentTarget.value)} />
            <button class="btn ghost" disabled=${!ready || !text.trim() || !!flow.busy}>${flow.busy === "execute" ? "AI 正在修改…" : "交给 AI"}</button>
        </form>
        <p class="hint">${!ready ? "请先保存当前镜头和声音修改，再请求模型建议。" : "仅发送已保存镜头的文字和时间；模型没有观看画面。旁白仍用免费本机语音。"}
            ${mode === "insertion" ? " 插入会延长画面。" : mode === "replacement" ? " 可在一句需求里指定多个镜头，整组预览、应用与撤销。" : mode === "mixed" ? " 可组合变速、换序、换镜、插入和删裁。镜头编号按改动前的顺序。" : ""}
            ${!flow.available ? " 文本模型尚未配置 DEEPSEEK_API_KEY，不能发送；可先查看请求。" : ""}</p>
        ${history.length ? html`<details class="reasoning-history"><summary>已确认请求的结果记录（${history.length}）</summary>
            ${history.map((saved) => html`<div class="actions-row"><span>${saved.at} · ${saved.text.slice(0, 50)}</span>
                <button type="button" class="btn ghost" disabled=${!ready || !!flow.busy} onClick=${() => { setText(saved.text); setRestoring(saved); }}>读取已确认结果（不调用模型）</button></div>`)}
            <p class="hint">切换模式或修改镜头不会清除已发送记录；回到对应的已保存版本后可恢复。未完成或失败的请求不会自动重发。</p>
        </details>` : null}
        ${flow.quote && html`<div class="reasoning-quote">
            <p aria-label="AI预算">DeepSeek 文本模型 · ${client.budgetText(flow.quote.budget)}${flow.quote.budget && !flow.quote.budget.eligible ? `${flow.quote.budget.reason}；确认后按完整上下文上限 ¥${flow.quote.maxCostCny} 预留。` : ""}</p>
            <details><summary>查看将发送的文字</summary><pre>${flow.quote.payloadPreview ? JSON.stringify(flow.quote.payloadPreview, null, 2) : JSON.stringify({instruction: text, clips: editing.clips.map((c) => ({clipId: c.clipId, startUs: c.startUs, endUs: c.endUs, scriptDraft: c.scriptDraft}))}, null, 2)}</pre></details>
            ${!flow.sent && html`<label class="check"><input type="checkbox" aria-label="同意本次文字发送和费用上限" checked=${flow.confirmed} disabled=${!!flow.busy}
                onChange=${(e) => flow.update({confirmed: e.currentTarget.checked})} />我同意发送以上文字，并确认本次费用上限。</label>
                <button type="button" class="btn" disabled=${!ready || !flow.confirmed || !flow.available || !!flow.busy} onClick=${actions.execute}>确认本次调用（最高 ¥${flow.quote.maxCostCny}）</button>`}
            ${flow.sent && !flow.result && html`<button type="button" class="btn ghost" disabled=${!!flow.busy} onClick=${actions.recover}>读取本次结果（不重新调用）</button>`}
        </div>`}
        ${flow.message && html`<p class="reasoning-message" role="status">${flow.message}</p>`}
        ${preview.problem && html`<p class="reasoning-message" role="status">${preview.problem}</p>`}
        ${flow.result?.billing && html`<p class="hint" aria-label="本次文本模型费用">${flow.result.billing.unresolvedAttempts || flow.result.billing.knownCostCny === null
            ? `实际费用未知，仍保留 ¥${flow.result.billing.reservedCny} 的费用占用；不会自动重试。`
            : `${flow.result.metadata?.usage?.cost_status === "confirmed" ? "已确认费用" : "按价目估算费用"} ¥${flow.result.billing.knownCostCny}，以提供方账单为准。`}</p>`}
        ${response?.questions?.length ? html`<ul>${response.questions.map((q) => html`<li>${q}</li>`)}</ul>` : null}
        ${mixed?.kind === "mixed_edit" && flow.projection && html`<div>
            <ul>${mixedActionLabels(mixed, flow.projection, editing.clips, editing.editor.fps).map(label => html`<li>${label}</li>`)}</ul>
            <button type="button" class="btn" disabled=${!ready || !!flow.busy || !!preview.problem} onClick=${actions.apply}>应用AI组合剪辑</button>
        </div>`}
        ${flow.result?.replacement?.kind === "replacement" && flow.projection && html`<div>
            <p>将替换 ${flow.projection.replacements.length} 个镜头，尚未应用。</p>
            <ul>${flow.projection.replacements.map(op => {
                const index = editing.clips.findIndex(c => c.clipId === op.targetClipId);
                const clip = flow.projection.clips.find(c => c.clipId === op.targetClipId);
                return html`<li>第 ${index + 1} 段 → 原片 ${(clip.startUs / 1e6).toFixed(2)}–${(clip.endUs / 1e6).toFixed(2)} 秒：${clip.scriptDraft || "无描述"}</li>`;
            })}</ul><button type="button" class="btn" disabled=${!ready || !!flow.busy || !!preview.problem} onClick=${actions.apply}>应用AI换镜头</button></div>`}
        ${flow.result?.insertion?.kind === "insertion" && flow.projection && html`<div class="actions-row"><span>插入画面建议尚未应用。</span><button type="button" class="btn" disabled=${!ready || !!flow.busy || !!preview.problem} onClick=${actions.apply}>应用AI插入镜头</button></div>`}
        ${response?.kind === "edit_proposal" && html`<div class="actions-row"><span>改动预览：${flow.result.proposal.before_seconds.toFixed(1)} → ${flow.result.proposal.after_seconds.toFixed(1)} 秒；尚未应用。</span>
            <button type="button" class="btn" disabled=${!ready || !!flow.busy || !!preview.problem} onClick=${actions.apply}>应用AI建议</button></div>`}
        ${response?.kind === "overlay_edit_proposal" && html`<div class="actions-row"><span>图层预览：结束 ${(editing.overlays.find((o) => o.overlayId === response.overlayEdit.overlayId)?.endFrame / editing.editor.fps).toFixed(2)} → ${(response.overlayEdit.endFrame / editing.editor.fps).toFixed(2)} 秒；淡出 ${(editing.overlays.find((o) => o.overlayId === response.overlayEdit.overlayId)?.fadeOutFrames / editing.editor.fps).toFixed(2)} → ${(response.overlayEdit.fadeOutFrames / editing.editor.fps).toFixed(2)} 秒；尚未应用。</span>
            <button type="button" class="btn" disabled=${!ready || !!flow.busy} onClick=${actions.apply}>应用AI建议</button></div>`}
        ${flow.quote && html`<button type="button" class="btn ghost" disabled=${!!flow.busy} onClick=${actions.discard}>关闭本次建议</button>`}
    </section>`;
}
