import {useEffect, useState} from "../vendor/hooks.module.js";

export const OUTCOME_LABELS = {ctrBps: "点击率（CTR）", retention3sBps: "3 秒留存", completionBps: "完播率"};
const keyFor = scope => `studio-structure-feedback-v1:${scope}`;

function read(key) {
    try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; }
}

export function writeStructureFeedback(scope, value) {
    const key = keyFor(scope);
    try {
        if (value === null) localStorage.removeItem(key);
        else localStorage.setItem(key, JSON.stringify(value));
        return true;
    } catch { return false; }
}

export function matchesStructureFeedback(value, contentType, platform) {
    const expected = value?.source?.outcome?.platform;
    return value?.contentType === contentType && (!expected || expected === platform);
}

export function useStructureFeedback(scope) {
    const key = keyFor(scope);
    const [saved, setSaved] = useState(() => ({key, value: read(key)}));
    useEffect(() => {
        const sync = () => setSaved({key, value: read(key)});
        const changed = (event) => { if (event.key === key || event.key === null) sync(); };
        sync();
        window.addEventListener("storage", changed);
        return () => window.removeEventListener("storage", changed);
    }, [key]);
    return {saved: saved.key === key ? saved.value : null, read: () => read(key), write: (value) => {
        if (!writeStructureFeedback(scope, value)) return false;
        setSaved({key, value}); return true;
    }};
}
