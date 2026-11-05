// Instant plan preview: play a plan's edit list straight from the source recordings,
// jumping between segments, so a plan can be watched before anything is rendered.
import {useCallback, useEffect, useLayoutEffect, useRef, useState} from "../vendor/hooks.module.js";

// Plan segments → playback items on an output clock (microseconds). Each item plays
// source [startUs, endUs) at `rate` (speed), taking outDurUs of output time.
export function timeline(segments, fps) {
    let out = 0;
    return segments.map((segment) => {
        const duration = Math.round((segment.outputFrames * 1e6) / fps);
        const item = {...segment, rate: 1, endUs: segment.startUs + duration, outStartUs: out, outDurUs: duration};
        out += duration;
        return item;
    });
}

// Output frames of an edited clip, the same integer rule the server uses.
export function clipFrames(clip, fps) {
    const {numerator, denominator} = clip.speed;
    return Number((BigInt(clip.endUs - clip.startUs) * BigInt(fps) * BigInt(denominator)) / (1000000n * BigInt(numerator)));
}

// Editor clips → playback items. Transitions preview as cuts.
export function editTimeline(clips, fps) {
    let out = 0;
    return clips.map((clip) => {
        const duration = Math.round((clipFrames(clip, fps) * 1e6) / fps);
        const item = {...clip, rate: clip.speed.numerator / clip.speed.denominator, outStartUs: out, outDurUs: duration};
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

function mediaReady(video, signal, metadata = false) {
    const complete = () => metadata ? video.readyState >= 1 : !video.seeking && video.readyState >= 3;
    if (signal.aborted) return Promise.reject(new DOMException("Cancelled", "AbortError"));
    if (complete()) return Promise.resolve();
    return new Promise((resolve, reject) => {
        const events = ["loadedmetadata", "seeked", "canplay", "loadeddata"];
        const cleanup = () => {
            events.forEach((name) => video.removeEventListener(name, check));
            video.removeEventListener("error", fail); signal.removeEventListener("abort", abort);
        };
        const check = () => { if (complete()) { cleanup(); resolve(); } };
        const fail = () => { cleanup(); reject(new Error("素材无法播放")); };
        const abort = () => { cleanup(); reject(new DOMException("Cancelled", "AbortError")); };
        events.forEach((name) => video.addEventListener(name, check));
        video.addEventListener("error", fail); signal.addEventListener("abort", abort);
    });
}

export function usePlanPlayer(videoRef, items, urlFor) {
    const [outUs, setOutUs] = useState(0);
    const [playing, setPlaying] = useState(false);
    const [buffering, setBuffering] = useState(false);
    const pending = useRef(null), stalled = useRef(false);
    const current = useRef({index: -1, src: ""});
    const frame = useRef(0), busy = useRef(false), token = useRef(0);
    const total = items.length ? items.at(-1).outStartUs + items.at(-1).outDurUs : 0;

    const live = useRef(false);
    const stop = useCallback(() => { token.current += 1; pending.current?.abort(); busy.current = false; live.current = false; cancelAnimationFrame(frame.current); videoRef.current?.pause(); setPlaying(false); }, []);

    const load = useCallback(async (index, offsetUs, run) => {
        pending.current?.abort();
        const controller = new AbortController(); pending.current = controller;
        const video = videoRef.current, item = items[index], src = urlFor(item.runId);
        stalled.current = true; setBuffering(true); video.pause();
        if (current.current.src !== src) { video.src = src; current.current.src = src; }
        await mediaReady(video, controller.signal, true);
        if (run !== token.current) return;
        video.playbackRate = item.rate || 1;
        const target = (item.startUs + offsetUs * (item.rate || 1)) / 1e6;
        if (Math.abs(video.currentTime - target) > 0.015) video.currentTime = target;
        await mediaReady(video, controller.signal);
        if (run !== token.current) return;
        current.current.index = index;
        stalled.current = false; setBuffering(false);
    }, [items, urlFor]);

    // Advance across segment boundaries and update the output clock. Called from animation
    // frames (smooth while visible) and from the video's timeupdate (keeps working in background).
    const tick = useCallback(async (run) => {
        if (run !== token.current || !live.current || busy.current || stalled.current) return;
        const video = videoRef.current, index = current.current.index, item = items[index];
        if (!video || !item) return;
        if (video.currentTime * 1e6 >= item.endUs - 15000) {
            if (index + 1 >= items.length) { stop(); setOutUs(total); return; }
            const next = items[index + 1];
            if (urlFor(next.runId) === current.current.src && (next.rate || 1) === (item.rate || 1) && Math.abs(next.startUs - video.currentTime * 1e6) < 60000) current.current.index = index + 1;
            else {
                busy.current = true;
                try { await load(index + 1, 0, run); if (run === token.current && live.current) await video.play(); } catch { if (run === token.current) stop(); return; } finally { if (run === token.current) busy.current = false; }
            }
        }
        if (run !== token.current) return;
        const now = items[current.current.index];
        setOutUs(now.outStartUs + Math.min(now.outDurUs, Math.max(0, (video.currentTime * 1e6 - now.startUs) / (now.rate || 1))));
    }, [items, urlFor, load, stop, total]);

    const loop = useCallback((run) => {
        frame.current = requestAnimationFrame(async () => { await tick(run); if (run === token.current && live.current) loop(run); });
    }, [tick]);

    useEffect(() => {
        const video = videoRef.current; if (!video) return;
        const onTime = () => void tick(token.current);
        const waiting = () => { stalled.current = true; setBuffering(true); };
        const resumed = () => {
            if (!video.seeking && video.readyState >= 3 && !busy.current) {
                stalled.current = false; setBuffering(false);
            }
        };
        video.addEventListener("timeupdate", onTime);
        ["waiting", "seeking"].forEach((name) => video.addEventListener(name, waiting));
        ["playing", "canplay", "seeked"].forEach((name) => video.addEventListener(name, resumed));
        return () => {
            video.removeEventListener("timeupdate", onTime);
            ["waiting", "seeking"].forEach((name) => video.removeEventListener(name, waiting));
            ["playing", "canplay", "seeked"].forEach((name) => video.removeEventListener(name, resumed));
        };
    }, [tick]);

    const seek = useCallback(async (target, play = false) => {
        if (!items.length || !videoRef.current) return;
        const run = ++token.current; cancelAnimationFrame(frame.current); live.current = false; busy.current = false; setPlaying(false);
        const clamped = Math.max(0, Math.min(target, total - 1));
        const index = Math.max(0, items.findIndex((item) => clamped < item.outStartUs + item.outDurUs));
        setOutUs(clamped);
        // Media that cannot load or play leaves the player stopped; the timeline stays usable.
        try {
            await load(index, clamped - items[index].outStartUs, run);
            if (play && run === token.current) { live.current = true; await videoRef.current.play(); if (run !== token.current) return; setPlaying(true); loop(run); }
        } catch { if (run === token.current) stop(); }
    }, [items, load, loop, total, stop]);

    const toggle = useCallback(() => {
        if (playing) return stop();
        void seek(outUs >= total - 50000 ? 0 : outUs, true);
    }, [playing, outUs, total, seek, stop]);

    // A different plan resets the player.
    useLayoutEffect(() => { token.current += 1; stop(); setOutUs(0); current.current = {index: -1, src: ""}; }, [items]);
    useEffect(() => {
        const video = videoRef.current;
        return () => { token.current += 1; live.current = false; pending.current?.abort(); cancelAnimationFrame(frame.current); video?.pause(); };
    }, []);
    return {outUs, totalUs: total, playing, buffering, seek, toggle, stop};
}
