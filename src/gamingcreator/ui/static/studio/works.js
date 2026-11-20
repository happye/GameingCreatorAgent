import {h} from "../vendor/preact.module.js";
import {useEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import {api, requestId, forgetIntent} from "./api.js";
import {EditWorkspace} from "./edit.js";
const html = htm.bind(h);
const selectionKey = project => `studio-work-v1:${project}`;
const saved = (key) => { try { return localStorage.getItem(key) || ""; } catch { return ""; } };
const last = (project, workId) => {
    try { return JSON.parse(localStorage.getItem("studio-last-job-v1") || "{}")[workId ? `${project}:work:${workId}` : project]; }
    catch { return null; }
};
function remember(project, work, job) {
    localStorage.setItem(selectionKey(project), work?.workId || "");
    if (!job) return;
    const all = JSON.parse(localStorage.getItem("studio-last-job-v1") || "{}");
    all[work ? `${project}:work:${work.workId}` : project] = job;
    localStorage.setItem("studio-last-job-v1", JSON.stringify(all));
}

// Selection is only a hint until the server has verified its project membership.
export function WorksWorkspace({project, open, leave, isOpenConsumed = () => false, onOpenConsumed = () => {}, onCatalogChanged = () => {}, ...props}) {
    const [items, setItems] = useState([]), [current, setCurrent] = useState(null);
    const [ready, setReady] = useState(false), [busy, setBusy] = useState(false), [message, setMessage] = useState("");
    const [target, setTarget] = useState(null);
    const [name, setName] = useState(""), [naming, setNaming] = useState(false), [nameMessage, setNameMessage] = useState("");
    const generation = useRef(0);
    const nameScope = useRef(null); nameScope.current = `${project}:${current?.workId || ""}`;
    const externalOpen = useRef(open); externalOpen.current = open;
    useEffect(() => {
        setName(""); setNameMessage(""); setNaming(false);
    }, [project, open]);
    const verify = async (workId) => {
        if (!workId) return null;
        const {work} = await api(`/api/creation/works/${workId}`, {projectId: project});
        if (work.workId !== workId || work.projectId !== project) throw new Error("无法恢复所选作品，请重试。");
        return work;
    };
    const activate = (work, job = null) => {
        remember(project, work, job);
        setCurrent(work); setTarget(job); setReady(true); setMessage("");
        setName(work?.workName || ""); setNameMessage(""); setNaming(false);
        onOpenConsumed(open);
    };
    useEffect(() => {
        const mine = ++generation.current;
        setReady(false);
        void (async () => {
            let catalogMessage = "";
            const {works} = await api("/api/creation/works", {projectId: project}).catch(error => {
                catalogMessage = `作品列表暂不可读；当前作品仍会单独核对：${error.message}`;
                return {works: []};
            });
            let workId = saved(selectionKey(project));
            const job = (open && !isOpenConsumed(open) ? open : null) || last(project, workId);
            if (job) {
                const scope = await api("/api/creation/work-scope", {projectId: project, jobId: job.id});
                workId = scope.workId || "";
            }
            const work = await verify(workId);
            if (mine !== generation.current) return;
            setItems(work && !works.some(item => item.workId === work.workId) ? [work, ...works] : works);
            activate(work, job); if (catalogMessage) setMessage(catalogMessage);
        })().catch(error => { if (mine === generation.current) setMessage(error.message); });
        return () => { generation.current++; };
    }, [project, open]);
    const choose = (workId) => leave(() => {
        const mine = ++generation.current;
        setReady(false); setBusy(true);
        void (async () => {
            const work = await verify(workId), job = last(project, workId);
            if (job) {
                const scope = await api("/api/creation/work-scope", {projectId: project, jobId: job.id});
                if ((scope.workId || "") !== workId) throw new Error("最近方案不属于所选作品，无法自动恢复。");
            }
            if (mine === generation.current) activate(work, job);
        })()
            .catch(error => { if (mine === generation.current) setMessage(error.message); })
            .finally(() => { if (mine === generation.current) setBusy(false); });
    });
    const create = () => leave(() => {
        const mine = ++generation.current;
        setBusy(true);
        void (async () => {
            const id = requestId("work", {projectId: project}, project);
            await api("/api/creation/works", {}, {body: {projectId: project, requestId: id}});
            const work = await verify(id);
            if (mine !== generation.current) return;
            activate(work); setItems(old => old.some(item => item.workId === id) ? old : [...old, work]);
            forgetIntent("work", project);
            onCatalogChanged();
        })().catch(error => { if (mine === generation.current) setMessage(`${error.message}。可重试新建以恢复本次作品。`); })
            .finally(() => { if (mine === generation.current) setBusy(false); });
    });
    const rename = async () => {
        const workId = current?.workId, trimmed = name.trim();
        if (!workId || !ready || busy || naming) return;
        if (!trimmed || [...trimmed].length > 100 || /[\u0000-\u001f\u007f-\u009f]/u.test(name)) {
            setNameMessage("请输入 1–100 个字符的作品名称，且不能包含控制字符。"); return;
        }
        const mine = generation.current, scope = nameScope.current;
        const active = () => mine === generation.current && scope === nameScope.current && externalOpen.current === open;
        setNaming(true); setNameMessage("");
        try {
            const {work} = await api("/api/creation/work-name", {}, {body: {projectId: project, workId, name: trimmed}});
            if (!active()) return;
            if (work?.workId !== workId || work?.projectId !== project || work?.workName !== trimmed) {
                throw new Error("作品名称保存结果无法核对，请重试。");
            }
            setCurrent(old => ({...old, workName: work.workName}));
            setItems(old => old.map(item => item.workId === workId ? {...item, workName: work.workName} : item));
            setName(work.workName); setNameMessage("作品名称已保存。");
            onCatalogChanged();
        } catch (error) { if (active()) setNameMessage(error.message); }
        finally { if (active()) setNaming(false); }
    };
    const controls = html`<div class="field"><label class="form-row">当前作品
        <select class="select" aria-label="当前作品" disabled=${busy} value=${current?.workId || ""} onChange=${e => { if (!choose(e.currentTarget.value)) e.currentTarget.value = current?.workId || ""; }}>
            <option value="">原有草稿</option>${items.map(work => html`<option value=${work.workId}>${work.workName || `作品 ${new Date(work.createdAt).toLocaleString("zh-CN", {hour12: false})}`}</option>`)}
        </select></label><button class="btn ghost" disabled=${busy} onClick=${create}>新建作品</button>
        ${current ? html`<label class="form-row">作品名称
            <input class="input" aria-label="作品名称" value=${name} disabled=${!ready || naming || busy}
                onInput=${e => setName(e.currentTarget.value)} />
            </label><button type="button" class="btn ghost" disabled=${!ready || naming || busy} onClick=${rename}>${naming ? "正在保存名称…" : "保存作品名称"}</button>
            ${nameMessage ? html`<p role="status">${nameMessage}</p>` : null}` : null}
        ${message ? html`<p role="status">${message}</p>` : null}</div>`;
    const mine = generation.current;
    const guarded = Object.fromEntries(Object.entries(props).map(([key, value]) => [key,
        typeof value === "function" ? (...args) => { if (mine === generation.current && externalOpen.current === open) return value(...args); } : value]));
    return ready ? html`<${EditWorkspace} key=${`${project}:${current?.workId || "legacy"}`} ...${guarded} onPublish=${jobId => guarded.onPublish?.(jobId, current?.workId || null)} project=${project} workId=${current?.workId || null} open=${target} workControls=${controls} />`
        : html`<div class="panel-body">${controls}<p role="status">${message || "正在恢复作品…"}</p></div>`;
}
