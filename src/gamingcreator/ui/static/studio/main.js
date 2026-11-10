// Studio shell: design system, workspaces, the read-only Assets workspace
// (recordings → viewer + event timeline + inspector) and the Edit workspace (edit.js).
import {h, render} from "../vendor/preact.module.js";
import {useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";
import "../source-clock.js";
import {BasketList, ClipSearch, useBasket} from "./basket.js";
import {PublishWorkspace} from "./publish.js";
import {EditWorkspace} from "./edit.js";
import {clipSelection, groupRecordings} from "./recordings.js";

const html = htm.bind(h);
const STORE = "studio-v1";
const WORKSPACES = [["assets", "素材"], ["edit", "剪辑"], ["deliver", "发布"]];
const KIND = {render: "成片", plan: "方案", revision: "剪辑版本", publication: "封面与文案", package: "平台预览包", narration: "旁白"};

function loadPrefs() { try { return JSON.parse(localStorage.getItem(STORE) || "{}") || {}; } catch { return {}; } }
function savePrefs(value) { try { localStorage.setItem(STORE, JSON.stringify(value)); } catch { /* Storage may be disabled. */ } }
const seconds = (us) => us / 1e6;
function timecode(us) {
    const total = Math.max(0, Math.floor(us / 1e3)), ms = total % 1000, s = Math.floor(total / 1000);
    return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
}

// Run one request at a time per slot; a newer request aborts the older one so late replies never land.
function useLatest() {
    const ref = useRef(null);
    return useCallback(async (task) => {
        ref.current?.abort(); const controller = new AbortController(); ref.current = controller;
        try {
            const value = await task(controller.signal);
            return controller.signal.aborted ? {ok: false, aborted: true} : {ok: true, value};
        }
        catch (error) { return controller.signal.aborted ? {ok: false, aborted: true} : {ok: false, error}; }
    }, []);
}

function App() {
    const prefs = useMemo(loadPrefs, []);
    const [workspace, setWorkspace] = useState(prefs.workspace || "assets");
    const [searchSeed, setSearchSeed] = useState(null);
    const findMaterial = useCallback((text) => { setSearchSeed({text, at: Date.now()}); setWorkspace("assets"); }, []);
    const [layout, setLayout] = useState({bin: prefs.bin !== false, insp: prefs.insp !== false});
    const [projects, setProjects] = useState([]);
    const [project, setProject] = useState("");
    const [runs, setRuns] = useState([]), [runsLoaded, setRunsLoaded] = useState(false);
    const [runId, setRunId] = useState("");
    const [view, setView] = useState(null);
    const [works, setWorks] = useState([]);
    const [worksProject, setWorksProject] = useState("");
    const [selected, setSelected] = useState(null);
    const [status, setStatus] = useState("正在读取项目…");
    const [time, setTime] = useState(0);
    const [open, setOpen] = useState(null);
    const [pendingEvent, setPendingEvent] = useState(null);
    const [basketAt, setBasketAt] = useState(0);
    const basket = useBasket(project);
    const video = useRef(null);
    const pendingSeek = useRef(null);
    const [clock, setClock] = useState(null);
    useEffect(() => {
        let active = true; setClock(null);
        const media = view?.media;
        const url = media && client.sameOrigin(media.videoUrl, "/api/media");
        if (url) SourceClock.establish(SourceClock.clockCandidates(media), new URL(url, location.href).href)
            .then(result => { if (active) setClock(result.established ? result.clock : null); });
        return () => { active = false; pendingSeek.current?.(); };
    }, [view]);
    const latestRuns = useLatest(), latestView = useLatest(), latestWorks = useLatest();

    useEffect(() => { savePrefs({project, runId, workspace, bin: layout.bin, insp: layout.insp}); }, [project, runId, workspace, layout]);

    useEffect(() => {
        client.projects().then((data) => {
            setProjects(data.projects);
            const keep = data.projects.some((p) => p.path === prefs.project) ? prefs.project : data.projects[0]?.path || "";
            setProject(keep);
            if (!data.projects.length) setStatus("还没有项目：先在旧版素材工作台准备素材。");
        }).catch((error) => setStatus(`无法读取项目：${error.message}`));
    }, []);

    useEffect(() => {
        setRuns([]); setRunsLoaded(false); setView(null); setSelected(null); setWorks([]); setOpen(null);
        if (!project) return;
        setStatus("正在读取录像…");
        latestRuns((signal) => client.runs(project, signal)).then((result) => {
            if (result.aborted) return;
            if (!result.ok) return setStatus(result.error.message);
            const list = result.value.runs;
            setRuns(list); setRunsLoaded(true);
            const usable = list.filter((r) => r.completedEligible);
            const keep = usable.find((r) => r.id === prefs.runId) || usable[0];
            setRunId(keep ? keep.id : "");
            setStatus(usable.length ? "" : "这个项目还没有分析完成的录像。");
        });
        reloadWorks();
    }, [project]);

    useEffect(() => {
        setView(null); setSelected(null); setTime(0);
        pendingSeek.current?.();
        if (!project || !runId) return;
        setStatus("正在读取时间线…");
        latestView((signal) => client.inspect(project, runId, signal)).then((result) => {
            if (result.aborted) return;
            if (!result.ok) return setStatus(`时间线读取失败：${result.error.message}`);
            if (result.value.runId !== runId) return setStatus("返回的录像与选择不一致，请重试。");
            setView(result.value); setStatus("");
        });
    }, [project, runId]);

    // A search hit or basket item opens its recording, then selects the clip once loaded.
    const showEvent = useCallback((runIdToShow, eventId, range = null) => { setWorkspace("assets"); setRunId(runIdToShow); setPendingEvent({runId: runIdToShow, eventId, range}); }, []);
    useEffect(() => {
        if (!pendingEvent || !view || pendingEvent.runId !== view.runId) return;
        const event = view.timeline.find((e) => e.eventId === pendingEvent.eventId);
        if (event) { setPendingEvent(null); selectEvent(pendingEvent.range ? {...clipSelection(event, view.media?.durationUs), startUs: pendingEvent.range.startUs, endUs: pendingEvent.range.endUs} : event); }
    }, [view, pendingEvent]);
    const thumbOf = (event) => {
        const image = (view?.evidence || []).find((e) => e.id === event?.evidenceIds?.[0] && e.kind === "image");
        return image ? client.sameOrigin(image.url, "/api/evidence") : null;
    };
    const currentRun = runs.find((r) => r.id === runId);
    const toggleBasket = (event) => { if (event && currentRun) basket.toggle(event, currentRun, thumbOf(event)); };

    const reloadWorks = useCallback(() => {
        if (project) latestWorks((signal) => client.creationJobs(project, signal)).then((result) => { if (result.ok) { setWorksProject(project); setWorks(result.value.jobs); } });
    }, [project]);
    // After export, open exactly that render in Publish (not just the newest one).
    const publishRender = useCallback((jobId) => { reloadWorks(); setOpen({id: jobId, kind: "render", project, at: Date.now()}); setWorkspace("deliver"); }, [project, reloadWorks]);
    const openWork = useCallback((job) => {
        if (!["plan", "revision", "render", "publication", "package"].includes(job.kind) || job.status !== "completed") return;
        setOpen({id: job.jobId, kind: job.kind, project, at: Date.now()}); setWorkspace(["publication", "package"].includes(job.kind) ? "deliver" : "edit");
    }, [project]);

    const seek = useCallback((us, play = false) => {
        const el = video.current, target = SourceClock.sourceUsToPlayerSeconds(clock, us);
        if (!el || target === null) return;
        pendingSeek.current?.(); let active = true;
        pendingSeek.current = () => { active = false; };
        void SourceClock.settleExact(el, target, {toleranceSeconds: clock.axisToleranceUs / 1e6, isCurrent: () => active && video.current === el}).then(actual => {
            if (!active || video.current !== el || actual === null) return;
            const source = SourceClock.playerToSourceUs(clock, actual);
            if (source !== null) setTime(source);
            if (play) void el.play().catch(() => {});
        });
    }, [clock]);
    const selectEvent = useCallback((event) => {
        const selection = clipSelection(event, view?.media?.durationUs);
        video.current?.pause(); setSelected(selection); seek(clock ? Math.max(selection.startUs, clock.videoStartUs) : selection.startUs);
    }, [seek, view, clock]);
    useEffect(() => { if (clock && selected) seek(Math.max(selected.startUs, clock.videoStartUs)); }, [clock]);
    const changeRange = (range) => {
        const next = {...selected, ...range};
        const point = next.analysisStartUs === next.analysisEndUs;
        const covers = point ? next.startUs <= next.analysisStartUs && (next.analysisStartUs < next.endUs || next.endUs === next.sourceDurationUs && next.analysisStartUs === next.endUs)
            : next.startUs < next.analysisEndUs && next.endUs > next.analysisStartUs;
        if (!Number.isSafeInteger(next.startUs) || !Number.isSafeInteger(next.endUs) || next.startUs < 0 || next.endUs <= next.startUs || next.endUs > view.media.durationUs || !covers) return;
        video.current?.pause(); setSelected(next); seek(clock ? Math.max(next.startUs, clock.videoStartUs) : next.startUs);
        if (basket.ids.has(next.eventId)) basket.updateRange(next.eventId, {startUs: next.startUs, endUs: next.endUs});
    };

    useEffect(() => {
        const onKey = (event) => {
            if (event.target.closest("input, textarea, select") || workspace !== "assets") return;
            const el = video.current, events = view?.timeline || [];
            if (event.key === " " && el) { event.preventDefault(); el.paused ? void el.play().catch(() => {}) : el.pause(); }
            else if ((event.key === "ArrowLeft" || event.key === "ArrowRight") && el) {
                event.preventDefault(); const step = (event.shiftKey ? 5 : 1) * (event.key === "ArrowLeft" ? -1 : 1);
                const source = SourceClock.playerToSourceUs(clock, el.currentTime);
                if (source !== null) seek(Math.min(clock.durationUs, Math.max(0, source + step * 1e6)));
            } else if ((event.key === "b" || event.key === "B") && selected) {
                toggleBasket(selected);
            } else if ((event.key === "j" || event.key === "l") && events.length) {
                const index = events.findIndex((e) => e.eventId === selected?.eventId);
                const next = events[Math.min(events.length - 1, Math.max(0, index + (event.key === "l" ? 1 : -1)))];
                if (next) selectEvent(next);
            }
        };
        addEventListener("keydown", onKey); return () => removeEventListener("keydown", onKey);
    }, [view, selected, workspace, selectEvent, basket, currentRun, clock, seek]);

    const work = `work${layout.bin ? "" : " no-bin"}${layout.insp ? "" : " no-insp"}`;
    return html`<div class="shell">
        <${TopBar} ...${{workspace, setWorkspace, projects, project, setProject, layout, setLayout, status}} />
        ${workspace === "assets"
            ? html`<div class=${work}>
                <${Bin} runs=${runs} runsLoaded=${runsLoaded} runId=${runId} setRunId=${setRunId} works=${worksProject === project ? works : []} onOpen=${openWork} hidden=${!layout.bin}
                    top=${html`<${ClipSearch} project=${project} runs=${runs} runId=${runId} basket=${basket} seed=${searchSeed} onShow=${(run, event) => showEvent(run.id, event.eventId)} />
                        <${BasketList} basket=${basket} onShow=${(item) => showEvent(item.runId, item.eventId, item)} onUse=${() => { setBasketAt(Date.now()); setWorkspace("edit"); }} />`} />
                <div class="center">
                    <${Viewer} onClockInvalid=${() => setClock(null)} clock=${clock} media=${view?.media} videoRef=${video} time=${time} setTime=${setTime} selected=${selected} onFullSource=${() => setSelected(null)} />
                    <${Timeline} view=${view} time=${time} selected=${selected} onSelect=${selectEvent} inBasket=${basket.ids} />
                </div>
                <${Inspector} view=${view} selected=${selected} run=${currentRun} hidden=${!layout.insp} inBasket=${!!selected && basket.ids.has(selected.eventId)} onBasket=${() => toggleBasket(selected)} onRange=${changeRange} />
            </div>`
            : workspace === "edit"
                ? html`<${EditWorkspace} project=${project} runs=${runs} open=${open?.project === project ? open : null} onWorksChanged=${reloadWorks} layout=${layout} basket=${basket} basketAt=${basketAt} onBasketSeen=${() => setBasketAt(0)} onFindMaterial=${findMaterial} onPublish=${publishRender} />`
                : html`<${PublishWorkspace} project=${project} works=${worksProject === project ? works : []} open=${open?.project === project ? open : null} onWorksChanged=${reloadWorks} layout=${layout} />`}
        ${workspace === "assets" && html`<div class="dock"><strong>提示</strong><span>左上角“搜索片段”按描述找画面，“+”或 B 键加入片段篮，再点“用片段篮生成方案”。一句话修改镜头在剪辑区底部。</span></div>`}
    </div>`;
}

function TopBar({workspace, setWorkspace, projects, project, setProject, layout, setLayout, status}) {
    return html`<header class="topbar">
        <div class="brand">Gaming Creator<small>工作台预览版</small></div>
        <div class="tabs" role="tablist" aria-label="工作区">
            ${WORKSPACES.map(([id, label]) => html`<button role="tab" aria-selected=${workspace === id} onClick=${() => setWorkspace(id)}>${label}</button>`)}
        </div>
        <select class="select" aria-label="项目" value=${project} onChange=${(e) => setProject(e.currentTarget.value)}>
            ${projects.map((p) => html`<option value=${p.path}>${p.name || p.path}</option>`)}
        </select>
        <span class="status" role="status" aria-live="polite">${status}</span>
        <span class="spacer"></span>
        <button class="icon-btn" aria-pressed=${layout.bin} title="显示或隐藏素材箱" onClick=${() => setLayout({...layout, bin: !layout.bin})}>素材箱</button>
        <button class="icon-btn" aria-pressed=${layout.insp} title="显示或隐藏检查器" onClick=${() => setLayout({...layout, insp: !layout.insp})}>检查器</button>
        <a class="link" href="/">旧版素材工作台</a>
        <a class="link" href="/creation">旧版创作页</a>
    </header>`;
}

function Bin({runs, runsLoaded = false, runId, setRunId, works, onOpen, hidden, top}) {
    const groups = Object.keys(KIND).map((kind) => [kind, works.filter((job) => job.kind === kind)]).filter(([, list]) => list.length);
    return html`<aside class="panel" hidden=${hidden} aria-label="素材箱">
        <div class="panel-head">素材箱</div>
        <div class="panel-body">
            ${top}
            <div class="section-label">原始录像（${groupRecordings(runs).length} 个文件）</div>
            ${groupRecordings(runs).map((group) => html`<${Recording} group=${group} runId=${runId} onSelect=${setRunId} />`)}
            ${!runs.length && (runsLoaded ? html`<div class="note first-run" role="note" aria-label="第一次使用">
                <strong>第一次使用：三步出片</strong>
                <ol><li>打开<a class="link" href="/">素材工作台</a>，选择本地录像并分析（会先显示费用确认，本页不会发送任何请求）。</li>
                <li>回到这里，在左上角“搜索片段”挑画面放进片段篮。</li><li>到“剪辑”填需求、生成方案，再导出成片和发布包。</li></ol>
            </div>` : html`<p class="note">这里会列出项目里的录像。</p>`)}
            <div class="section-label">我的作品</div>
            ${groups.map(([kind, list]) => html`<details class="group" open=${kind === "render"}>
                <summary>${KIND[kind]}（${list.length}）</summary>
                ${list.slice(0, 20).map((job) => {
                    const openable = ["plan", "revision", "render", "publication", "package"].includes(job.kind) && job.status === "completed";
                    const newest = openable && job === list.find((j) => j.status === "completed");
                    const reason = job.error?.message || "";
                    const meta = job.status === "completed" ? (openable ? (newest ? "最新 · 打开" : "打开") : "") : client.jobStatus(job.status) + (reason ? `：${reason}` : "");
                    return html`<button class="row" disabled=${!openable} title=${openable ? (["publication", "package"].includes(job.kind) ? "在发布区打开" : "在剪辑区打开") : reason || client.jobStatus(job.status)} onClick=${() => onOpen(job)}><span class=${`dot ${job.status === "completed" ? "ok" : job.status === "failed" ? "bad" : "warn"}`}></span>
                    <span class="name">${new Date(job.createdAt).toLocaleString("zh-CN", {hour12: false})}</span><span class="meta">${meta}</span></button>`;
                })}
            </details>`)}
            ${!groups.length && html`<p class="note">生成的成片、方案会出现在这里。</p>`}
        </div>
    </aside>`;
}

function Recording({group, runId, onSelect}) {
    const run = group.runs.find((r) => r.id === runId) || group.runs.find((r) => r.completedEligible) || group.runs[0];
    return html`<div class="recording">
        <button class="row" aria-current=${group.runs.some((r) => r.id === runId)} disabled=${!run.completedEligible} title=${run.sourceName}
            onClick=${() => onSelect(run.id)}><span class=${`dot ${run.completedEligible ? "ok" : "bad"}`}></span><span class="name">${run.sourceName || run.id.slice(0, 8)}</span><span class="meta">${timecode(run.durationUs || 0).slice(0, 5)}</span></button>
        <details class="group"><summary>分析记录（${group.runs.length}）</summary>
            ${group.runs.map((version, i) => html`<button class="row" disabled=${!version.completedEligible} aria-current=${version.id === runId}
                onClick=${() => onSelect(version.id)}><span class="name">${version.analysisProfile || "分析"} · ${i + 1}</span><span class="meta">${version.completedEligible ? "查看" : version.status === "failed" ? "分析失败" : "未完成"}</span></button>`)}
        </details>
    </div>`;
}

function Viewer({onClockInvalid, clock, media, videoRef, time, setTime, selected, onFullSource}) {
    const src = media ? client.sameOrigin(media.videoUrl, "/api/media") : null;
    const [playing, setPlaying] = useState(false);
    const bounded = selected && clock && selected.startUs < selected.endUs
        && SourceClock.sourceUsToPlayerSeconds(clock, selected.startUs) !== null
        && SourceClock.sourceUsToPlayerSeconds(clock, selected.endUs) !== null;
    const playableStart = bounded ? Math.max(selected.startUs, clock.videoStartUs) : null;
    const hasPicture = bounded && playableStart < Math.min(selected.endUs, clock.videoEndUs);
    useLayoutEffect(() => {
        const el = videoRef.current;
        if (!el || !bounded) return;
        let frame = 0;
        const bound = () => {
            cancelAnimationFrame(frame);
            if (el.seeking) { if (!el.paused) frame = requestAnimationFrame(bound); return; }
            const source = SourceClock.playerToSourceUs(clock, el.currentTime);
            if (source !== null && source >= selected.endUs) {
                el.pause();
                if (Math.abs(source - selected.endUs) > 1000) el.currentTime = SourceClock.sourceUsToPlayerSeconds(clock, selected.endUs);
                setTime(selected.endUs);
            } else if (!el.paused) frame = requestAnimationFrame(bound);
        };
        const play = () => {
            if (!hasPicture) { el.pause(); return; }
            const source = SourceClock.playerToSourceUs(clock, el.currentTime);
            if (source === null || source >= selected.endUs || source < playableStart) el.currentTime = SourceClock.sourceUsToPlayerSeconds(clock, playableStart);
            cancelAnimationFrame(frame); bound();
        };
        const pause = () => cancelAnimationFrame(frame);
        el.addEventListener("play", play); el.addEventListener("timeupdate", bound); el.addEventListener("pause", pause);
        return () => { cancelAnimationFrame(frame); el.removeEventListener("play", play); el.removeEventListener("timeupdate", bound); el.removeEventListener("pause", pause); };
    }, [selected, src, clock, bounded, playableStart, hasPicture]);
    return html`<section class="viewer" aria-label="预览窗" data-source-clock=${clock ? "ready" : "unavailable"}>
        ${src
            ? html`<video ref=${videoRef} src=${src} preload="metadata" playsinline
                onTimeUpdate=${(e) => { const source = SourceClock.playerToSourceUs(clock, e.currentTarget.currentTime); if (source !== null) setTime(source); }}
                onDurationChange=${e => { if (clock && SourceClock.durationChangeVerdict(clock, e.currentTarget.duration, true)) onClockInvalid(); }}
                onPlay=${() => setPlaying(true)} onPause=${() => setPlaying(false)} onClick=${(e) => (e.currentTarget.paused ? void e.currentTarget.play().catch(() => {}) : e.currentTarget.pause())}></video>`
            : html`<div class="empty">从左侧素材箱选择一段已分析的录像</div>`}
        <div class="transport">
            <button class="icon-btn" disabled=${!src} onClick=${() => { const el = videoRef.current; if (el) el.paused ? void el.play().catch(() => {}) : el.pause(); }}>${playing ? "暂停" : "播放"}</button>
            <span class="tc">${clock ? timecode(time) : "源时间未校准"} / ${media ? timecode(media.durationUs) : "00:00.000"}</span>
            <span class="spacer"></span>
            ${!clock && src ? html`<span class="hint">无法精确定位片段，可观看整段录像</span>` : null}
            ${bounded && !hasPicture ? html`<span class="hint">选段内没有可播放画面，不能预览；取景范围已保留</span>`
                : bounded && selected.startUs < clock.videoStartUs ? html`<span class="hint">片段开头无画面，从首个可播放画面开始，仍在选段终点暂停</span>` : null}
            ${selected && html`<span class="hint">${bounded ? "仅播放选中片段" : "片段寻址不可用"}</span><button class="btn ghost" onClick=${onFullSource}>查看整段录像</button>`}
            <span class="tc">空格 播放/暂停 · ←/→ 1 秒 · J/L 上/下一段</span>
        </div>
    </section>`;
}

function Timeline({view, time, selected, onSelect, inBasket}) {
    const area = useRef(null);
    const [width, setWidth] = useState(800);
    const [zoom, setZoom] = useState(1);
    useEffect(() => {
        const el = area.current; if (!el) return;
        const observer = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width - 24)));
        observer.observe(el); return () => observer.disconnect();
    }, []);
    const duration = view?.media?.durationUs || 0;
    const scale = duration ? (width * zoom) / duration : 0; // px per µs
    const thumbs = useMemo(() => Object.fromEntries((view?.evidence || []).filter((e) => e.kind === "image").map((e) => [e.id, client.sameOrigin(e.url, "/api/evidence")])), [view]);
    const step = duration ? [1, 2, 5, 10, 15, 30, 60, 120, 300].find((s) => s * 1e6 * scale >= 70) || 600 : 0;
    const ticks = step ? Array.from({length: Math.floor(seconds(duration) / step) + 1}, (_, i) => i * step) : [];
    return html`<section class="timeline" aria-label="时间轴">
        <div class="panel-head">时间轴
            <span class="track-label">${view ? `${view.timeline.length} 个分析片段` : ""}</span>
            <span class="spacer"></span>
            <button class="icon-btn" onClick=${() => setZoom(Math.max(1, zoom / 2))} disabled=${zoom <= 1}>－</button>
            <button class="icon-btn" onClick=${() => setZoom(1)}>适配</button>
            <button class="icon-btn" onClick=${() => setZoom(Math.min(32, zoom * 2))}>＋</button>
        </div>
        <div class="track-area" ref=${area}>
            ${view && html`<div style=${{width: `${width * zoom}px`, position: "relative"}}>
                <div class="ruler">${ticks.map((s) => html`<span style=${{left: `${s * 1e6 * scale}px`}}>${timecode(s * 1e6).slice(0, 5)}</span>`)}</div>
                <div class="track">
                    ${view.timeline.map((event) => {
                        const thumb = thumbs[event.evidenceIds?.[0]];
                        return html`<button class=${`clip${inBasket.has(event.eventId) ? " in-basket" : ""}`} aria-current=${selected?.eventId === event.eventId} title=${`${event.startTimecode} ${event.displayFacts?.[0] || ""}`}
                            style=${{left: `${event.startUs * scale}px`, width: `${Math.max(3, (event.endUs - event.startUs) * scale - 1)}px`, backgroundImage: thumb ? `url("${thumb}")` : "none"}}
                            onClick=${() => onSelect(event)} aria-label=${`片段 ${event.startTimecode}`}></button>`;
                    })}
                    <div class="playhead" style=${{left: `${time * scale}px`}}></div>
                </div>
            </div>`}
            ${!view && html`<p class="note">选中录像后，这里按时间显示它的分析片段（缩略图来自分析时的采样帧）。</p>`}
        </div>
    </section>`;
}

function Inspector({view, selected, run, hidden, inBasket, onBasket, onRange}) {
    const images = useMemo(() => {
        if (!selected || !view) return [];
        const byId = Object.fromEntries(view.evidence.filter((e) => e.kind === "image").map((e) => [e.id, e]));
        return selected.evidenceIds.map((id) => byId[id]).filter(Boolean).map((e) => client.sameOrigin(e.url, "/api/evidence")).filter(Boolean).slice(0, 6);
    }, [view, selected]);
    return html`<aside class="panel" hidden=${hidden} aria-label="检查器">
        <div class="panel-head">检查器</div>
        <div class="panel-body">
            ${selected ? html`
                <div class="field"><div class="k">取景选段</div><div class="v num">${timecode(selected.startUs)} – ${timecode(selected.endUs)}（${(seconds(selected.endUs - selected.startUs)).toFixed(1)} 秒）</div>
                    <div class="pair even"><label class="form-row">入点（秒）<input class="input" aria-label="选段入点" type="number" min="0" step="0.1" value=${selected.startUs / 1e6} onInput=${(e) => { if (e.currentTarget.value !== "") onRange({startUs: Math.round(Number(e.currentTarget.value) * 1e6)}); }} /></label>
                        <label class="form-row">出点（秒）<input class="input" aria-label="选段出点" type="number" min="0" max=${view.media.durationUs / 1e6} step="0.1" value=${selected.endUs / 1e6} onInput=${(e) => { if (e.currentTarget.value !== "") onRange({endUs: Math.round(Number(e.currentTarget.value) * 1e6)}); }} /></label></div>
                    <p class="hint">分析区间 ${timecode(selected.analysisStartUs)} – ${timecode(selected.analysisEndUs)}；取景可包含上下文，需覆盖原观察位置。扩展画面请回看确认。</p>
                    <div class="actions-row"><button class=${inBasket ? "btn ghost" : "btn"} onClick=${onBasket}>${inBasket ? "移出片段篮" : "加入片段篮"}</button><span class="hint">快捷键 B</span></div></div>
                <div class="field"><div class="k">分析描述（模型观察，未经人工核对）</div><ul class="facts">${(selected.displayFacts || selected.observableFacts || []).map((fact) => html`<li>${fact}</li>`)}</ul></div>
                ${selected.uncertainty && html`<div class="field"><div class="k">不确定</div><div class="v">${selected.uncertainty}</div></div>`}
                <div class="field"><div class="k">采样帧</div><div class="thumbs">${images.map((src) => html`<img src=${src} alt="分析采样帧" loading="lazy" />`)}</div></div>`
            : run ? html`
                <div class="field"><div class="k">录像</div><div class="v">${run.sourceName}</div></div>
                <div class="field"><div class="k">时长</div><div class="v num">${timecode(run.durationUs || 0)}</div></div>
                <div class="field"><div class="k">分析</div><div class="v"><span class="badge">${view ? `${view.timeline.length} 个片段 · ${view.evidence.length} 张采样帧` : "读取中"}</span></div></div>
                <p class="note">点时间轴上的片段，查看它的描述和采样帧。</p>`
            : html`<p class="note">选中录像或片段后，这里显示它的详细信息。</p>`}
        </div>
    </aside>`;
}

const root = document.getElementById("studio");
root.replaceChildren(); root.classList.remove("boot");
render(html`<${App} />`, root);
