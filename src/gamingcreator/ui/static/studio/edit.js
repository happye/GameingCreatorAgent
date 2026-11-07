// Edit workspace, step 2: brief → plans as filmstrips → instant preview → export an MP4.
import {h} from "../vendor/preact.module.js";
import {useCallback, useEffect, useMemo, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";
import {recordingRuns} from "./recordings.js";
import {editTimeline, shots, timeline, usePlanPlayer} from "./preview.js";
import {ClipInspector, CommandDock, transitionProblem, useClipEditor} from "./clipedit.js";
import {AudioPanel, narrationProblem, useAudioPreview, useMusicCatalog} from "./audio.js";
import {PlanReasoningPanel} from "./planning.js";
import {OverlayPanel, OverlayPreview, overlayProblem} from "./overlays.js";

const html = htm.bind(h);
const DRAFT = "studio-brief-v1";
const LAST = "studio-last-job-v1";
const TYPES = [["feature_showcase", "玩法展示"], ["guide", "攻略"], ["campaign", "活动投稿"], ["commentary", "游戏解说"], ["live_cut", "实况精剪"], ["highlight", "高光"], ["ad", "广告/买量"]];
const PLATFORMS = [["bilibili", "B站"], ["douyin", "抖音"], ["kuaishou", "快手"], ["xiaohongshu", "小红书"]];
const DEFAULTS = {runIds: [], game: "", contentType: "feature_showcase", targetDuration: "60", platform: "bilibili", objective: "整理已有素材中的玩法片段", audience: "新玩家", tone: "清楚简洁", mandatoryTopics: "", exclude: "", fps: "30"};

const list = (text) => [...new Set(text.split(/[,，\n]/).map((s) => s.trim()).filter(Boolean))];
const secondsText = (us) => `${(us / 1e6).toFixed(1)} 秒`;
function timecode(us) { const s = Math.max(0, Math.floor(us / 1e6)); return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; }

function readDraft(project) {
    try { const all = JSON.parse(localStorage.getItem(DRAFT) || "{}"); return {...DEFAULTS, ...(all[project] || {})}; } catch { return {...DEFAULTS}; }
}
// The last plan or video opened per project comes back after a reload.
function lastJob(project, value) {
    try {
        const all = JSON.parse(localStorage.getItem(LAST) || "{}");
        if (value === undefined) return all[project] || null;
        all[project] = value; localStorage.setItem(LAST, JSON.stringify(all));
    } catch { /* Storage may be disabled. */ }
    return null;
}
function writeDraft(project, draft) {
    try { const all = JSON.parse(localStorage.getItem(DRAFT) || "{}"); all[project] = draft; localStorage.setItem(DRAFT, JSON.stringify(all)); return true; } catch { return false; }
}

// Fit the entire output canvas in the viewer, including portrait exports.
function useOutputCanvas(stage, width, height) {
    const [bounds, setBounds] = useState({width: 0, height: 0});
    useEffect(() => {
        const element = stage.current;
        if (!element) return;
        const measure = () => setBounds({width: element.clientWidth, height: element.clientHeight});
        const observer = new ResizeObserver(measure);
        observer.observe(element); measure();
        return () => observer.disconnect();
    }, []);
    const scale = Math.min(bounds.width / width, bounds.height / height);
    return {width: width * scale, height: height * scale, scale};
}

export function EditWorkspace({project, runs, open, onWorksChanged, layout, basket, basketAt, onBasketSeen}) {
    const [draft, setDraft] = useState(() => readDraft(project));
    const [saved, setSaved] = useState("");
    const [planJob, setPlanJob] = useState(null);
    const [planId, setPlanId] = useState("");
    const [renderJob, setRenderJob] = useState(null);
    const [mode, setMode] = useState("plan");
    const [busy, setBusy] = useState("");
    const [message, setMessage] = useState("");
    const [selectedShot, setSelectedShot] = useState(null);
    const [size, setSize] = useState("1280,720");
    const [subtitles, setSubtitles] = useState("none");
    const [overlayBusy, setOverlayBusy] = useState(false);
    const stage = useRef(null);
    const [canvasWidth, canvasHeight] = size.split(",").map(Number);
    const canvas = useOutputCanvas(stage, canvasWidth, canvasHeight);
    const planVideo = useRef(null), planVideoNext = useRef(null), resultVideo = useRef(null), work = useRef(null), restoring = useRef(null);
    const editing = useClipEditor(project);
    const [commandRows, setCommandRows] = useState(null);
    const [commandOverlays, setCommandOverlays] = useState(null);
    const commandPreview = !!commandRows || !!commandOverlays;
    // A monotonic edit generation preserves changes even after an A/B/A roundtrip.
    const adoptionView = [project, planJob?.jobId, planId, editing.clips, editing.audio, editing.replacements, editing.overlays, commandRows, commandOverlays];
    const adoptionGuard = useRef({view: adoptionView, generation: 0});
    if (adoptionView.some((value, index) => value !== adoptionGuard.current.view[index])) {
        adoptionGuard.current = {view: adoptionView, generation: adoptionGuard.current.generation + 1};
    }

    useEffect(() => { setDraft(readDraft(project)); setPlanJob(null); setRenderJob(null); setPlanId(""); setMode("plan"); }, [project]);
    const update = (patch) => { const next = {...draft, ...patch}; setDraft(next); setSaved(writeDraft(project, next) ? "草稿已保存" : "浏览器不允许保存草稿"); };
    // "用片段篮生成方案" in Assets turns the basket option on.
    useEffect(() => { if (basketAt) { update({useBasket: true}); onBasketSeen(); } }, [basketAt]);
    const fromBasket = !!draft.useBasket && basket.items.length > 0;

    // Abort polling of a previous job when another one is opened.
    const follow = useCallback(async (id, apply) => {
        work.current?.abort(); const controller = new AbortController(); work.current = controller;
        try { return await client.settle(id, controller.signal, apply); }
        catch (error) { if (!controller.signal.aborted) setMessage(error.message); return null; }
    }, []);

    const showPlan = useCallback((job, selectedPlanId = null) => {
        setPlanJob(job); setRenderJob(null); setMode("plan"); setSelectedShot(null);
        const first = (job.plans || []).find((p) => p.ready && p.id === selectedPlanId) || (job.plans || []).find((p) => p.ready);
        lastJob(project, {id: job.jobId, kind: "plan", planId: first?.id || ""});
        setPlanId(first ? first.id : "");
    }, [project]);

    useEffect(() => {
        const target = open || lastJob(project);
        if (!target) return;
        setMessage("正在打开…");
        void follow(target.id, (job) => {
            if (job.status !== "completed") return setMessage(job.status === "failed" ? `任务失败：${job.error?.message || ""}` : "处理中…");
            setMessage("");
            if (job.kind === "plan") showPlan(job, target.planId);
            if (job.kind === "revision") void reopenVersion(job);
            if (job.kind === "render") {
                setRenderJob(job); setMode("result"); lastJob(project, {id: job.jobId, kind: "render"});
                // Bring back the plans this video came from, so preview and re-export stay one click away.
                if (job.parentJobId) void client.job(job.parentJobId).then((parent) => {
                    if (parent.status !== "completed") return;
                    if (parent.kind === "revision") return reopenVersion(parent, false);
                    if (parent.kind !== "plan") return;
                    setPlanJob(parent); setPlanId((parent.plans || []).find((p) => p.ready)?.id || "");
                }).catch(() => {});
            }
        });
    }, [open, project]);

    // A saved version reopens with its edits, and with the plan job it started from.
    const reopenVersion = async (job, remember = true) => {
        const editor = await editing.load(job.jobId, job.editor?.planId || job.planId || "", "revision").catch(() => null);
        if (!editor) return;
        let parent = job;
        for (let hop = 0; hop < 20 && parent?.kind !== "plan" && parent?.parentJobId; hop++) parent = await client.job(parent.parentJobId).catch(() => null);
        if (parent?.kind === "plan") { restoring.current = editor.planId; setPlanJob(parent); setPlanId(editor.planId); }
        if (remember) lastJob(project, {id: job.jobId, kind: "revision"});
    };

    const generate = async () => {
        const eventIds = fromBasket ? basket.items.map((i) => i.eventId) : null;
        const runIds = fromBasket ? [...new Set(basket.items.map((i) => i.runId))]
            : recordingRuns(runs.filter((r) => draft.runIds.includes(r.id)), draft.runIds).map((r) => r.id);
        if (!runIds.length) return setMessage("先在上面勾选至少一段录像。");
        if (!draft.game.trim()) return setMessage("请填写游戏名。");
        const brief = {game: draft.game.trim(), contentType: draft.contentType, platforms: [draft.platform], targetDuration: Number(draft.targetDuration),
            objective: draft.objective, audience: draft.audience, tone: draft.tone, mandatoryTopics: list(draft.mandatoryTopics), exclude: list(draft.exclude)};
        setBusy("plan"); setMessage("正在生成方案…");
        try {
            const accepted = await client.submit("plan", {projectId: project, runIds, brief, fps: Number(draft.fps), ...(eventIds ? {eventIds,
                clipRanges: basket.items.map(({runId, eventId, startUs, endUs}) => ({runId, eventId, startUs, endUs}))} : {})});
            const done = await follow(accepted.jobId, () => {});
            if (done?.status === "completed") { client.forgetIntent("plan"); showPlan(done); setMessage(""); onWorksChanged(); }
            else if (done) setMessage(`方案生成失败：${done.error?.message || done.status}`);
        } catch (error) { setMessage(`${error.message}。再次点击会复用同一请求，不会重复创建。`); }
        finally { setBusy(""); }
    };

    const plan = planJob?.plans?.find((p) => p.id === planId) || null;
    const fps = planJob?.fps || 30;
    // Choosing a plan loads its editable clips (unless a saved version of it was just reopened).
    useEffect(() => {
        if (!planJob || !planId) return;
        if (restoring.current === planId) { restoring.current = null; return; }
        void editing.load(planJob.jobId, planId, "plan");
    }, [planJob, planId]);
    const editable = editing.status === "ready";
    const shownClips = useMemo(() => {
        if (!commandRows || !editable) return editable ? editing.clips : null;
        const byId = new Map(editing.clips.map((c) => [c.clipId, c]));
        return commandRows.map((row) => ({...byId.get(row.clipId), ...row}));
    }, [commandRows, editable, editing.clips]);
    const items = useMemo(() => (shownClips ? editTimeline(shownClips, fps) : plan ? timeline(plan.segments || [], fps) : []).map(item => ({...item, sourceClock: runs.find(run => run.id === item.runId)?.sourceClock})), [shownClips, plan, fps, runs]);
    const changed = useMemo(() => {
        if (!commandRows) return new Set();
        // Highlight clips whose content changed or that moved relative to the others; a deletion
        // shifts later clips but does not mark them.
        const key = (c) => JSON.stringify([c.startUs, c.endUs, c.speed, c.transitionIn]);
        const before = new Map(editing.clips.map((c) => [c.clipId, key(c)]));
        const kept = new Set(commandRows.map((r) => r.clipId));
        const expected = editing.clips.map((c) => c.clipId).filter((id) => kept.has(id));
        return new Set(commandRows.filter((r, i) => !before.has(r.clipId) || before.get(r.clipId) !== key(r) || expected[i] !== r.clipId).map((r) => r.clipId));
    }, [commandRows, editing.clips]);
    const previewProblem = (shownClips ? transitionProblem(shownClips, fps) : "") || (items.some(item => !SourceClock.clockCandidates({sourceClock: item.sourceClock}).length) ? "素材源时钟不支持即时预览，请导出成片后观看" : "");
    const totalFrames = items.length ? items.at(-1).outStartFrame + items.at(-1).outFrames : 0;
    const problem = editable ? transitionProblem(editing.clips, fps) || narrationProblem(editing.audio, items.length ? items.at(-1).outStartUs + items.at(-1).outDurUs : 0, fps)
        || overlayProblem(editing.overlays, editing.overlayAssets, totalFrames, canvasWidth, canvasHeight) : "";
    const groups = useMemo(() => shots(items), [items]);
    const urlFor = useCallback((runId) => client.mediaUrl(project, runId), [project]);
    const player = usePlanPlayer(planVideo, items, urlFor, planVideoNext, previewProblem);
    const music = useMusicCatalog();
    const [audioBusy, setAudioBusy] = useState(false);
    const saveReason = !editable ? "正在读取可编辑镜头" : busy ? "任务正在处理，完成后可保存"
        : commandPreview ? "请先应用或取消创作助手的改动" : audioBusy ? "声音任务正在处理，完成后可保存" : overlayBusy ? "叠加素材正在处理，完成后可保存"
        : problem || (!editing.dirty ? "修改镜头、声音或叠加后可保存新版本" : "");
    // The inspector has three pages so sound and export stay reachable while a clip is selected.
    const [inspTab, setInspTab] = useState("shot");
    const sound = useAudioPreview(player, editing.audio, fps, planVideo, music.tracks, `${project}:${editing.base?.jobId}:${editing.base?.planId}`);
    const thumb = useCallback((item) => (item?.evidenceIds?.[0] ? client.evidenceUrl(project, item.runId, item.evidenceIds[0]) : null), [project]);

    const saveVersion = async () => {
        setBusy("save"); setMessage("正在保存版本…"); player.stop();
        try { const id = await editing.save((jobId) => follow(jobId, () => {})); setMessage("已保存为新版本。"); onWorksChanged(); lastJob(project, {id, kind: "revision"}); return id; }
        catch (error) { setMessage(error.message); return null; }
        finally { setBusy(""); }
    };

    const adoptPlans = async (jobId) => {
        const generation = adoptionGuard.current.generation;
        setBusy("adopt"); setMessage("正在登记动态方案，不会再次调用模型…"); player.stop();
        try {
            const done = await follow(jobId, () => {});
            onWorksChanged();
            if (adoptionGuard.current.generation !== generation) {
                setMessage("动态方案已登记到作品，当前编辑已保留，可稍后打开。"); return;
            }
            if (done?.status !== "completed") throw new Error(done?.error?.message || "动态方案未能登记完成");
            setCommandRows(null); showPlan(done); setMessage("");
        } catch (error) { setMessage(error.message); }
        finally { setBusy(""); }
    };

    const exportVideo = async () => {
        if (!plan?.ready || !planJob || problem) return;
        const [width, height] = size.split(",").map(Number);
        // Unsaved edits become a version first; the video is always rendered from a saved state.
        let source = {planJobId: planJob.jobId, planId: plan.id};
        if (editable && editing.dirty) { const id = await saveVersion(); if (!id) return; source = {revisionJobId: id}; }
        else if (editable && editing.base?.kind === "revision") source = {revisionJobId: editing.base.jobId};
        setBusy("render"); setMessage("正在生成成片，60 秒的视频大约需要一分钟…"); player.stop();
        try {
            const accepted = await client.submit("render", {...source, width, height, subtitleMode: subtitles});
            const done = await follow(accepted.jobId, (job) => setRenderJob(job));
            if (done?.status === "completed") { client.forgetIntent("render"); setMode("result"); setMessage(""); onWorksChanged(); lastJob(project, {id: done.jobId, kind: "render"}); }
            else if (done) setMessage(`成片生成失败：${done.error?.message || done.status}`);
        } catch (error) { setMessage(`${error.message}。再次点击会复用同一请求，不会重复创建。`); }
        finally { setBusy(""); }
    };

    const result = renderJob?.status === "completed" ? renderJob.artifact : null;
    const resultSrc = result ? client.sameOrigin(result.previewUrl, `/api/creation/jobs/${renderJob.jobId}/video`) : null;
    const resultDownload = result ? client.sameOrigin(result.downloadUrl, `/api/creation/jobs/${renderJob.jobId}/video`) : null;

    useEffect(() => {
        const onKey = (event) => {
            if (event.target.closest("input, textarea, select") || mode !== "plan" || !items.length) return;
            if (event.key === " ") { event.preventDefault(); player.toggle(); }
            if ((event.key === "Delete" || event.key === "Backspace") && editing.selectedId && editable && !commandPreview) { event.preventDefault(); editing.ops.remove(editing.selectedId); }
            if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); void player.seek(player.outUs + (event.key === "ArrowLeft" ? -1 : 1) * (event.shiftKey ? 5e6 : 1e6), player.playing); }
        };
        addEventListener("keydown", onKey); return () => removeEventListener("keydown", onKey);
    }, [player, mode, items, editing, editable, commandPreview]);

    const cls = `work edit${layout.bin ? "" : " no-bin"}${layout.insp ? "" : " no-insp"}`;
    const selectedIndex = editable ? editing.clips.findIndex((c) => c.clipId === editing.selectedId) : -1;
    const seekClip = (clipId) => { const item = items.find((i) => i.clipId === clipId); if (item) { setMode("plan"); void player.seek(item.outStartUs, true); } };
    return html`<div class=${cls}>
        <aside class="panel" hidden=${!layout.bin} aria-label="需求与方案">
            <div class="panel-head">需求<span class="spacer"></span><span class="track-label">${saved}</span></div>
            <div class="panel-body">
                <${Brief} runs=${runs} draft=${draft} update=${update} busy=${busy} onGenerate=${generate} basket=${basket} />
                <div class="section-label">方案${planJob ? `（${planJob.plans.length}）` : ""}</div>
                ${planJob ? planJob.plans.map((p) => html`<${PlanCard} plan=${p} fps=${fps} active=${p.id === planId} thumb=${thumb}
                    onPick=${() => { if (overlayBusy || audioBusy || busy) return; if (editing.dirty && !confirmLeave()) return; setPlanId(p.id); setMode("plan"); setSelectedShot(null); setCommandRows(null); lastJob(project, {id: planJob.jobId, kind: "plan", planId: p.id}); }} />`)
                    : html`<p class="note">填好需求后点“生成方案”。方案只是剪辑清单，生成很快；选中后可以直接预览，不用先渲染。</p>`}
                ${planJob ? html`<${PlanReasoningPanel} key=${`${project}:${planJob.jobId}`} project=${project} jobId=${planJob.jobId}
                    disabled=${!!busy || editing.dirty || commandPreview || audioBusy || overlayBusy} onAdopt=${adoptPlans} />` : null}
            </div>
        </aside>
        <div class="center">
            <section class="viewer" aria-label="预览窗">
                <div class="stage" ref=${stage} style=${{position: "relative"}}>
                    <div class="program-frame" hidden=${mode !== "plan" || !items.length} style=${{position: "absolute", overflow: "hidden", left: "50%", top: "50%", transform: "translate(-50%, -50%)", width: `${canvas.width}px`, height: `${canvas.height}px`}}>
                    <video ref=${planVideo} hidden=${mode !== "plan" || !items.length} playsinline preload="metadata" onClick=${() => { if (!previewProblem) player.toggle(); }}></video><video ref=${planVideoNext} hidden=${mode !== "plan" || !items.length} playsinline preload="auto" onClick=${() => { if (!previewProblem) player.toggle(); }}></video>${sound}
                    ${editable ? html`<div class="overlay-scale" style=${{position: "absolute", pointerEvents: "none", left: 0, top: 0, width: `${canvasWidth}px`, height: `${canvasHeight}px`, transform: `scale(${canvas.scale})`}}>
                        <${OverlayPreview} items=${commandOverlays ?? editing.overlays} assets=${editing.overlayAssets} outUs=${player.outUs} fps=${fps} width=${canvasWidth} height=${canvasHeight} />
                    </div>` : null}
                    </div>
                    ${mode === "plan" && (previewProblem || player.error) ? html`<div class="empty">${previewProblem || player.error}</div>` : null}
                    ${mode === "result" && resultSrc ? html`<video ref=${resultVideo} src=${resultSrc} controls playsinline preload="metadata"></video>` : null}
                    ${(mode === "plan" && !items.length) || (mode === "result" && !resultSrc) ? html`<div class="empty">${planJob ? "在左侧选一个方案，即可在这里预览" : "生成方案后，在这里即时预览"}</div>` : null}
                </div>
                <div class="transport">
                    ${mode === "plan"
                        ? html`<button class="icon-btn" disabled=${!items.length} onClick=${player.toggle}>${player.playing ? "暂停" : "预览方案"}</button>
                            <span class="tc">${timecode(player.outUs)} / ${timecode(player.totalUs)}</span>
                            <span class="badge" title="直接播放原片，未渲染">即时预览·未渲染</span>`
                        : html`<span class="badge">成片</span>`}
                    <span class="spacer"></span>
                    ${result ? html`<div class="tabs"><button aria-selected=${mode === "plan"} onClick=${() => setMode("plan")}>方案预览</button><button aria-selected=${mode === "result"} onClick=${() => { player.stop(); setMode("result"); }}>成片</button></div>` : null}
                    ${result && resultDownload ? html`<a class="btn ghost" href=${resultDownload} download>下载 MP4（${(result.sizeBytes / 1048576).toFixed(1)} MB）</a>` : null}
                    <button class="btn" disabled=${!plan?.ready || !!busy || audioBusy || overlayBusy || !!problem || commandPreview} title=${!plan ? "先在左侧选择一个方案" : !plan.ready ? "这个方案有缺口，不能导出" : problem || (commandPreview ? "先应用或取消一句话修改" : editing.dirty ? "先保存为新版本，再渲染 MP4" : "按当前内容渲染 MP4")} onClick=${exportVideo}>${busy === "render" ? "正在生成…" : busy === "save" ? "正在保存…" : "导出成片"}</button>
                </div>
            </section>
            <${ProgramTrack} items=${items} totalUs=${player.totalUs} outUs=${player.outUs} thumb=${thumb} selectedId=${editing.selectedId} changed=${changed} preview=${!!commandRows} lanes=${editable ? audioLanes(editing.audio, music.tracks, fps, player.totalUs) : []}
                onLane=${() => setInspTab("sound")}
                onPick=${(item) => { editing.setSelectedId(item.clipId || ""); setInspTab("shot"); setMode("plan"); void player.seek(item.outStartUs, false); }} />
        </div>
        <aside class="panel" hidden=${!layout.insp} aria-label="检查器">
            <div class="panel-head">检查器</div>
            <div class="tabs insp-tabs" role="tablist" aria-label="检查器页面">
                ${[["shot", "镜头"], ["overlay", "叠加"], ["sound", "声音"], ["export", "导出"]].map(([key, label]) => html`<button role="tab" aria-selected=${inspTab === key} onClick=${() => setInspTab(key)}>${label}</button>`)}
            </div>
            <div class="panel-body">
                ${message && html`<p class="note" role="status">${message}</p>`}
                <div hidden=${inspTab !== "export"}>
                <div class="field">
                    <div class="k">导出设置（导出按钮在预览窗下方）</div>
                    <div class="pair even">
                        <label class="form-row">尺寸<select class="select" value=${size} onChange=${(e) => setSize(e.currentTarget.value)}><option value="1280,720">横屏 1280×720</option><option value="720,1280">竖屏 720×1280</option></select></label>
                        <label class="form-row">字幕<select class="select" value=${subtitles} onChange=${(e) => setSubtitles(e.currentTarget.value)}><option value="none">不加字幕</option><option value="sidecar">导出 SRT</option><option value="burn">烧入并导出 SRT</option></select></label>
                    </div>
                </div>
                </div>
                ${plan && html`<div class="field"><div class="k">编辑状态</div>
                    <div class="v">${editing.status === "loading" ? "正在读取镜头…" : !editable ? `只能预览和导出${editing.reason ? `（${editing.reason}）` : ""}` : editing.dirty ? "有未保存的修改" : editing.base?.kind === "revision" ? "已保存的版本" : "方案原样"}</div>
                    ${problem && html`<p class="hint warn">${problem}</p>`}
                    ${editable && html`<p class="hint" role="status" aria-label="版本保存状态">${saveReason || "修改已就绪，可以保存新版本"}</p><div class="actions-row"><button class="btn ghost" disabled=${!!saveReason} title=${saveReason || "保存新版本"} onClick=${saveVersion}>保存版本</button>
                        <button class="btn ghost" disabled=${!editing.dirty || !!busy} onClick=${() => editing.ops.reset()}>撤销修改</button></div>`}</div>`}
                <div hidden=${inspTab !== "shot"}>
                ${selectedIndex >= 0 && !commandPreview ? html`<${ClipInspector} editing=${editing} index=${selectedIndex} onSeek=${seekClip} basket=${basket} />`
                    : plan ? html`<p class="hint">点时间轴上的一个镜头，可以裁短、调速、换顺序或替换画面。</p><${PlanInspector} plan=${plan} groups=${groups} count=${items.length} totalUs=${player.totalUs} shot=${null} />` : html`<p class="note">选中方案后，这里显示它的时长、镜头和缺口。</p>`}
                </div>
                <div hidden=${inspTab !== "sound"}>
                ${editable ? html`<${AudioPanel} editing=${editing} project=${project} fps=${fps} totalUs=${player.totalUs} music=${music} onBusy=${setAudioBusy} />`
                    : html`<p class="note">${plan ? "这个方案还不能编辑声音（正在读取或只能导出）。" : "先在左侧选一个方案，再在这里加旁白和配乐。"}</p>`}
                </div>
                <div hidden=${inspTab !== "overlay"}>
                ${editable ? html`<${OverlayPanel} key=${`${project}:${editing.base?.jobId}:${editing.base?.planId}`} editing=${editing} fps=${fps} totalFrames=${totalFrames} canvasWidth=${canvasWidth} canvasHeight=${canvasHeight} onBusy=${setOverlayBusy} disabled=${!!busy || commandPreview} />`
                    : html`<p class="note">选中可编辑的方案后，可以添加定时文字或PNG图片。</p>`}
                </div>
            </div>
        </aside>
    </div>
    <${CommandDock} editing=${editing} onPreview=${setCommandRows} onOverlayPreview=${setCommandOverlays} />`;
}

function audioLanes(audio, tracks, fps, totalUs) {
    const lanes = [], track = tracks.find((t) => t.trackId === audio.mix.bgm?.trackId);
    lanes.push(audio.narration && audio.asset
        ? {kind: "voice", label: `旁白 ${audio.asset.durationSeconds.toFixed(1)} 秒`, startUs: (audio.narration.startFrame / fps) * 1e6, durUs: audio.asset.durationSeconds * 1e6}
        : {kind: "voice", label: "旁白轨：未添加，点此添加", startUs: 0, durUs: 0});
    lanes.push(audio.mix.bgm
        ? {kind: "music", label: `配乐 ${track?.title || ""}`, startUs: 0, durUs: totalUs}
        : {kind: "music", label: "配乐轨：未添加，点此添加", startUs: 0, durUs: 0});
    return lanes;
}

function confirmLeave() {
    // window.confirm may be unavailable in some hosts; then keep the edits.
    try { return window.confirm("当前方案有未保存的修改，切换会丢弃这些修改。继续吗？"); } catch { return false; }
}

function Brief({runs, draft, update, busy, onGenerate, basket}) {
    const usable = recordingRuns(runs, draft.runIds);
    const field = (name, label, props = {}) => html`<label class="form-row">${label}<input class="input" value=${draft[name]} onInput=${(e) => update({[name]: e.currentTarget.value})} ...${props} /></label>`;
    return html`<form class="brief" onSubmit=${(e) => { e.preventDefault(); void onGenerate(); }}>
        ${basket.items.length ? html`<label class="check basket-option"><input type="checkbox" checked=${!!draft.useBasket} onChange=${(e) => update({useBasket: e.currentTarget.checked})} />
            <span>只用片段篮里的 ${basket.items.length} 段（共 ${(basket.totalUs / 1e6).toFixed(0)} 秒）${draft.useBasket && basket.totalUs / 1e6 < Number(draft.targetDuration) ? "：比目标秒数短，方案会偏短" : ""}</span></label>` : null}
        <fieldset class="runs" disabled=${!!draft.useBasket && basket.items.length > 0}><legend>录像${draft.useBasket && basket.items.length ? "（按片段篮自动选择）" : ""}</legend>
            ${usable.map((run) => html`<label class="check"><input type="checkbox" checked=${draft.runIds.includes(run.id)}
                onChange=${(e) => update({runIds: e.currentTarget.checked ? [...draft.runIds, run.id] : draft.runIds.filter((id) => id !== run.id)})} /><span>${run.sourceName}</span></label>`)}
            ${!usable.length && html`<p class="note">这个项目还没有分析完成的录像。</p>`}
        </fieldset>
        ${field("game", "游戏", {placeholder: "例如：漫画群星：大集结", maxLength: 500})}
        <div class="pair">
            <label class="form-row">类型<select class="select" value=${draft.contentType} onChange=${(e) => update({contentType: e.currentTarget.value})}>${TYPES.map(([v, l]) => html`<option value=${v}>${l}</option>`)}</select></label>
            ${field("targetDuration", "秒数", {type: "number", min: 1, max: 86400})}
        </div>
        <label class="form-row">平台<select class="select" value=${draft.platform} onChange=${(e) => update({platform: e.currentTarget.value})}>${PLATFORMS.map(([v, l]) => html`<option value=${v}>${l}</option>`)}</select></label>
        <details class="group"><summary>高级选项（可不填）</summary>
            ${field("objective", "创作目标")}${field("audience", "目标观众")}${field("tone", "表达语气")}
            ${field("mandatoryTopics", "必须包含的主题（逗号分隔）")}${field("exclude", "排除这些词的片段（如：加载, 菜单）")}
            ${field("fps", "输出帧率", {type: "number", min: 1, max: 120})}
        </details>
        <button class="btn wide" type="submit" disabled=${!!busy}>${busy === "plan" ? "正在生成…" : "生成方案"}</button>
    </form>`;
}

function PlanCard({plan, fps, active, thumb, onPick}) {
    const items = timeline(plan.segments || [], fps), groups = shots(items);
    const total = items.length ? items.at(-1).outStartUs + items.at(-1).outDurUs : 0;
    return html`<button class="plan" aria-current=${active} disabled=${!plan.ready} onClick=${onPick} title=${plan.ready ? "选中后在预览窗播放" : "方案有缺口，不能选择"}>
        <span class="plan-title">${plan.mode ? html`<span class="badge rec">推荐</span>` : null}${plan.title || plan.structure}</span>
        <span class="plan-meta">${secondsText(total)} · ${items.length} 个镜头 · 平均 ${(total / 1e6 / Math.max(1, items.length)).toFixed(1)} 秒</span>
        <span class="strip">${groups.slice(0, 8).map((g) => { const src = thumb(g.items[0]); return html`<span style=${{backgroundImage: src ? `url("${src}")` : "none"}}></span>`; })}</span>
        ${!plan.ready && html`<span class="plan-gap">缺口：${(plan.gaps || []).join("；")}</span>`}
    </button>`;
}

function ProgramTrack({items, totalUs, outUs, thumb, selectedId, changed, preview, lanes = [], onLane, onPick}) {
    const area = useRef(null);
    const [width, setWidth] = useState(800);
    useEffect(() => {
        const observer = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width - 24)));
        if (area.current) observer.observe(area.current); return () => observer.disconnect();
    }, []);
    const scale = totalUs ? width / totalUs : 0;
    const hint = preview ? `一句话修改预览：高亮的是会变化的镜头（共 ${items.length} 个）` : `${items.length} 个镜头 · 点选一个可以裁短、调速、换顺序；Delete 删除`;
    return html`<section class="timeline" aria-label="方案时间轴">
        <div class="panel-head">时间轴<span class="track-label">${items.length ? hint : ""}</span></div>
        <div class="track-area" ref=${area}>
            ${items.length ? html`<div class="track program">
                ${items.map((item, index) => {
                    const src = thumb(item), speed = item.rate && item.rate !== 1 ? item.rate : null;
                    return html`<button class=${`clip${changed.has(item.clipId) ? " changed" : ""}`} aria-current=${!!item.clipId && item.clipId === selectedId}
                        style=${{left: `${item.outStartUs * scale}px`, width: `${Math.max(3, item.outDurUs * scale - 1)}px`, backgroundImage: src ? `url("${src}")` : "none"}}
                        title=${`第 ${index + 1} 个镜头 · ${timecode(item.outStartUs)} · ${(item.outDurUs / 1e6).toFixed(1)} 秒${speed ? ` · ${speed}×` : ""} · ${item.scriptDraft || ""}`} onClick=${() => onPick(item)}>
                        <span class="clip-no">${index + 1}</span>${speed ? html`<span class="clip-speed">${speed}×</span>` : null}</button>`;
                })}
                <div class="playhead" style=${{left: `${outUs * scale}px`}}></div>
            </div>` : html`<p class="note">选中方案后，镜头按成片顺序排在这里。</p>`}
            ${items.length ? lanes.map((lane) => html`<button class=${`lane ${lane.kind}`} title=${`${lane.label} · 点击打开“声音”`} onClick=${onLane}>
                ${lane.durUs ? html`<span class="bar" style=${{left: `${lane.startUs * scale}px`, width: `${Math.max(3, Math.min(lane.durUs, totalUs - lane.startUs) * scale)}px`}}>${lane.label}</span>`
                    : html`<span class="lane-empty">${lane.label}</span>`}</button>`) : null}
        </div>
    </section>`;
}

function PlanInspector({plan, groups, count, totalUs, shot}) {
    return html`
        <div class="field"><div class="k">方案</div><div class="v">${plan.structure}</div></div>
        <div class="field"><div class="k">时长与镜头</div><div class="v num">${secondsText(totalUs)} · ${count ?? groups.length} 个镜头</div></div>
        ${(plan.advisories || []).length ? html`<div class="field"><div class="k">提醒</div><ul class="facts">${plan.advisories.map((a) => html`<li>${a}</li>`)}</ul></div>` : null}
        ${shot ? html`<div class="field"><div class="k">选中镜头 · 成片 ${timecode(shot.outStartUs)} 起 ${(shot.outDurUs / 1e6).toFixed(1)} 秒</div>
            <ul class="facts">${shot.items.map((i) => html`<li>${i.role ? `【${i.role}】` : ""}原片 ${(i.startUs / 1e6).toFixed(1)} 秒：${i.scriptDraft || "无描述"}</li>`)}</ul></div>`
        : html`<p class="note">点下方时间轴上的镜头，查看它取自原片哪里、描述是什么。</p>`}
        <p class="note">描述代理评分、非画面理解／未做人评／投放未验证：方案按分析时保存的文字挑片，预览一遍再导出。</p>`;
}
