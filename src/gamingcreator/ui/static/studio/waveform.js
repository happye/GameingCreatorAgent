// Stage C (2026-11-11): source-audio waveform under the program track, like PR/AE. Each shot
// draws the peaks of its own source range (fetched once per range), stretched to its output
// width, so speed changes and trims show directly. Display only.
import {h} from "../vendor/preact.module.js";
import {useEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";

const html = htm.bind(h);
const cache = new Map();

function peaksFor(project, item, buckets) {
    const origin = item.sourceClock?.originUs || 0;
    const query = {project, run: item.runId, startUs: String(Math.max(0, Math.round(origin + item.startUs))), endUs: String(Math.round(origin + item.endUs)), buckets: String(buckets)};
    const key = JSON.stringify(query);
    if (!cache.has(key)) cache.set(key, client.api("/api/waveform", query).catch((error) => { cache.delete(key); throw error; }));
    return cache.get(key);
}

function ShotWave({project, item, left, width, gain}) {
    const canvas = useRef(null);
    const [data, setData] = useState(null);
    const buckets = Math.max(8, Math.min(400, Math.round(width / 3)));
    useEffect(() => {
        let alive = true;
        if (!item.runId || item.endUs <= item.startUs) return;
        peaksFor(project, item, buckets).then((d) => { if (alive) setData({audio: d?.audio === true, peaks: Array.isArray(d?.peaks) ? d.peaks : []}); }).catch(() => { if (alive) setData({audio: false, peaks: []}); });
        return () => { alive = false; };
    }, [project, item.runId, item.startUs, item.endUs, buckets]);
    useEffect(() => {
        const el = canvas.current; if (!el || !data) return;
        const ctx = el.getContext("2d"), w = el.width, mid = el.height / 2;
        ctx.clearRect(0, 0, w, el.height);
        ctx.fillStyle = getComputedStyle(el).color;
        const step = w / Math.max(1, data.peaks.length);
        data.peaks.forEach((p, i) => { const a = Math.max(0.5, Math.min(1, p * gain) * mid); ctx.fillRect(i * step, mid - a, Math.max(1, step - 0.5), a * 2); });
    }, [data, gain, width]);
    return html`<canvas ref=${canvas} class=${`wave${data && !data.audio ? " silent" : ""}`} width=${Math.max(1, Math.round(width))} height="28"
        style=${{left: `${left}px`, width: `${width}px`}} title=${data && !data.audio ? "这段录像没有声音" : "原声波形"}></canvas>`;
}

export function WaveLane({project, items, scale, gainDb = 0, envelope = null}) {
    if (!project || !scale || !items.some((i) => i.runId)) return null;
    const gain = 10 ** (gainDb / 20);
    return html`<div class="track wave-lane" aria-label="原声波形">
        ${items.map((item) => html`<${ShotWave} key=${`${item.clipId || item.eventId}:${item.startUs}:${item.endUs}`} project=${project} item=${item}
            left=${item.outStartUs * scale} width=${Math.max(3, item.outDurUs * scale - 1)} gain=${gain} />`)}
        ${envelope ? html`<${EnvelopeOverlay} ...${envelope} />` : null}
    </div>`;
}

// Stage C keyframes: dB-linear between points, held at the ends (same rule as the renderer).
export function envelopeDb(points = [], frame) {
    if (!points.length) return 0;
    if (frame <= points[0].frame) return points[0].gainDb;
    for (let i = 1; i < points.length; i++) {
        const a = points[i - 1], b = points[i];
        if (frame <= b.frame) return a.gainDb + (b.gainDb - a.gainDb) * (frame - a.frame) / (b.frame - a.frame);
    }
    return points.at(-1).gainDb;
}

const FLOOR_DB = -40, HEIGHT = 28;
let lastDragEnd = 0; // releasing a drag also clicks the lane; that click must not add a point
const yOf = (db) => 2 + (Math.min(0, Math.max(FLOOR_DB, db)) / FLOOR_DB) * (HEIGHT - 4);
const dbOf = (y) => Math.round(Math.max(-60, Math.min(0, ((y - 2) / (HEIGHT - 4)) * FLOOR_DB)) * 2) / 2;

// Click the lane to add a point (at the current level, so adding changes nothing), drag a
// point to move it, double-click a point to remove it. One drag is one undo step.
export function EnvelopeOverlay({points = [], fps, totalFrames, pxPerFrame, onChange}) {
    if (!onChange || !pxPerFrame || !totalFrames) return null;
    const width = totalFrames * pxPerFrame;
    const line = points.length ? [[0, points[0].gainDb], ...points.map((p) => [p.frame, p.gainDb]), [totalFrames, points.at(-1).gainDb]]
        .map(([f, db]) => `${f * pxPerFrame},${yOf(db)}`).join(" ") : `0,${yOf(0)} ${width},${yOf(0)}`;
    const add = (event) => {
        if (event.target.tagName === "circle" || points.length >= 64 || performance.now() - lastDragEnd < 300) return;
        const box = event.currentTarget.getBoundingClientRect();
        const frame = Math.max(0, Math.min(totalFrames, Math.round((event.clientX - box.left) / pxPerFrame)));
        if (points.some((p) => p.frame === frame)) return;
        const gainDb = Math.round(envelopeDb(points, frame) * 2) / 2;
        onChange([...points, {frame, gainDb}].sort((a, b) => a.frame - b.frame));
    };
    const drag = (event, index) => {
        event.preventDefault(); event.stopPropagation();
        const svg = event.currentTarget.ownerSVGElement, box = svg.getBoundingClientRect(), key = `envelope:${Date.now()}`;
        const lo = index ? points[index - 1].frame + 1 : 0, hi = index < points.length - 1 ? points[index + 1].frame - 1 : totalFrames;
        const move = (e) => {
            const frame = Math.max(lo, Math.min(hi, Math.round((e.clientX - box.left) / pxPerFrame)));
            onChange(points.map((p, i) => (i === index ? {frame, gainDb: dbOf(e.clientY - box.top)} : p)), key);
        };
        const end = () => { lastDragEnd = performance.now(); removeEventListener("pointermove", move); removeEventListener("pointerup", end); };
        addEventListener("pointermove", move); addEventListener("pointerup", end);
    };
    return html`<svg class="envelope" width=${width} height=${HEIGHT} aria-label="原声增益线" onClick=${add}>
        <polyline points=${line} />
        ${points.map((p, i) => html`<circle cx=${p.frame * pxPerFrame} cy=${yOf(p.gainDb)} r="4" role="slider" aria-label=${`增益点 ${(p.frame / fps).toFixed(2)} 秒`}
            aria-valuenow=${p.gainDb} onPointerDown=${(e) => drag(e, i)} onDblClick=${(e) => { e.stopPropagation(); onChange(points.filter((_, j) => j !== i)); }}>
            <title>${`${(p.frame / fps).toFixed(2)} 秒 · ${p.gainDb} dB（拖动调整，双击删除）`}</title></circle>`)}
    </svg>`;
}
