// Multi-track program timeline extracted from the edit workspace.
// Zoom and scrolling only change the view; clip trims and narration starts still
// go through the existing editor operations and the output clock.
import {h} from "../vendor/preact.module.js";
import {useEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import {WaveLane} from "./waveform.js";
import {maxNarrationStart} from "./audio.js";

const html = htm.bind(h);
const ZOOM = [["fit", "适应窗口"], ["2", "2倍"], ["4", "4倍"], ["8", "8倍"]];
const NAME_GUTTER = 36;
const TRACK_LABELS = {picture: "画面", source: "原声", voice: "旁白", music: "配乐", caption: "字幕"};

function timecode(us) {
    const s = Math.max(0, Math.floor(us / 1e6));
    return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function frameUs(fps) {
    return fps ? 1e6 / fps : 1e6 / 30;
}

function clampOut(us, totalUs, fps) {
    const step = frameUs(fps);
    const max = Math.max(0, (totalUs || 0) - 1);
    const snapped = Math.round((us || 0) / step) * step;
    return Math.max(0, Math.min(max, snapped));
}

// Time 0 lives in the content column, after the 36px name gutter. Use the
// scrolled .track-scroll box so padding and scrollLeft are not double-counted.
function contentX(event, scroller) {
    const row = scroller?.querySelector?.(".track-scroll");
    const origin = (row || scroller).getBoundingClientRect().left + NAME_GUTTER;
    return event.clientX - origin;
}

function trimDrag(event, item, field, scale, onTrim) {
    event.preventDefault();
    event.stopPropagation();
    const handle = event.currentTarget, x0 = event.clientX, base = item[field], rate = item.rate || 1;
    handle.setPointerCapture?.(event.pointerId);
    const move = (e) => onTrim(item.clipId, field, (base + (e.clientX - x0) / scale * rate) / 1e6);
    const end = () => {
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", end);
        handle.removeEventListener("pointercancel", end);
        handle.removeEventListener("lostpointercapture", end);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
    handle.addEventListener("lostpointercapture", end);
}

function rulerMarks(totalUs, scale, width) {
    if (!totalUs || !scale) return [];
    const span = width / scale;
    const steps = [1e6, 2e6, 5e6, 10e6, 15e6, 30e6, 60e6];
    const step = steps.find((value) => span / value <= 12) || 60e6;
    const marks = [];
    for (let us = 0; us <= totalUs + 1; us += step) marks.push(us);
    if (marks[marks.length - 1] !== totalUs) marks.push(totalUs);
    return marks;
}

// Without a trusted clipId, only a unique output-range match may be selected.
// An overlap or an unknown id seeks only and does not retarget the inspector.
export function clipForCue(items, cue) {
    if (cue?.clipId) return items.find((item) => item.clipId === cue.clipId) || null;
    const matches = items.filter((item) => cue.startUs >= item.outStartUs && cue.startUs < item.outStartUs + item.outDurUs);
    return matches.length === 1 ? matches[0] : null;
}

function shortCue(text) {
    const value = String(text || "").replace(/\s+/g, " ").trim();
    return value.length > 16 ? `${value.slice(0, 16)}…` : value;
}

function narrationGestureMatches(token, current, scope) {
    return !!(current
        && scope === token.scope
        && current.editEpoch === token.editEpoch
        && current.assetJobId === token.assetJobId
        && current.receiptSha256 === token.receiptSha256
        && current.status === "ready"
        && typeof current.onMove === "function");
}

function useTrackWidth(area) {
    const [width, setWidth] = useState(800);
    useEffect(() => {
        const observer = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width)));
        if (area.current) observer.observe(area.current);
        return () => observer.disconnect();
    }, []);
    return width;
}

function narrationMaxStart(totalUs, fps, asset) {
    return maxNarrationStart(Math.round((totalUs * fps) / 1e6), fps, asset);
}

function applyNarration(frame, previewFromStart, narrationMoveRef, maxStart) {
    const move = narrationMoveRef.current;
    if (!move) return;
    const next = Math.max(0, Math.min(maxStart(), Math.round(frame)));
    move.onMove(next);
    if (previewFromStart) move.onCommitPreview?.(next);
}

function bindNarrationDrag(event, ctx) {
    event.preventDefault();
    event.stopPropagation();
    const {narrationMove, narrationMoveRef, scope, scopeRef, scale, fps, maxStart, setDrag} = ctx;
    narrationMove.onStopPlayer?.();
    const origin = narrationMove.startFrame ?? 0;
    const handle = event.currentTarget;
    handle.setPointerCapture?.(event.pointerId);
    const current = narrationMoveRef.current;
    const token = {
        scope, origin, frame: origin, pointerId: event.pointerId,
        editEpoch: current.editEpoch, assetJobId: current.assetJobId, receiptSha256: current.receiptSha256,
    };
    const move = (e) => {
        if (!narrationGestureMatches(token, narrationMoveRef.current, scopeRef.current)) {
            setDrag(null);
            return;
        }
        const next = Math.max(0, Math.min(maxStart(), origin + Math.round((e.clientX - event.clientX) / (scale * 1e6 / fps))));
        token.frame = next;
        setDrag({...token, cleanup});
    };
    const finish = (commit) => {
        cleanup();
        setDrag(null);
        if (!commit || token.frame === origin) return;
        if (!narrationGestureMatches(token, narrationMoveRef.current, scopeRef.current)) return;
        applyNarration(token.frame, true, narrationMoveRef, maxStart);
    };
    const onKey = (e) => {
        if (e.key === "Escape") { e.preventDefault(); finish(false); }
    };
    const cleanup = () => {
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", onUp);
        handle.removeEventListener("pointercancel", onCancel);
        handle.removeEventListener("lostpointercapture", onCancel);
        removeEventListener("keydown", onKey);
        try { handle.releasePointerCapture?.(event.pointerId); } catch { /* already released */ }
    };
    const onUp = () => finish(true);
    const onCancel = () => finish(false);
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", onUp);
    handle.addEventListener("pointercancel", onCancel);
    handle.addEventListener("lostpointercapture", onCancel);
    addEventListener("keydown", onKey);
    setDrag({...token, cleanup});
}

function useNarrationGesture({scope, narrationMove, canDragNarration, scale, fps, totalUs}) {
    const [drag, setDrag] = useState(null);
    const dragRef = useRef(null);
    dragRef.current = drag;
    const scopeRef = useRef(scope);
    scopeRef.current = scope;
    const narrationMoveRef = useRef(narrationMove);
    narrationMoveRef.current = narrationMove;
    useEffect(() => {
        setDrag(null);
        return () => {
            const active = dragRef.current;
            if (active?.cleanup) active.cleanup();
            dragRef.current = null;
        };
    }, [scope]);
    useEffect(() => {
        const active = dragRef.current;
        if (!active || active.frame == null) return;
        if (!narrationGestureMatches(active, narrationMove, scopeRef.current)) setDrag(null);
    }, [narrationMove]);
    const maxStart = () => narrationMaxStart(totalUs, fps, narrationMove);
    const startNarrationDrag = (event) => {
        if (!canDragNarration) return;
        bindNarrationDrag(event, {narrationMove, narrationMoveRef, scope, scopeRef, scale, fps, maxStart, setDrag});
    };
    const nudgeNarration = (event) => {
        if (!canDragNarration) return;
        if (event.target.closest?.("input, textarea, select, [contenteditable=true]")) return;
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        const step = (event.shiftKey ? 10 : 1) * (event.key === "ArrowLeft" ? -1 : 1);
        narrationMove.onStopPlayer?.();
        applyNarration((narrationMove.startFrame ?? 0) + step, false, narrationMoveRef, maxStart);
    };
    return {drag, startNarrationDrag, nudgeNarration};
}

function playheadMark(scale, outUs) {
    return scale ? html`<div class="playhead" style=${{left: `${outUs * scale}px`}}></div>` : null;
}

function TrackRow({track, name, children}) {
    return html`<div class="track-row" data-track=${track}>
        <span class="track-name">${name || ""}</span>
        ${children}
    </div>`;
}

function ZoomControls({zoom, onZoom}) {
    return html`<div class="zoom-controls" role="toolbar" aria-label="时间轴缩放">
        ${ZOOM.map(([value, label]) => html`<button type="button" class="btn ghost" aria-pressed=${zoom === value}
            onClick=${() => onZoom(value)}>${label}</button>`)}
    </div>`;
}

function RulerTrack({totalUs, scale, contentWidth, playhead}) {
    return html`<${TrackRow} track="ruler" name="">
        <div class="ruler" aria-label="输出时间刻度">
            ${rulerMarks(totalUs, scale, contentWidth).map((us) => html`<span style=${{left: `${us * scale}px`}}>${timecode(us)}</span>`)}
            ${playhead}
        </div>
    </${TrackRow}>`;
}

function PictureTrack({items, thumb, changed, selectedId, scale, onPick, chosen, onTrim, playhead}) {
    return html`<${TrackRow} track="picture" name=${TRACK_LABELS.picture}>
        <div class="track program">
            ${items.map((item, index) => {
                const src = thumb(item), speed = item.rate && item.rate !== 1 ? item.rate : null;
                return html`<button class=${`clip${changed.has(item.clipId) ? " changed" : ""}`} aria-current=${!!item.clipId && item.clipId === selectedId}
                    style=${{left: `${item.outStartUs * scale}px`, width: `${Math.max(1, item.outDurUs * scale - 1)}px`, backgroundImage: src ? `url("${src}")` : "none"}}
                    title=${`第 ${index + 1} 个镜头 · ${timecode(item.outStartUs)} · ${(item.outDurUs / 1e6).toFixed(1)} 秒${speed ? ` · ${speed}×` : ""} · ${item.scriptDraft || ""}`} onClick=${() => onPick(item)}>
                    <span class="clip-no">${index + 1}</span>${speed ? html`<span class="clip-speed">${speed}×</span>` : null}</button>`;
            })}
            ${chosen ? ["startUs", "endUs"].map((field) => html`<div class=${`trim-handle ${field === "startUs" ? "in" : "out"}`} role="slider" aria-label=${field === "startUs" ? "拖动裁剪入点" : "拖动裁剪出点"}
                aria-valuenow=${(chosen[field] / 1e6).toFixed(2)} title="拖动裁剪；松开即生效，可撤销"
                style=${{left: `${(chosen.outStartUs + (field === "startUs" ? 0 : chosen.outDurUs)) * scale}px`}}
                onPointerDown=${(e) => trimDrag(e, chosen, field, scale, onTrim)}></div>`) : null}
            ${playhead}
        </div>
    </${TrackRow}>`;
}

function SourceTrack({project, items, scale, sourceGainDb, envelope, playhead}) {
    return html`<${TrackRow} track="source" name=${TRACK_LABELS.source}>
        <div class="lane-slot">
            <${WaveLane} project=${project} items=${items} scale=${scale} gainDb=${sourceGainDb}
                envelope=${envelope ? {...envelope, pxPerFrame: scale * 1e6 / envelope.fps} : null} />
            ${playhead}
        </div>
    </${TrackRow}>`;
}

function VoiceTrack({voice, voiceDurUs, voiceStartUs, canDragNarration, startFrame, scale, totalUs, problem, onLane, startNarrationDrag, nudgeNarration, playhead}) {
    return html`<${TrackRow} track="voice" name=${TRACK_LABELS.voice}>
        <div class="lane-slot">
            <button class="lane voice" title=${`${voice?.label || TRACK_LABELS.voice} · 点击打开“声音”`} onClick=${(e) => { e.stopPropagation(); onLane(); }}>
                ${voiceDurUs ? html`<span class=${`bar${canDragNarration ? " movable" : ""}`} style=${{left: `${voiceStartUs * scale}px`, width: `${Math.max(3, Math.min(voiceDurUs, totalUs - voiceStartUs) * scale)}px`}}
                    role=${canDragNarration ? "slider" : undefined}
                    tabindex=${canDragNarration ? 0 : undefined}
                    aria-label=${canDragNarration ? "旁白起点" : undefined}
                    aria-valuenow=${canDragNarration ? startFrame : undefined}
                    onPointerDown=${canDragNarration ? startNarrationDrag : undefined}
                    onKeyDown=${canDragNarration ? nudgeNarration : undefined}
                    onClick=${(e) => e.stopPropagation()}>${voice?.label || TRACK_LABELS.voice}</span>`
                    : html`<span class="lane-empty">${voice?.label || "旁白轨：未添加，点此添加"}</span>`}
            </button>
            ${problem ? html`<p class="note warn track-note" role="status">${problem}</p>` : null}
            ${playhead}
        </div>
    </${TrackRow}>`;
}

function MusicTrack({music, scale, totalUs, onLane, playhead}) {
    return html`<${TrackRow} track="music" name=${TRACK_LABELS.music}>
        <div class="lane-slot">
            <button class="lane music" title=${`${music?.label || TRACK_LABELS.music} · 点击打开“声音”`} onClick=${(e) => { e.stopPropagation(); onLane(); }}>
                ${music?.durUs ? html`<span class="bar" style=${{left: `${(music.startUs || 0) * scale}px`, width: `${Math.max(3, Math.min(music.durUs, totalUs - (music.startUs || 0)) * scale)}px`}}
                    onClick=${(e) => e.stopPropagation()}>${music.label}</span>`
                    : html`<span class="lane-empty">${music?.label || "配乐轨：未添加，点此添加"}</span>`}
            </button>
            ${playhead}
        </div>
    </${TrackRow}>`;
}

function CaptionTrack({cues, captionStatus, items, scale, totalUs, fps, onSeek, onOpenCaption, playhead}) {
    return html`<${TrackRow} track="caption" name=${TRACK_LABELS.caption}>
        <div class="lane-slot">
            <div class="lane caption-lane" aria-label="字幕轨">
                ${cues.length ? cues.map((cue) => html`<button type="button" class="caption-block" style=${{left: `${cue.startUs * scale}px`, width: `${Math.max(3, (cue.endUs - cue.startUs) * scale)}px`}}
                    title=${`${timecode(cue.startUs)}–${timecode(cue.endUs)} · ${cue.text || ""}`}
                    data-clip-id=${cue.clipId || ""}
                    onClick=${(e) => {
                        e.stopPropagation();
                        onSeek?.(clampOut(cue.startUs, totalUs, fps));
                        const clip = clipForCue(items, cue);
                        onOpenCaption?.(clip?.clipId || null);
                    }}>${shortCue(cue.text)}</button>`)
                    : html`<span class="lane-empty">${captionStatus || "当前没有字幕"}</span>`}
            </div>
            ${playhead}
        </div>
    </${TrackRow}>`;
}

function seekAtEvent(event, onSeek, scale, area, totalUs, fps) {
    if (!onSeek || !scale || !area.current) return;
    if (event.target.closest?.(".clip, .trim-handle, .lane .bar, .caption-block, .zoom-controls, .envelope")) return;
    onSeek(clampOut(contentX(event, area.current) / scale, totalUs, fps));
}

export function ProgramTrack({
    items, totalUs, outUs, thumb, selectedId, changed, preview, lanes = [], onLane, onPick, onTrim = null,
    project = "", sourceGainDb = 0, envelope = null, fps = 30, cues = [], captionStatus = "",
    onSeek = null, onOpenCaption = null, narrationMove = null, scope = "",
}) {
    const area = useRef(null);
    const width = useTrackWidth(area);
    const [zoom, setZoom] = useState("fit");
    useEffect(() => { setZoom("fit"); }, [scope]);
    const visibleContent = Math.max(200, width - NAME_GUTTER);
    const contentWidth = zoom === "fit" ? visibleContent : visibleContent * Number(zoom);
    const scale = totalUs ? contentWidth / totalUs : 0;
    const hint = preview
        ? `一句话修改预览：高亮的是会变化的镜头（共 ${items.length} 个）`
        : `${items.length} 个镜头 · 点选一个后拖动两端可裁剪，也可调速、换顺序；Delete 删除`;
    const chosen = onTrim && scale ? items.find((item) => item.clipId && item.clipId === selectedId) : null;
    const voice = lanes.find((lane) => lane.kind === "voice");
    const music = lanes.find((lane) => lane.kind === "music");
    const voiceDurUs = voice?.durUs || (narrationMove?.durationSeconds ? narrationMove.durationSeconds * 1e6 : 0);
    const canDragNarration = !!(narrationMove && voiceDurUs && !narrationMove.problem);
    const {drag, startNarrationDrag, nudgeNarration} = useNarrationGesture({scope, narrationMove, canDragNarration, scale, fps, totalUs});
    const startFrame = drag ? drag.frame : (narrationMove?.startFrame ?? (voice && voice.durUs
        ? Math.round((voice.startUs * fps) / 1e6) : null));
    const voiceStartUs = startFrame != null && fps ? (startFrame / fps) * 1e6 : voice?.startUs || 0;
    const playhead = playheadMark(scale, outUs);
    return html`<section class="timeline" aria-label="方案时间轴">
        <div class="panel-head">时间轴<span class="track-label">${items.length ? hint : ""}</span>
            ${items.length ? html`<${ZoomControls} zoom=${zoom} onZoom=${setZoom} />` : null}
        </div>
        <div class="track-area" ref=${area} onClick=${(e) => seekAtEvent(e, onSeek, scale, area, totalUs, fps)}>
            ${items.length ? html`<div class="track-scroll" data-scale=${scale} data-total-us=${totalUs} data-fps=${fps} style=${{width: `${contentWidth + NAME_GUTTER}px`}}>
                <${RulerTrack} totalUs=${totalUs} scale=${scale} contentWidth=${contentWidth} playhead=${playhead} />
                <${PictureTrack} items=${items} thumb=${thumb} changed=${changed} selectedId=${selectedId} scale=${scale} onPick=${onPick} chosen=${chosen} onTrim=${onTrim} playhead=${playhead} />
                <${SourceTrack} project=${project} items=${items} scale=${scale} sourceGainDb=${sourceGainDb} envelope=${envelope} playhead=${playhead} />
                <${VoiceTrack} voice=${voice} voiceDurUs=${voiceDurUs} voiceStartUs=${voiceStartUs} canDragNarration=${canDragNarration} startFrame=${startFrame} scale=${scale} totalUs=${totalUs} problem=${narrationMove?.problem} onLane=${onLane} startNarrationDrag=${startNarrationDrag} nudgeNarration=${nudgeNarration} playhead=${playhead} />
                <${MusicTrack} music=${music} scale=${scale} totalUs=${totalUs} onLane=${onLane} playhead=${playhead} />
                <${CaptionTrack} cues=${cues} captionStatus=${captionStatus} items=${items} scale=${scale} totalUs=${totalUs} fps=${fps} onSeek=${onSeek} onOpenCaption=${onOpenCaption} playhead=${playhead} />
            </div>` : html`<p class="note">选中方案后，镜头按成片顺序排在这里。</p>`}
        </div>
    </section>`;
}
