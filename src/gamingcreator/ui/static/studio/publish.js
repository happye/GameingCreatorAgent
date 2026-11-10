// Publish workspace: pick a finished video, write its title, description and tags, pick the
// cover from a frame, save that as a publication version, then build a platform package to
// download. Nothing is posted to any platform from here.
import {h} from "../vendor/preact.module.js";
import {useCallback, useEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";

const html = htm.bind(h);
const PLATFORMS = {bilibili: "B站", douyin: "抖音", kuaishou: "快手", xiaohongshu: "小红书"};
const CHECKS = {width: "视频宽度", height: "视频高度", codec: "编码", pixelFormat: "像素格式", frames: "帧数", fps: "帧率", maxBytes: "文件大小", minDurationMs: "最短时长", maxDurationMs: "最长时长", titleMaxChars: "标题字数", descriptionMaxChars: "简介字数", tagMaxCount: "标签数量", requiredTags: "必需标签"};
const STATUS = {pass: "通过", fail: "未通过", unknown: "未知", not_configured: "未配置"};
const jobPath = (id) => `/api/creation/jobs/${encodeURIComponent(id)}`;
const when = (iso) => new Date(iso).toLocaleString("zh-CN", {hour12: false});
const tagList = (text) => [...new Set(text.split(/[,，\n]/).map((t) => t.trim()).filter(Boolean))];

export function PublishWorkspace({project, works, open, onWorksChanged, layout, onDirtyChange = () => {}}) {
    const renders = works.filter((j) => j.kind === "render" && j.status === "completed");
    const [renderId, setRenderId] = useState("");
    const [pub, setPub] = useState(null); // the snapshot shown: a draft from the render or a saved publication
    const [form, setForm] = useState({title: "", description: "", tags: "", coverFrame: 0});
    const [profiles, setProfiles] = useState([]);
    const [platform, setPlatform] = useState("");
    const [packages, setPackages] = useState([]);
    const [selected, setSelected] = useState([]);
    const epoch = useRef(0);
    const polling = useRef(new AbortController());
    const activeProject = useRef(project);
    const shownProject = useRef(null);
    const shownOpen = useRef(null);
    const rejectedOpen = useRef(null);
    if (activeProject.current !== project) { activeProject.current = project; epoch.current++; polling.current.abort(); polling.current = new AbortController(); }
    useEffect(() => () => { epoch.current++; polling.current.abort(); }, []);
    const [busy, setBusy] = useState("");
    const [message, setMessage] = useState("");
    const video = useRef(null);

    useEffect(() => {
        client.api("/api/creation/platform-profiles").then((data) => { setProfiles(data.profiles || []); setPlatform(data.profiles?.[0]?.Platform || ""); setSelected([data.profiles?.[0]?.Platform].filter(Boolean)); }).catch(() => setProfiles([]));
    }, []);
    // Open what was asked for (a video, publication or package from the bin), else the newest video.
    useEffect(() => {
        const changedProject = shownProject.current !== null && shownProject.current !== project;
        if (changedProject && open === shownOpen.current) rejectedOpen.current = open;
        if (open !== rejectedOpen.current && open && ["render", "publication", "package"].includes(open.kind)) void show(open.id, open.kind);
        else if ((!renderId || shownProject.current !== project) && renders[0]) void show(renders[0].jobId, "render");
        else if (changedProject) { setPub(null); setPackages([]); setRenderId(""); setBusy(""); setMessage(""); }
        shownProject.current = project; shownOpen.current = open;
    }, [open, project, renders.length]);

    const show = useCallback(async (id, kind) => {
        polling.current.abort(); polling.current = new AbortController();
        const generation = ++epoch.current;
        const current = () => generation === epoch.current;
        setMessage(""); setPackages([]); setPub(null); setBusy("");
        try {
            let publicationId = id;
            if (kind === "package") { const data = await client.api(`${jobPath(id)}/package`); if (!current()) return; publicationId = data.publicationJobId; }
            const data = await client.api(`${jobPath(publicationId)}/publication`);
            if (!current()) return;
            setRenderId(data.renderJobId); setPub(data);
            setForm({title: data.title, description: data.description, tags: data.tags.join("，"), coverFrame: data.coverFrame});
            if (data.publicationJobId) await restore(data, generation);
            return generation;
        } catch (error) { if (current()) setMessage(error.message); }
    }, [project]);

    const fps = pub ? pub.fps.numerator / pub.fps.denominator : 30;
    const dirty = pub && (form.title !== pub.title || form.description !== pub.description || tagList(form.tags).join("|") !== pub.tags.join("|") || form.coverFrame !== pub.coverFrame);
    useEffect(() => { onDirtyChange(!!dirty); }, [dirty]);
    useEffect(() => () => onDirtyChange(false), []);
    const useFrame = () => {
        const el = video.current; if (!el || !pub) return;
        setForm({...form, coverFrame: Math.max(0, Math.min(pub.frames - 1, Math.floor(el.currentTime * fps)))});
    };
    const save = async () => {
        if (!pub) return;
        const generation = epoch.current;
        const current = () => generation === epoch.current;
        setBusy("publication"); setMessage("正在保存发布信息并截取封面…");
        try {
            const accepted = await client.submit("publication", {renderJobId: pub.renderJobId, expectedRenderReceiptSha256: pub.expectedRenderReceiptSha256,
                coverFrame: form.coverFrame, title: form.title.trim(), description: form.description, tags: tagList(form.tags)});
            if (!current()) return;
            const done = await client.settle(accepted.jobId);
            if (!current()) return;
            if (done.status !== "completed") throw new Error(`保存失败：${done.error?.message || done.status}`);
            client.forgetIntent("publication"); onWorksChanged();
            setBusy("");
            const shown = await show(done.jobId, "publication"); if (epoch.current !== shown) return; setMessage("已保存。可以生成平台包了。");
        } catch (error) { if (current()) setMessage(error.message); } finally { if (current()) setBusy(""); }
    };
    const restore = async (snapshot, generation) => {
        const data = await client.api(`${jobPath(snapshot.publicationJobId)}/packages`, {projectId: project});
        if (generation !== epoch.current) return [];
        setPackages(data.jobs);
        for (const row of data.jobs) {
            if (generation !== epoch.current) return data.jobs;
            if (["pending", "running"].includes(row.status)) {
                void client.settle(row.jobId, polling.current.signal, (state) => {
                    if (generation === epoch.current) setPackages((rows) => rows.map((r) => r.jobId === row.jobId ? {...r, ...state} : r));
                }).then(() => loadDetail(row, generation)).catch((error) => { if (generation === epoch.current) setMessage(error.message); });
            } else if (row.status === "completed") void loadDetail(row, generation).catch((error) => { if (generation === epoch.current) setMessage(error.message); });
        }
        return data.jobs;
    };
    const loadDetail = async (row, generation) => {
        const data = await client.api(`${jobPath(row.jobId)}/package`);
        if (generation === epoch.current) setPackages((rows) => rows.map((r) => r.jobId === row.jobId ? {...r, ...data} : r));
    };
    const buildPackage = async (retry = null) => {
        if (!pub?.publicationJobId) return;
        const generation = epoch.current, snapshot = pub;
        const current = () => generation === epoch.current;
        const chosen = profiles.filter((p) => retry ? JSON.stringify(p) === JSON.stringify(retry.profile) : selected.includes(p.Platform));
        setBusy("package"); setMessage("");
        try {
            const existing = await restore(snapshot, generation);
            for (const profile of chosen) {
                if (!current()) return;
                const scope = JSON.stringify([project, snapshot.publicationJobId, snapshot.publicationReceiptSha256, profile]);
                const attempts = existing.filter((r) => JSON.stringify(r.profile) === JSON.stringify(profile));
                const running = attempts.find((r) => ["pending", "running"].includes(r.status));
                if (running) {
                    const done = await client.settle(running.jobId, polling.current.signal, (state) => {
                        if (current()) setPackages((rows) => rows.map((r) => r.jobId === running.jobId ? {...r, ...state} : r));
                    });
                    if (!current()) return;
                    if (done.status === "completed") await loadDetail(running, generation);
                    continue;
                }
                if (attempts.some((r) => r.status === "completed")) continue;
                if (retry) {
                    if (!attempts.some((r) => r.jobId === retry.jobId && ["failed", "interrupted"].includes(r.status))) continue;
                    client.retryPackageIntent(scope, attempts);
                } else if (attempts.length) continue;
                let accepted;
                try {
                    accepted = await client.submit("package", {publicationJobId: snapshot.publicationJobId, expectedPublicationReceiptSha256: snapshot.publicationReceiptSha256, profile}, scope);
                } catch (error) {
                    if (!current()) return;
                    // Unknown transport outcome retains this scope's request id. Reconcile before any resubmit.
                    await restore(snapshot, generation);
                    if (!current()) return;
                    setMessage(error.message);
                    if (!error.status) return;
                    setPackages((rows) => [...rows, {jobId: scope, profile, status: "denied", error: {message: error.message}}]);
                    continue;
                }
                if (!current()) return;
                const row = {...accepted, profile};
                setPackages((rows) => [...rows.filter((r) => r.jobId !== row.jobId), row]);
                const done = await client.settle(accepted.jobId, polling.current.signal, (state) => {
                    if (current()) setPackages((rows) => rows.map((r) => r.jobId === row.jobId ? {...r, ...state} : r));
                });
                if (!current()) return;
                onWorksChanged();
                if (done.status === "completed") {
                    try { await loadDetail(row, generation); }
                    catch (error) { if (current()) setMessage(error.message); }
                }
            }
        } catch (error) { if (current()) setMessage(error.message); }
        finally { if (current()) setBusy(""); }
    };

    const saved = !!pub?.publicationJobId && !dirty;
    const coverSrc = pub?.publicationJobId && !dirty ? `${jobPath(pub.publicationJobId)}/publication-files/cover.png` : null;
    const limits = profiles.find((p) => p.Platform === platform)?.Fields?.limits || {};
    const cls = `work${layout.bin ? "" : " no-bin"}${layout.insp ? "" : " no-insp"}`;
    return html`<div class=${cls}>
        <aside class="panel" hidden=${!layout.bin} aria-label="成片列表">
            <div class="panel-head">成片</div>
            <div class="panel-body">
                ${renders.map((job) => html`<button class="row" aria-current=${job.jobId === renderId} onClick=${() => show(job.jobId, "render")}>
                    <span class="dot ok"></span><span class="name">${when(job.createdAt)}</span><span class="meta">成片</span></button>`)}
                ${!renders.length && html`<p class="note">还没有成片。先在剪辑区导出一个视频。</p>`}
            </div>
        </aside>
        <div class="center">
            <section class="viewer" aria-label="成片预览">
                <div class="stage">${pub ? html`<video ref=${video} src=${client.sameOrigin(pub.videoUrl, `${jobPath(pub.renderJobId)}/video`) || ""} controls playsinline preload="metadata"></video>` : html`<div class="empty">在左侧选一个成片</div>`}</div>
                <div class="transport">
                    <button class="btn ghost" disabled=${!pub} onClick=${useFrame}>用当前画面做封面</button>
                    <span class="tc">封面：第 ${form.coverFrame} 帧（${(form.coverFrame / fps).toFixed(2)} 秒）</span>
                    <span class="spacer"></span>
                    ${pub && html`<span class="badge">${pub.width}×${pub.height} · ${(pub.frames / fps).toFixed(1)} 秒</span>`}
                </div>
            </section>
            <section class="timeline publish-pkg" aria-label="平台包">
                <div class="panel-head">平台包<span class="track-label">${saved ? "按平台预设转码、截封面、打包；不会自动发布" : "先保存右侧的发布信息"}</span></div>
                <div class="track-area">
                    <div class="actions-row">
                        ${profiles.map((p) => html`<label><input type="checkbox" checked=${selected.includes(p.Platform)} disabled=${!!busy} onChange=${(e) => { setPlatform(p.Platform); setSelected(e.currentTarget.checked ? [...selected, p.Platform] : selected.filter((v) => v !== p.Platform)); }} />${PLATFORMS[p.Platform] || p.Platform}${selected.includes(p.Platform) && !packages.some((r) => r.profile?.Platform === p.Platform) ? " · 尚未提交" : ""}</label>`)}
                        <button class="btn" disabled=${!saved || !!busy || !selected.length} onClick=${() => buildPackage()}>${busy === "package" ? "正在生成…" : "生成平台包"}</button>
                        ${saved && !selected.length ? html`<span class="hint" role="status" aria-label="平台包状态">至少勾选一个平台</span>` : null}
                        <span class="hint">${["titleMaxChars", "descriptionMaxChars", "tagMaxCount"].filter((k) => limits[k]).map((k) => `${CHECKS[k]}≤${limits[k]}`).join(" · ")}</span>
                    </div>
                    ${packages.map((pkg) => html`<div class="pkg-result">
                        <p>${PLATFORMS[pkg.profile?.Platform] || ""} · ${client.jobStatus(pkg.status)} ${pkg.error?.message || ""}</p>
                        ${["failed", "interrupted"].includes(pkg.status) && html`<button class="btn ghost" disabled=${!!busy || !saved} onClick=${() => buildPackage(pkg)}>重试此平台</button>`}
                        ${pkg.generationStatus && html`<div>
                        <p class="v">${PLATFORMS[pkg.profile?.Platform] || ""}：${pkg.generationStatus === "completed" ? "已生成" : "未完成"}；本地检查${STATUS[pkg.localChecks] || "未知"}${pkg.publicationEligibility === "blocked" ? "；发布受阻（含仅供测试的音乐等）" : ""}${pkg.watermark ? "；含水印" : ""}。平台官方规则、素材权利尚未核实。</p>
                        <p class="hint">${Object.entries(pkg.validation?.checks || {}).map(([k, s]) => `${CHECKS[k] || k}：${STATUS[s] || "未知"}`).join("　")}</p>
                        <div class="actions-row"><a class="btn" href=${`${jobPath(pkg.jobId)}/package-files/package.zip?download=1`} download="package.zip">下载平台包（zip）</a>
                            <a class="btn ghost" href=${`${jobPath(pkg.jobId)}/package-files/video.mp4?download=1`} download="video.mp4">只下载视频</a></div>
                    </div>`}
                    </div>`)}
                </div>
            </section>
        </div>
        <aside class="panel" hidden=${!layout.insp} aria-label="发布信息">
            <div class="panel-head">发布信息</div>
            <div class="panel-body">
                ${message && html`<p class="note" role="status">${message}</p>`}
                ${pub ? html`
                    <p class="hint">${pub.publicationJobId ? (dirty ? "有未保存的修改" : "已保存的版本") : "按需求自动起草的模板，请改一遍再保存。"}</p>
                    <label class="form-row">标题（${form.title.length} 字）<input class="input" value=${form.title} maxLength="200" onInput=${(e) => setForm({...form, title: e.currentTarget.value})} /></label>
                    <label class="form-row">简介（${form.description.length} 字）<textarea class="input" rows="6" value=${form.description} onInput=${(e) => setForm({...form, description: e.currentTarget.value})}></textarea></label>
                    <label class="form-row">标签（逗号分隔，${tagList(form.tags).length} 个）<input class="input" value=${form.tags} onInput=${(e) => setForm({...form, tags: e.currentTarget.value})} /></label>
                    <div class="field"><div class="k">封面</div>${coverSrc ? html`<img class="cover" src=${coverSrc} alt="封面" />` : html`<p class="hint">保存后在这里显示封面截图。</p>`}</div>
                    <div class="actions-row"><button class="btn" disabled=${!!busy || !form.title.trim() || (pub.publicationJobId && !dirty)} onClick=${save}>${busy === "publication" ? "正在保存…" : "保存发布信息"}</button></div>`
                : html`<p class="note">选中成片后，在这里写标题、简介和标签。</p>`}
            </div>
        </aside>
    </div>`;
}
