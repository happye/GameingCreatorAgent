// Local game knowledge panel for Studio sound inspector. Uses existing /api/knowledge only.
import {h} from "../vendor/preact.module.js";
import {useEffect, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import {api, copyText} from "./api.js";

const html = htm.bind(h);
const SOURCE_KINDS = [
    {value: "official", label: "官方说明"},
    {value: "wiki", label: "Wiki/攻略站"},
    {value: "user", label: "用户资料"},
];
const SOURCE_LABEL = Object.fromEntries(SOURCE_KINDS.map((row) => [row.value, row.label]));
const LIMITS = {game: 100, title: 100, text: 20000, sourceLabel: 200};
const FILE_MAX = 10 * 1024 * 1024;
const FILE_EXT = new Set(["txt", "md", "html", "htm", "png", "jpg", "jpeg", "bmp", "pdf"]);
const codepoints = (value) => [...String(value ?? "")].length;
const preview = (value, n = 300) => {
    const chars = [...String(value ?? "")];
    return chars.length <= n ? chars.join("") : chars.slice(0, n).join("") + "…";
};
const sourceLine = (entry) => {
    const kind = SOURCE_LABEL[entry?.source?.kind] || entry?.source?.kind || "";
    const label = entry?.source?.label || "";
    return entry?.citation || `（来源：${kind}·${label}）`;
};
const toBase64 = async (file) => {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
    return btoa(binary);
};

function KnowledgeComparison({value, onOpen}) {
    const [showEqual, setShowEqual] = useState(false);
    const labels = {equal: "未变", removed: "删除", added: "新增"};
    return html`<section class="field" aria-label="知识版本差异" style=${{minWidth: 0, overflowWrap: "anywhere"}}>
        <div class="k">知识文本版本对比</div>
        <p class="hint">只对照已登记原文，不自动判断玩法变化；方向由你选择。</p>
        <div>${[["before", "旧版"], ["after", "新版"]].map(([key, label]) => html`<div style=${{marginBottom: "12px"}}>
            <strong>${label}：${value[key].title}</strong>
            <p class="hint">${value[key].citation}</p>
            <details><summary>条目 ID 与登记时间</summary>
                <code style=${{overflowWrap: "anywhere"}}>${value[key].entryId}</code>
                <p class="hint">${value[key].createdAt}</p>
            </details>
            <button type="button" class="btn ghost" onClick=${() => onOpen(value[key])}>查看${label}原文</button>
        </div>`)}</div>
        ${value.sameText && html`<p class="note">正文无差异；两侧出处和日期仍可分别核对。</p>`}
        <label class="check"><input type="checkbox" checked=${showEqual} onChange=${(e) => setShowEqual(e.currentTarget.checked)} />显示未变化行</label>
        <div style=${{maxHeight: "320px", overflow: "auto"}} aria-label="知识逐行差异">
            ${value.rows.map((row, index) => row.kind === "equal" && !showEqual ? null : html`<div key=${index} data-change=${row.kind}>
                <span class="hint" style=${{color: row.kind === "added" ? "#65d4a4" : row.kind === "removed" ? "#ef7b7b" : "inherit"}}>${labels[row.kind]}</span>
                <pre style=${{whiteSpace: "pre-wrap", overflowWrap: "anywhere", margin: "0 0 8px"}}>${row.text}</pre>
            </div>`)}
        </div>
    </section>`;
}

export function KnowledgePanel({project, game}) {
    const gameName = String(game || "").trim();
    const [query, setQuery] = useState("");
    const [entries, setEntries] = useState(null);
    const [searchNote, setSearchNote] = useState("");
    const [searching, setSearching] = useState(false);
    const [selected, setSelected] = useState(null);
    const [history, setHistory] = useState(null);
    const [historyNote, setHistoryNote] = useState("");
    const [historyBusy, setHistoryBusy] = useState(false);
    const [historyOwner, setHistoryOwner] = useState("");
    const [compareBefore, setCompareBefore] = useState(null);
    const [compareAfter, setCompareAfter] = useState(null);
    const [comparison, setComparison] = useState(null);
    const [comparing, setComparing] = useState(false);
    const [compareNote, setCompareNote] = useState("");
    const [mode, setMode] = useState("text"); // text | file
    const [title, setTitle] = useState("");
    const [text, setText] = useState("");
    const [sourceKind, setSourceKind] = useState("official");
    const [sourceLabel, setSourceLabel] = useState("");
    const [file, setFile] = useState(null);
    const [fileInputKey, setFileInputKey] = useState(0);
    const [replaces, setReplaces] = useState("");
    const [editingCurrent, setEditingCurrent] = useState(false);
    const [saving, setSaving] = useState(false);
    const [saveNote, setSaveNote] = useState("");
    const [formError, setFormError] = useState("");
    const [copyNote, setCopyNote] = useState("");
    // Directory import (existing POST /api/knowledge-import)
    const [importDir, setImportDir] = useState("");
    const [importKind, setImportKind] = useState("official");
    const [importLabel, setImportLabel] = useState("");
    const [includeMedia, setIncludeMedia] = useState(false);
    const [importing, setImporting] = useState(false);
    const [importNote, setImportNote] = useState("");
    const [importSummary, setImportSummary] = useState(null);
    const [importItems, setImportItems] = useState(null);
    const [importFilter, setImportFilter] = useState("all");
    const [importError, setImportError] = useState("");
    const searchEpoch = useRef(0);
    const saveEpoch = useRef(0);
    const historyEpoch = useRef(0);
    const importEpoch = useRef(0);
    const compareEpoch = useRef(0);
    const panelEpoch = useRef(0);
    const mounted = useRef(true);
    const fileInputRef = useRef(null);

    useEffect(() => () => {
        mounted.current = false;
        panelEpoch.current += 1;
        searchEpoch.current += 1;
        saveEpoch.current += 1;
        historyEpoch.current += 1;
        importEpoch.current += 1;
    }, []);

    useEffect(() => {
        panelEpoch.current += 1;
        searchEpoch.current += 1;
        saveEpoch.current += 1;
        historyEpoch.current += 1;
        importEpoch.current += 1;
        setEntries(null);
        setSearchNote("");
        setSearching(false);
        setSelected(null);
        setHistory(null);
        setHistoryNote("");
        setHistoryBusy(false);
        setHistoryOwner("");
        compareEpoch.current += 1;
        setCompareBefore(null);
        setCompareAfter(null);
        setComparison(null);
        setComparing(false);
        setCompareNote("");
        setTitle("");
        setText("");
        setFile(null);
        setFileInputKey((k) => k + 1);
        setReplaces("");
        setEditingCurrent(false);
        setSaveNote("");
        setFormError("");
        setCopyNote("");
        setQuery("");
        setImportNote("");
        setImportSummary(null);
        setImportItems(null);
        setImportError("");
        setImporting(false);
    }, [project, gameName]);

    const invalidateSearch = () => {
        searchEpoch.current += 1;
        setSearching(false);
    };

    const invalidateHistory = () => {
        historyEpoch.current += 1;
        setHistoryBusy(false);
        setHistory(null);
        setHistoryNote("");
        setHistoryOwner("");
    };

    const openDetail = (entry) => {
        // R03: opening another full text must invalidate in-flight history.
        invalidateHistory();
        setSelected(entry);
        setCopyNote("");
    };

    const runSearch = async (rawQuery) => {
        if (!gameName) {
            setSearchNote("请先在已加载方案中填写游戏名（当前方案无游戏名，无法查询）。");
            setEntries(null);
            return;
        }
        const q = String(rawQuery ?? query);
        const token = ++searchEpoch.current;
        const panel = panelEpoch.current;
        invalidateHistory();
        setSearching(true);
        setSearchNote("正在查找…");
        setEntries(null);
        setSelected(null);
        try {
            const data = await api("/api/knowledge", {game: gameName, q});
            if (searchEpoch.current !== token || panelEpoch.current !== panel || !mounted.current) return;
            const list = data.entries || [];
            setEntries(list);
            setSearchNote(list.length ? `找到 ${list.length} 条` : "没有匹配的知识条目");
        } catch (error) {
            if (searchEpoch.current !== token || panelEpoch.current !== panel || !mounted.current) return;
            setEntries(null);
            setSearchNote(`查找失败：${error.message}（查询仍为「${q}」，可再试）`);
        } finally {
            if (searchEpoch.current === token && panelEpoch.current === panel && mounted.current) setSearching(false);
        }
    };

    const onSearchSubmit = (event) => {
        event.preventDefault();
        if (searching) return;
        void runSearch(query);
    };

    const validateForm = () => {
        if (!gameName) return "请先在已加载方案中填写游戏名。";
        if (codepoints(gameName) > LIMITS.game) return `游戏名超过 ${LIMITS.game} 字。`;
        const t = title.trim();
        if (!t) return "请填写标题。";
        if (codepoints(t) > LIMITS.title) return `标题超过 ${LIMITS.title} 字。`;
        if (!SOURCE_KINDS.some((row) => row.value === sourceKind)) return "来源类型无效。";
        const label = sourceLabel.trim();
        if (!label) return "请填写来源说明。";
        if (codepoints(label) > LIMITS.sourceLabel) return `来源说明超过 ${LIMITS.sourceLabel} 字。`;
        if (mode === "text") {
            if (!text.trim()) return "请填写正文。";
            if (codepoints(text) > LIMITS.text) return `正文超过 ${LIMITS.text} 字。`;
        } else {
            if (!file) return "请选择本地文件。";
            if (file.size <= 0) return "文件不能为空（0 字节）。";
            if (file.size > FILE_MAX) return "文件不能超过 10 MiB。";
            const ext = (file.name.split(".").pop() || "").toLowerCase();
            if (!FILE_EXT.has(ext)) return "仅支持 txt/md/html/htm/png/jpg/jpeg/bmp/pdf。";
        }
        return "";
    };

    const clearNativeFile = () => {
        setFile(null);
        setFileInputKey((k) => k + 1);
        if (fileInputRef.current) fileInputRef.current.value = "";
    };

    const save = async (event) => {
        event.preventDefault();
        const err = validateForm();
        if (err) {
            setFormError(err);
            return;
        }
        setFormError("");
        const token = ++saveEpoch.current;
        const panel = panelEpoch.current;
        const gameAtStart = gameName;
        const keptFile = file;
        setSaving(true);
        setSaveNote("正在保存…");
        try {
            const body = {
                game: gameAtStart,
                title: title.trim(),
                sourceKind,
                sourceLabel: sourceLabel.trim(),
            };
            if (replaces) body.replaces = replaces;
            if (mode === "text") {
                body.text = text;
            } else {
                body.fileName = keptFile.name;
                body.dataBase64 = await toBase64(keptFile);
            }
            if (saveEpoch.current !== token || panelEpoch.current !== panel || !mounted.current) return;
            const saved = await api("/api/knowledge", {}, {body});
            if (saveEpoch.current !== token || panelEpoch.current !== panel || !mounted.current) return;
            if (gameName !== gameAtStart) {
                setSaveNote(`已保存到「${gameAtStart}」：${saved.title}（${saved.entryId}）。当前游戏已切换，未改动当前表单。`);
                return;
            }
            setSaveNote(`已保存「${saved.title}」（${saved.entryId}）`);
            setTitle("");
            setText("");
            // R02: clear file state and native input so the same file can be re-selected.
            clearNativeFile();
            setReplaces("");
            setEditingCurrent(false);
            setSelected(saved);
            setHistory(null);
            setHistoryOwner("");
            if (!searching) void runSearch(saved.title);
        } catch (error) {
            if (saveEpoch.current !== token || panelEpoch.current !== panel || !mounted.current) return;
            // R05: keep form fields (including file selection) after real reject.
            setSaveNote(`保存失败：${error.message}`);
            if (mode === "file" && keptFile) setFile(keptFile);
        } finally {
            if (saveEpoch.current === token && panelEpoch.current === panel && mounted.current) setSaving(false);
        }
    };

    const loadHistory = async (entryId) => {
        const token = ++historyEpoch.current;
        const panel = panelEpoch.current;
        const owner = entryId;
        setHistoryBusy(true);
        setHistoryNote("正在读取历史…");
        setHistory(null);
        setHistoryOwner(owner);
        try {
            const data = await api("/api/knowledge", {entryId});
            if (historyEpoch.current !== token || panelEpoch.current !== panel || !mounted.current) return;
            // R03: only apply when this history still belongs to the requested entry.
            const rows = data.history || [];
            setHistory(rows);
            setHistoryNote(rows.length ? `共 ${rows.length} 个版本（首项为当前查询版本）` : "没有历史版本");
            // Do not overwrite a different full-text selection with late history.
            setSelected((prev) => {
                if (prev && prev.entryId !== owner && !rows.some((r) => r.entryId === prev.entryId)) {
                    return prev;
                }
                return rows[0] || prev;
            });
        } catch (error) {
            if (historyEpoch.current !== token || panelEpoch.current !== panel || !mounted.current) return;
            setHistory(null);
            setHistoryNote(`读取历史失败：${error.message}`);
        } finally {
            if (historyEpoch.current === token && panelEpoch.current === panel && mounted.current) setHistoryBusy(false);
        }
    };

    // R01: both edit entries + internal guard while saving.
    const beginEdit = (entry) => {
        if (saving) return;
        setEditingCurrent(true);
        setReplaces(entry.entryId);
        setTitle(entry.title || "");
        setText(entry.text || "");
        setSourceKind(entry.source?.kind || "official");
        setSourceLabel(entry.source?.label || "");
        setMode("text");
        clearNativeFile();
        setFormError("");
        setSaveNote(`正在修改「${entry.title}」，保存将生成新版本。`);
    };

    const cancelEdit = () => {
        if (saving) return;
        setEditingCurrent(false);
        setReplaces("");
        setTitle("");
        setText("");
        clearNativeFile();
        setFormError("");
        setSaveNote("");
    };

    const runImport = async (event) => {
        event.preventDefault();
        if (importing) return;
        if (!gameName) {
            setImportError("请先在已加载方案中填写游戏名。");
            return;
        }
        const directory = importDir.trim();
        if (!directory) {
            setImportError("请填写本机目录路径。");
            return;
        }
        if (!SOURCE_KINDS.some((row) => row.value === importKind)) {
            setImportError("来源类型无效。");
            return;
        }
        const label = importLabel.trim();
        if (!label) {
            setImportError("请填写来源说明。");
            return;
        }
        setImportError("");
        const token = ++importEpoch.current;
        const panel = panelEpoch.current;
        const gameAtStart = gameName;
        setImporting(true);
        setImportNote("本机导入中");
        try {
            const body = {
                game: gameAtStart,
                directory,
                sourceKind: importKind,
                sourceLabel: label,
                includeMedia: !!includeMedia,
            };
            const data = await api("/api/knowledge-import", {}, {body});
            if (importEpoch.current !== token || panelEpoch.current !== panel || !mounted.current) return;
            if (gameName !== gameAtStart) {
                setImportNote(`目录导入已在「${gameAtStart}」完成，当前游戏已切换，未改动当前列表。`);
                return;
            }
            if (data?.schemaVersion !== "knowledge-directory-import-v1") {
                setImportSummary(null);
                setImportItems(null);
                setImportNote(`导入失败：无法识别响应 schema（${data?.schemaVersion || "无"}）`);
                return;
            }
            setImportSummary(data.summary || null);
            setImportItems(Array.isArray(data.items) ? data.items : []);
            const s = data.summary || {};
            setImportNote(`导入完成：导入 ${s.imported ?? "?"} / 跳过 ${s.skipped ?? "?"} / 失败 ${s.failed ?? "?"} / 候选 ${s.considered ?? "?"}`);
        } catch (error) {
            if (importEpoch.current !== token || panelEpoch.current !== panel || !mounted.current) return;
            setImportSummary(null);
            setImportItems(null);
            setImportNote(`导入失败：${error.message}`);
        } finally {
            if (importEpoch.current === token && panelEpoch.current === panel && mounted.current) setImporting(false);
        }
    };

    const exportFailures = () => {
        const failed = (importItems || []).filter((row) => row.status === "failed");
        const lines = failed.map((row) => `${row.file}\t${row.reason || ""}`);
        const blob = new Blob([lines.join("\n")], {type: "text/plain;charset=utf-8"});
        const url = URL.createObjectURL(blob);
        try {
            const anchor = document.createElement("a");
            anchor.href = url;
            anchor.download = "knowledge-import-failures.txt";
            anchor.rel = "noopener";
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
        } finally {
            URL.revokeObjectURL(url);
        }
    };

    const viewing = selected;
    const chooseComparison = (entry, side) => {
        compareEpoch.current += 1;
        setComparing(false);
        setComparison(null);
        setCompareNote("");
        if (side === "before") setCompareBefore(entry);
        else setCompareAfter(entry);
    };
    const compareButtons = (entry) => html`<button type="button" class="btn ghost" onClick=${() => chooseComparison(entry, "before")}>设为旧版</button>
        <button type="button" class="btn ghost" onClick=${() => chooseComparison(entry, "after")}>设为新版</button>`;
    const runComparison = async () => {
        if (!compareBefore || !compareAfter || comparing) return;
        const token = ++compareEpoch.current;
        const panel = panelEpoch.current;
        setComparing(true);
        setComparison(null);
        setCompareNote("正在对比…");
        try {
            const data = await api("/api/knowledge", {before: compareBefore.entryId, after: compareAfter.entryId});
            if (compareEpoch.current !== token || panelEpoch.current !== panel || !mounted.current) return;
            if (data.schemaVersion !== "game-knowledge-comparison-v1") throw new Error("无法识别对比响应版本。");
            setComparison(data);
            setCompareNote("");
        } catch (error) {
            if (compareEpoch.current === token && panelEpoch.current === panel && mounted.current) setCompareNote(`对比失败：${error.message}`);
        } finally {
            if (compareEpoch.current === token && panelEpoch.current === panel && mounted.current) setComparing(false);
        }
    };
    const canEditSelected = !!(viewing && entries?.some((row) => row.entryId === viewing.entryId));
    const filteredItems = !importItems ? null : importFilter === "all"
        ? importItems
        : importItems.filter((row) => row.status === importFilter);

    return html`<details class="group knowledge-panel">
        <summary>游戏知识（本机）</summary>
        <p class="note">当前游戏：${gameName || "（未设置，请先生成/选中带游戏名的方案）"}。知识只存本机；保存后可用「起草旁白稿」引用。展开本身不请求知识。</p>
        <form class="knowledge-search" onSubmit=${onSearchSubmit}>
            <label class="form-row">关键词<input class="input" value=${query} aria-label="知识关键词"
                onInput=${(e) => { invalidateSearch(); setQuery(e.currentTarget.value); }} /></label>
            <button type="button" class="btn ghost" disabled=${searching} onClick=${() => { if (!searching) void runSearch(query); }}>${searching ? "正在查找…" : "查找"}</button>
        </form>
        <p class="note" role="status" aria-label="知识查找状态">${searchNote}</p>
        ${entries && entries.length > 0 && html`<ul class="facts knowledge-results" aria-label="知识搜索结果">
            ${entries.map((entry) => html`<li key=${entry.entryId} style=${{overflowWrap: "anywhere"}}>
                <strong>${entry.title}</strong>
                <div class="hint">${preview(entry.text, 300)}</div>
                <div class="hint">${sourceLine(entry)}</div>
                <div class="actions-row">
                    <button type="button" class="btn ghost" onClick=${() => openDetail(entry)}>查看全文</button>
                    <button type="button" class="btn ghost" disabled=${historyBusy} onClick=${() => void loadHistory(entry.entryId)}>历史</button>
                    ${compareButtons(entry)}
                    <button type="button" class="btn ghost" disabled=${saving} onClick=${() => beginEdit(entry)}>修改并保存新版本</button>
                </div>
            </li>`)}
        </ul>`}

        ${viewing && html`<div class="rules-result knowledge-detail" aria-label="知识全文详情" style=${{overflowWrap: "anywhere", whiteSpace: "pre-wrap"}}>
            <div class="field"><div class="k">标题</div><div class="v">${viewing.title}</div></div>
            <div class="field"><div class="k">正文</div><div class="v">${viewing.text}</div></div>
            <div class="field"><div class="k">来源</div><div class="v">${sourceLine(viewing)}</div></div>
            <div class="field"><div class="k">创建时间</div><div class="v">${viewing.createdAt || ""}</div></div>
            <div class="field"><div class="k">条目 ID</div><div class="v" style=${{overflowWrap: "anywhere"}}>${viewing.entryId}</div></div>
            <div class="actions-row">
                <button type="button" class="btn ghost" onClick=${() => void copyText(viewing.text, () => setCopyNote("已复制正文"), () => setCopyNote("无法自动复制正文，请手动选择"))}>复制正文</button>
                <button type="button" class="btn ghost" onClick=${() => void copyText(viewing.entryId, () => setCopyNote("已复制条目 ID"), () => setCopyNote("无法自动复制条目 ID，请手动选择"))}>复制条目 ID</button>
                ${canEditSelected ? html`<button type="button" class="btn ghost" disabled=${saving} onClick=${() => beginEdit(viewing)}>修改并保存新版本</button>` : null}
            </div>
            <p class="note" role="status">${copyNote}</p>
        </div>`}

        ${historyNote && html`<p class="note" role="status" aria-label="知识历史状态">${historyNote}${historyOwner ? ` · 条目 ${historyOwner}` : ""}</p>`}
        ${history && history.length > 0 && html`<ul class="facts knowledge-history" aria-label="知识历史版本">
            ${history.map((entry, index) => html`<li key=${entry.entryId}>
                <button type="button" class="btn ghost" onClick=${() => openDetail(entry)}>查看版本 ${index + 1}</button>
                <span class="hint"> ${entry.title} · ${entry.entryId}</span>
                ${compareButtons(entry)}
            </li>`)}
        </ul>`}

        <div class="field" aria-label="知识对比选择" style=${{overflowWrap: "anywhere"}}>
            <p class="hint">旧版：${compareBefore ? `${compareBefore.title} · ${compareBefore.entryId}` : "未选择"}</p>
            <p class="hint">新版：${compareAfter ? `${compareAfter.title} · ${compareAfter.entryId}` : "未选择"}</p>
            <button type="button" class="btn ghost" disabled=${!compareBefore || !compareAfter || comparing} onClick=${runComparison}>${comparing ? "正在对比…" : "对比所选版本"}</button>
            <p class="note" role="status" aria-label="知识对比状态">${compareNote}</p>
        </div>
        ${comparison && html`<${KnowledgeComparison} value=${comparison} onOpen=${openDetail} />`}

        <form class="knowledge-form" onSubmit=${save}>
            <div class="k">${editingCurrent ? "修改并保存新版本" : "新增知识"}</div>
            <div class="actions-row" role="group" aria-label="知识输入模式">
                <label class="check"><input type="radio" name="knowledge-mode" checked=${mode === "text"} disabled=${saving}
                    onChange=${() => { setMode("text"); clearNativeFile(); setFormError(""); }} /> 文本</label>
                <label class="check"><input type="radio" name="knowledge-mode" checked=${mode === "file"} disabled=${saving || editingCurrent}
                    onChange=${() => { setMode("file"); setText(""); setFormError(""); }} /> 本地文件</label>
            </div>
            <label class="form-row">标题<input class="input" value=${title} disabled=${saving} aria-label="知识标题"
                onInput=${(e) => setTitle(e.currentTarget.value)} /></label>
            ${mode === "text"
                ? html`<label class="form-row">正文<textarea class="input" rows="5" value=${text} disabled=${saving} aria-label="知识正文"
                    onInput=${(e) => setText(e.currentTarget.value)}></textarea></label>`
                : html`<label class="form-row">本地文件<input key=${fileInputKey} ref=${fileInputRef} type="file" disabled=${saving} aria-label="知识本地文件"
                    accept=".txt,.md,.html,.htm,.png,.jpg,.jpeg,.bmp,.pdf"
                    onChange=${(e) => { setFile(e.currentTarget.files?.[0] || null); setFormError(""); }} /></label>
                    ${file && html`<p class="note">将上传：${file.name}（${file.size} 字节）</p>`}`}
            <label class="form-row">来源类型<select class="select" value=${sourceKind} disabled=${saving} aria-label="知识来源类型"
                onChange=${(e) => setSourceKind(e.currentTarget.value)}>
                ${SOURCE_KINDS.map((row) => html`<option value=${row.value}>${row.label}</option>`)}
            </select></label>
            <label class="form-row">来源说明<input class="input" value=${sourceLabel} disabled=${saving} aria-label="知识来源说明"
                onInput=${(e) => setSourceLabel(e.currentTarget.value)} /></label>
            ${formError && html`<p class="note warn" role="alert">${formError}</p>`}
            <div class="actions-row">
                <button type="submit" class="btn" disabled=${saving}>${saving ? "正在保存…" : editingCurrent ? "保存新版本" : "保存知识"}</button>
                ${editingCurrent && html`<button type="button" class="btn ghost" disabled=${saving} onClick=${cancelEdit}>取消修改</button>`}
            </div>
            <p class="note" role="status" aria-label="知识保存状态">${saveNote}</p>
        </form>

        <form class="knowledge-import" onSubmit=${runImport} aria-label="知识目录导入">
            <div class="k">目录批量导入</div>
            <p class="note">使用现有本机导入接口；只读目录直接子文件，不做递归。展开/填写本身不请求。</p>
            <label class="form-row">本机目录路径<input class="input" value=${importDir} disabled=${importing} aria-label="知识导入目录"
                onInput=${(e) => setImportDir(e.currentTarget.value)} /></label>
            <label class="form-row">来源类型<select class="select" value=${importKind} disabled=${importing} aria-label="知识导入来源类型"
                onChange=${(e) => setImportKind(e.currentTarget.value)}>
                ${SOURCE_KINDS.map((row) => html`<option value=${row.value}>${row.label}</option>`)}
            </select></label>
            <label class="form-row">来源说明<input class="input" value=${importLabel} disabled=${importing} aria-label="知识导入来源说明"
                onInput=${(e) => setImportLabel(e.currentTarget.value)} /></label>
            <label class="check"><input type="checkbox" checked=${includeMedia} disabled=${importing} aria-label="包含图片与PDF"
                onChange=${(e) => setIncludeMedia(e.currentTarget.checked)} /> 包含图片与PDF（includeMedia）</label>
            ${importError && html`<p class="note warn" role="alert">${importError}</p>`}
            <div class="actions-row">
                <button type="submit" class="btn" disabled=${importing}>${importing ? "本机导入中" : "导入目录"}</button>
                ${(importItems || []).some((row) => row.status === "failed") && html`<button type="button" class="btn ghost" disabled=${importing} onClick=${exportFailures}>导出失败清单</button>`}
            </div>
            <p class="note" role="status" aria-label="知识导入状态">${importNote}</p>
            ${importSummary && html`<p class="hint" aria-label="知识导入汇总">汇总：导入 ${importSummary.imported} / 跳过 ${importSummary.skipped} / 失败 ${importSummary.failed} / 候选 ${importSummary.considered}</p>`}
            ${importItems && html`<div class="actions-row" role="group" aria-label="导入结果筛选">
                <button type="button" class="btn ghost" onClick=${() => setImportFilter("all")}>全部</button>
                <button type="button" class="btn ghost" onClick=${() => setImportFilter("imported")}>导入</button>
                <button type="button" class="btn ghost" onClick=${() => setImportFilter("skipped")}>跳过</button>
                <button type="button" class="btn ghost" onClick=${() => setImportFilter("failed")}>失败</button>
            </div>
            <ul class="facts" aria-label="知识导入逐文件结果">
                ${filteredItems.map((row, index) => html`<li key=${`${row.file}-${index}`} style=${{overflowWrap: "anywhere"}}>
                    <strong>${row.file}</strong> · ${row.status}
                    ${row.title ? html`<div class="hint">标题：${row.title}</div>` : null}
                    ${row.entryId ? html`<div class="hint">ID：${row.entryId}</div>` : null}
                    ${row.reason ? html`<div class="hint">原因：${row.reason}</div>` : null}
                    ${row.status === "imported" && row.entryId ? html`<button type="button" class="btn ghost" onClick=${() => void (async () => {
                        try {
                            const data = await api("/api/knowledge", {entryId: row.entryId});
                            const entry = (data.history && data.history[0]) || data.entry || null;
                            if (entry) openDetail(entry);
                        } catch (error) {
                            setImportNote(`打开全文失败：${error.message}`);
                        }
                    })()}>打开全文</button>` : null}
                </li>`)}
            </ul>`}
        </form>
    </details>`;
}
