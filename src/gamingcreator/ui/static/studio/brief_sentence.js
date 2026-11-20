// One sentence → brief fields; applied only on click. Stage B (2026-11-12): the text model
// reads the sentence within the monthly AI budget; the local rule parser (P019) is the
// labelled fallback when AI is not configured, over budget, or gives no usable answer.
import {h} from "../vendor/preact.module.js";
import {useEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import {api, budgetText} from "./api.js";
const html = htm.bind(h);
const split = (text) => text.split(/[,，、\n]/).map((s) => s.trim()).filter(Boolean);

export function patchFor(fields, draft) {
    const patch = {};
    for (const key of ["game", "contentType", "platform", "objective", "audience", "tone"]) if (fields[key] != null) patch[key] = String(fields[key]);
    if (fields.targetDuration != null) patch.targetDuration = String(fields.targetDuration);
    for (const key of ["mandatoryTopics", "exclude"]) {
        if (fields[key]?.length) patch[key] = [...new Set([...split(draft[key] || ""), ...fields[key]])].join(", ");
    }
    return patch;
}

// Game names from recording file names ("漫画群星：大集结 - TapTap.mp4" -> "漫画群星：大集结").
const gameNames = (runs = []) => [...new Set(runs.map((r) => (r.sourceName || "").replace(/\.[^.]+$/, "").split(/\s+-\s+/)[0].trim()).filter((n) => n.length >= 2))];
const reasoning = (body) => api("/api/creation/reasoning", {}, {body});
const PENDING_KEY = "studio-brief-pending-v1";
const savedPending = (key) => { try { return JSON.parse(sessionStorage.getItem(key)) || null; } catch { return null; } };
const billingText = (billing) => !billing ? "" : billing.unresolvedAttempts || billing.knownCostCny === null
    ? `AI 实际费用未知，仍按 ¥${billing.reservedCny} 计入预算；不会自动重试。`
    : `AI 本次约 ¥${Number(billing.knownCostCny).toFixed(4)}（按价目估算，以提供方账单为准）。`;

export function BriefSentence({draft, update, runs = [], project = "", workId = null}) {
    const pendingKey = `${PENDING_KEY}:${project}${workId ? `:work:${workId}` : ""}`;
    const [text, setText] = useState(() => savedPending(pendingKey)?.sentence || ""), [result, setResult] = useState(null), [message, setMessage] = useState("");
    const [busy, setBusy] = useState(false), [available, setAvailable] = useState(false), [pending, setPending] = useState(() => savedPending(pendingKey));
    const [localOnly, setLocalOnly] = useState(() => savedPending(pendingKey)?.localOnly === true);
    const generation = useRef(0);
    useEffect(() => {
        let active = true;
        api("/api/creation/reasoning/config").then((data) => { if (active) setAvailable(data.available === true); }).catch(() => {});
        return () => { active = false; generation.current += 1; };
    }, []);
    const rules = async (reason) => {
        const parsed = await api("/api/creation/brief-sentence", {}, {body: {text: text.trim(), games: gameNames(runs)}});
        return {parsed, line: `${reason ? `${reason}；` : ""}本机规则版${parsed.recognized.length ? `识别到：${parsed.recognized.join("；")}` : "没有识别到时长、类型、平台等，只会把这句话作为创作目标"}。`};
    };
    const fromAi = (data, quote) => {
        const brief = data.status === "completed" ? data.brief : null;
        const extra = [budgetText(quote?.budget), billingText(data.billing)].filter(Boolean).join(" ");
        if (!brief) return {brief: null, extra};
        const recognized = brief.recognized.length ? `识别到：${brief.recognized.join("；")}` : "没有识别到时长、类型、平台等";
        return {brief, extra, line: `AI 理解：${recognized}。${brief.notes ? `AI 备注：${brief.notes}。` : ""}其余保持不变。`};
    };
    const show = (parsed, line, extra = "") => { setResult(parsed); setMessage(`${line}${extra ? ` ${extra}` : ""}`); };
    const parse = async () => {
        if (!text.trim() || busy) return;
        const mine = ++generation.current, current = () => generation.current === mine;
        setBusy(true); setResult(null); if (!localOnly) setPending(null); setMessage(available && !localOnly ? "AI 正在理解这句话…" : "");
        try {
            let reason = localOnly ? "本次使用本机规则，旧 AI 请求仍可读取" : available ? "" : "文本模型未配置";
            if (available && !localOnly) {
                const quote = await reasoning({action: "prepare_brief", text: text.trim(), games: gameNames(runs), ...(workId ? {projectId: project, workId} : {})});
                if (!current()) return;
                if (!quote.budget?.eligible) reason = `${quote.budget?.reason || "超出 AI 预算"}，未调用 AI`;
                else {
                    let data;
                    const saved = {...quote, sentence: text.trim()};
                    // Save before sending: a reload or lost response must never require a new call.
                    sessionStorage.setItem(pendingKey, JSON.stringify(saved));
                    try { data = await reasoning({action: "execute_budget", preparedHash: quote.preparedHash, snapshotFingerprint: quote.snapshotFingerprint}); }
                    catch (error) {
                        // Even a 400 may be a disk failure after the paid call completed.
                        if (current()) setPending(saved);
                        throw new Error(`${error.message}。AI 结果可能尚未取回，可读取本次结果，不会重复付费`);
                    }
                    if (!current()) return;
                    if (data) {
                        sessionStorage.removeItem(pendingKey);
                        const ai = fromAi(data, quote);
                        if (ai.brief) return show(ai.brief, ai.line, ai.extra);
                        reason = `AI 没有给出可用结果（不会自动重试）${ai.extra ? `，${ai.extra}` : ""}`;
                    }
                }
            }
            const {parsed, line} = await rules(reason);
            if (current()) show(parsed, line);
        } catch (error) {
            if (!current()) return;
            try { const {parsed, line} = await rules(error.message); if (current()) show(parsed, line); }
            catch (inner) { setResult(null); setMessage(`未能解析：${inner.message}`); }
        } finally { if (current()) setBusy(false); }
    };
    const recover = async () => {
        if (!pending || busy) return;
        const mine = ++generation.current;
        setBusy(true);
        try {
            const data = await reasoning({action: "result", preparedHash: pending.preparedHash});
            if (generation.current !== mine) return;
            const ai = fromAi(data, pending);
            sessionStorage.removeItem(pendingKey);
            setPending(null);
            setLocalOnly(false);
            setText(pending.sentence);
            if (ai.brief) show(ai.brief, ai.line, ai.extra); else setMessage(`AI 没有给出可用结果（不会自动重试）。${ai.extra}`);
        } catch (error) { if (generation.current === mine) setMessage(`暂未取回 AI 结果：${error.message}`); }
        finally { if (generation.current === mine) setBusy(false); }
    };
    const useLocal = () => {
        sessionStorage.setItem(pendingKey, JSON.stringify({...pending, localOnly: true}));
        setLocalOnly(true); setResult(null); setMessage("已切换本机规则；旧 AI 请求保留供读取，不会重新调用。");
    };
    const apply = () => { update(patchFor(result.fields, draft)); setResult(null); setMessage("已填入下方需求，可继续修改后生成方案。"); };
    return html`<div class="field brief-sentence"><div class="k">一句话需求（${available && !localOnly ? "AI 理解，预算内自动调用" : "本机规则，不调用模型"}）</div>
        <textarea class="input" rows="2" maxlength="500" disabled=${busy || (!!pending && !localOnly)} aria-label="一句话需求" placeholder="例如：给新玩家做个《游戏名》1分钟玩法展示，发B站，讲角色、技能和玩法思路"
            value=${text} onInput=${(e) => { generation.current += 1; setText(e.currentTarget.value); setResult(null); setMessage(""); if (!localOnly) setPending(null); setBusy(false); }}></textarea>
        <div class="actions-row"><button type="button" class="btn ghost" disabled=${!text.trim() || busy || (!!pending && !localOnly)} onClick=${parse}>${busy ? "解析中…" : "解析"}</button>
            ${pending ? html`<button type="button" class="btn ghost" disabled=${busy} onClick=${recover}>读取本次 AI 结果（不重新调用）</button>` : null}
            ${pending && !localOnly ? html`<button type="button" class="btn ghost" disabled=${busy} onClick=${useLocal}>继续本机规则（保留 AI 记录）</button>` : null}
            ${result ? html`<button type="button" class="btn" onClick=${apply}>填入需求</button>` : null}</div>
        <p class="hint" role="status" aria-label="一句话需求状态">${message}</p>
    </div>`;
}
