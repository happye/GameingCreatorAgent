// Output-clock text preview; typography is an approximation of the export.
import {h} from "../vendor/preact.module.js";
import {useEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import {api} from "./api.js";
import {asrWordsPayload} from "./word_highlights.js";
export {WordHighlightSwitch, wordHighlightDraft, setWordHighlightDraft, asrWordsPayload} from "./word_highlights.js";
const html = htm.bind(h);

export function useSubtitlePreview(project, editing, clips, mode, wordDraft, projection) {
    const kept = new Set((clips || []).map(c => c.clipId));
    const swaps = (projection?.replacements || Object.entries(editing.replacements || {}).map(([targetClipId, candidateId]) => ({targetClipId, candidateId})))
        .filter(r => kept.has(r.targetClipId));
    const manifest = projection?.candidateManifestSha256 || editing.candidateManifestSha256 || editing.editor?.candidateManifestSha256 || (swaps.length ? editing.candidates?.candidateManifestSha256 : null);
    const insertions = projection && Object.hasOwn(projection, "insertions") ? projection.insertions : editing.insertions;
    const overrides = projection?.subtitleOverrides ?? editing.subtitleOverrides.filter(o =>
        !projection?.replacements?.some(swap => swap.targetClipId === o.clipId));
    const narration = projection && Object.hasOwn(projection, "narration")
        ? projection.narration : editing.audio?.narration;
    const payload = editing.status === "ready" && clips ? {
        projectId: project, parentJobId: editing.base.jobId, planId: editing.base.planId,
        expectedParentReceiptSha256: editing.editor.expectedParentReceiptSha256, subtitleMode: mode,
        clips: clips.map(({clipId, startUs, endUs, speed, transitionIn}) => ({clipId, startUs, endUs, speed, transitionIn})),
        subtitleOverrides: overrides.filter(o => kept.has(o.clipId)),
        ...(narration !== undefined ? {narration} : {}),
        ...(manifest ? {candidateManifestSha256: manifest, replacements: swaps} : {}),
        ...(insertions != null ? {insertions} : {}),
        ...asrWordsPayload(wordDraft),
    } : null;
    const key = JSON.stringify(payload), sequence = useRef(0);
    const [state, setState] = useState({key: null, cues: [], status: ""});
    useEffect(() => {
        const controller = new AbortController(), serial = ++sequence.current;
        if (!payload || mode === "none") return () => controller.abort();
        const timer = setTimeout(async () => {
            try {
                const result = await api("/api/creation/subtitle-preview", {}, {body: payload, signal: controller.signal});
                if (!controller.signal.aborted && serial === sequence.current) setState({key, cues: result.cues, status: result.wordHighlights ? "逐词高亮预览（定位与暂停跟输出时钟走）" : result.cues.length ? "字幕内容与时机预览（字体排版以导出为准）" : "当前没有字幕", subtitleSource: result.subtitleSource, wordHighlights: !!result.wordHighlights});
            } catch (error) {
                if (!controller.signal.aborted && serial === sequence.current) setState({key, cues: [], status: `字幕预览失败：${error.message}`});
            }
        }, 250);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [key]);
    if (mode === "none") return {cues: [], status: "不加字幕", subtitleSource: "none", wordHighlights: false};
    return state.key === key ? state : {cues: [], status: payload ? "正在读取字幕…" : "正在读取可编辑镜头", subtitleSource: "segment", wordHighlights: false};
}

// Approximates the burned ASS styles (standard / large / boxed) in ffmpeg_render._subtitle_style_line.
const CUE_STYLES = {
    standard: {textShadow: "0 1px 3px black, 1px 0 2px black", fontSize: "1.25rem"},
    large: {textShadow: "0 0 3px black, 0 0 3px black, 1px 1px 2px black", fontSize: "1.75rem", fontWeight: 700},
    boxed: {fontSize: "1.25rem", background: "rgba(50, 50, 50, 0.62)", padding: "0.1em 0.45em", borderRadius: "2px"},
};

export function SubtitlePreview({cues, outUs, styleName = "standard", wordHighlights = false, subtitleSource = "segment"}) {
    const look = CUE_STYLES[styleName] || CUE_STYLES.standard;
    return html`<div aria-label="字幕预览" data-subtitle-style=${styleName} data-word-highlights=${wordHighlights ? "true" : "false"} data-subtitle-source=${subtitleSource} style=${{position: "absolute", inset: 0, pointerEvents: "none", zIndex: 4}}>
        ${cues.filter(c => c.startUs <= outUs && outUs < c.endUs).map(c => html`<div style=${{position: "absolute", bottom: c.lifted ? (12.5 * (c.lane || 1)) + "%" : "1%", width: "100%", textAlign: "center", whiteSpace: "pre-line", color: "white"}}><span style=${{...look, display: "inline-block"}}>${c.text}</span></div>`)}
    </div>`;
}
