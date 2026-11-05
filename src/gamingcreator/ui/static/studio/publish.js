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

export function PublishWorkspace({project, works, open, onWorksChanged, layout}) {
    const renders = works.filter((j) => j.kind === "render" && j.status === "completed");
    const [renderId, setRenderId] = useState("");
    const [pub, setPub] = useState(null); // the snapshot shown: a draft from the render or a saved publication
    const [form, setForm] = useState({title: "", description: "", tags: "", coverFrame: 0});
    const [profiles, setProfiles] = useState([]);
    const [platform, setPlatform] = useState("");
    const [pkg, setPkg] = useState(null);
    const [busy, setBusy] = useState("");
    const [message, setMessage] = useState("");
    const video = useRef(null);

    useEffect(() => {
        client.api("/api/creation/platform-profiles").then((data) => { setProfiles(data.profiles || []); setPlatform(data.profiles?.[0]?.Platform || ""); }).catch(() => setProfiles([]));
    }, []);
    // Open what was asked for (a video, publication or package from the bin), else the newest video.
    useEffect(() => {
        if (open && ["render", "publication", "package"].includes(open.kind)) void show(open.id, open.kind);
        else if (!renderId && renders[0]) void show(renders[0].jobId, "render");
    }, [open, project, renders.length]);

    const show = useCallback(async (id, kind) => {
        setMessage(""); setPkg(null);
        try {
            let publicationId = id;
            if (kind === "package") { const data = await client.api(`${jobPath(id)}/package`); setPkg({...data, jobId: id}); publicationId = data.publicationJobId; }
            const data = await client.api(`${jobPath(publicationId)}/publication`);
            setRenderId(data.renderJobId); setPub(data);
            setForm({title: data.title, description: data.description, tags: data.tags.join("，"), coverFrame: data.coverFrame});
        } catch (error) { setMessage(error.message); }
    }, []);

    const fps = pub ? pub.fps.numerator / pub.fps.denominator : 30;
    const dirty = pub && (form.title !== pub.title || form.description !== pub.description || tagList(form.tags).join("|") !== pub.tags.join("|") || form.coverFrame !== pub.coverFrame);
    const useFrame = () => {
        const el = video.current; if (!el || !pub) return;
        setForm({...form, coverFrame: Math.max(0, Math.min(pub.frames - 1, Math.floor(el.currentTime * fps)))});
    };
    const save = async () => {
        if (!pub) return;
        setBusy("publication"); setMessage("正在保存发布信息并截取封面…");
        try {
            const accepted = await client.submit("publication", {renderJobId: pub.renderJobId, expectedRenderReceiptSha256: pub.expectedRenderReceiptSha256,
                coverFrame: form.coverFrame, title: form.title.trim(), description: form.description, tags: tagList(form.tags)});
            const done = await client.settle(accepted.jobId);
            if (done.status !== "completed") throw new Error(`保存失败：${done.error?.message || done.status}`);
            client.forgetIntent("publication"); onWorksChanged();
            await show(done.jobId, "publication"); setMessage("已保存。可以生成平台包了。");
        } catch (error) { setMessage(error.message); } finally { setBusy(""); }
    };
    const buildPackage = async () => {
        const profile = profiles.find((p) => p.Platform === platform);
        if (!pub?.publicationJobId || !profile) return;
        setBusy("package"); setMessage(`正在生成${PLATFORMS[platform] || platform}平台包（会转码，可能需要一分钟）…`);
        try {
            const accepted = await client.submit("package", {publicationJobId: pub.publicationJobId, expectedPublicationReceiptSha256: pub.publicationReceiptSha256, profile});
            const done = await client.settle(accepted.jobId);
            if (done.status !== "completed") throw new Error(`生成失败：${done.error?.message || done.status}`);
            client.forgetIntent("package"); onWorksChanged();
            setPkg({...(await client.api(`${jobPath(done.jobId)}/package`)), jobId: done.jobId}); setMessage("");
        } catch (error) { setMessage(error.message); } finally { setBusy(""); }
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
                        <select class="select" aria-label="平台" value=${platform} onChange=${(e) => setPlatform(e.currentTarget.value)}>${profiles.map((p) => html`<option value=${p.Platform}>${PLATFORMS[p.Platform] || p.Platform}</option>`)}</select>
                        <button class="btn" disabled=${!saved || !!busy || !platform} onClick=${buildPackage}>${busy === "package" ? "正在生成…" : "生成平台包"}</button>
                        <span class="hint">${["titleMaxChars", "descriptionMaxChars", "tagMaxCount"].filter((k) => limits[k]).map((k) => `${CHECKS[k]}≤${limits[k]}`).join(" · ")}</span>
                    </div>
                    ${pkg && html`<div class="pkg-result">
                        <p class="v">${PLATFORMS[pkg.profile?.Platform] || ""}：${pkg.generationStatus === "completed" ? "已生成" : "未完成"}；本地检查${STATUS[pkg.localChecks] || "未知"}${pkg.publicationEligibility === "blocked" ? "；发布受阻（含仅供测试的音乐等）" : ""}${pkg.watermark ? "；含水印" : ""}。平台官方规则、素材权利尚未核实。</p>
                        <p class="hint">${Object.entries(pkg.validation?.checks || {}).map(([k, s]) => `${CHECKS[k] || k}：${STATUS[s] || "未知"}`).join("　")}</p>
                        <div class="actions-row"><a class="btn" href=${`${jobPath(pkg.jobId)}/package-files/package.zip?download=1`} download="package.zip">下载平台包（zip）</a>
                            <a class="btn ghost" href=${`${jobPath(pkg.jobId)}/package-files/video.mp4?download=1`} download="video.mp4">只下载视频</a></div>
                    </div>`}
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
