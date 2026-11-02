// Studio shell, step 1: design system, workspaces, and a read-only Assets workspace
// (recordings → viewer + event timeline + inspector). Edit and Deliver arrive in later steps.
import {h, render} from "../vendor/preact.module.js";
import {useCallback, useEffect, useMemo, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";

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
        try { return {ok: true, value: await task(controller.signal)}; }
        catch (error) { return controller.signal.aborted ? {ok: false, aborted: true} : {ok: false, error}; }
    }, []);
}

function App() {
    const prefs = useMemo(loadPrefs, []);
    const [workspace, setWorkspace] = useState(prefs.workspace || "assets");
    const [layout, setLayout] = useState({bin: prefs.bin !== false, insp: prefs.insp !== false});
    const [projects, setProjects] = useState([]);
    const [project, setProject] = useState("");
    const [runs, setRuns] = useState([]);
    const [runId, setRunId] = useState("");
    const [view, setView] = useState(null);
    const [works, setWorks] = useState([]);
    const [selected, setSelected] = useState(null);
    const [status, setStatus] = useState("正在读取项目…");
    const [time, setTime] = useState(0);
    const video = useRef(null);
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
        setRuns([]); setView(null); setSelected(null); setWorks([]);
        if (!project) return;
        setStatus("正在读取录像…");
        latestRuns((signal) => client.runs(project, signal)).then((result) => {
            if (result.aborted) return;
            if (!result.ok) return setStatus(result.error.message);
            const list = result.value.runs;
            setRuns(list);
            const usable = list.filter((r) => r.completedEligible);
            const keep = usable.find((r) => r.id === prefs.runId) || usable[0];
            setRunId(keep ? keep.id : "");
            setStatus(usable.length ? "" : "这个项目还没有分析完成的录像。");
        });
        latestWorks((signal) => client.creationJobs(project, signal)).then((result) => { if (result.ok) setWorks(result.value.jobs); });
    }, [project]);

    useEffect(() => {
        setView(null); setSelected(null); setTime(0);
        if (!project || !runId) return;
        setStatus("正在读取时间线…");
        latestView((signal) => client.inspect(project, runId, signal)).then((result) => {
            if (result.aborted) return;
            if (!result.ok) return setStatus(`时间线读取失败：${result.error.message}`);
            if (result.value.runId !== runId) return setStatus("返回的录像与选择不一致，请重试。");
            setView(result.value); setStatus("");
        });
    }, [project, runId]);

    const seek = useCallback((us, play = false) => {
        const el = video.current; if (!el) return;
        el.currentTime = seconds(us); setTime(us);
        if (play) void el.play().catch(() => {});
    }, []);
    const selectEvent = useCallback((event) => { setSelected(event); seek(event.startUs); }, [seek]);

    useEffect(() => {
        const onKey = (event) => {
            if (event.target.closest("input, textarea, select") || workspace !== "assets") return;
            const el = video.current, events = view?.timeline || [];
            if (event.key === " " && el) { event.preventDefault(); el.paused ? void el.play().catch(() => {}) : el.pause(); }
            else if ((event.key === "ArrowLeft" || event.key === "ArrowRight") && el) {
                event.preventDefault(); const step = (event.shiftKey ? 5 : 1) * (event.key === "ArrowLeft" ? -1 : 1);
                el.currentTime = Math.max(0, el.currentTime + step);
            } else if ((event.key === "j" || event.key === "l") && events.length) {
                const index = events.findIndex((e) => e === selected);
                const next = events[Math.min(events.length - 1, Math.max(0, index + (event.key === "l" ? 1 : -1)))];
                if (next) selectEvent(next);
            }
        };
        addEventListener("keydown", onKey); return () => removeEventListener("keydown", onKey);
    }, [view, selected, workspace, selectEvent]);

    const work = `work${layout.bin ? "" : " no-bin"}${layout.insp ? "" : " no-insp"}`;
    return html`<div class="shell">
        <${TopBar} ...${{workspace, setWorkspace, projects, project, setProject, layout, setLayout, status}} />
        ${workspace === "assets"
            ? html`<div class=${work}>
                <${Bin} runs=${runs} runId=${runId} setRunId=${setRunId} works=${works} hidden=${!layout.bin} />
                <div class="center">
                    <${Viewer} media=${view?.media} videoRef=${video} time=${time} setTime=${setTime} />
                    <${Timeline} view=${view} time=${time} selected=${selected} onSelect=${selectEvent} />
                </div>
                <${Inspector} view=${view} selected=${selected} run=${runs.find((r) => r.id === runId)} hidden=${!layout.insp} />
            </div>`
            : html`<${Upcoming} workspace=${workspace} />`}
        <div class="dock"><strong>创作助手</strong><span>下一步接入：用一句话描述想要的视频，方案会以胶片条出现在剪辑区。</span></div>
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

function Bin({runs, runId, setRunId, works, hidden}) {
    const groups = Object.keys(KIND).map((kind) => [kind, works.filter((job) => job.kind === kind)]).filter(([, list]) => list.length);
    return html`<aside class="panel" hidden=${hidden} aria-label="素材箱">
        <div class="panel-head">素材箱</div>
        <div class="panel-body">
            <div class="section-label">录像</div>
            ${runs.map((run) => {
                const tone = run.completedEligible ? "ok" : run.status === "failed" ? "bad" : "warn";
                const label = run.completedEligible ? timecode(run.durationUs || 0).slice(0, 5) : run.status === "failed" ? "分析失败" : "未完成";
                return html`<button class="row" aria-current=${run.id === runId} disabled=${!run.completedEligible} title=${run.sourceName}
                    onClick=${() => setRunId(run.id)}><span class=${`dot ${tone}`}></span><span class="name">${run.sourceName || run.id.slice(0, 8)}</span><span class="meta">${label}</span></button>`;
            })}
            ${!runs.length && html`<p class="note">这里会列出项目里的录像。</p>`}
            <div class="section-label">我的作品</div>
            ${groups.map(([kind, list]) => html`<details class="group" open=${kind === "render"}>
                <summary>${KIND[kind]}（${list.length}）</summary>
                ${list.slice(0, 20).map((job) => html`<div class="row" style="cursor:default"><span class=${`dot ${job.status === "completed" ? "ok" : job.status === "failed" ? "bad" : "warn"}`}></span>
                    <span class="name">${new Date(job.createdAt).toLocaleString("zh-CN", {hour12: false})}</span><span class="meta">${job.status === "completed" ? "" : job.status}</span></div>`)}
            </details>`)}
            ${!groups.length && html`<p class="note">生成的成片、方案会出现在这里。</p>`}
        </div>
    </aside>`;
}

function Viewer({media, videoRef, time, setTime}) {
    const src = media ? client.sameOrigin(media.videoUrl, "/api/media") : null;
    const [playing, setPlaying] = useState(false);
    return html`<section class="viewer" aria-label="预览窗">
        ${src
            ? html`<video ref=${videoRef} src=${src} preload="metadata" playsinline
                onTimeUpdate=${(e) => setTime(Math.round(e.currentTarget.currentTime * 1e6))}
                onPlay=${() => setPlaying(true)} onPause=${() => setPlaying(false)} onClick=${(e) => (e.currentTarget.paused ? e.currentTarget.play() : e.currentTarget.pause())}></video>`
            : html`<div class="empty">从左侧素材箱选择一段已分析的录像</div>`}
        <div class="transport">
            <button class="icon-btn" disabled=${!src} onClick=${() => { const el = videoRef.current; if (el) el.paused ? void el.play().catch(() => {}) : el.pause(); }}>${playing ? "暂停" : "播放"}</button>
            <span class="tc">${timecode(time)} / ${media ? timecode(media.durationUs) : "00:00.000"}</span>
            <span class="spacer"></span>
            <span class="tc">空格 播放/暂停 · ←/→ 1 秒 · J/L 上/下一段</span>
        </div>
    </section>`;
}

function Timeline({view, time, selected, onSelect}) {
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
                        return html`<button class="clip" aria-current=${selected === event} title=${`${event.startTimecode} ${event.displayFacts?.[0] || ""}`}
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

function Inspector({view, selected, run, hidden}) {
    const images = useMemo(() => {
        if (!selected || !view) return [];
        const byId = Object.fromEntries(view.evidence.filter((e) => e.kind === "image").map((e) => [e.id, e]));
        return selected.evidenceIds.map((id) => byId[id]).filter(Boolean).map((e) => client.sameOrigin(e.url, "/api/evidence")).filter(Boolean).slice(0, 6);
    }, [view, selected]);
    return html`<aside class="panel" hidden=${hidden} aria-label="检查器">
        <div class="panel-head">检查器</div>
        <div class="panel-body">
            ${selected ? html`
                <div class="field"><div class="k">片段</div><div class="v num">${selected.startTimecode} – ${selected.endTimecode}（${(seconds(selected.endUs - selected.startUs)).toFixed(1)} 秒）</div></div>
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

function Upcoming({workspace}) {
    const text = workspace === "edit"
        ? ["剪辑区（第 2 步）", "方案将以缩略图胶片条展示，点“预览”即可在原片上即时播放，不用先渲染。在这之前，请用旧版创作页生成视频。", "/creation", "打开旧版创作页"]
        : ["发布区（第 6 步）", "封面、文案和各平台预览包会集中在这里。在这之前，请在旧版创作页的“4. 成片”里操作。", "/creation", "打开旧版创作页"];
    return html`<div class="placeholder"><div><h2>${text[0]}</h2><p>${text[1]}</p><a class="btn" href=${text[2]}>${text[3]}</a></div></div>`;
}

const root = document.getElementById("studio");
root.replaceChildren(); root.classList.remove("boot");
render(html`<${App} />`, root);
