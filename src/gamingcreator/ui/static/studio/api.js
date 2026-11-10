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

// One request id per intent: resubmitting the same payload reuses it, so the server never
// creates a duplicate job for a double click or a retry.
const intents = new Map();
const persisted = (kind, scope) => kind === "package" && !!scope;
const intentSlot = (kind, scope) => `${kind}:${scope}`;
const storageKey = (slot) => `studio-intent-v1:${slot}`;
function intent(kind, scope) {
    const slot = intentSlot(kind, scope);
    if (persisted(kind, scope)) {
        try {
            const raw = sessionStorage.getItem(storageKey(slot));
            const value = raw === null ? null : JSON.parse(raw);
            if (value && (typeof value.key !== "string" || !/^[0-9a-f]{32}$/.test(value.id) || (value.jobId !== undefined && !/^[0-9a-f]{32}$/.test(value.jobId)))) throw new Error("invalid intent");
            return value;
        } catch { throw new ApiError("无法读取平台包请求身份，请恢复本页会话存储后重试；尚未发送新请求。", "intent.storage"); }
    }
    return intents.get(slot);
}
function saveIntent(kind, scope, value) {
    const slot = intentSlot(kind, scope);
    if (persisted(kind, scope)) {
        try { sessionStorage.setItem(storageKey(slot), JSON.stringify(value)); }
        catch { throw new ApiError("无法保存平台包请求身份，请允许本页会话存储后重试。", "intent.storage"); }
    }
    intents.set(slot, value);
}
export function requestId(kind, payload, scope = "") {
    const key = JSON.stringify(payload), known = intent(kind, scope);
    if (known?.key === key) return known.id;
    if (known && persisted(kind, scope)) throw new ApiError("平台包请求身份与内容不一致，不能创建第二个请求。", "intent.conflict");
    const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), (v) => v.toString(16).padStart(2, "0")).join("");
    saveIntent(kind, scope, {key, id});
    return id;
}
export function forgetIntent(kind, scope = "") {
    const slot = intentSlot(kind, scope);
    if (persisted(kind, scope)) {
        try { sessionStorage.removeItem(storageKey(slot)); }
        catch { throw new ApiError("无法更新平台包请求身份，请恢复会话存储后重试。", "intent.storage"); }
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
export const job = (id, signal) => api(`/api/creation/jobs/${encodeURIComponent(id)}`, {}, {signal});

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
export const creationJobs = (projectId, signal) => api("/api/creation/jobs", {projectId}, {signal});
