import {h} from "../vendor/preact.module.js";
import {useEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";
import {OUTCOME_LABELS, writeStructureFeedback} from "./structure_feedback.js";

const html = htm.bind(h);
const PATH = "/api/creation/publication-feedback";
const METRICS = Object.entries(OUTCOME_LABELS);
const emptyForm = () => ({ctrBps: "", retention3sBps: "", completionBps: "", postUrl: "", source: "creator",
    observedOn: new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 10)});
const percent = (value) => value === null ? "未知" : `${(value / 100).toFixed(2)}%`;

function FeedbackHistory({records}) {
    if (!records.length) return html`<p class="hint">暂无成效记录。</p>`;
    return html`<ul class="facts" aria-label="发布成效记录">${records.map(row => html`<li key=${row.observationId}>
        <strong>${row.observedOn} · ${row.source === "test" ? "测试示例" : "创作者手录"}</strong>
        <div>${METRICS.map(([key, label]) => `${label} ${percent(row.metrics[key])}`).join(" · ")}</div>
        ${row.postUrl && html`<div class="feedback-url">${row.postUrl}</div>`}
    </li>`)}</ul>`;
}

function OutcomeComparison({scope, observationCount, onOpenReference}) {
    const [open, setOpen] = useState(false);
    const [showTests, setShowTests] = useState(false);
    const [metric, setMetric] = useState("completionBps");
    const [result, setResult] = useState(null);
    const [message, setMessage] = useState("");
    const [picked, setPicked] = useState(null);
    const [refresh, setRefresh] = useState(0);
    const key = JSON.stringify([scope, metric, observationCount, refresh]);
    useEffect(() => {
        if (!open) return;
        const controller = new AbortController();
        setResult(null); setMessage(""); setPicked(null);
        client.api(`${PATH}/compare`, {...scope, metric}, {signal: controller.signal}).then(data => {
            if (!controller.signal.aborted) setResult({key, data});
        }).catch(error => { if (!controller.signal.aborted) setMessage(error.message); });
        return () => controller.abort();
    }, [open, key]);
    const data = result?.key === key ? result.data : null;
    const rows = data?.rows.filter(row => row.source !== "test" || showTests) || [];
    const remember = (row) => {
        const storageScope = data.workId ? `${scope.projectId}:work:${data.workId}` : scope.projectId;
        const saved = writeStructureFeedback(storageScope, {contentType: data.contentType, label: row.planLabel, source: row.choice});
        setMessage(saved ? "已设为该作品同平台、同类型的下次结构参考。" : "浏览器不允许保存结构参考。");
        setPicked(saved ? row.choice : null);
    };
    return html`<details class="group" onToggle=${event => setOpen(event.currentTarget.open)}>
        <summary>对比同平台版本</summary>
        ${open && html`<div class="feedback-comparison">
            <div class="actions-row">
                <label>排序指标 <select class="select" value=${metric} onChange=${event => setMetric(event.currentTarget.value)}>
                    ${METRICS.map(([key, label]) => html`<option value=${key}>${label}</option>`)}</select></label>
                <label class="check"><input type="checkbox" checked=${showTests} onChange=${e => setShowTests(e.currentTarget.checked)} />显示测试示例</label>
                <button type="button" class="btn ghost" onClick=${() => setRefresh(value => value + 1)}>刷新对比</button>
            </div>
            <p class="hint">同作品、同内容类型的各平台包，按各自最近一次观察比较。</p>
            ${!data && !message && html`<p class="hint" role="status">正在核对版本与成效…</p>`}
            ${data?.skipped > 0 && html`<p class="hint">有 ${data.skipped} 个版本无法核对。</p>`}
            ${data && !rows.length && html`<p class="hint">暂无可比较的${showTests ? "成效" : "手录成效"}。</p>`}
            ${rows.length ? html`<table aria-label="同平台版本成效">
                <thead><tr>${["发布版本", "日期与来源", ...METRICS.map(([, label]) => label), "结构参考"].map(label => html`<th scope="col">${label}</th>`)}</tr></thead>
                <tbody>${rows.map(row => html`<tr key=${`${row.packageJobId}:${row.source}`}>
                    <th scope="row">${row.title} <small>${row.packageJobId.slice(0, 8)}${row.shortVersion ? " · 短版" : ""}</small></th>
                    <td><time datetime=${row.observedOn}>${row.observedOn}</time><br />${row.source === "test" ? "测试示例" : "创作者手录"}</td>
                    ${METRICS.map(([key]) => html`<td>${percent(row.metrics[key])}</td>`)}
                    <td>${row.choice ? html`<span class="feedback-plan-label" title=${row.planLabel}>${row.planLabel}</span> <button type="button" class="btn ghost" onClick=${() => remember(row)}>参考原方案结构</button>` : "—"}</td>
                </tr>`)}</tbody>
            </table>` : null}
            ${message && html`<p class="hint" role="status">${message}</p>`}
            ${picked && html`<button type="button" class="btn ghost" onClick=${() => onOpenReference(picked)}>前往该作品剪辑</button>`}
        </div>`}
    </details>`;
}

export function PublicationFeedback({project, publicationId, packageId, videoSha256, onOpenReference}) {
    const [open, setOpen] = useState(false);
    const [records, setRecords] = useState(null);
    const [form, setForm] = useState(emptyForm);
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState("");
    const alive = useRef(true);
    const writeEpoch = useRef(0);
    useEffect(() => () => { alive.current = false; }, []);
    const scope = {projectId: project, publicationJobId: publicationId, packageJobId: packageId, packageVideoSha256: videoSha256};
    useEffect(() => {
        if (!open) return;
        const controller = new AbortController();
        const before = writeEpoch.current;
        setMessage("");
        client.api(PATH, scope, {signal: controller.signal}).then(data => {
            if (!controller.signal.aborted && writeEpoch.current === before) setRecords(data.records);
        }).catch(error => {
            if (!controller.signal.aborted && writeEpoch.current === before) {
                setRecords(null); setMessage(error.message);
            }
        });
        return () => controller.abort();
    }, [open, project, publicationId, packageId, videoSha256]);
    const field = (key, value) => setForm(current => ({...current, [key]: value}));
    const save = async (event) => {
        event.preventDefault();
        if (busy || records === null) return;
        setBusy(true); setMessage("");
        try {
            const metrics = Object.fromEntries(METRICS.map(([key]) => [key, form[key] === "" ? null : Math.round(Number(form[key]) * 100)]));
            const payload = {...scope, source: form.source, observedOn: form.observedOn, postUrl: form.postUrl.trim() || null, metrics};
            const row = await client.api(PATH, {}, {body: payload});
            if (!alive.current) return;
            writeEpoch.current += 1;
            setRecords(current => [row, ...(current || []).filter(prior => prior.observationId !== row.observationId)]
                .sort((a, b) => b.observedOn.localeCompare(a.observedOn) || b.recordedAt.localeCompare(a.recordedAt)));
            setForm({...emptyForm(), source: form.source}); setMessage("成效已保存。");
        } catch (error) { if (alive.current) setMessage(error.message); }
        finally { if (alive.current) setBusy(false); }
    };
    return html`<details class="group publication-feedback" onToggle=${event => setOpen(event.currentTarget.open)}>
        <summary>发布成效</summary>
        ${open && records !== null && html`<${FeedbackHistory} records=${records} />`}
        ${open && html`<${OutcomeComparison} scope=${scope} observationCount=${records?.length} onOpenReference=${onOpenReference} />`}
        ${open && records === null && !message && html`<p class="hint" role="status">正在读取成效记录…</p>`}
        ${open && html`<form class="brief feedback-form" onSubmit=${save}>
            <p class="hint">从平台后台手录数据，空白为未知。手录记录由创作者提供，测试示例单独标记。</p>
            <label class="form-row">记录来源<select class="select" disabled=${busy} value=${form.source} onChange=${e => field("source", e.currentTarget.value)}>
                <option value="creator">创作者手录</option><option value="test">测试示例</option></select></label>
            <label class="form-row">观察日期<input class="input" type="date" required disabled=${busy} value=${form.observedOn} onInput=${e => field("observedOn", e.currentTarget.value)} /></label>
            <label class="form-row">帖子链接（选填）<input class="input" type="url" maxlength="2048" disabled=${busy} value=${form.postUrl} onInput=${e => field("postUrl", e.currentTarget.value)} /></label>
            ${METRICS.map(([key, label]) => html`<label class="form-row" key=${key}>${label}（%）<input class="input" type="number" min="0" max="100" step="0.01" disabled=${busy} value=${form[key]} onInput=${e => field(key, e.currentTarget.value)} /></label>`)}
            <button type="submit" class="btn ghost" disabled=${busy || records === null}>保存成效</button>
        </form>`}
        ${message && html`<p class="hint" role="status">${message}</p>`}
    </details>`;
}
