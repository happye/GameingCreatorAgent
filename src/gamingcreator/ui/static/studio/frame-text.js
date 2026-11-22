import {h} from "../vendor/preact.module.js";
import {useCallback, useLayoutEffect, useMemo, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";

const html = htm.bind(h);
const MAX_VISIBLE_HITS = 50;
const compact = (value) => value.replace(/\s+/gu, "");
const graphemes = typeof Intl.Segmenter === "function" ? new Intl.Segmenter(undefined, {granularity: "grapheme"}) : null;
const count = (value) => Number.isSafeInteger(value) && value >= 0;
const strings = (value) => Array.isArray(value) && value.every((item) => typeof item === "string");

function checkedReport(report, project, view, density) {
    if (report?.schemaVersion !== "frame-text-v1" || report.project !== project || report.runId !== view.runId) {
        throw new Error("画面文字报告与当前项目或录像不一致。");
    }
    if (!density && report.available === false) return {status: "empty"};
    if (report.available !== true || report.sourceSha256 !== view.media.sha256 || report.durationUs !== view.media.durationUs
        || report.readOnly !== true || report.paidRequests !== 0 || report.humanReviewed !== false) {
        throw new Error("画面文字报告与当前原片不一致，请重新识别。");
    }
    if (report.contentVerified !== true) return {status: "legacy"};
    const {engine, summary, frames} = report;
    if (report.ocrSchemaVersion !== "ocr-frames-v1" || !["quick", "full"].includes(report.density)
        || (density && report.density !== density) || !count(report.every) || !report.every
        || typeof report.framesDigest !== "string" || !/^[a-f0-9]{64}$/.test(report.framesDigest)
        || typeof engine?.name !== "string" || typeof engine?.platform !== "string"
        || !strings(engine.usedLanguages) || !strings(engine.unavailableLanguages)
        || !count(summary?.frames) || !count(summary?.framesWithText) || !count(summary?.failedFrames)
        || !Array.isArray(frames) || !frames.every((frame) => count(frame?.timeUs) && frame.timeUs <= report.durationUs
            && Array.isArray(frame.lines) && frame.lines.every((line) => typeof line?.text === "string" && typeof line.likelyText === "boolean"))) {
        throw new Error("画面文字报告的取帧、来源或识别记录无法核对，请重新识别。");
    }
    return {status: "ready", report};
}

function useFrameText(project, view) {
    const [state, setState] = useState(null);
    const active = useRef(null);
    const load = useCallback(async (density = "") => {
        if (!view || active.current?.scanning) return;
        active.current?.controller.abort();
        const controller = new AbortController();
        active.current = {controller, scanning: !!density};
        setState({view, status: density ? "scanning" : "loading"});
        try {
            const payload = density ? await client.scanFrameText(project, view.runId, density, controller.signal)
                : await client.frameText(project, view.runId, controller.signal);
            if (!controller.signal.aborted) setState({view, ...checkedReport(payload, project, view, density)});
        } catch (error) {
            if (!controller.signal.aborted) setState({view, status: "error", error: `画面文字${density ? "识别" : "读取"}失败。${error.message}`});
        } finally {
            if (active.current?.controller === controller) active.current = null;
        }
    }, [project, view]);
    useLayoutEffect(() => {
        void load();
        return () => { active.current?.controller.abort(); active.current = null; };
    }, [load]);
    return {...(view && state?.view === view ? state : {status: view ? "loading" : "idle"}), load};
}

function literalQuery(query) {
    const text = compact(query);
    return text ? new RegExp(text.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "iu") : null;
}

function highlighted(text, pattern) {
    const match = pattern.exec(compact(text));
    if (!match || !graphemes) return text;
    const from = match.index, to = from + match[0].length;
    let offset = 0, start = null, end = 0;
    for (const {segment, index} of graphemes.segment(text)) {
        const next = offset + compact(segment).length;
        if (next > offset && next > from && offset < to) {
            start ??= index;
            end = index + segment.length;
        }
        if (next >= to) break;
        offset = next;
    }
    return start === null ? text : html`${text.slice(0, start)}<mark>${text.slice(start, end)}</mark>${text.slice(end)}`;
}

function exportMatches(report, query, matches) {
    const {project, runId, sourceSha256, durationUs, schemaVersion, ocrSchemaVersion, density, every, framesDigest, engine, summary} = report;
    const output = {schemaVersion: "studio-frame-text-search-v1", project, runId, sourceSha256, durationUs, query,
        report: {schemaVersion, ocrSchemaVersion, density, every, framesDigest, engine, summary, contentVerified: true},
        humanReviewed: false, paidRequests: 0, readOnly: true, note: "本机 OCR 候选，可能有错字，未经人工核对。", matches};
    const url = URL.createObjectURL(new Blob([JSON.stringify(output, null, 2) + "\n"], {type: "application/json;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = `frame-text-${runId.replace(/[^a-z0-9_-]/gi, "").slice(0, 40)}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function FrameTextStatus({status, report, error}) {
    const messages = {idle: "选择已分析的录像后可识别画面文字。", loading: "正在读取保存的画面文字…",
        empty: "这段录像尚无保存的画面文字。", scanning: "正在本机识别画面文字…",
        legacy: "旧画面文字报告未经内容完整性验证，请重新识别后再查询、定位或导出。"};
    const missing = report?.engine.unavailableLanguages || [];
    return html`<p class="hint" role="status" data-frame-text-status=${status}>${error || messages[status]}
        ${report ? html`${report.density === "full" ? "完整" : "快速"}识别 ${report.summary.frames} 帧，${report.summary.framesWithText} 帧有文字。
            ${report.summary.failedFrames ? ` ${report.summary.failedFrames} 帧读取失败。` : ""}
            ${missing.length ? ` 本机缺少识别语言：${missing.join("、")}。` : ""}
            本机识别可能有错字，未经人工核对。` : null}</p>`;
}

function FrameTextSession({project, view, seekReady, onSeek, timecode}) {
    const [density, setDensity] = useState("quick");
    const [query, setQuery] = useState("");
    const {status, report, error, load} = useFrameText(project, view);
    const pattern = useMemo(() => literalQuery(query), [query]);
    const hits = useMemo(() => {
        if (!report || !pattern) return [];
        return report.frames.flatMap(({timeUs, lines}) => lines.filter(({text}) => pattern.test(compact(text)))
            .map(({text, likelyText}) => ({timeUs, text, likelyText})));
    }, [report, pattern]);
    const scanning = status === "scanning";
    return html`<section class="frame-text-panel" aria-label="画面文字">
        <label class="form-row">识别密度<select class="select" value=${density} disabled=${!view || scanning} onChange=${(e) => setDensity(e.currentTarget.value)}>
            <option value="quick">快速</option><option value="full">完整</option>
        </select></label>
        <button class="btn ghost" type="button" disabled=${!view || scanning} onClick=${() => void load(density)}>识别画面文字</button>
        <${FrameTextStatus} status=${status} report=${report} error=${error} />
        ${report ? html`<label class="form-row">搜索画面文字<input class="input" type="search" value=${query}
            onInput=${(e) => setQuery(e.currentTarget.value)} placeholder="例如：角色名或菜单文字" /></label>
            <button class="btn ghost" type="button" disabled=${!pattern} onClick=${() => exportMatches(report, query, hits)}>导出画面文字 JSON</button>
            ${!seekReady && hits.length ? html`<p class="hint">源时间校准后可定位。</p>` : null}
            ${pattern && !hits.length ? html`<p class="hint">未找到匹配文字。识别可能有错字，可以试更短的词。</p>` : null}
            ${hits.length > MAX_VISIBLE_HITS ? html`<p class="hint">显示 ${MAX_VISIBLE_HITS} / ${hits.length} 条，导出包含全部匹配。</p>` : null}
            ${hits.length ? html`<div class="frame-text-hits">${hits.slice(0, MAX_VISIBLE_HITS).map(({timeUs, text}, index) => html`
                <button class="hit-main" type="button" key=${index} data-frame-text-time-us=${timeUs} disabled=${!seekReady}
                    onClick=${() => onSeek(timeUs)}><span class="meta">${timecode(timeUs)}</span><span class="frame-text-hit-text">${highlighted(text, pattern)}</span></button>`)}
                </div>` : null}` : null}
    </section>`;
}

export function FrameText({project, view, seekReady, onSeek, timecode}) {
    const [panel, setPanel] = useState({open: false, retainedScope: null});
    const scope = JSON.stringify([project, view?.runId]);
    return html`<div class="frame-text">
        <button class="btn ghost" type="button" aria-expanded=${panel.open}
            onClick=${() => setPanel({open: !panel.open, retainedScope: scope})}>画面文字</button>
        ${panel.open || panel.retainedScope === scope ? html`<div hidden=${!panel.open}>
            <${FrameTextSession} key=${scope} project=${project} view=${view} seekReady=${seekReady} onSeek=${onSeek} timecode=${timecode} />
        </div>` : null}
    </div>`;
}
