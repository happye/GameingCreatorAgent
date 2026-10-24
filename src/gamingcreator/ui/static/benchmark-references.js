"use strict";

(() => {
    const context = source.context;
    let record = structuredClone(source.template);
    let queryIndex = 0;
    let revision = 0;
    let loadGeneration = 0;
    let validationToken = 0;
    let activeGeneration = -1;
    // Bounded re-validation of the visible axis after the player was busy or moved during a
    // probe. Interaction or the probe target itself is never treated as axis evidence.
    const AXIS_RETRY_DELAYS_MS = [1500, 2500];
    const byId = (id) => document.getElementById(id);
    const video = byId("source-video");
    const REASONS = {
        seek_unavailable: "浏览器没有给出可定位的原片时间范围",
        seek_incomplete: "浏览器的原片定位没有完成",
        duration_unavailable: "浏览器没有读到可用的原片时长",
        duration_mismatch: "浏览器读到的原片时长与保存的原片时长不一致",
        duration_changed: "浏览器读到的原片时长发生了意外变化",
        axis_unavailable: "浏览器没有返回可核对的播放位置",
        axis_unstable: "浏览器播放位置在核对过程中发生了变化",
        axis_mismatch: "浏览器播放起点与保存的原片起点不一致",
        media_unavailable: "浏览器不能读取这段原片",
        source_mismatch: "浏览器实际载入的原片与当前查询的原片不同",
        observation_invalid: "浏览器返回的原片时间信息不完整",
        clock_unavailable: "这段原片没有可核对的浏览器时钟",
    };
    const EMPTY_SESSION = () => ({ generation: loadGeneration, url: null, headerDuration: null, status: "pending", clock: null, reason: null, axisAttempts: 0, axisReason: null, seeked: false });
    let session = EMPTY_SESSION();
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
    function unavailableText(state) {
        const reason = state.status === "pending"
            ? (state.reason === "axis_unconfirmed"
                ? "原片播放起点尚未确认，正在等待播放器空闲后重新核对"
                : "正在核对原片浏览器时钟")
            : REASONS[state.reason] || "浏览器时间无法核对为规范源时间";
        return `${reason}；请手填规范源时间并打开本机原片核对。`;
    }
    function resetSession() {
        loadGeneration += 1;
        session = EMPTY_SESSION();
    }
    function markUnavailable(reason) {
        session = { ...session, status: "unavailable", clock: null, reason };
        renderClockState();
    }
    function deferAxis(generation, token, axisReason) {
        // No acceptable axis evidence yet: keep the page pending/manual and retry a bounded
        // number of times only while the player is idle. Interaction is never proof.
        const attempts = (session.axisAttempts || 0) + 1;
        session = { ...session, status: "pending", clock: null, reason: "axis_unconfirmed", axisAttempts: attempts, axisReason };
        renderClockState();
        if (attempts > AXIS_RETRY_DELAYS_MS.length) { markUnavailable(axisReason); return; }
        const delay = AXIS_RETRY_DELAYS_MS[attempts - 1];
        setTimeout(() => {
            if (generation !== loadGeneration || token !== validationToken) return;
            if (session.status !== "pending" || session.reason !== "axis_unconfirmed") return;
            if (video.seeking) { deferAxis(generation, token, axisReason); return; }
            void validateVisibleClock(generation);
        }, delay);
    }
    function renderClockState() {
        const media = selectedMedia();
        const link = byId("open-source");
        link.href = media.videoUrl;
        const ready = session.status === "ready" && session.clock && session.generation === loadGeneration && session.url === media.videoUrl;
        if (ready) {
            const clock = session.clock;
            link.hidden = true;
            byId("capture-start").disabled = byId("capture-end").disabled = false;
            byId("clock-state").textContent = clock.videoStartUs > 0
                ? `已把浏览器播放位置换算为规范源时间；原片开头 ${(clock.videoStartUs / 1000000).toFixed(3)} 秒没有画面，该段不能标记。`
                : "已把浏览器播放位置换算为规范源时间；可用“用当前位置标记”，保存前请核对完整动作与区间。";
        } else {
            link.hidden = false;
            byId("capture-start").disabled = byId("capture-end").disabled = true;
            byId("clock-state").textContent = unavailableText(session);
        }
    }
    async function validateVisibleClock(generation) {
        if (generation !== loadGeneration || activeGeneration === generation) return;
        const token = ++validationToken;
        const media = selectedMedia();
        const url = video.currentSrc;
        if (!url || url !== media.videoUrl) {
            // The element has not selected the query's media yet, or it selected another file.
            if (url && url !== media.videoUrl) markUnavailable("source_mismatch");
            return;
        }
        if (session.status === "ready" && session.generation === generation && session.url === url) return;
        if (session.headerDuration === null) return; // Wait for the current load's metadata.
        const candidates = SourceClock.clockCandidates(media);
        if (!candidates.length) { markUnavailable("clock_unavailable"); return; }
        activeGeneration = generation;
        try {
            // The mapping is re-established for every visible load generation, never cached
            // by URL: the probe element is created fresh from the current `currentSrc`.
            const verdict = await SourceClock.establish(candidates, url);
            if (token !== validationToken || generation !== loadGeneration) return;
            if (!verdict.established) { markUnavailable(verdict.reason); return; }
            const clock = verdict.clock;
            if (Math.abs(session.headerDuration * 1000000 - clock.durationUs) > clock.durationToleranceUs) {
                markUnavailable("duration_mismatch");
                return;
            }
            if (video.readyState < 1 || !(video.videoWidth > 0)) { markUnavailable("duration_unavailable"); return; }
            // Confirm the axis on the element the reviewer is actually using. Only the probed
            // origin is evidence; the probe target and any user interaction are not. The first
            // attempt runs only while the player is still untouched at its initial position; a
            // bounded retry may probe an idle player and restores its position afterwards.
            const retrying = (session.axisAttempts || 0) > 0;
            const idle = !video.seeking;
            const atStart = idle && Math.abs(video.currentTime) <= 0.000001;
            if (!atStart && !(retrying && idle && Number.isFinite(video.currentTime))) {
                deferAxis(generation, token, "axis_mismatch");
                return;
            }
            const restoreTo = atStart ? null : video.currentTime;
            // The axis probe may be woken by a late event from a media that has already been
            // switched or reloaded. Every await below must still belong to the same validation
            // before anything (especially the restore write) is applied to the visible player.
            const sameVisibleMedia = () => token === validationToken
                && generation === loadGeneration
                && video.currentSrc === url;
            const axis = await SourceClock.settle(video, 0.000001);
            if (!sameVisibleMedia()) return;
            if (restoreTo !== null) {
                await SourceClock.settle(video, restoreTo);
                if (!sameVisibleMedia()) return;
            }
            if (axis === null) { deferAxis(generation, token, "seek_incomplete"); return; }
            if (Math.abs(axis * 1000000 - clock.originUs) > clock.axisToleranceUs) {
                deferAxis(generation, token, "axis_mismatch");
                return;
            }
            session = { ...session, generation, url, status: "ready", clock, reason: null, axisAttempts: 0, axisReason: null };
            renderClockState();
        } finally {
            if (activeGeneration === generation) activeGeneration = -1;
        }
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
        resetSession();
        const query = record.plan.queries[queryIndex]; const media = selectedMedia();
        video.src = media.videoUrl;
        byId("query-info").textContent = `${query.text} · ${media.path.split(/[\\/]/).pop()} · ${seconds(media.durationUs)} 秒`;
        byId("add-reference").disabled = query.kind === "negative";
        for (const id of ["start-seconds", "end-seconds", "event-id", "event-group", "reason"]) byId(id).value = "";
        renderClockState();
        renderReferences();
        void validateVisibleClock(loadGeneration);
    }
    video.addEventListener("loadstart", () => {
        resetSession();
        renderClockState();
        void validateVisibleClock(loadGeneration);
    });
    video.addEventListener("loadedmetadata", () => {
        if (!Number.isFinite(video.duration) || video.duration <= 0) { markUnavailable("duration_unavailable"); return; }
        if (session.headerDuration === null) session.headerDuration = video.duration;
        if (video.currentSrc) session.url = video.currentSrc;
        renderClockState();
        void validateVisibleClock(loadGeneration);
    });
    video.addEventListener("seeked", () => {
        if (session.generation === loadGeneration) session.seeked = true;
    });
    video.addEventListener("emptied", () => {
        resetSession();
        renderClockState();
    });
    video.addEventListener("durationchange", () => {
        if (session.status !== "ready" || !session.clock) return;
        // Only the measured bounded non-zero-PTS growth after a seek may stay ready; any
        // shrink, non-finite value or unexpected growth revokes the capability.
        const verdict = SourceClock.durationChangeVerdict(session.clock, video.duration, session.seeked);
        if (verdict !== null) markUnavailable(verdict);
    });
    video.addEventListener("error", () => {
        markUnavailable("media_unavailable");
        notify("原片无法播放；请检查原文件和浏览器编码支持，已填标注保留。");
    });
    for (const [index, query] of record.plan.queries.entries()) {
        const option = document.createElement("option"); option.value = String(index); option.textContent = `${query.text} · ${selectedMedia(index).path.split(/[\\/]/).pop()}`; byId("query-select").append(option);
    }
    byId("query-select").addEventListener("change", switchQuery);
    for (const id of ["label-version", "annotators", "confirmed", "reviewed"]) byId(id).addEventListener("input", () => { readMetadata(); edited(); });
    for (const id of ["start-seconds", "end-seconds", "event-id", "event-group", "reason"]) byId(id).addEventListener("input", () => { revision += 1; });
    for (const [button, field] of [["capture-start", "start-seconds"], ["capture-end", "end-seconds"]]) byId(button).addEventListener("click", () => {
        const media = selectedMedia();
        if (session.status !== "ready" || !session.clock || session.generation !== loadGeneration || session.url !== media.videoUrl) return notify(unavailableText(session));
        if (video.seeking || video.readyState < 2 || video.currentSrc !== media.videoUrl || !Number.isFinite(video.currentTime)) return notify("浏览器仍在定位原片，请等定位完成后再标记，或手填规范源时间。");
        // The duration is rechecked at capture time as well, so a change that arrived without a
        // usable event can never be turned into a canonical source value.
        const verdict = SourceClock.durationChangeVerdict(session.clock, video.duration, session.seeked);
        if (verdict !== null) { markUnavailable(verdict); return notify(unavailableText(session)); }
        const sourcePosition = SourceClock.captureSourceUs(session.clock, video.currentTime);
        if (sourcePosition === null) return notify("当前位置没有可核对的原片画面，请移到有画面的位置，或手填规范源时间。");
        byId(field).value = seconds(sourcePosition); revision += 1; notify("已把当前位置换算为规范源时间；保存前请核对完整动作与区间。");
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
    fillMetadata(); switchQuery();
})();
