import {h} from "../vendor/preact.module.js";
import {useEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import {api} from "./api.js";

const html = htm.bind(h);
const ROLES = {owner: "负责人", editor: "编辑", reviewer: "审核", viewer: "只读"};
const ACTIONS = {submit: "提交审核", approve: "批准", reject: "驳回"};
const REVIEW = {pending: "审核中", approved: "已通过", rejected: "已驳回"};
const SANDBOX = {submitted: "已提交", processing: "处理中", published: "已完成"};
const auditLink = (project, format) => `/api/enterprise/audit?${new URLSearchParams({projectId: project, format})}`;
const terms = value => value.split(/[,，\n]/).map(t => t.trim()).filter(Boolean);

function useRequest() {
    const controller = useRef(null);
    const pending = useRef(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    useEffect(() => {
        controller.current = new AbortController();
        return () => controller.current.abort();
    }, []);
    const run = async task => {
        const signal = controller.current?.signal;
        if (!signal || signal.aborted || pending.current) return;
        pending.current = true;
        setBusy(true); setError("");
        try { await task(signal); }
        catch (reason) { if (!signal.aborted) setError(reason.message); }
        finally { if (!signal.aborted) { pending.current = false; setBusy(false); } }
    };
    return {busy, error, run};
}

const initialTeam = () => ({members: [{name: "", role: "owner"}], brandTerms: {required: [], forbidden: []}, reviewRequired: true});

function TeamEditor({project, onSaved}) {
    const {busy, error, run} = useRequest();
    const [stored, setStored] = useState(undefined);
    const [draft, setDraft] = useState(initialTeam);
    const [actor, setActor] = useState("");
    const [required, setRequired] = useState("");
    const [forbidden, setForbidden] = useState("");
    const [notice, setNotice] = useState("");
    const fill = team => {
        setStored(team);
        setDraft(team || initialTeam());
        setRequired(team?.brandTerms.required.join("\n") || "");
        setForbidden(team?.brandTerms.forbidden.join("\n") || "");
    };
    const load = () => run(async signal => {
        const {team} = await api("/api/enterprise/team", {projectId: project}, {signal});
        if (!signal.aborted) fill(team);
    });
    useEffect(() => { void load(); }, []);
    const changeMember = (index, patch) => setDraft({...draft, members: draft.members.map((member, i) => i === index ? {...member, ...patch} : member)});
    const save = () => run(async signal => {
        setNotice("");
        const team = await api("/api/enterprise/team", {}, {signal, body: {projectId: project, actor: actor.trim(), team: {
            ...draft, brandTerms: {required: terms(required), forbidden: terms(forbidden)},
        }}});
        if (!signal.aborted) { fill(team); setNotice("团队设置已保存"); onSaved(); }
    });
    return html`<div class="enterprise-form">
        <p class="hint">操作人自报姓名。本机记录用于团队分工和复核。</p>
        ${stored === undefined ? html`<button class="btn ghost" disabled=${busy} onClick=${load}>读取团队设置</button>` : html`
            <fieldset disabled=${busy} class="enterprise-fields">
                <legend>团队成员</legend>
                ${draft.members.map((member, i) => html`<div class="enterprise-member" key=${i}>
                    <input class="input" value=${member.name} maxLength="50" placeholder="姓名" aria-label=${`成员 ${i + 1} 姓名`} onInput=${e => changeMember(i, {name: e.currentTarget.value})} />
                    <select class="select" value=${member.role} aria-label=${`成员 ${i + 1} 角色`} onChange=${e => changeMember(i, {role: e.currentTarget.value})}>
                        ${Object.entries(ROLES).map(([id, label]) => html`<option value=${id}>${label}</option>`)}
                    </select>
                    <button class="btn ghost" disabled=${draft.members.length === 1} aria-label=${`移除成员 ${i + 1}`} onClick=${() => setDraft({...draft, members: draft.members.filter((_, index) => i !== index)})}>移除</button>
                </div>`)}
                <button class="btn ghost" disabled=${draft.members.length >= 200} onClick=${() => setDraft({...draft, members: [...draft.members, {name: "", role: "editor"}]})}>添加成员</button>
                <label class="form-row">必须出现的品牌词<textarea class="input" rows="2" value=${required} onInput=${e => setRequired(e.currentTarget.value)} /></label>
                <label class="form-row">禁用词<textarea class="input" rows="2" value=${forbidden} onInput=${e => setForbidden(e.currentTarget.value)} /></label>
                <label class="check"><input type="checkbox" checked=${draft.reviewRequired} onChange=${e => setDraft({...draft, reviewRequired: e.currentTarget.checked})} />模拟发布前必须审核通过</label>
                <label class="form-row">负责人姓名<input class="input" value=${actor} maxLength="50" onInput=${e => setActor(e.currentTarget.value)} /></label>
                <button class="btn" disabled=${!actor.trim() || draft.members.some(member => !member.name.trim())} onClick=${save}>保存团队设置</button>
            </fieldset>`}
        ${notice && html`<p role="status">${notice}</p>`}
        ${error && html`<p role="alert">${error}</p>`}
    </div>`;
}

export function EnterpriseTeam({project, onSaved}) {
    const [open, setOpen] = useState(false);
    return html`<details class="group field" aria-label="团队与品牌" onToggle=${e => setOpen(e.currentTarget.open)}>
        <summary>团队与品牌</summary>
        ${open && html`<${TeamEditor} project=${project} onSaved=${onSaved} />
            <div class="actions-row"><a class="btn ghost" href=${auditLink(project, "json")}>下载审计 JSON</a>
                <a class="btn ghost" href=${auditLink(project, "csv")}>下载审计 CSV</a></div>`}
    </details>`;
}

function ReviewHistory({events}) {
    if (!events.length) return null;
    return html`<details>
        <summary>审核记录（${events.length}）</summary>
        <ol class="facts">${events.map(event => html`<li>${new Date(event.at).toLocaleString("zh-CN")} · ${event.actor}（${ROLES[event.role]}）· ${ACTIONS[event.action]}
            ${event.comment && html`<div>${event.comment}</div>`}
            ${event.brandIssues?.length > 0 && html`<div class="hint">${event.brandIssues.join("、")}</div>`}</li>`)}</ol>
    </details>`;
}

function ReviewEditor({project, pkg}) {
    const packageJobId = pkg.jobId;
    const {busy, error, run} = useRequest();
    const [snapshot, setSnapshot] = useState(null);
    const [sandbox, setSandbox] = useState(null);
    const [actor, setActor] = useState("");
    const [comment, setComment] = useState("");
    const load = async signal => {
        const data = await api("/api/enterprise/review", {projectId: project, packageJobId}, {signal});
        const {records} = await api("/api/creation/publish", {packageJobId}, {signal});
        if (!signal.aborted) { setSnapshot(data); setSandbox(records.at(-1) || null); }
    };
    useEffect(() => { void run(load); }, []);
    const review = action => run(async signal => {
        const updated = await api("/api/enterprise/review", {}, {signal, body: {packageJobId, actor, action, comment}});
        if (!signal.aborted) {
            setSnapshot(prev => ({...prev, review: updated}));
            setComment("");
        }
        await load(signal);
    });
    const simulate = () => run(async signal => {
        const record = await api("/api/creation/publish", {}, {signal, body: {packageJobId, target: "sandbox"}});
        if (!signal.aborted) setSandbox(record);
    });
    const check = () => run(async signal => {
        const record = await api(`/api/creation/publish/${encodeURIComponent(sandbox.publishId)}`, {}, {signal});
        if (!signal.aborted) setSandbox(record);
    });
    const team = snapshot?.team, record = snapshot?.review;
    const role = team?.members.find(member => member.name === actor)?.role;
    const pending = record?.state === "pending";
    const canApprove = pending && actor !== record.submittedBy && ["owner", "reviewer"].includes(role);
    return html`<div class="enterprise-form">
        ${team && html`<p class="hint">审核人自报姓名 · ${team.reviewRequired ? "模拟发布前需通过审核" : "审核可选"}</p>
            <p role="status">审核状态 · ${REVIEW[record?.state] || "尚未提交"}</p>
            ${snapshot.brandIssues.length ? html`<ul class="facts">${snapshot.brandIssues.map(issue => html`<li>${issue}</li>`)}</ul>` : html`<p>品牌词检查通过</p>`}
            <label class="form-row">操作人<select class="select" value=${actor} disabled=${busy} onChange=${e => setActor(e.currentTarget.value)}>
                <option value="">选择团队成员</option>
                ${team.members.map(member => html`<option value=${member.name}>${member.name}（${ROLES[member.role]}）</option>`)}
            </select></label>
            <label class="form-row">审核意见（驳回必填）<textarea class="input" rows="2" value=${comment} maxLength="1000" disabled=${busy} onInput=${e => setComment(e.currentTarget.value)} /></label>
            <div class="actions-row">
                <button class="btn ghost" disabled=${busy || pending || !["owner", "editor"].includes(role)} onClick=${() => review("submit")}>提交审核</button>
                <button class="btn ghost" disabled=${busy || !canApprove || snapshot.brandIssues.length > 0} onClick=${() => review("approve")}>批准</button>
                <button class="btn ghost" disabled=${busy || !canApprove || !comment.trim()} onClick=${() => review("reject")}>驳回</button>
            </div>
            <${ReviewHistory} events=${record?.events || []} />`}
        ${snapshot && !team && html`<p class="hint">在「团队与品牌」设置成员和审核规则。</p>`}
        ${snapshot?.blockers.map(blocker => html`<p class="hint">${blocker}</p>`)}
        <div class="actions-row">
            ${sandbox ? html`<span role="status">本机模拟 · ${SANDBOX[sandbox.state]}</span>
                ${sandbox.state !== "published" && html`<button class="btn ghost" disabled=${busy} onClick=${check}>刷新模拟状态</button>`}` :
                html`<button class="btn ghost" disabled=${busy || !snapshot || !!snapshot.blockers.length || pkg.localChecks !== "pass" || pkg.publicationEligibility === "blocked"} onClick=${simulate}>模拟发布（本机）</button>`}
            <button class="btn ghost" disabled=${busy} onClick=${() => run(load)}>刷新审核状态</button>
        </div>
        ${error && html`<p role="alert">${error}</p>`}
    </div>`;
}

export function PackageReview({project, pkg, teamVersion}) {
    const [open, setOpen] = useState(false);
    return html`<details class="group" aria-label="发布包审核" onToggle=${e => setOpen(e.currentTarget.open)}>
        <summary>审核与模拟发布</summary>
        ${open && html`<${ReviewEditor} key=${teamVersion} project=${project} pkg=${pkg} />`}
    </details>`;
}
