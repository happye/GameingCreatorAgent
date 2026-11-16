// 只按素材身份记住是否用代理预览，不保存证据、地址或其他身份。
(function (global) {
    const KEY = "gamingcreator:preview-preference-v1";

    function load() {
        try {
            const raw = JSON.parse(global.localStorage.getItem(KEY) || "{}");
            if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
            const out = {};
            for (const [mediaId, value] of Object.entries(raw)) {
                if (typeof mediaId === "string" && mediaId && (value === true || value === false)) {
                    out[mediaId] = value;
                }
            }
            return out;
        } catch {
            return {};
        }
    }

    function get(mediaId) {
        if (!mediaId || typeof mediaId !== "string") return null;
        const all = load();
        return Object.prototype.hasOwnProperty.call(all, mediaId) ? all[mediaId] : null;
    }

    function set(mediaId, preferProxy) {
        if (!mediaId || typeof mediaId !== "string") return;
        const all = load();
        all[mediaId] = Boolean(preferProxy);
        try {
            global.localStorage.setItem(KEY, JSON.stringify(all));
        } catch {
            /* 浏览器可能禁止本地存储，本次会话仍可用内存中的选择。 */
        }
    }

    global.PreviewPreference = {key: KEY, load, get, set};
})(typeof globalThis !== "undefined" ? globalThis : window);
