"use strict";

(() => {
    let draft = structuredClone(initialDraft), revision = 0;
    const byId = id => document.getElementById(id);
    const fail = message => { throw new Error(message); };
    const notify = message => { byId("status").textContent = message; };
    const edited = () => { revision += 1; notify("登记已修改，请保存草稿或导出计划。"); };
    const keys = (value, expected) => value && typeof value === "object" && !Array.isArray(value)
        && JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort());
    const boundedText = value => typeof value === "string" && value.length <= 16384 && value.isWellFormed();
    function strictJson(text) {
        const value = JSON.parse(text);
        const tokens = text.match(/"(?:\\.|[^"\\])*"|[{}\[\],:]|true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g);
        let cursor = 0;
        function walk(depth) {
            if (depth > 64) fail("草稿嵌套过深。");
            const token = tokens[cursor++];
            if (token === "{") {
                const names = new Set();
                while (tokens[cursor] !== "}") {
                    const name = JSON.parse(tokens[cursor++]);
                    if (names.has(name)) fail("草稿包含重复字段。");
                    names.add(name); cursor++; walk(depth + 1);
                    if (tokens[cursor] === ",") cursor++;
                }
                cursor++;
            } else if (token === "[") {
                while (tokens[cursor] !== "]") { walk(depth + 1); if (tokens[cursor] === ",") cursor++; }
                cursor++;
            } else if (token.startsWith('"')) {
                if (!JSON.parse(token).isWellFormed()) fail("文字不是有效Unicode。");
            } else if (!["true", "false", "null"].includes(token) && !Number.isFinite(JSON.parse(token))) fail("草稿包含无效数字。");
        }
        walk(0); return value;
    }
    function validate(value) {
        if (!keys(value, ["schemaVersion", "datasetId", "sources", "queries"])
            || value.schemaVersion !== "benchmark-plan-draft-v1" || !boundedText(value.datasetId)
            || !Array.isArray(value.sources) || value.sources.length > 200
            || !Array.isArray(value.queries) || value.queries.length > 1000) fail("登记草稿格式无效，已有人工参考请用原片标注继续。");
        for (const source of value.sources) {
            if (!keys(source, ["id", "path", "recordingGroup", "partition", "modelResultsViewed"])
                || ![source.id, source.path, source.partition].every(boundedText)
                || (source.recordingGroup !== null && !boundedText(source.recordingGroup))
                || !["", "development", "test"].includes(source.partition)
                || (source.modelResultsViewed !== null && typeof source.modelResultsViewed !== "boolean")) fail("录像登记字段无效。");
        }
        for (const query of value.queries) {
            if (!keys(query, ["id", "text", "kind", "sourceId", "family"])
                || ![query.id, query.text, query.kind, query.sourceId, query.family].every(boundedText)
                || !["", "main", "sparse", "negative"].includes(query.kind)) fail("查询登记字段无效。");
        }
        if (new TextEncoder().encode(JSON.stringify(value) + "\n").length > 1048576) fail("登记资料超过1MiB。");
        return value;
    }
    function makePlan() {
        validate(draft);
        if (!draft.datasetId.trim() || !draft.sources.length || !draft.queries.length) fail("请填写计划名称，至少登记一段录像和一个查询。");
        const sourceIds = new Set(), queryIds = new Set();
        for (const source of draft.sources) {
            if (!source.id.trim() || sourceIds.has(source.id)
                || !/^(?:[A-Za-z]:[\\/]|\\\\[^\\/]+[\\/][^\\/]+(?:[\\/]|$))/.test(source.path)
                || !source.partition || source.modelResultsViewed === null) fail("请填写不同录像编号、完整本地路径，并明确选择用途和是否看过结果。");
            sourceIds.add(source.id);
        }
        for (const query of draft.queries) {
            if (!query.id.trim() || queryIds.has(query.id) || !query.text.trim() || !query.family.trim()
                || !query.kind || !sourceIds.has(query.sourceId)) fail("请填写不同查询编号、需求和归组，并选择类别及对应录像。");
            queryIds.add(query.id);
        }
        return { schemaVersion: "benchmark-plan-v1", datasetId: draft.datasetId, labelVersion: null,
            humanReferences: { confirmed: false, annotators: [], reviewed: false },
            sources: draft.sources.map(row => ({ ...row, recordingGroup: row.recordingGroup?.trim() || null })),
            queries: draft.queries.map(row => ({ ...row, referenceEvents: [] })) };
    }
    function add(parent, tag, text) {
        const node = document.createElement(tag); if (text !== undefined) node.textContent = text;
        parent.append(node); return node;
    }
    function field(parent, label, row, key, placeholder = "") {
        const node = add(add(parent, "label", label), "input"); node.type = "text";
        node.dataset.field = key; node.value = row[key] || ""; node.placeholder = placeholder;
        node.addEventListener("input", () => {
            const previous = row[key]; row[key] = key === "recordingGroup" ? node.value.trim() || null : node.value;
            if (key === "id" && draft.sources.includes(row)) {
                if (previous) draft.queries.forEach(query => { if (query.sourceId === previous) query.sourceId = row.id; });
                updateSourceOptions();
            }
            edited();
        });
        return node;
    }
    function choice(parent, label, row, key, options, decode = value => value) {
        const node = add(add(parent, "label", label), "select"); node.dataset.field = key;
        for (const [value, title] of options) { const option = add(node, "option", title); option.value = value; }
        node.value = key === "modelResultsViewed" ? row[key] === null ? "" : row[key] ? "yes" : "no" : row[key];
        node.addEventListener("change", () => { row[key] = decode(node.value); edited(); });
        return node;
    }
    function updateSourceOptions() {
        byId("query-list").querySelectorAll("select[data-field='sourceId']").forEach((select, index) => {
            select.replaceChildren(); const empty = add(select, "option", "请选择对应录像"); empty.value = "";
            for (const source of draft.sources) { const option = add(select, "option", source.id || "编号未填写"); option.value = source.id; }
            select.value = draft.queries[index].sourceId;
        });
    }
    function render() {
        byId("dataset-id").value = draft.datasetId;
        const sources = byId("source-list"), queries = byId("query-list"); sources.replaceChildren(); queries.replaceChildren();
        for (const row of draft.sources) {
            const card = add(sources, "article"); card.className = "slot source-row";
            const fields = add(card, "div"); fields.className = "fields";
            field(fields, "录像编号", row, "id"); field(fields, "完整本地路径", row, "path", "G:\\录像\\原片.mp4");
            field(fields, "来自哪次录制（未知可留空）", row, "recordingGroup");
            choice(fields, "用途", row, "partition", [["", "请选择用途"], ["development", "开发／调试"], ["test", "独立测试"]]);
            choice(fields, "是否看过模型结果", row, "modelResultsViewed", [["", "尚未确认"], ["no", "没有看过"], ["yes", "已经看过"]], value => value === "" ? null : value === "yes");
            const remove = add(card, "button", "删除这段录像"); remove.type = "button";
            remove.addEventListener("click", () => {
                if (row.id && draft.queries.some(query => query.sourceId === row.id)) return notify("这段录像还有关联查询，请先删除或调整对应查询。");
                draft.sources = draft.sources.filter(source => source !== row); edited(); render();
            });
        }
        for (const row of draft.queries) {
            const card = add(queries, "article"); card.className = "slot query-row";
            const fields = add(card, "div"); fields.className = "fields";
            field(fields, "查询编号", row, "id"); field(fields, "想找什么", row, "text", "例如：寻找闪避后反击的片段");
            field(fields, "同一需求／改写归组", row, "family");
            choice(fields, "类别", row, "kind", [["", "请选择类别"], ["main", "主查询（至少十个参考）"], ["sparse", "少例（1–9个参考）"], ["negative", "负例（无可用参考）"]]);
            choice(fields, "对应录像", row, "sourceId", []);
            const remove = add(card, "button", "删除这个查询"); remove.type = "button";
            remove.addEventListener("click", () => { draft.queries = draft.queries.filter(query => query !== row); edited(); render(); });
        }
        updateSourceOptions();
    }
    function nextId(rows, prefix) { let number = 1; while (rows.some(row => row.id === `${prefix}-${number}`)) number++; return `${prefix}-${number}`; }
    function download(value, name) {
        const text = JSON.stringify(value) + "\n";
        if (new TextEncoder().encode(text).length > 1048576) fail("下载资料超过1MiB。");
        const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
        const link = add(document.body, "a"); link.href = url; link.download = name; link.click(); link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    byId("dataset-id").addEventListener("input", () => { draft.datasetId = byId("dataset-id").value; edited(); });
    byId("add-source").addEventListener("click", () => {
        if (draft.sources.length >= 200) return notify("最多登记200段录像。");
        draft.sources.push({ id: nextId(draft.sources, "source"), path: "", recordingGroup: null, partition: "", modelResultsViewed: null }); edited(); render();
    });
    byId("add-query").addEventListener("click", () => {
        if (draft.queries.length >= 1000) return notify("最多登记1000个查询。");
        draft.queries.push({ id: nextId(draft.queries, "query"), text: "", kind: "", sourceId: "", family: "" }); edited(); render();
    });
    byId("save-draft").addEventListener("click", () => {
        try { download(validate(draft), "验收登记草稿.json"); notify("登记草稿已下载；未知项保留，尚未核对录像或冻结。"); } catch (error) { notify(error.message); }
    });
    byId("export-plan").addEventListener("click", () => {
        try { download(makePlan(), "事前验收计划.json"); notify("待核对计划已下载；接下来原片标注和冻结，验收尚未通过。"); } catch (error) { notify(error.message); }
    });
    byId("load-draft").addEventListener("change", async () => {
        const file = byId("load-draft").files[0], expectedRevision = revision;
        if (!file) return;
        try {
            if (file.size > 1048576) fail("草稿超过1MiB。");
            const proposed = validate(strictJson((await file.text()).replace(/^\uFEFF/, "")));
            if (revision !== expectedRevision || byId("load-draft").files[0] !== file) return notify("载入期间登记已变化，保留当前编辑；请重新选择草稿。");
            draft = proposed; revision += 1; render(); notify("登记草稿已载入，未知项仍待填写。");
        } catch (error) { notify(`${error.message} 当前登记保持。`); }
    });
    render();
})();
