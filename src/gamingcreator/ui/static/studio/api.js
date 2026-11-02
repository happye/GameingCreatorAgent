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

export const projects = (signal) => api("/api/projects", {}, {signal});
export const runs = (project, signal) => api("/api/runs", {project}, {signal});
export const inspect = (project, run, signal) => api("/api/inspect", {project, run, query: "", mode: "hybrid", top: 10, detailProfile: "v1"}, {signal});
export const creationJobs = (projectId, signal) => api("/api/creation/jobs", {projectId}, {signal});
