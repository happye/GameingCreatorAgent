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
        peaksFor(project, item, buckets).then((d) => { if (alive) setData(d); }).catch(() => { if (alive) setData({audio: false, peaks: []}); });
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

export function WaveLane({project, items, scale, gainDb = 0}) {
    if (!project || !scale || !items.some((i) => i.runId)) return null;
    const gain = 10 ** (gainDb / 20);
    return html`<div class="track wave-lane" aria-label="原声波形">
        ${items.map((item) => html`<${ShotWave} key=${`${item.clipId || item.eventId}:${item.startUs}:${item.endUs}`} project=${project} item=${item}
            left=${item.outStartUs * scale} width=${Math.max(3, item.outDurUs * scale - 1)} gain=${gain} />`)}
    </div>`;
}
