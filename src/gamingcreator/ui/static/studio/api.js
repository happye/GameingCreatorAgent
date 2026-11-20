// Thin client over the existing local HTTP API. The studio adds no endpoints of its own.

export class ApiError extends Error {
    constructor(message, code = "", status = 0) { super(message); this.code = code; this.status = status; }
}

export async function api(path, params = {}, {signal, body} = {}) {
    const url = new URL(path, location.origin);
    for (const [name, value] of Object.entries(params)) if (value !== undefined && value !== null) url.searchParams.set(name, String(value));
    const response = await fetch(url, {
        signal, cache: "no-store", credentials: "same-origin",
        ...(body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)}),
    });
    let data = null;
    try { data = await response.json(); } catch { /* Non-JSON error bodies fall through to the status text. */ }
    if (!response.ok) {
        const error = data?.error;
        throw new ApiError((typeof error === "string" ? error : error?.message) || data?.message || `请求失败（${response.status}）`, data?.code || error?.code || "", response.status);
    }
    return data;
}

// Only same-origin media/evidence URLs produced by the server are ever put into <video>/<img>.
export function sameOrigin(value, pathname) {
    try {
        const url = new URL(value, location.origin);
        return url.origin === location.origin && url.pathname === pathname ? url.pathname + url.search : null;
    } catch { return null; }
}

// 只用服务端已经核对过的代理地址替换原片预览；没有有效代理就播原片，不会自己拼路径。
export function choosePreview(videoUrl, offeredProxyUrl, preferProxy = true) {
    const original = sameOrigin(videoUrl, "/api/media");
    const proxy = offeredProxyUrl ? sameOrigin(offeredProxyUrl, "/api/media") : null;
    if (!preferProxy || !original || !proxy) return {url: original, source: original ? "original" : null};
    try {
        const wanted = new URL(proxy, location.origin);
        const base = new URL(original, location.origin);
        if (wanted.searchParams.get("proxy") !== "1"
            || wanted.searchParams.get("project") !== base.searchParams.get("project")
            || wanted.searchParams.get("run") !== base.searchParams.get("run")) {
            return {url: original, source: "original"};
        }
    } catch {
        return {url: original, source: "original"};
    }
    return {url: proxy, source: "proxy"};
}

// One request id per intent: resubmitting the same payload reuses it, so the server never
// creates a duplicate job for a double click or a retry.
const intents = new Map();
const persisted = (kind, scope) => ["package", "work"].includes(kind) && !!scope;
const intentSlot = (kind, scope) => `${kind}:${scope}`;
const storageKey = (slot) => `studio-intent-v1:${slot}`;
const intentStore = (kind) => kind === "work" ? localStorage : sessionStorage;
function intentError(kind, action) {
    const label = kind === "work" ? "作品" : "平台包";
    const store = kind === "work" ? "本地存储" : "会话存储";
    if (action === "read") return new ApiError(`无法读取${label}请求身份，请恢复本页${store}后重试；尚未发送新请求。`, "intent.storage");
    if (action === "save") return new ApiError(`无法保存${label}请求身份，请允许本页${store}后重试。`, "intent.storage");
    if (action === "update") return new ApiError(`无法更新${label}请求身份，请恢复${store}后重试。`, "intent.storage");
    return new ApiError(`${label}请求身份与内容不一致，不能创建第二个请求。`, "intent.conflict");
}
function intent(kind, scope) {
    const slot = intentSlot(kind, scope);
    if (persisted(kind, scope)) {
        try {
            const raw = intentStore(kind).getItem(storageKey(slot));
            const value = raw === null ? null : JSON.parse(raw);
            if (value && (typeof value.key !== "string" || !/^[0-9a-f]{32}$/.test(value.id) || (value.jobId !== undefined && !/^[0-9a-f]{32}$/.test(value.jobId)))) throw new Error("invalid intent");
            return value;
        } catch (error) { if (error instanceof ApiError) throw error; throw intentError(kind, "read"); }
    }
    return intents.get(slot);
}
function saveIntent(kind, scope, value) {
    const slot = intentSlot(kind, scope);
    if (persisted(kind, scope)) {
        try { intentStore(kind).setItem(storageKey(slot), JSON.stringify(value)); }
        catch { throw intentError(kind, "save"); }
    }
    intents.set(slot, value);
}
export function requestId(kind, payload, scope = "") {
    const key = JSON.stringify(payload), known = intent(kind, scope);
    if (known?.key === key) return known.id;
    if (known && persisted(kind, scope)) throw intentError(kind, "conflict");
    const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), (v) => v.toString(16).padStart(2, "0")).join("");
    saveIntent(kind, scope, {key, id});
    return id;
}
export function forgetIntent(kind, scope = "") {
    const slot = intentSlot(kind, scope);
    if (persisted(kind, scope)) {
        try { intentStore(kind).removeItem(storageKey(slot)); }
        catch { throw intentError(kind, "update"); }
    }
    intents.delete(slot);
}
export function retryPackageIntent(scope, attempts) {
    const known = intent("package", scope);
    // An old failed row says nothing about a newer POST still waiting for registration.
    // Only the task acknowledged for this exact intent can authorize a fresh request id.
    if (known?.jobId && attempts.some((row) => row.jobId === known.jobId && ["failed", "interrupted"].includes(row.status))) forgetIntent("package", scope);
}

export async function submit(kind, payload, scope = "") {
    const path = {plan: "/api/creation/plans", revision: "/api/creation/revisions", render: "/api/creation/renders", narration: "/api/creation/narrations", publication: "/api/creation/publications", package: "/api/creation/packages"}[kind];
    const id = requestId(kind, payload, scope);
    const accepted = await api(path, {}, {body: {...payload, requestId: id}});
    if (persisted(kind, scope)) {
        const current = intent(kind, scope);
        if (current?.id === id && current.key === JSON.stringify(payload)) saveIntent(kind, scope, {...current, jobId: accepted.jobId});
    }
    return accepted;
}
// Job states the backend writes (creation_jobs.py); unknown values fall back to the raw text.
export const JOB_STATUS = {pending: "排队中", running: "处理中", completed: "完成", failed: "失败", interrupted: "已中断", cancelled: "已取消"};
export const jobStatus = (status) => JOB_STATUS[status] || status;
// Clipboard with a manual-copy fallback message (shared by narration, knowledge, publish).
export const copyText = async (value, onOk, onFail) => {
    try {
        await navigator.clipboard.writeText(value);
        onOk();
    } catch {
        onFail();
    }
};
export const job = (id, signal) => api(`/api/creation/jobs/${encodeURIComponent(id)}`, {}, {signal});
export function studioJobLink(project, jobId) {
    const url = new URL("/studio", location.origin);
    url.search = new URLSearchParams({project, job: jobId});
    return url.href;
}

// Poll a creation job until it settles; the server recovers crashed jobs as "interrupted".
export async function settle(id, signal, onUpdate = () => {}) {
    for (;;) {
        const state = await job(id, signal);
        onUpdate(state);
        if (!["pending", "running"].includes(state.status)) return state;
        await new Promise((resolve, reject) => {
            const timer = setTimeout(resolve, 1000);
            signal?.addEventListener("abort", () => { clearTimeout(timer); reject(new DOMException("aborted", "AbortError")); }, {once: true});
        });
    }
}

export const mediaUrl = (project, run) => `/api/media?${new URLSearchParams({project, run})}`;
export const evidenceUrl = (project, run, id) => `/api/evidence?${new URLSearchParams({project, run, id})}`;

export const projects = (signal) => api("/api/projects", {}, {signal});
export const runs = (project, signal) => api("/api/runs", {project}, {signal});
export const inspect = (project, run, signal) => api("/api/inspect", {project, run, query: "", mode: "hybrid", top: 10, detailProfile: "v1"}, {signal});
export const creationJobs = (projectId, signal, workId = "") => api("/api/creation/jobs", {projectId, workId: workId || undefined}, {signal});
export const creationWorks = (projectId, signal) => api("/api/creation/works", {projectId}, {signal});

// Monthly AI budget (user authorization 2026-11-11): one line shown wherever AI is called.
export const budgetText = (b) => b ? `本月 AI 已用约 ¥${Number(b.monthSpentCny).toFixed(2)} / ¥${b.monthCapCny}，这条视频 ¥${Number(b.videoSpentCny).toFixed(2)} / ¥${b.videoCapCny}；本次最多 ¥${Number(b.ceilingCny).toFixed(2)}。` : "";
