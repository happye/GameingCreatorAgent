// Studio shell: design system, workspaces, the read-only Assets workspace
// (recordings → viewer + event timeline + inspector) and the Edit workspace (edit.js).
import {h, render} from "../vendor/preact.module.js";
import {useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";
import "../source-clock.js";
import "../preview-preference.js";
import {BasketList, ClipSearch, useBasket} from "./basket.js";
import {PublishWorkspace} from "./publish.js";
import {confirmLeave, renderRate} from "./edit.js";
import {WorksWorkspace} from "./works.js";
import {clipSelection, groupRecordings} from "./recordings.js";

const html = htm.bind(h);
const STORE = "studio-v1";
const WORKSPACES = [["assets", "素材"], ["edit", "剪辑"], ["deliver", "发布"]];
const KIND = {render: "成片", plan: "方案", revision: "剪辑版本", publication: "封面与文案", package: "平台预览包", narration: "旁白"};
const canOpenWork = (job) => job.status === "completed" && ["plan", "revision", "render", "publication", "package"].includes(job.kind);

function readJobLink() {
    const params = new URLSearchParams(location.search);
    if (!params.has("job")) return null;
    const project = params.get("project"), id = params.get("job");
    return params.getAll("project").length === 1 && project && params.getAll("job").length === 1 && /^[a-f0-9]{32}$/.test(id)
        ? {project, id} : {};
}

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
    const consumedOpen = useRef(new WeakSet());
    const prefs = useMemo(loadPrefs, []);
    const initialLink = useMemo(readJobLink, []);
    const pendingLink = useRef(initialLink);
    const [linkStatus, setLinkStatus] = useState(initialLink ? "正在打开指定作品…" : "");
    const [workspace, setWorkspace] = useState(initialLink ? "assets" : prefs.workspace || "assets");
    const [searchSeed, setSearchSeed] = useState(null);
    // Unsaved edit/publish work: leaving the workspace or project asks first (J1 data loss).
    const dirtyRef = useRef(false);
    const onDirtyChange = useCallback((value) => { dirtyRef.current = value; }, []);
    const leave = useCallback((fn) => {
        if (dirtyRef.current && !confirmLeave()) return false;
        dirtyRef.current = false;
        pendingLink.current = null;
        setLinkStatus("");
        fn();
        return true;
    }, []);
    useEffect(() => {
        const warn = (event) => { if (dirtyRef.current) { event.preventDefault(); event.returnValue = ""; } };
        window.addEventListener("beforeunload", warn);
        return () => window.removeEventListener("beforeunload", warn);
    }, []);
    const findMaterial = useCallback((text) => { leave(() => { setSearchSeed({text, at: Date.now()}); setWorkspace("assets"); }); }, [leave]);
    const [layout, setLayout] = useState({bin: prefs.bin !== false, insp: prefs.insp !== false});
    const [projects, setProjects] = useState([]);
    const [project, setProject] = useState("");
    const [runs, setRuns] = useState([]), [runsLoaded, setRunsLoaded] = useState(false);
    const [runId, setRunId] = useState("");
    const [view, setView] = useState(null);
    const [works, setWorks] = useState([]);
    const [worksProject, setWorksProject] = useState("");
    const [worksStatus, setWorksStatus] = useState({project: "", text: ""});
    const [workSelections, setWorkSelections] = useState({});
    const workId = workSelections[project] || "";
    const scope = JSON.stringify([project, workId]);
    const [workCatalog, setWorkCatalog] = useState({project: "", works: []});
    const [filtered, setFiltered] = useState({scope: "", jobs: [], status: ""});
    const [refreshAt, setRefreshAt] = useState(0);
    const [catalogAt, setCatalogAt] = useState(0);
    const refreshCatalog = useCallback(() => setCatalogAt(n => n + 1), []);
    const visibleJobs = workId ? (filtered.scope === scope ? filtered.jobs : []) : (worksProject === project ? works : []);
    const filterStatus = workId ? (filtered.scope === scope ? filtered.status : "正在读取作品…")
        : (worksStatus.project === project ? worksStatus.text : "正在读取作品任务…");
    useEffect(() => {
        const controller = new AbortController();
        if (!project) return () => controller.abort();
        setWorkCatalog(old => ({project, works: old.project === project ? old.works : [], status: "正在读取作品目录…"}));
        client.creationWorks(project, controller.signal).then(data => {
            if (!controller.signal.aborted) setWorkCatalog({project, works: data.works || [], status: ""});
        }).catch(error => {
            if (!controller.signal.aborted) setWorkCatalog({project, works: [], status: `作品目录读取失败：${error.message}`});
        });
        return () => controller.abort();
    }, [project, catalogAt]);
    useEffect(() => {
        const controller = new AbortController();
        if (!project || !workId) return () => controller.abort();
        setFiltered(old => ({scope, jobs: old.scope === scope ? old.jobs : [], status: "正在读取作品任务…"}));
        client.creationJobs(project, controller.signal, workId).then(data => {
            if (!controller.signal.aborted) setFiltered({scope, jobs: data.jobs, status: data.truncated ? "仅显示最近的作品任务。" : ""});
        }).catch(error => {
            if (!controller.signal.aborted) setFiltered({scope, jobs: [], status: `作品任务读取失败：${error.message}`});
        });
        return () => controller.abort();
    }, [project, workId, refreshAt]);
    const [selected, setSelected] = useState(null);
    const [status, setStatus] = useState("正在读取项目…");
    const [time, setTime] = useState(0);
    const [open, setOpen] = useState(null);
    const applyOpen = useCallback((job, projectId) => {
        setOpen({id: job.jobId, kind: job.kind, planId: job.planId || job.editor?.planId, project: projectId, at: Date.now()});
        setWorkspace(["publication", "package"].includes(job.kind) ? "deliver" : "edit");
    }, []);
    const [pendingEvent, setPendingEvent] = useState(null);
    const [basketAt, setBasketAt] = useState(0);
    const basket = useBasket(project);
    const video = useRef(null);
    const pendingSeek = useRef(null);
    const [clock, setClock] = useState(null);
    const [preview, setPreview] = useState({url: null, source: null, reason: null});
    const [previewPreferAt, setPreviewPreferAt] = useState(0);
    const httpFailed = useRef(new Set());
    const proxyFailReason = useRef(null);
    const [httpFailAt, setHttpFailAt] = useState(0);
    const preferProxy = (previewPreferAt >= 0) && (httpFailAt >= 0)
        && !httpFailed.current.has(view?.media?.id)
        && ((globalThis.PreviewPreference?.get(view?.media?.id) ?? true));
    const proxyHttpFailed = Boolean(view?.media?.id && httpFailed.current.has(view.media.id));
    const timeRef = useRef(0);
    const wantPlay = useRef(false);
    timeRef.current = time;
    useEffect(() => {
        let active = true; setClock(null);
        if (video.current) {
            wantPlay.current = !video.current.paused;
            const source = clock ? SourceClock.playerToSourceUs(clock, video.current.currentTime) : null;
            if (source !== null) { timeRef.current = source; setTime(source); }
        }
        const media = view?.media;
        const original = media && client.sameOrigin(media.videoUrl, "/api/media");
        const offered = media ? client.choosePreview(media.videoUrl, media.proxyUrl, preferProxy) : {url: null, source: null};
        const attempted = offered.source === "proxy";
        if (!original) {
            setPreview({url: null, source: null, reason: null});
            return () => { active = false; pendingSeek.current?.(); };
        }
        const abs = (url) => new URL(url, location.href).href;
        SourceClock.alignPreview(
            SourceClock.clockCandidates(media),
            abs(original),
            attempted ? abs(offered.url) : null,
            attempted,
        ).then((result) => {
            if (!active) return;
            if (attempted && (result.reason === "proxy_http_failed" || result.reason === "proxy_decode_failed") && media?.id && !httpFailed.current.has(media.id)) {
                httpFailed.current.add(media.id);
                proxyFailReason.current = result.reason;
                setHttpFailAt((n) => n + 1);
            }
            setClock(result.established ? result.clock : null);
            setPreview({
                url: result.url,
                source: result.source,
                reason: attempted && result.source === "original" ? result.reason : null,
            });
        });
        return () => { active = false; pendingSeek.current?.(); };
    }, [view, preferProxy]);
    useEffect(() => {
        const el = video.current;
        if (!el || !clock || !preview.url) return;
        const target = SourceClock.sourceUsToPlayerSeconds(clock, timeRef.current);
        if (target === null) return;
        let active = true;
        const matches = () => {
            try {
                const now = el.currentSrc || el.getAttribute("src") || "";
                return new URL(now, location.href).href === new URL(preview.url, location.href).href;
            } catch { return false; }
        };
        pendingSeek.current?.();
        const onReady = () => {
            if (!active || !matches()) return;
            void SourceClock.settleExact(el, target, {
                toleranceSeconds: clock.axisToleranceUs / 1e6,
                isCurrent: () => active && video.current === el && matches(),
            }).then((actual) => {
                if (!active || actual === null || video.current !== el || !matches()) return;
                const source = SourceClock.playerToSourceUs(clock, actual);
                if (source !== null) setTime(source);
                if (wantPlay.current) void el.play().catch(() => {});
                else el.pause();
            });
        };
        pendingSeek.current = () => { active = false; el.removeEventListener("loadedmetadata", onReady); };
        if (matches() && el.readyState >= 1) onReady();
        else el.addEventListener("loadedmetadata", onReady);
    }, [preview.url, clock]);
    const latestRuns = useLatest(), latestView = useLatest(), latestWorks = useLatest();

    useEffect(() => { savePrefs({project, runId, workspace, bin: layout.bin, insp: layout.insp}); }, [project, runId, workspace, layout]);

    useEffect(() => {
        const controller = new AbortController();
        const fail = (message) => {
            pendingLink.current = null;
            setLinkStatus(message);
        };
        client.projects(controller.signal).then(async ({projects: list}) => {
            setProjects(list);
            const link = pendingLink.current;
            const linkedProject = list.find((item) => item.path === link?.project);
            const keep = linkedProject || list.find((item) => item.path === prefs.project) || list[0];
            setProject(keep?.path || "");
            if (!list.length) { setStatus("还没有项目：先在旧版素材工作台准备素材。"); setRunsLoaded(true); }
            if (!link) return;
            if (!link.id) return fail("作品链接无效。");
            if (!linkedProject) return fail("作品链接的项目在本机不可用。");
            try {
                const job = await client.job(link.id, controller.signal);
                if (pendingLink.current !== link || controller.signal.aborted) return;
                if (job.jobId !== link.id || job.projectId !== link.project || !canOpenWork(job)) return fail("指定作品在这个项目中不可用。");
                pendingLink.current = null;
                setLinkStatus("");
                applyOpen(job, link.project);
            } catch {
                if (pendingLink.current === link && !controller.signal.aborted) fail("无法读取链接中的指定作品。");
            }
        }).catch((error) => {
            if (controller.signal.aborted) return;
            if (pendingLink.current) fail("无法读取作品链接的项目。");
            setStatus(`无法读取项目：${error.message}`);
        });
        return () => controller.abort();
    }, []);

    useEffect(() => {
        setRuns([]); setRunsLoaded(false); setView(null); setSelected(null); setWorks([]);
        setOpen(current => current?.project === project ? current : null);
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

    // A number, not the list: passing the list re-rendered the edit page on every list refresh.
    const secondsPerSecond = useMemo(() => (worksProject === project ? renderRate(works) : null), [works, worksProject, project]);
    const reloadWorks = useCallback(() => {
        setRefreshAt(n => n + 1);
        setWorksStatus({project, text: "正在读取作品任务…"});
        if (project) latestWorks((signal) => client.creationJobs(project, signal)).then((result) => {
            if (result.aborted) return;
            if (result.ok) {
                setWorksProject(project); setWorks(result.value.jobs);
                setWorksStatus({project, text: result.value.truncated ? "仅显示最近的作品任务。" : ""});
            } else setWorksStatus({project, text: `作品任务读取失败：${result.error.message}`});
        });
    }, [project]);
    // After export, open exactly that render in Publish (not just the newest one).
    const publishRender = useCallback((jobId, selectedWorkId) => { leave(() => { setWorkSelections(old => ({...old, [project]: selectedWorkId || ""})); reloadWorks(); setOpen({id: jobId, kind: "render", project, at: Date.now()}); setWorkspace("deliver"); }); }, [project, reloadWorks, leave]);
    const openWork = useCallback((job) => {
        if (canOpenWork(job)) leave(() => applyOpen(job, project));
    }, [project, leave, applyOpen]);

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
    const catalog = workCatalog.project === project ? workCatalog.works : [];
    const filterControls = html`<label class="field form-row">按作品查看
        <select class="select" aria-label="按作品查看" value=${workId} disabled=${!project} onChange=${e => {
            const next = e.currentTarget.value;
            if (next === workId) return;
            if (!leave(() => { setOpen(null); setWorkSelections(old => ({...old, [project]: next})); })) e.currentTarget.value = workId;
        }}>
            <option value="">全部作品</option>
            ${workId && !catalog.some(item => item.workId === workId) ? html`<option value=${workId}>作品 ${workId.slice(0, 8)}</option>` : null}
            ${catalog.map(item => html`<option key=${item.workId} value=${item.workId}>${item.workName || `未命名作品 ${item.workId.slice(0, 8)}`}</option>`)}
        </select></label>
        <p class="hint" role="status">${filterStatus || (workCatalog.project === project ? workCatalog.status : "正在读取作品目录…")}</p>`;
    return html`<div class="shell">
        <${TopBar} ...${{workspace, setWorkspace: (w) => w !== workspace && leave(() => setWorkspace(w)), projects, project, setProject: (p) => p === project || leave(() => setProject(p)), layout, setLayout, status: linkStatus || status}} />
        ${workspace === "assets"
            ? html`<div class=${work}>
                <${Bin} runs=${runs} runsLoaded=${runsLoaded} runId=${runId} setRunId=${setRunId} works=${visibleJobs} onOpen=${openWork} hidden=${!layout.bin} filterControls=${filterControls}
                    top=${html`<${ClipSearch} project=${project} runs=${runs} runId=${runId} basket=${basket} seed=${searchSeed} onShow=${(run, event) => showEvent(run.id, event.eventId)} />
                        <${BasketList} basket=${basket} onShow=${(item) => showEvent(item.runId, item.eventId, item)} onUse=${() => { setBasketAt(Date.now()); setWorkspace("edit"); }} />`} />
                <div class="center">
                    <${Viewer} onClockInvalid=${() => setClock(null)} clock=${clock} media=${view?.media} preview=${preview} preferProxy=${preferProxy} proxyHttpFailed=${proxyHttpFailed} proxyFailReason=${proxyFailReason.current} onPreferPreview=${(checked) => { if (view?.media?.id) { PreviewPreference.set(view.media.id, checked); if (checked) { httpFailed.current.delete(view.media.id); proxyFailReason.current = null; } } setPreviewPreferAt((n) => n + 1); }} onProxyHttpError=${(el) => { const id = view?.media?.id; if (!id || httpFailed.current.has(id)) return; httpFailed.current.add(id); proxyFailReason.current = (SourceClock.proxyLoadReason && SourceClock.proxyLoadReason(el)) || "proxy_http_failed"; setHttpFailAt((n) => n + 1); }} videoRef=${video} time=${time} setTime=${setTime} selected=${selected} onFullSource=${() => setSelected(null)} />
                    <${Timeline} view=${view} time=${time} selected=${selected} onSelect=${selectEvent} inBasket=${basket.ids} />
                </div>
                <${Inspector} view=${view} selected=${selected} run=${currentRun} hidden=${!layout.insp} inBasket=${!!selected && basket.ids.has(selected.eventId)} onBasket=${() => toggleBasket(selected)} onRange=${changeRange} />
            </div>`
            : workspace === "edit"
                ? html`<${WorksWorkspace} key=${project} onCatalogChanged=${refreshCatalog} leave=${leave} project=${project} runs=${runs} open=${open?.project === project && ["plan", "revision", "render"].includes(open.kind) ? open : null} isOpenConsumed=${intent => consumedOpen.current.has(intent)} onOpenConsumed=${intent => { if (intent) consumedOpen.current.add(intent); }} onWorksChanged=${reloadWorks} layout=${layout} basket=${basket} basketAt=${basketAt} onBasketSeen=${() => setBasketAt(0)} onFindMaterial=${findMaterial} onPublish=${publishRender} onDirtyChange=${onDirtyChange} renderSecondsPerSecond=${secondsPerSecond} />`
                : html`<${PublishWorkspace} key=${scope} project=${project} workId=${workId} works=${visibleJobs} open=${open?.project === project ? open : null} leave=${leave} onWorksChanged=${reloadWorks} layout=${layout} onDirtyChange=${onDirtyChange} filterControls=${filterControls}
                    onOpenReference=${choice => openWork({jobId: choice.sourceJobId, planId: choice.sourcePlanId, status: "completed", kind: "plan"})} />`}
        ${workspace === "assets" && html`<div class="dock"><strong>提示</strong><span>左上角“搜索片段”按描述找画面，“+”或 B 键加入片段篮，再点“用片段篮生成方案”。一句话修改镜头在剪辑区底部。</span></div>`}
    </div>`;
}

function TopBar({workspace, setWorkspace, projects, project, setProject, layout, setLayout, status}) {
    const [usageOpen, setUsageOpen] = useState(false);
    return html`<header class="topbar">
        <div class="brand">Gaming Creator<small>工作台预览版</small></div>
        <div class="tabs" role="tablist" aria-label="工作区">
            ${WORKSPACES.map(([id, label]) => html`<button role="tab" aria-selected=${workspace === id} onClick=${() => setWorkspace(id)}>${label}</button>`)}
        </div>
        <select class="select" aria-label="项目" title=${(projects.find((p) => p.path === project)?.name) || project}
            value=${project} onChange=${(e) => { if (!setProject(e.currentTarget.value)) e.currentTarget.value = project; }}>
            ${projects.map((p) => html`<option value=${p.path} title=${p.name || p.path}>${p.name || p.path}</option>`)}
        </select>
        <span class="status" role="status" aria-live="polite">${status}</span>
        <span class="spacer"></span>
        <div class="topbar-actions">
            <button class="icon-btn" aria-expanded=${usageOpen} onClick=${() => setUsageOpen(!usageOpen)}>套餐与用量</button>
            <button class="icon-btn" aria-pressed=${layout.bin} title="显示或隐藏素材箱" onClick=${() => setLayout({...layout, bin: !layout.bin})}>素材箱</button>
            <button class="icon-btn" aria-pressed=${layout.insp} title="显示或隐藏检查器" onClick=${() => setLayout({...layout, insp: !layout.insp})}>检查器</button>
            <a class="link" href="/">旧版素材工作台</a>
            <a class="link" href="/creation">旧版创作页</a>
        </div>
        ${usageOpen && html`<${EntitlementPanel} key=${project} project=${project} onClose=${() => setUsageOpen(false)} />`}
    </header>`;
}

function EntitlementPanel({project, onClose}) {
    const [data, setData] = useState(null);
    const [busy, setBusy] = useState(true);
    const [error, setError] = useState("");
    const active = useRef(null);
    const load = async (signal, plan) => {
        setBusy(true); setError("");
        try {
            if (plan) {
                const selected = await client.api("/api/entitlement", {}, {signal, body: {plan}});
                if (!signal.aborted) setData(selected);
            }
            const next = await client.api("/api/entitlement", {projectId: project || undefined}, {signal});
            if (!signal.aborted) setData(next);
        } catch (reason) {
            if (!signal.aborted) setError(reason.message);
        } finally {
            if (!signal.aborted) setBusy(false);
        }
    };
    useEffect(() => {
        const controller = new AbortController();
        active.current = controller;
        void load(controller.signal);
        return () => controller.abort();
    }, []);
    const analysis = data?.analysisUsage;
    const quota = (used, limit, unit) => limit == null
        ? `${used} ${unit}（不限）` : `${used} / ${limit} ${unit}`;
    return html`<section class="entitlement-panel" aria-label="套餐与用量">
        <div class="entitlement-head"><h2>套餐与用量</h2><span class="spacer"></span>
            <button class="btn ghost" aria-label="关闭套餐与用量" onClick=${onClose}>关闭</button></div>
        ${data && html`<label class="form-row">本地评估套餐
            <select class="select" aria-label="本地评估套餐" value=${data.plan} disabled=${busy}
                onChange=${e => void load(active.current.signal, e.currentTarget.value)}>
                ${Object.entries(data.plans).map(([id, label]) => html`<option value=${id}>${label}</option>`)}
            </select></label>
            <div class="entitlement-usage">
                <h3>本机用量 · ${data.usageMonth} UTC</h3>
                <dl><dt>成片</dt><dd>${quota(data.rendersThisMonth, data.monthlyRenders, "次")}</dd>
                    <dt>准备录像</dt><dd>${quota(data.preparationMinutesThisMonth, data.monthlyPreparationMinutes, "分钟")}</dd></dl>
                ${analysis && html`<h3>当前项目 · 已完成视频分析</h3>
                    <dl><dt>本月</dt><dd>${analysis.completedRunsThisMonth} 个版本 · ${analysis.sourceMinutesThisMonth} 分钟</dd>
                        <dt>累计</dt><dd>${analysis.completedRunsTotal} 个版本 · ${analysis.sourceMinutesTotal} 分钟</dd></dl>
                    <p class="hint">按已完成版本的原片时长统计。</p>`}
                ${data.analysisUsageUnavailable && html`<p class="hint">当前项目的分析统计暂不可用。</p>`}
                <p class="hint">${Object.entries(data.features).map(([key, enabled]) =>
                    `${data.featureLabels[key]} ${enabled ? "可用" : "未包含"}`).join(" · ")}</p>
                ${data.watermark && html`<p class="hint">新成片带 ${data.watermark} 水印。</p>`}
            </div>`}
        ${busy && html`<p role="status">正在读取用量…</p>`}
        ${error && html`<p role="alert">${error}</p>`}
        <button class="btn ghost" disabled=${busy} onClick=${() => void load(active.current.signal)}>刷新用量</button>
    </section>`;
}

// "横屏 1280×720 · 0:32 · 15.2 MB" so finished videos can be told apart in the list.
function videoFacts({width, height, durationSeconds, sizeBytes}) {
    const shape = width > height ? "横屏" : width < height ? "竖屏" : "方形";
    const total = Math.round(durationSeconds ?? -1), clock = total < 0 ? null : `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
    return [`${shape} ${width}×${height}`, clock, sizeBytes ? `${(sizeBytes / 1048576).toFixed(1)} MB` : null].filter(Boolean).join(" · ");
}

function Bin({runs, runsLoaded = false, runId, setRunId, works, onOpen, hidden, top, filterControls}) {
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
            ${filterControls}
            ${groups.map(([kind, list]) => html`<details class="group" open=${kind === "render"}>
                <summary>${KIND[kind]}（${list.length}）</summary>
                ${list.slice(0, 20).map((job) => {
                    const openable = canOpenWork(job);
                    const newest = openable && job === list.find((j) => j.status === "completed");
                    const reason = job.error?.message || "";
                    const meta = job.status === "completed" ? (openable ? (newest ? "最新 · 打开" : "打开") : "") : client.jobStatus(job.status) + (reason ? `：${reason}` : "");
                    return html`<button class="row" disabled=${!openable} title=${openable ? (["publication", "package"].includes(job.kind) ? "在发布区打开" : "在剪辑区打开") : reason || client.jobStatus(job.status)} onClick=${() => onOpen(job)}><span class=${`dot ${job.status === "completed" ? "ok" : job.status === "failed" ? "bad" : "warn"}`}></span>
                    <span class="name">${job.name ? html`${job.name}<small style=${{display: "block", opacity: 0.7}}>${new Date(job.createdAt).toLocaleString("zh-CN", {hour12: false})}</small>` : new Date(job.createdAt).toLocaleString("zh-CN", {hour12: false})}${job.video ? html`<small class="video-facts" style=${{display: "block", opacity: 0.7}}>${videoFacts(job.video)}</small>` : null}</span><span class="meta">${meta}</span></button>`;
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

function Viewer({onClockInvalid, clock, media, preview, preferProxy, proxyHttpFailed, proxyFailReason, onPreferPreview, onProxyHttpError, videoRef, time, setTime, selected, onFullSource}) {
    const src = preview?.url || null;
    const [playing, setPlaying] = useState(false);
    const [originalError, setOriginalError] = useState("");
    useEffect(() => { setOriginalError(""); }, [src]);
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
                onError=${(e) => {
                    const el = e.currentTarget;
                    const src = el.currentSrc || el.getAttribute("src") || "";
                    const assigned = preview?.url || "";
                    if (!assigned || !src) return;
                    try { if (new URL(src, location.href).href !== new URL(assigned, location.href).href) return; } catch { return; }
                    if (preview?.source === "proxy") onProxyHttpError?.(el);
                    else setOriginalError(SourceClock.playbackErrorText(el.error));
                }}
                onPlay=${() => setPlaying(true)} onPause=${() => setPlaying(false)} onClick=${(e) => (e.currentTarget.paused ? void e.currentTarget.play().catch(() => {}) : e.currentTarget.pause())}></video>`
            : html`<div class="empty">从左侧素材箱选择一段已分析的录像</div>`}
        <div class="transport">
            <button class="icon-btn" disabled=${!src} onClick=${() => { const el = videoRef.current; if (el) el.paused ? void el.play().catch(() => {}) : el.pause(); }}>${playing ? "暂停" : "播放"}</button>
            <span class="tc">${clock ? timecode(time) : "源时间未校准"} / ${media ? timecode(media.durationUs) : "00:00.000"}</span>
            ${src ? html`<span class="preview-source" data-preview-source=${preview.source}>${preview.source === "proxy" ? "编辑代理（非原片）" : "原始素材"}</span>` : null}
            ${media?.sourceHasAudio === false ? html`<span class="hint" data-audio-status="silent">这段录像没有声音</span>` : null}
            ${src && media?.proxyUrl ? html`<label id="proxy-toggle"><input type="checkbox" id="proxy-toggle-input" checked=${preferProxy !== false} onChange=${(e) => onPreferPreview(e.currentTarget.checked)} /> 使用编辑代理预览（360p，仅用于流畅浏览）</label>` : null}
            ${originalError ? html`<span class="hint" data-original-playback-error>${originalError}</span>` : proxyHttpFailed ? html`<span class="hint" data-preview-clock-reason=${proxyFailReason || "proxy_http_failed"}>${SourceClock.previewClockReason(proxyFailReason || "proxy_http_failed")}</span>` : preview?.reason ? html`<span class="hint" data-preview-clock-reason=${preview.reason}>${SourceClock.previewClockReason(preview.reason)}</span>` : null}
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
