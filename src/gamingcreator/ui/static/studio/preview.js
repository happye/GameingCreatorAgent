// Instant plan preview: play a plan's edit list straight from the source recordings,
// jumping between segments, so a plan can be watched before anything is rendered.
import {useCallback, useEffect, useRef, useState} from "../vendor/hooks.module.js";

// Plan segments → playback items on an output clock (microseconds).
export function timeline(segments, fps) {
    let out = 0;
    return segments.map((segment) => {
        const duration = Math.round((segment.outputFrames * 1e6) / fps);
        const item = {...segment, outStartUs: out, outDurUs: duration};
        out += duration;
        return item;
    });
}

// Back-to-back segments of one source play as one continuous shot.
export function shots(items) {
    const groups = [];
    for (const item of items) {
        const last = groups.at(-1), tail = last?.items.at(-1);
        const continuous = tail && tail.runId === item.runId && Math.abs(item.startUs - (tail.startUs + tail.outDurUs)) <= 250000;
        if (continuous) { last.items.push(item); last.outDurUs += item.outDurUs; }
        else groups.push({outStartUs: item.outStartUs, outDurUs: item.outDurUs, items: [item]});
    }
    return groups;
}

function ready(video) {
    if (video.readyState >= 1) return Promise.resolve();
    return new Promise((resolve, reject) => {
        video.addEventListener("loadedmetadata", resolve, {once: true});
        video.addEventListener("error", () => reject(new Error("素材无法播放")), {once: true});
    });
}

export function usePlanPlayer(videoRef, items, urlFor) {
    const [outUs, setOutUs] = useState(0);
    const [playing, setPlaying] = useState(false);
    const current = useRef({index: -1, src: ""});
    const frame = useRef(0), busy = useRef(false), token = useRef(0);
    const total = items.length ? items.at(-1).outStartUs + items.at(-1).outDurUs : 0;

    const live = useRef(false);
    const stop = useCallback(() => { live.current = false; cancelAnimationFrame(frame.current); videoRef.current?.pause(); setPlaying(false); }, []);

    const load = useCallback(async (index, offsetUs) => {
        const video = videoRef.current, item = items[index], src = urlFor(item.runId);
        if (current.current.src !== src) { video.src = src; current.current.src = src; }
        await ready(video);
        video.currentTime = (item.startUs + offsetUs) / 1e6;
        current.current.index = index;
    }, [items, urlFor]);

    // Advance across segment boundaries and update the output clock. Called from animation
    // frames (smooth while visible) and from the video's timeupdate (keeps working in background).
    const tick = useCallback(async (run) => {
        if (run !== token.current || !live.current || busy.current) return;
        const video = videoRef.current, index = current.current.index, item = items[index];
        if (!video || !item) return;
        if (video.currentTime * 1e6 - item.startUs >= item.outDurUs - 15000) {
            if (index + 1 >= items.length) { stop(); setOutUs(total); return; }
            const next = items[index + 1];
            if (urlFor(next.runId) === current.current.src && Math.abs(next.startUs - video.currentTime * 1e6) < 60000) current.current.index = index + 1;
            else {
                busy.current = true;
                try { await load(index + 1, 0); if (run === token.current && live.current) await video.play(); } finally { busy.current = false; }
            }
        }
        const now = items[current.current.index];
        setOutUs(now.outStartUs + Math.min(now.outDurUs, Math.max(0, video.currentTime * 1e6 - now.startUs)));
    }, [items, urlFor, load, stop, total]);

    const loop = useCallback((run) => {
        frame.current = requestAnimationFrame(async () => { await tick(run); if (run === token.current && live.current) loop(run); });
    }, [tick]);

    useEffect(() => {
        const video = videoRef.current; if (!video) return;
        const onTime = () => void tick(token.current);
        video.addEventListener("timeupdate", onTime); return () => video.removeEventListener("timeupdate", onTime);
    }, [tick]);

    const seek = useCallback(async (target, play = false) => {
        if (!items.length || !videoRef.current) return;
        const run = ++token.current; cancelAnimationFrame(frame.current); live.current = false;
        const clamped = Math.max(0, Math.min(target, total - 1));
        const index = Math.max(0, items.findIndex((item) => clamped < item.outStartUs + item.outDurUs));
        await load(index, clamped - items[index].outStartUs);
        setOutUs(clamped);
        if (play && run === token.current) { live.current = true; await videoRef.current.play(); setPlaying(true); loop(run); }
    }, [items, load, loop, total]);

    const toggle = useCallback(() => {
        if (playing) return stop();
        void seek(outUs >= total - 50000 ? 0 : outUs, true).catch(() => setPlaying(false));
    }, [playing, outUs, total, seek, stop]);

    // A different plan resets the player.
    useEffect(() => { token.current += 1; stop(); setOutUs(0); current.current = {index: -1, src: ""}; }, [items]);
    useEffect(() => () => cancelAnimationFrame(frame.current), []);
    return {outUs, totalUs: total, playing, seek, toggle, stop};
}
