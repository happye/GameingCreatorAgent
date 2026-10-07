"use strict";

(() => {
    const context = source.context;
    let record = structuredClone(source.template);
    let queryIndex = 0;
    let revision = 0;
    const byId = (id) => document.getElementById(id);
    const video = byId("source-video");
    const canonical = (value) => {
        if (Array.isArray(value)) return value.map(canonical);
        if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
        return value;
    };
    const equal = (left, right) => JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
    function fixed(plan) {
        const result = structuredClone(plan);
        delete result.labelVersion; delete result.humanReferences;
        result.queries.forEach((query) => { delete query.referenceEvents; });
        return result;
    }
    function notify(message) { byId("status").textContent = message; }
    function edited() { revision += 1; notify("标注已修改，请下载保存。"); }
    function text(value) { return typeof value === "string" && value.trim() && value.length <= 16384; }
    function selectedMedia(index = queryIndex) { return context.media.find((row) => row.id === record.plan.queries[index].sourceId); }
    function seconds(microseconds) { return (microseconds / 1000000).toFixed(6); }
    function timeInput(value) {
        const parts = /^(\d+)(?:\.(\d{1,6}))?$/.exec(value.trim());
        if (!parts) throw new Error("源时间请填写非负秒数，最多六位小数。");
        const valueUs = Number(parts[1]) * 1000000 + Number((parts[2] || "").padEnd(6, "0"));
        if (!Number.isSafeInteger(valueUs)) throw new Error("源时间超出允许范围。");
        return valueUs;
    }
    function validate(value) {
        if (!value || typeof value !== "object" || Array.isArray(value)
            || !equal(Object.keys(value).sort(), ["contextSha256", "plan", "schemaVersion"])
            || value.schemaVersion !== source.template.schemaVersion || value.contextSha256 !== source.template.contextSha256
            || !equal(fixed(value.plan), fixed(context.plan))) throw new Error("记录不属于这份原片、事前查询和来源声明。");
        if (value.plan.labelVersion !== null && !text(value.plan.labelVersion)) throw new Error("人工参考版本无效。");
        const human = value.plan.humanReferences;
        if (!human || !equal(Object.keys(human).sort(), ["annotators", "confirmed", "reviewed"])
            || typeof human.confirmed !== "boolean" || typeof human.reviewed !== "boolean"
            || !Array.isArray(human.annotators) || human.annotators.some((name) => !text(name))
            || (human.confirmed && (!human.annotators.length || value.plan.labelVersion === null))) throw new Error("确认人工参考前请填写人和参考版本。");
        for (const query of value.plan.queries) {
            if (!Array.isArray(query.referenceEvents) || query.referenceEvents.length > 10000
                || (query.kind === "negative" && query.referenceEvents.length)) throw new Error("查询参考事件无效。");
            const media = context.media.find((row) => row.id === query.sourceId);
            const identifiers = new Set();
            for (const event of query.referenceEvents) {
                if (!event || !equal(Object.keys(event).sort(), ["humanEventId", "independenceGroup", "reason", "usableRanges"])
                    || !text(event.humanEventId) || !text(event.independenceGroup) || !text(event.reason)
                    || identifiers.has(event.humanEventId) || !Array.isArray(event.usableRanges) || !event.usableRanges.length) throw new Error("请填写不同的真实事件名称、动作归组、可用区间和理由。");
                identifiers.add(event.humanEventId);
                const intervals = new Set();
                for (const interval of event.usableRanges) {
                    const key = `${interval.startUs}:${interval.endUs}`;
                    if (!equal(Object.keys(interval).sort(), ["endUs", "startUs"])
                        || !Number.isSafeInteger(interval.startUs) || !Number.isSafeInteger(interval.endUs)
                        || interval.startUs < 0 || interval.startUs >= interval.endUs || interval.endUs > media.durationUs
                        || intervals.has(key)) throw new Error("可用区间须位于原录像内，不能重复或倒置。");
                    intervals.add(key);
                }
            }
        }
        if (new TextEncoder().encode(JSON.stringify(value.plan)).length > 1048576) throw new Error("参考计划超过1MiB。");
        return value;
    }
    function readMetadata() {
        record.plan.labelVersion = byId("label-version").value.trim() || null;
        record.plan.humanReferences = { confirmed: byId("confirmed").checked, reviewed: byId("reviewed").checked,
            annotators: byId("annotators").value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean) };
    }
    function fillMetadata() {
        byId("label-version").value = record.plan.labelVersion || "";
        byId("annotators").value = record.plan.humanReferences.annotators.join("\n");
        byId("confirmed").checked = record.plan.humanReferences.confirmed;
        byId("reviewed").checked = record.plan.humanReferences.reviewed;
    }
    function renderReferences() {
        const query = record.plan.queries[queryIndex];
        byId("reference-summary").textContent = `已登记 ${query.referenceEvents.length} 个真实事件 · ${query.kind === "main" ? "主查询须有至少十个独立可用参考" : query.kind === "negative" ? "负例不登记可用事件" : "少例单独评估"}`;
        const list = byId("reference-list"); list.replaceChildren();
        for (const event of query.referenceEvents) {
            const card = document.createElement("article"); card.className = "slot";
            const title = document.createElement("h3"); title.textContent = event.humanEventId;
            const ranges = document.createElement("p"); ranges.textContent = `${event.usableRanges.map((row) => `${seconds(row.startUs)}–${seconds(row.endUs)} 秒`).join("；")} · 动作归组：${event.independenceGroup}`;
            const reason = document.createElement("p"); reason.textContent = event.reason;
            const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "删除这个参考";
            remove.addEventListener("click", () => { query.referenceEvents = query.referenceEvents.filter((row) => row !== event); edited(); renderReferences(); });
            card.append(title, ranges, reason, remove); list.append(card);
        }
    }
    function switchQuery() {
        queryIndex = Number(byId("query-select").value); revision += 1;
        video.pause();
        const query = record.plan.queries[queryIndex]; const media = selectedMedia();
        video.src = media.videoUrl;
        byId("query-info").textContent = `${query.text} · ${media.path.split(/[\\/]/).pop()} · ${seconds(media.durationUs)} 秒`;
        byId("clock-state").textContent = media.automaticTimeCapture ? "可用播放器位置标记；保存前请核对完整动作与区间。" : "此录像起始时间特殊，请手填规范源时间；不自动采用播放器位置。";
        byId("capture-start").disabled = byId("capture-end").disabled = !media.automaticTimeCapture;
        byId("add-reference").disabled = query.kind === "negative";
        for (const id of ["start-seconds", "end-seconds", "event-id", "event-group", "reason"]) byId(id).value = "";
        renderReferences();
    }
    for (const [index, query] of record.plan.queries.entries()) {
        const option = document.createElement("option"); option.value = String(index); option.textContent = query.text; byId("query-select").append(option);
    }
    byId("query-select").addEventListener("change", switchQuery);
    for (const id of ["label-version", "annotators", "confirmed", "reviewed"]) byId(id).addEventListener("input", () => { readMetadata(); edited(); });
    for (const id of ["start-seconds", "end-seconds", "event-id", "event-group", "reason"]) byId(id).addEventListener("input", () => { revision += 1; });
    for (const [button, field] of [["capture-start", "start-seconds"], ["capture-end", "end-seconds"]]) byId(button).addEventListener("click", () => {
        if (!selectedMedia().automaticTimeCapture || video.readyState < 1 || !Number.isFinite(video.currentTime)) return notify("等待原片载入，或手填源时间。");
        const position = Math.round(video.currentTime * 1000000);
        if (position < 0 || position > selectedMedia().durationUs) return notify("播放器位置超出原源时间，请手填核对。");
        byId(field).value = seconds(position); revision += 1;
    });
    byId("add-reference").addEventListener("click", () => {
        try {
            readMetadata();
            const proposed = structuredClone(record); const query = proposed.plan.queries[queryIndex];
            const eventId = byId("event-id").value.trim(); const group = byId("event-group").value.trim(); const reason = byId("reason").value.trim();
            const interval = { startUs: timeInput(byId("start-seconds").value), endUs: timeInput(byId("end-seconds").value) };
            const existing = query.referenceEvents.find((row) => row.humanEventId === eventId);
            if (existing) {
                if (existing.independenceGroup !== group) throw new Error("同一真实事件请保持原动作归组。");
                existing.usableRanges.push(interval); existing.reason = reason;
            } else query.referenceEvents.push({ humanEventId: eventId, independenceGroup: group, usableRanges: [interval], reason });
            record = validate(proposed); edited(); renderReferences();
        } catch (error) { notify(error.message); }
    });
    byId("download-record").addEventListener("click", () => {
        try {
            readMetadata(); validate(record);
            const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2) + "\n"], { type: "application/json" }));
            const link = document.createElement("a"); link.href = url; link.download = "原片标注记录.json"; document.body.append(link); link.click(); link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000); notify("已下载标注记录；计划仍待核对和冻结，验收尚未通过。");
        } catch (error) { notify(error.message); }
    });
    byId("load-record").addEventListener("change", async () => {
        const file = byId("load-record").files[0]; const expectedRevision = revision;
        if (!file) return;
        try {
            if (file.size > 1049600) throw new Error("标注记录过大。");
            const proposed = validate(JSON.parse((await file.text()).replace(/^\uFEFF/, "")));
            if (revision !== expectedRevision || byId("load-record").files[0] !== file) return notify("载入期间标注已变化，保留当前内容；请重新选择记录。");
            record = proposed; revision += 1; fillMetadata(); renderReferences(); notify("已有标注已载入；请继续核对原片并下载保存。");
        } catch (error) { notify(`${error.message} 当前标注保持。`); }
    });
    video.addEventListener("error", () => notify("原片无法播放；请检查原文件和浏览器编码支持，已填标注保留。"));
    fillMetadata(); switchQuery();
})();
