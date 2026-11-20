// Project-scoped word-highlight preview switch; never auto-picks a result hash.
import {h} from "../vendor/preact.module.js";
import htm from "../vendor/htm.module.js";
const html = htm.bind(h);

const drafts = new Map();

export function wordHighlightDraft(project) {
    return drafts.get(project) || {enabled: false, runId: "", resultHash: ""};
}

export function setWordHighlightDraft(project, patch) {
    const current = wordHighlightDraft(project);
    const next = {
        enabled: patch.enabled ?? current.enabled,
        runId: patch.runId ?? current.runId,
        resultHash: patch.resultHash ?? current.resultHash,
    };
    drafts.set(project, next);
    return next;
}

export function asrWordsPayload(draft) {
    if (!draft?.enabled) return {wordHighlights: false};
    if (!draft.runId || !draft.resultHash) return {wordHighlights: true};
    return {wordHighlights: true, asrWords: {runId: draft.runId, resultHash: draft.resultHash}};
}

export function WordHighlightSwitch({project, draft, onChange, disabled}) {
    const current = draft || wordHighlightDraft(project);
    const change = (patch) => onChange(setWordHighlightDraft(project, patch));
    return html`<div>
        <label class="form-row"><input type="checkbox" aria-label="逐词高亮预览" disabled=${!!disabled} checked=${!!current.enabled} onChange=${(event) => change({enabled: event.currentTarget.checked})} />逐词高亮预览</label>
        ${current.enabled ? html`
            <label class="form-row">识别任务<input class="input" aria-label="词级结果任务" value=${current.runId} onInput=${(event) => change({runId: event.currentTarget.value.trim()})} /></label>
            <label class="form-row">已核对结果<input class="input" aria-label="词级结果校对码" value=${current.resultHash} onInput=${(event) => change({resultHash: event.currentTarget.value.trim()})} /></label>
        ` : null}
    </div>`;
}
