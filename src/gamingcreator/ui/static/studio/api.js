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
export function requestId(kind, payload) {
    const key = JSON.stringify(payload), known = intents.get(kind);
    if (known?.key === key) return known.id;
    const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), (v) => v.toString(16).padStart(2, "0")).join("");
    intents.set(kind, {key, id});
    return id;
}
export const forgetIntent = (kind) => intents.delete(kind);

export async function submit(kind, payload) {
    const path = {plan: "/api/creation/plans", revision: "/api/creation/revisions", render: "/api/creation/renders", narration: "/api/creation/narrations", publication: "/api/creation/publications", package: "/api/creation/packages"}[kind];
    return api(path, {}, {body: {...payload, requestId: requestId(kind, payload)}});
}
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
