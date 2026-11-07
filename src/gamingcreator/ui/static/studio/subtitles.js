// Output-clock text preview; typography is an approximation of the export.
import {h} from "../vendor/preact.module.js";
import {useEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import {api} from "./api.js";
const html = htm.bind(h);

export function useSubtitlePreview(project, editing, clips, mode) {
    const kept = new Set((clips || []).map(c => c.clipId));
    const swaps = Object.entries(editing.replacements || {}).filter(([id]) => kept.has(id)).map(([targetClipId, candidateId]) => ({targetClipId, candidateId}));
    const manifest = editing.editor?.candidateManifestSha256 || (swaps.length ? editing.candidates?.candidateManifestSha256 : null);
    const payload = editing.status === "ready" && clips ? {
        projectId: project, parentJobId: editing.base.jobId, planId: editing.base.planId,
        expectedParentReceiptSha256: editing.editor.expectedParentReceiptSha256, subtitleMode: mode,
        clips: clips.map(({clipId, startUs, endUs, speed, transitionIn}) => ({clipId, startUs, endUs, speed, transitionIn})),
        subtitleOverrides: editing.subtitleOverrides.filter(o => kept.has(o.clipId)),
        ...(manifest ? {candidateManifestSha256: manifest, replacements: swaps} : {}),
    } : null;
    const key = JSON.stringify(payload), sequence = useRef(0);
    const [state, setState] = useState({key: null, cues: [], status: ""});
    useEffect(() => {
        const controller = new AbortController(), serial = ++sequence.current;
        if (!payload || mode === "none") return () => controller.abort();
        const timer = setTimeout(async () => {
            try {
                const result = await api("/api/creation/subtitle-preview", {}, {body: payload, signal: controller.signal});
                if (!controller.signal.aborted && serial === sequence.current) setState({key, cues: result.cues, status: result.cues.length ? "字幕内容与时机预览（字体排版以导出为准）" : "当前没有字幕"});
            } catch (error) {
                if (!controller.signal.aborted && serial === sequence.current) setState({key, cues: [], status: `字幕预览失败：${error.message}`});
            }
        }, 250);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [key]);
    if (mode === "none") return {cues: [], status: "不加字幕"};
    return state.key === key ? state : {cues: [], status: payload ? "正在读取字幕…" : "正在读取可编辑镜头"};
}

export function SubtitlePreview({cues, outUs}) {
    return html`<div aria-label="字幕预览" style=${{position: "absolute", inset: 0, pointerEvents: "none", zIndex: 4}}>
        ${cues.filter(c => c.startUs <= outUs && outUs < c.endUs).map(c => html`<div style=${{position: "absolute", bottom: c.lifted ? "12.5%" : "1%", width: "100%", textAlign: "center", whiteSpace: "pre-line", color: "white", textShadow: "0 1px 3px black, 1px 0 2px black", fontSize: "1.25rem"}}>${c.text}</div>`)}
    </div>`;
}
