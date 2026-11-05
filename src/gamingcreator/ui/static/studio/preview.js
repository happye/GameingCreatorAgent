// Instant plan preview: play a plan's edit list straight from the source recordings,
// jumping between segments, so a plan can be watched before anything is rendered.
import "../source-clock.js";
import {useCallback, useLayoutEffect, useRef, useState} from "../vendor/hooks.module.js";

// Plan segments → playback items on an output clock (microseconds). Each item plays
// source [startUs, endUs) at `rate` (speed), taking outDurUs of output time.
export function timeline(segments, fps) {
    let out = 0;
    return segments.map((segment) => {
        const duration = segment.outputFrames * 1e6 / fps;
        const item = {...segment, rate: 1, endUs: segment.startUs + duration, outStartUs: out * 1e6 / fps, outDurUs: duration};
        out += segment.outputFrames;
        return item;
    });
}

// Output frames of an edited clip, the same integer rule the server uses.
export function clipFrames(clip, fps) {
    const {numerator, denominator} = clip.speed;
    return Number((BigInt(clip.endUs - clip.startUs) * BigInt(fps) * BigInt(denominator)) / (1000000n * BigInt(numerator)));
}

// Editor clips → playback items on the integer export frame clock.
export function editTimeline(clips, fps) {
    let out = 0;
    return clips.map((clip) => {
        const frames = clipFrames(clip, fps);
        const duration = frames * 1e6 / fps;
        out -= clip.transitionIn?.frames || 0;
        const item = {...clip, rate: clip.speed.numerator / clip.speed.denominator, outStartUs: out * 1e6 / fps, outDurUs: duration};
        out += frames;
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

function waitMedia(video, signal, complete, message) {
    if (signal.aborted) return Promise.reject(new DOMException("Cancelled", "AbortError"));
    if (complete()) return Promise.resolve();
    return new Promise((resolve, reject) => {
        const events = ["loadedmetadata", "seeked", "canplay", "loadeddata", "progress", "durationchange"];
        const cleanup = () => {
            clearTimeout(timer);
            events.forEach(name => video.removeEventListener(name, check));
            video.removeEventListener("error", fail); signal.removeEventListener("abort", abort);
        };
        const check = () => { if (complete()) { cleanup(); resolve(); } };
        const fail = () => { cleanup(); reject(new Error(message)); };
        const abort = () => { cleanup(); reject(new DOMException("Cancelled", "AbortError")); };
        const timer = setTimeout(fail, 8000);
        events.forEach(name => video.addEventListener(name, check));
        video.addEventListener("error", fail); signal.addEventListener("abort", abort);
    });
}

function mediaReady(video, signal, metadata = false, target = null) {
    return waitMedia(video, signal, () => metadata ? video.readyState >= 1
        : !video.seeking && video.readyState >= 3
            && (target === null || Math.abs(video.currentTime - target) <= .015),
    "素材无法定位到所选片段，请导出成片后观看");
}

function seekableTarget(video, signal, target) {
    if (Number.isFinite(video.duration) && target > video.duration) {
        return Promise.reject(new Error("所选片段超出素材可播放范围，请导出成片后观看"));
    }
    return waitMedia(video, signal, () => {
        for (let index = 0; index < video.seekable.length; index++) {
            if (video.seekable.start(index) <= target && video.seekable.end(index) >= target) return true;
        }
        return false;
    }, "素材无法读取所选片段，请导出成片后观看");
}

class PlanPlayback {
    constructor(videos, items, urlFor, publish, disabled) {
        Object.assign(this, {items, urlFor, publish, disabled, error: disabled, run: 0, live: false, out: 0});
        this.slots = videos.map(video => {
            video.dataset.previewSlot = "";
            video.style.opacity = "0";
            return {video, index: -1, ready: false, loading: false, run: -1};
        });
        this.total = items.length ? items.at(-1).outStartUs + items.at(-1).outDurUs : 0;
        this.listeners = [];
        for (const slot of this.slots) for (const name of ["waiting", "seeking", "canplay", "seeked", "playing", "timeupdate"]) {
            const fn = () => this.event(slot, name);
            slot.video.addEventListener(name, fn);
            this.listeners.push(() => slot.video.removeEventListener(name, fn));
        }
    }
    state(buffering = false) { if (this.disposed) return; this.publish({outUs: this.out, totalUs: this.total, playing: this.live, buffering, error: this.error || ""}); }
    active() {
        return this.items.map((item, index) => ({item, index}))
            .filter(({item}) => this.out >= item.outStartUs && this.out < item.outStartUs + item.outDurUs)
            .map(({index}) => index);
    }
    async prepare(slot, index, run) {
        slot.pending?.abort();
        const controller = new AbortController(); slot.pending = controller;
        slot.index = index; slot.ready = false; slot.loading = true; slot.error = ""; slot.run = run;
        const video = slot.video, item = this.items[index], src = this.urlFor(item.runId);
        video.pause(); video.style.opacity = "0"; video.volume = 0;
        if (video.getAttribute("src") !== src) { video.src = src; video.load(); }
        await mediaReady(video, controller.signal, true);
        if (run !== this.run) return;
        video.playbackRate = item.rate || 1;
        const target = ((item.sourceClock?.originUs || 0) + item.startUs
            + Math.max(0, this.out - item.outStartUs) * (item.rate || 1)) / 1e6;
        if (target > 0) await seekableTarget(video, controller.signal, target);
        if (run !== this.run) return;
        if (Math.abs(video.currentTime - target) > .015) video.currentTime = target;
        await mediaReady(video, controller.signal, false, target);
        if (run === this.run) { slot.ready = true; slot.loading = false; if (this.live) { this.paint(); this.resume(); } }
    }
    stop() {
        this.run++; this.live = false; cancelAnimationFrame(this.frame);
        this.slots.forEach(slot => {
            slot.pending?.abort(); slot.video.pause();
            slot.index = -1; slot.ready = false; slot.loading = false; slot.run = -1; slot.error = "";
        });
        this.state();
    }
    dispose() { this.disposed = true; this.stop(); this.listeners.forEach(remove => remove()); }
    async seek(target, play = false) {
        if (this.disabled || !this.items.length) return;
        this.stop(); this.error = ""; const run = this.run;
        this.slots.forEach(slot => {
            slot.video.style.opacity = "0"; slot.video.dataset.previewGain = "0"; slot.video.volume = 0;
        });
        this.out = Math.max(0, Math.min(target, this.total - 1)); this.state(true);
        try {
            await Promise.all(this.active().map((index, n) => this.prepare(this.slots[n], index, run)));
            if (run !== this.run) return;
            this.live = play; this.paint(); this.state();
            if (play) { this.resume(); this.loop(); }
            this.preload();
        } catch (error) { if (run === this.run) this.fail(error.message); }
    }
    fail(message) { this.error = message; this.stop(); }
    preload() {
        const active = this.active(), next = Math.max(...active) + 1;
        if (!this.items[next] || this.slots.some(slot => slot.index === next && slot.run === this.run && (slot.loading || slot.ready))) return;
        const slot = this.slots.find(candidate => !active.includes(candidate.index));
        if (!slot) return;
        const run = this.run;
        void this.prepare(slot, next, run).catch(error => {
            if (run !== this.run || error.name === "AbortError") return;
            slot.error = error.message; slot.loading = false;
            if (this.active().includes(slot.index)) this.fail(slot.error);
        });
    }
    event(slot, name) {
        if (slot.loading || !this.active().includes(slot.index)) return;
        if (name === "waiting" || name === "seeking") {
            slot.ready = false; this.slots.forEach(other => other.video.pause());
            if (this.live) this.state(true);
        } else if (["canplay", "seeked", "playing"].includes(name)) {
            if (!slot.video.seeking && slot.video.readyState >= 3) slot.ready = true;
            if (this.live) this.resume();
        } else this.tick();
    }
    resume() {
        const required = this.active().map(index => this.slots.find(slot => slot.index === index));
        const failed = required.find(slot => slot?.error);
        if (failed) { this.fail(failed.error); return false; }
        if (required.some(slot => !slot?.ready)) return false;
        this.state();
        const run = this.run;
        for (const slot of required) if (slot.video.paused) {
            void slot.video.play().catch(error => {
                if (run === this.run && this.live) this.fail(error.message || "素材无法播放");
            });
        }
        return true;
    }
    paint() {
        const active = this.active();
        for (const slot of this.slots) {
            const visible = active.includes(slot.index);
            slot.video.style.opacity = visible ? "1" : "0";
            slot.video.style.zIndex = visible ? "2" : "1";
            slot.video.dataset.previewGain = visible ? "1" : "0";
            slot.video.volume = visible ? Math.min(1, Number(slot.video.dataset.sourceLevel || 1)) : 0;
            if (!visible) slot.video.pause();
        }
    }
    tick() {
        if (!this.live) return;
        const indices = this.active(), master = this.slots.find(slot => slot.index === indices[0]);
        if (!master?.ready || !this.resume()) return;
        const item = this.items[master.index];
        const proposed = item.outStartUs + (master.video.currentTime * 1e6
            - (item.sourceClock?.originUs || 0) - item.startUs) / (item.rate || 1);
        const boundary = this.items[master.index + 1]?.outStartUs;
        if (boundary !== undefined && proposed >= boundary && !indices.includes(master.index + 1)) {
            this.out = boundary;
            if (!this.resume()) { if (!this.live) return; this.slots.forEach(slot => slot.video.pause()); this.state(true); return; }
        } else this.out = Math.max(this.out, proposed);
        if (this.out >= this.total) { this.out = this.total; this.stop(); return; }
        this.paint(); this.state(); this.preload();
    }
    loop() { this.frame = requestAnimationFrame(() => { this.tick(); if (this.live) this.loop(); }); }
}

export function usePlanPlayer(videoRef, items, urlFor, secondRef, disabled = "") {
    const [state, setState] = useState({outUs: 0, totalUs: 0, playing: false, buffering: false});
    const engine = useRef(null);
    useLayoutEffect(() => {
        const first = videoRef.current;
        if (!first) return;
        const second = secondRef?.current || first.cloneNode(false);
        if (!secondRef) first.after(second);
        const player = new PlanPlayback([first, second], items, urlFor, setState, disabled);
        engine.current = player; player.state();
        return () => { player.dispose(); if (!secondRef) second.remove(); };
    }, [items, urlFor, disabled]);
    const seek = useCallback((target, play = false) => engine.current?.seek(target, play), []);
    const stop = useCallback(() => engine.current?.stop(), []);
    const toggle = useCallback(() => {
        const player = engine.current;
        if (player?.live) player.stop();
        else if (player) void player.seek(player.out >= player.total - 50000 ? 0 : player.out, true);
    }, []);
    return {...state, seek, stop, toggle};
}
