// Edit workspace, step 2: brief → plans as filmstrips → instant preview → export an MP4.
import {h} from "../vendor/preact.module.js";
import {useCallback, useEffect, useMemo, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";
import {shots, timeline, usePlanPlayer} from "./preview.js";

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

export function EditWorkspace({project, runs, open, onWorksChanged, layout}) {
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
    const planVideo = useRef(null), resultVideo = useRef(null), work = useRef(null);

    useEffect(() => { setDraft(readDraft(project)); setPlanJob(null); setRenderJob(null); setPlanId(""); setMode("plan"); }, [project]);
    const update = (patch) => { const next = {...draft, ...patch}; setDraft(next); setSaved(writeDraft(project, next) ? "草稿已保存" : "浏览器不允许保存草稿"); };

    // Abort polling of a previous job when another one is opened.
    const follow = useCallback(async (id, apply) => {
        work.current?.abort(); const controller = new AbortController(); work.current = controller;
        try { return await client.settle(id, controller.signal, apply); }
        catch (error) { if (!controller.signal.aborted) setMessage(error.message); return null; }
    }, []);

    const showPlan = useCallback((job) => {
        setPlanJob(job); setRenderJob(null); setMode("plan"); setSelectedShot(null); lastJob(project, {id: job.jobId, kind: "plan"});
        const first = (job.plans || []).find((p) => p.ready);
        setPlanId(first ? first.id : "");
    }, [project]);

    useEffect(() => {
        const target = open || lastJob(project);
        if (!target) return;
        setMessage("正在打开…");
        void follow(target.id, (job) => {
            if (job.status !== "completed") return setMessage(job.status === "failed" ? `任务失败：${job.error?.message || ""}` : "处理中…");
            setMessage("");
            if (job.kind === "plan") showPlan(job);
            if (job.kind === "render") {
                setRenderJob(job); setMode("result"); lastJob(project, {id: job.jobId, kind: "render"});
                // Bring back the plans this video came from, so preview and re-export stay one click away.
                if (job.parentJobId) void client.job(job.parentJobId).then((parent) => {
                    if (parent.kind !== "plan" || parent.status !== "completed") return;
                    setPlanJob(parent); setPlanId((parent.plans || []).find((p) => p.ready)?.id || "");
                }).catch(() => {});
            }
        });
    }, [open, project]);

    const generate = async () => {
        const runIds = draft.runIds.filter((id) => runs.some((r) => r.id === id && r.completedEligible));
        if (!runIds.length) return setMessage("先在上面勾选至少一段录像。");
        if (!draft.game.trim()) return setMessage("请填写游戏名。");
        const brief = {game: draft.game.trim(), contentType: draft.contentType, platforms: [draft.platform], targetDuration: Number(draft.targetDuration),
            objective: draft.objective, audience: draft.audience, tone: draft.tone, mandatoryTopics: list(draft.mandatoryTopics), exclude: list(draft.exclude)};
        setBusy("plan"); setMessage("正在生成方案…");
        try {
            const accepted = await client.submit("plan", {projectId: project, runIds, brief, fps: Number(draft.fps)});
            const done = await follow(accepted.jobId, () => {});
            if (done?.status === "completed") { client.forgetIntent("plan"); showPlan(done); setMessage(""); onWorksChanged(); }
            else if (done) setMessage(`方案生成失败：${done.error?.message || done.status}`);
        } catch (error) { setMessage(`${error.message}。再次点击会复用同一请求，不会重复创建。`); }
        finally { setBusy(""); }
    };

    const plan = planJob?.plans?.find((p) => p.id === planId) || null;
    const fps = planJob?.fps || 30;
    const items = useMemo(() => (plan ? timeline(plan.segments || [], fps) : []), [plan, fps]);
    const groups = useMemo(() => shots(items), [items]);
    const urlFor = useCallback((runId) => client.mediaUrl(project, runId), [project]);
    const player = usePlanPlayer(planVideo, items, urlFor);
    const thumb = useCallback((item) => (item?.evidenceIds?.[0] ? client.evidenceUrl(project, item.runId, item.evidenceIds[0]) : null), [project]);

    const exportVideo = async () => {
        if (!plan?.ready || !planJob) return;
        const [width, height] = size.split(",").map(Number);
        setBusy("render"); setMessage("正在生成成片，60 秒的视频大约需要一分钟…"); player.stop();
        try {
            const accepted = await client.submit("render", {planJobId: planJob.jobId, planId: plan.id, width, height, subtitleMode: subtitles});
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
            if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); void player.seek(player.outUs + (event.key === "ArrowLeft" ? -1 : 1) * (event.shiftKey ? 5e6 : 1e6), player.playing); }
        };
        addEventListener("keydown", onKey); return () => removeEventListener("keydown", onKey);
    }, [player, mode, items]);

    const cls = `work edit${layout.bin ? "" : " no-bin"}${layout.insp ? "" : " no-insp"}`;
    return html`<div class=${cls}>
        <aside class="panel" hidden=${!layout.bin} aria-label="需求与方案">
            <div class="panel-head">需求<span class="spacer"></span><span class="track-label">${saved}</span></div>
            <div class="panel-body">
                <${Brief} runs=${runs} draft=${draft} update=${update} busy=${busy} onGenerate=${generate} />
                <div class="section-label">方案${planJob ? `（${planJob.plans.length}）` : ""}</div>
                ${planJob ? planJob.plans.map((p) => html`<${PlanCard} plan=${p} fps=${fps} active=${p.id === planId} thumb=${thumb}
                    onPick=${() => { setPlanId(p.id); setMode("plan"); setSelectedShot(null); }} />`)
                    : html`<p class="note">填好需求后点“生成方案”。方案只是剪辑清单，生成很快；选中后可以直接预览，不用先渲染。</p>`}
            </div>
        </aside>
        <div class="center">
            <section class="viewer" aria-label="预览窗">
                <div class="stage">
                    <video ref=${planVideo} hidden=${mode !== "plan" || !items.length} playsinline preload="metadata" onClick=${player.toggle}></video>
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
                    <button class="btn" disabled=${!plan?.ready || !!busy} title=${!plan ? "先在左侧选择一个方案" : !plan.ready ? "这个方案有缺口，不能导出" : "按当前方案渲染 MP4"} onClick=${exportVideo}>${busy === "render" ? "正在生成…" : "导出成片"}</button>
                </div>
            </section>
            <${ProgramTrack} groups=${groups} totalUs=${player.totalUs} outUs=${player.outUs} thumb=${thumb} selected=${selectedShot}
                onPick=${(group) => { setSelectedShot(group); setMode("plan"); void player.seek(group.outStartUs, true); }} />
        </div>
        <aside class="panel" hidden=${!layout.insp} aria-label="检查器">
            <div class="panel-head">检查器</div>
            <div class="panel-body">
                ${message && html`<p class="note" role="status">${message}</p>`}
                <div class="field">
                    <div class="k">导出设置（导出按钮在预览窗下方）</div>
                    <div class="pair even">
                        <label class="form-row">尺寸<select class="select" value=${size} onChange=${(e) => setSize(e.currentTarget.value)}><option value="1280,720">横屏 1280×720</option><option value="720,1280">竖屏 720×1280</option></select></label>
                        <label class="form-row">字幕<select class="select" value=${subtitles} onChange=${(e) => setSubtitles(e.currentTarget.value)}><option value="none">不加字幕</option><option value="sidecar">导出 SRT</option><option value="burn">烧入并导出 SRT</option></select></label>
                    </div>
                </div>
                ${plan ? html`<${PlanInspector} plan=${plan} groups=${groups} totalUs=${player.totalUs} shot=${selectedShot} />` : html`<p class="note">选中方案后，这里显示它的时长、镜头和缺口。</p>`}
            </div>
        </aside>
    </div>`;
}

function Brief({runs, draft, update, busy, onGenerate}) {
    const usable = runs.filter((r) => r.completedEligible);
    const field = (name, label, props = {}) => html`<label class="form-row">${label}<input class="input" value=${draft[name]} onInput=${(e) => update({[name]: e.currentTarget.value})} ...${props} /></label>`;
    return html`<form class="brief" onSubmit=${(e) => { e.preventDefault(); void onGenerate(); }}>
        <fieldset class="runs"><legend>录像</legend>
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
        <span class="plan-title">${plan.mode ? html`<span class="badge rec">推荐</span>` : null}${plan.structure}</span>
        <span class="plan-meta">${secondsText(total)} · ${groups.length} 个镜头 · 平均 ${(total / 1e6 / Math.max(1, groups.length)).toFixed(1)} 秒</span>
        <span class="strip">${groups.slice(0, 8).map((g) => { const src = thumb(g.items[0]); return html`<span style=${{backgroundImage: src ? `url("${src}")` : "none"}}></span>`; })}</span>
        ${!plan.ready && html`<span class="plan-gap">缺口：${(plan.gaps || []).join("；")}</span>`}
    </button>`;
}

function ProgramTrack({groups, totalUs, outUs, thumb, selected, onPick}) {
    const area = useRef(null);
    const [width, setWidth] = useState(800);
    useEffect(() => {
        const observer = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width - 24)));
        if (area.current) observer.observe(area.current); return () => observer.disconnect();
    }, []);
    const scale = totalUs ? width / totalUs : 0;
    return html`<section class="timeline" aria-label="方案时间轴">
        <div class="panel-head">方案时间轴<span class="track-label">${groups.length ? `${groups.length} 个镜头 · 点镜头从这里播放` : ""}</span></div>
        <div class="track-area" ref=${area}>
            ${groups.length ? html`<div class="track program">
                ${groups.map((g) => { const src = thumb(g.items[0]); return html`<button class="clip" aria-current=${selected === g}
                    style=${{left: `${g.outStartUs * scale}px`, width: `${Math.max(3, g.outDurUs * scale - 2)}px`, backgroundImage: src ? `url("${src}")` : "none"}}
                    title=${`${timecode(g.outStartUs)} · ${(g.outDurUs / 1e6).toFixed(1)} 秒 · ${g.items[0].scriptDraft || ""}`} onClick=${() => onPick(g)}></button>`; })}
                <div class="playhead" style=${{left: `${outUs * scale}px`}}></div>
            </div>` : html`<p class="note">选中方案后，镜头按成片顺序排在这里。</p>`}
        </div>
    </section>`;
}

function PlanInspector({plan, groups, totalUs, shot}) {
    return html`
        <div class="field"><div class="k">方案</div><div class="v">${plan.structure}</div></div>
        <div class="field"><div class="k">时长与镜头</div><div class="v num">${secondsText(totalUs)} · ${groups.length} 个镜头</div></div>
        ${(plan.advisories || []).length ? html`<div class="field"><div class="k">提醒</div><ul class="facts">${plan.advisories.map((a) => html`<li>${a}</li>`)}</ul></div>` : null}
        ${shot ? html`<div class="field"><div class="k">选中镜头 · 成片 ${timecode(shot.outStartUs)} 起 ${(shot.outDurUs / 1e6).toFixed(1)} 秒</div>
            <ul class="facts">${shot.items.map((i) => html`<li>${i.role ? `【${i.role}】` : ""}原片 ${(i.startUs / 1e6).toFixed(1)} 秒：${i.scriptDraft || "无描述"}</li>`)}</ul></div>`
        : html`<p class="note">点下方时间轴上的镜头，查看它取自原片哪里、描述是什么。</p>`}
        <p class="note">描述代理评分、非画面理解／未做人评／投放未验证：方案按分析时保存的文字挑片，预览一遍再导出。</p>`;
}
