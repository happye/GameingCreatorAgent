// Browser-local unfinished narration text drafts (not Agent memory / not fees).
export const DRAFT_SCHEMA = "studio-narration-draft-v1";

export function draftKey(projectId, baseJobId, planId, attachedAssetJobId) {
    const identity = [
        String(projectId ?? ""),
        String(baseJobId ?? ""),
        String(planId ?? ""),
        String(attachedAssetJobId ?? ""),
    ];
    return `${DRAFT_SCHEMA}:${encodeURIComponent(JSON.stringify(identity))}`;
}

export function readDraft(storage, key) {
    try {
        const raw = storage.getItem(key);
        if (raw == null) return {ok: true, draft: null};
        let parsed;
        try {
            parsed = JSON.parse(raw);
        } catch {
            return {ok: false, reason: "损坏的本机草稿 JSON，可复制当前输入或导出 TXT；未改动当前输入。", draft: null, raw};
        }
        if (!parsed || parsed.schemaVersion !== DRAFT_SCHEMA) {
            return {ok: false, reason: "未知本机草稿格式，可复制当前输入或导出 TXT；未改动当前输入。", draft: null, raw};
        }
        if (typeof parsed.text !== "string" || typeof parsed.voiceId !== "string" || typeof parsed.updatedAt !== "string") {
            return {ok: false, reason: "本机草稿字段无效，可复制当前输入或导出 TXT；未改动当前输入。", draft: null, raw};
        }
        // Never treat cached fees/receipts/media even if present.
        return {
            ok: true,
            draft: {
                schemaVersion: DRAFT_SCHEMA,
                text: parsed.text,
                voiceId: parsed.voiceId,
                updatedAt: parsed.updatedAt,
            },
        };
    } catch {
        return {ok: false, reason: "无法读取本机草稿存储，可复制当前输入或导出 TXT。", draft: null};
    }
}

export function writeDraft(storage, key, text, voiceId) {
    const envelope = {
        schemaVersion: DRAFT_SCHEMA,
        text: String(text ?? ""),
        voiceId: String(voiceId ?? ""),
        updatedAt: new Date().toISOString(),
    };
    try {
        storage.setItem(key, JSON.stringify(envelope));
        return {ok: true, draft: envelope};
    } catch {
        return {ok: false, reason: "无法写入本机草稿（可能超出配额），可复制当前输入或导出 TXT；保留当前输入与原存储。"};
    }
}

export function clearDraft(storage, key) {
    try {
        storage.removeItem(key);
        return {ok: true};
    } catch {
        return {ok: false, reason: "无法清除本机草稿存储。"};
    }
}