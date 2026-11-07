// Output-clock overlays; sprites and receipts are registered by the local server.
import {h} from "../vendor/preact.module.js";
import {useEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import {api, sameOrigin} from "./api.js";

const html = htm.bind(h);
const halfUp = (n, d) => Math.floor((2 * n + d) / (2 * d));
const integer = (n, min, max) => Number.isSafeInteger(n) && n >= min && n <= max;
const textProblem = (value) => typeof value !== "string" || !value.trim() || [...value].length > 120
    || /[{}\\<>\p{C}\u2028\u2029]/u.test(value) ? "文字须为 1–120 字单行纯文字，不含控制符、花括号、反斜线或尖括号。" : "";
const assetFor = (item, assets) => assets.find((a) => a.assetId === item.assetId && a.assetReceiptSha256 === item.assetReceiptSha256);
const spriteUrl = (asset) => sameOrigin(asset.imageUrl, `/api/creation/overlay-assets/${asset.assetId}/image`);

export function overlayGeometry(item, asset, width, height) {
    if (![width, height, asset?.width, asset?.height].every((v) => integer(v, 1, Number.MAX_SAFE_INTEGER))) return null;
    const x = halfUp(item.x * width, 10000), y = halfUp(item.y * height, 10000);
    const w = Math.max(1, halfUp(item.width * width, 10000));
    const h = Math.max(1, halfUp(w * asset.height, asset.width));
    return [x, y, w, h].every(Number.isFinite) && x >= 0 && y >= 0 && x + w <= width && y + h <= height
        ? {x, y, width: w, height: h} : null;
}

export function overlayOpacity(item, frame) {
    if (!Number.isInteger(frame) || frame < item.startFrame || frame >= item.endFrame) return 0;
    return Math.min(1, item.fadeInFrames ? (frame - item.startFrame) / item.fadeInFrames : 1,
        item.fadeOutFrames ? (item.endFrame - frame) / item.fadeOutFrames : 1);
}

export function overlayProblem(items = [], assets = [], totalFrames, width, height) {
    if (!Array.isArray(items) || items.length > 16) return "最多支持 16 个叠加图层。";
    const seen = new Set(), required = new Map();
    for (let i = 0; i < items.length; i++) {
        const item = items[i], prefix = `第 ${i + 1} 个叠加图层：`;
        if (!/^[0-9a-f]{32}$/.test(item.overlayId) || seen.has(item.overlayId)) return prefix + "图层标识重复或无效。";
        seen.add(item.overlayId);
        if (!integer(item.startFrame, 0, totalFrames) || !integer(item.endFrame, item.startFrame + 1, totalFrames)) return prefix + "开始须早于结束，且必须位于成片时长内。";
        const duration = item.endFrame - item.startFrame;
        if (!integer(item.fadeInFrames, 0, duration) || !integer(item.fadeOutFrames, 0, duration)
            || item.fadeInFrames + item.fadeOutFrames > duration) return prefix + "淡入、淡出之和不能超过图层时长。";
        if (!integer(item.x, 0, 10000) || !integer(item.y, 0, 10000) || !integer(item.width, 1, 10000)
            || item.x + item.width > 10000) return prefix + "位置或宽度超出画布。";
        const asset = assetFor(item, assets);
        if (!asset || asset.kind !== item.kind || !/^[0-9a-f]{32}$/.test(item.assetId)
            || !/^[0-9a-f]{64}$/.test(item.assetReceiptSha256)) return prefix + "素材或登记回执不匹配，请重新添加。";
        if (item.kind === "text" && (textProblem(item.text) || item.text !== asset.text)) return prefix + "文字与登记素材不一致，请重新登记文字。";
        if (!["text", "image"].includes(item.kind)) return prefix + "不支持的素材类型。";
        if (!overlayGeometry(item, asset, width, height)) return prefix + "精灵高度或宽度超出画布，请减小宽度或调整位置。";
        if (!spriteUrl(asset)) return prefix + "素材地址无效。";
        required.set(asset.assetId, asset);
    }
    if ([...required.values()].reduce((n, a) => n + a.width * a.height * 4, 0) > 128 * 1024 * 1024) return "叠加图层解码大小超过 128 MiB，请减少素材。";
    return "";
}

export function overlayFrame(outUs, fps) {
    const clock = Math.max(0, outUs) * fps / 1e6;
    // Recover exact integer-frame seek boundaries after microsecond conversion.
    return Math.floor(clock + Math.max(1, clock) * Number.EPSILON * 4);
}

export function OverlayPreview({items = [], assets = [], outUs, fps, width, height}) {
    const frame = overlayFrame(outUs, fps);
    return html`<div aria-hidden="true" style=${{position: "absolute", left: 0, top: 0, width: `${width}px`, height: `${height}px`, pointerEvents: "none"}}>
        ${items.map((item) => {
            const asset = assetFor(item, assets), geometry = overlayGeometry(item, asset, width, height);
            const url = asset && spriteUrl(asset), opacity = overlayOpacity(item, frame);
            return geometry && url ? html`<img key=${item.overlayId} data-overlay-id=${item.overlayId} src=${url} alt="" draggable=${false}
                style=${{position: "absolute", left: `${geometry.x}px`, top: `${geometry.y}px`, width: `${geometry.width}px`, height: `${geometry.height}px`, opacity, pointerEvents: "none"}} />` : null;
        })}
    </div>`;
}

function fileBody(file) {
    if (!file || !/\.png$/i.test(file.name) || file.size > 8 * 1024 * 1024 || !file.size) throw new Error("请选择不超过 8 MiB 的 PNG 图片。");
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(new Error("读取 PNG 失败。"));
        reader.onload = () => resolve({kind: "image", fileName: file.name, dataBase64: String(reader.result).split(",")[1]});
        reader.readAsDataURL(file);
    });
}

function retainAssets(items, assets) {
    const ids = new Set(items.map((item) => item.assetId));
    return [...new Map(assets.filter((a) => ids.has(a.assetId)).map((a) => [a.assetId, a])).values()];
}

function newItem(asset, totalFrames, width, height) {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    const item = {overlayId: [...bytes].map((b) => b.toString(16).padStart(2, "0")).join(""),
        kind: asset.kind, startFrame: 0, endFrame: totalFrames, x: 0, y: 0, width: 3000,
        fadeInFrames: 0, fadeOutFrames: 0, assetId: asset.assetId, assetReceiptSha256: asset.assetReceiptSha256};
    if (asset.kind === "text") item.text = asset.text;
    // Tall sprites start small enough to fit; later manual overflow is reported, never silently clipped.
    while (item.width > 1 && !overlayGeometry(item, asset, width, height)) item.width -= 1;
    return item;
}

function NumberField({label, value, factor, onChange}) {
    return html`<label>${label}<input type="number" aria-label=${label} step=${factor === 100 ? "0.01" : "any"}
        value=${Number.isFinite(value) ? Number((value / factor).toFixed(6)) : ""}
        onInput=${(event) => onChange(event.currentTarget.value === "" ? NaN : Math.round(Number(event.currentTarget.value) * factor))} /></label>`;
}

function OverlayRow({item, index, count, fps, update, move, remove, register}) {
    const [text, setText] = useState(item.text || "");
    useEffect(() => setText(item.text || ""), [item.text]);
    const timeFields = [["开始秒", "startFrame"], ["结束秒", "endFrame"], ["淡入秒", "fadeInFrames"], ["淡出秒", "fadeOutFrames"]];
    const geometryFields = [["横向位置%", "x"], ["纵向位置%", "y"], ["宽度%", "width"]];
    return html`<div class="overlay-row" data-overlay-id=${item.overlayId}>
        <strong>图层 ${index + 1} · ${item.kind === "text" ? "文字" : "PNG"}</strong>
        ${item.kind === "text" ? html`<label>文字<input aria-label="图层文字" value=${text} onInput=${(e) => setText(e.currentTarget.value)} /></label>
            <button type="button" disabled=${text === item.text} onClick=${() => register({kind: "text", text}, item.overlayId)}>更新文字</button>` : null}
        ${timeFields.map(([label, field]) => html`<${NumberField} key=${field} label=${label} value=${item[field]} factor=${fps} onChange=${(v) => update({[field]: v})} />`)}
        ${geometryFields.map(([label, field]) => html`<${NumberField} key=${field} label=${label} value=${item[field]} factor=${100} onChange=${(v) => update({[field]: v})} />`)}
        <button type="button" disabled=${index === count - 1} onClick=${() => move(1)}>上移一层</button>
        <button type="button" disabled=${index === 0} onClick=${() => move(-1)}>下移一层</button>
        <button type="button" onClick=${remove}>删除图层</button>
    </div>`;
}

export function OverlayPanel({editing, fps, totalFrames, onBusy, disabled, canvasWidth, canvasHeight}) {
    const [text, setText] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState("");
    const latest = useRef(editing), pending = useRef(false), alive = useRef(true);
    latest.current = editing;
    useEffect(() => () => { alive.current = false; onBusy?.(false); }, []);
    const items = editing.overlays || [], assets = editing.overlayAssets || [];
    const apply = (next) => editing.ops.overlays(next, retainAssets(next, assets));
    async function register(body, overlayId) {
        if (pending.current || disabled || (!overlayId && items.length >= 16)) return;
        const snapshot = latest.current, epoch = snapshot.overlayEpoch;
        const identity = (e) => JSON.stringify([e.project, e.base?.jobId, e.base?.planId, e.overlayEpoch]);
        pending.current = true; setBusy(true); onBusy?.(true); setError("");
        try {
            const value = typeof body === "function" ? await body() : body;
            if (value.kind === "text" && textProblem(value.text)) throw new Error(textProblem(value.text));
            const asset = await api("/api/creation/overlay-assets", {}, {body: value});
            if (!alive.current || identity(latest.current) !== identity(snapshot) || latest.current.status !== "ready") return;
            const current = latest.current;
            const next = overlayId ? current.overlays.map((item) => item.overlayId === overlayId
                ? {...item, text: asset.text, assetId: asset.assetId, assetReceiptSha256: asset.assetReceiptSha256} : item)
                : [...current.overlays, newItem(asset, totalFrames, canvasWidth, canvasHeight)];
            current.ops.overlays(next, retainAssets(next, [...current.overlayAssets, asset]), epoch);
            if (!overlayId) setText("");
        } catch (err) { if (alive.current && identity(latest.current) === identity(snapshot)) setError(err.message || "登记叠加素材失败。"); }
        finally { pending.current = false; if (alive.current) { setBusy(false); onBusy?.(false); } }
    }
    const problem = overlayProblem(items, assets, totalFrames, canvasWidth, canvasHeight);
    return html`<section class="overlay-panel"><h3>定时文字 / PNG 叠加</h3>
        <p>按成片时间设置，结束帧不显示；列表从底层到顶层。最多 16 层。</p>
        <fieldset disabled=${disabled || busy || editing.status !== "ready"}>
            <label>文字<input aria-label="叠加文字" value=${text} onInput=${(e) => setText(e.currentTarget.value)} /></label>
            <button type="button" disabled=${items.length >= 16 || !totalFrames} onClick=${() => register({kind: "text", text})}>添加文字</button>
            <label>上传 PNG（≤8 MiB）<input type="file" accept="image/png,.png" aria-label="上传PNG叠加" disabled=${items.length >= 16 || !totalFrames}
                onChange=${(event) => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; if (file) register(() => fileBody(file)); }} /></label>
            ${items.map((item, index) => html`<${OverlayRow} key=${item.overlayId} item=${item} index=${index} count=${items.length} fps=${fps} register=${register}
                update=${(patch) => apply(items.map((row) => row.overlayId === item.overlayId ? {...row, ...patch} : row))}
                remove=${() => apply(items.filter((row) => row.overlayId !== item.overlayId))}
                move=${(offset) => { const next = [...items]; [next[index], next[index + offset]] = [next[index + offset], next[index]]; apply(next); }} />`)}
        </fieldset>
        ${busy ? html`<p role="status">正在登记叠加素材…</p>` : null}
        ${error || problem ? html`<p role="alert">${error || problem}</p>` : null}
    </section>`;
}
