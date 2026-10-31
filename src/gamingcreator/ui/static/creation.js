"use strict";
(() => {
    const $ = (id) => document.getElementById(id);
    const state = {project: "", job: "", epoch: 0, view: 0, timer: null, selected: null, busy: false, editor: null, editing: false, dirty: false, intents: {}, publication: null};
    let musicTracks = [];
    let platformProfiles = [], packageProfile = null;
    let musicNotice = "正在读取本地曲库…";
    const defaultMix = () => ({bgm: null, sourceGainDb: 0, ducking: "off"});
    const labels = {pending: "等待开始", running: "正在处理", completed: "已完成", failed: "失败", interrupted: "已中断"};
    function node(tag, text) { const el = document.createElement(tag); el.textContent = text; return el; }
    function notice(message) { $("notice").textContent = message; }
    function humanTime(value) { const time = new Date(value); return Number.isNaN(time.getTime()) ? "时间未知" : time.toLocaleString("zh-CN", {hour12: false}); }
    function save() { try { localStorage.setItem("creation-workspace-v1", JSON.stringify({project: state.project, job: state.job})); } catch { /* Storage may be disabled. */ } }
    async function api(url, body) {
        const response = await fetch(url, body ? {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)} : {});
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : data.error?.message || data.message || `请求失败 (${response.status})`);
        return data;
    }
    function requestId(kind, payload) {
        const key = JSON.stringify(payload);
        if (state.intents[kind]?.key !== key) {
            const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), (v) => v.toString(16).padStart(2, "0")).join("");
            state.intents[kind] = {key, id};
        }
        return state.intents[kind].id;
    }
    function controls() {
        $("generate-package").disabled = state.busy || !packageProfile || !state.publication?.publicationJobId || !state.publication?.publicationReceiptSha256;
        $("save-publication").disabled = state.busy || !state.publication;
        $("use-cover-frame").disabled = state.busy || !state.publication;
        $("plan").disabled = state.busy || !state.project || !$("runs").querySelector("input:checked");
        $("render").disabled = state.busy || state.editing || state.dirty || !state.selected || !!transitionError(state.editor);
        $("save-revision").disabled = state.busy || state.editing || !state.editor || !state.editor.clips.length || !!transitionError(state.editor);
    }
    function clearView() { closeReplacement(); $("package-form").hidden = true; $("package-result").hidden = true; $("package-downloads").replaceChildren(); $("package-preview").replaceChildren(); state.publication = null; $("publication-form").hidden = true; $("publication-cover").hidden = true; $("publication-cover").removeAttribute("src"); $("publication-downloads").replaceChildren(); state.selected = null; state.editor = null; $("audio-controls")?.remove(); $("narration-controls")?.remove(); state.dirty = false; state.editing = false; $("editor-rows").replaceChildren(); $("ancestry").replaceChildren(); $("editor-summary").textContent = "选择方案或剪辑版本后可编辑镜头。"; $("plans").replaceChildren(); $("artifact").replaceChildren(); $("job-status").textContent = "尚未选择任务"; controls(); }
    function showPlans(job) {
        $("plans").replaceChildren(); state.selected = null;
        for (const plan of job.plans || []) {
            const card = node("article", ""); card.className = "plan-card";
            card.append(node("h3", plan.structure), node("p", plan.ready ? "方案可用 · 模板草稿" : "方案有缺口 · 不可选择"), node("p", "脚本：已有描述草稿，待核对"));
            const segments = plan.segments || [];
            card.append(node("p", `${segments.length} 个片段 · ${(segments.reduce((sum, s) => sum + s.outputFrames, 0) / job.fps).toFixed(2)} 秒`));
            const list = node("ol", "");
            for (const segment of segments) list.append(node("li", `${(segment.startUs / 1e6).toFixed(2)}–${(segment.endUs / 1e6).toFixed(2)} 秒：${segment.scriptDraft || "无描述"}`));
            card.append(list);
            for (const gap of plan.gaps || []) card.append(node("p", `缺口：${gap}`));
            const select = node("button", "选择此方案"); select.type = "button"; select.disabled = plan.ready !== true;
            select.addEventListener("click", () => { document.querySelectorAll(".plan-card").forEach((c) => c.classList.remove("selected")); card.classList.add("selected"); void loadEditor(job.jobId, plan.id); });
            card.append(select); $("plans").append(card);
        }
        controls();
    }
    const kindLabel = (kind) => ({plan: "方案", revision: "剪辑版本", render: "视频", publication: "封面与文案", package: "平台预览包", narration: "旁白"}[kind] || kind);
    async function loadEditor(id, planId, revision = false) {
        closeReplacement();
        const epoch = state.epoch, view = ++state.view;
        state.selected = null; state.editor = null; state.editing = true; state.dirty = false;
        $("editor-rows").replaceChildren(); $("ancestry").replaceChildren();
        $("editor-summary").textContent = "正在读取镜头…"; controls();
        try {
            const editor = await api(`/api/creation/jobs/${encodeURIComponent(id)}/edit?planId=${encodeURIComponent(planId)}`);
            if (epoch !== state.epoch || view !== state.view) return;
            if (editor.parentJobId !== id || editor.planId !== planId) throw new Error("剪辑版本不匹配。");
            editor.replacements = [];
            editor.bounds = Object.fromEntries(editor.clips.map((c) => [c.clipId, {startUs: c.startUs, endUs: c.endUs}]));
            editor.clips.forEach((clip) => { clip.speed = clip.speed || {numerator: 1, denominator: 1}; clip.transitionIn = clip.transitionIn || {type: "cut", frames: 0}; });
            editor.subtitleOverrides = editor.subtitleOverrides || [];
            editor.audioMix = editor.audioMix || defaultMix();
            state.job = id; save(); state.editor = editor;
            state.selected = revision ? {revisionJobId: id} : {planJobId: id, planId};
            showEditor();
        } catch (error) { if (epoch === state.epoch && view === state.view) notice(`镜头读取失败：${error.message}`); }
        finally { if (epoch === state.epoch && view === state.view) { state.editing = false; controls(); } }
    }
    function showAudio(editor) {
        let panel = $("audio-controls");
        if (!panel) { panel = node("section", ""); panel.id = "audio-controls"; $("editor-rows").before(panel); }
        panel.replaceChildren(node("h3", "配乐与音量"), node("p", musicNotice));
        const select = document.createElement("select"); select.id = "bgm-track";
        select.append(new Option("不用配乐", ""));
        for (const track of musicTracks) select.append(new Option(`${track.title} · ${{unknown: "权利未核实", user_declared: "用户已声明，权利未核实", test_only: "仅供测试"}[track.licenseStatus] || "权利未核实"}`, track.trackId));
        const mix = editor.audioMix;
        if (mix.bgm && !musicTracks.some((t) => t.trackId === mix.bgm.trackId)) select.append(new Option("已保存曲目（当前曲库不可用）", mix.bgm.trackId));
        select.value = mix.bgm?.trackId || "";
        const trackLabel = node("label", "本地配乐"); trackLabel.append(select); panel.append(trackLabel);
        function dirty() { state.dirty = true; $("editor-summary").textContent = "配乐或音量已修改，请保存新版本后生成视频。"; controls(); }
        for (const [id, title, value] of [["source-gain", "原声音量（dB，0 为原音量）", mix.sourceGainDb], ["bgm-gain", "配乐音量（dB）", mix.bgm?.gainDb ?? -12]]) {
            const label = node("label", title), input = document.createElement("input"); input.id = id; input.type = "number"; input.min = "-60"; input.max = "0"; input.step = "1"; input.value = value;
            input.addEventListener("input", () => { if (state.busy || state.editing) return; const gain = Number(input.value); if (!input.value || !Number.isFinite(gain) || gain < -60 || gain > 0) { input.setCustomValidity("请填写 -60 到 0 的音量。"); state.dirty = true; controls(); return; } input.setCustomValidity(""); if (id === "source-gain") mix.sourceGainDb = gain; else if (mix.bgm) mix.bgm.gainDb = gain; dirty(); });
            label.append(input); panel.append(label);
        }
        const duckLabel = node("label", "原声响起时压低配乐（依据原声能量，包含音效）"), duck = document.createElement("input"); duck.type = "checkbox"; duck.id = "bgm-ducking"; duck.checked = mix.ducking === "source-v1"; duckLabel.prepend(duck); panel.append(duckLabel);
        duck.addEventListener("change", () => { if (state.busy || state.editing) return; mix.ducking = duck.checked ? "source-v1" : "off"; dirty(); });
        select.addEventListener("change", () => { if (state.busy || state.editing) return; const track = musicTracks.find((t) => t.trackId === select.value); mix.bgm = track ? {trackId: track.trackId, trackReceiptSha256: track.trackReceiptSha256, gainDb: Number($("bgm-gain").value)} : null; dirty(); });
        const remove = node("button", "移除配乐"); remove.id = "remove-bgm"; remove.type = "button"; remove.addEventListener("click", () => { if (state.busy || state.editing) return; mix.bgm = null; select.value = ""; dirty(); }); panel.append(remove);
    }
    async function loadMusic() {
        try { const data = await api("/api/creation/music"); musicTracks = data.tracks; musicNotice = musicTracks.length ? "许可状态为登记声明，不代表权利已核实。" : "曲库暂无音乐。以后可用 scripts/register-music.ps1 登记本地音乐；现在可继续编辑。"; if (data.issues?.length) musicNotice += " 部分曲目暂不可用。"; }
        catch { musicNotice = "曲库暂不可用，可继续镜头与字幕编辑。"; }
        if (state.editor) showAudio(state.editor);
    }
    const narr = {voices: [], voiceId: "", notice: "正在读取本地声音…", license: "", text: "", job: null, asset: null, timer: null, draftFor: null, startFrame: 0, gainDb: 0, ducking: false, scriptNote: ""};
    const outputFrameCount = (editor) => editor.clips.reduce((n, c) => n + clipFrames(c, editor.fps) - c.transitionIn.frames, 0);
    function checkedAsset(asset) {
        if (!asset || !/^[a-f0-9]{32}$/.test(asset.assetJobId) || !/^[a-f0-9]{64}$/.test(asset.receiptSha256) || !Number.isSafeInteger(asset.sampleCount) || !Number.isSafeInteger(asset.sampleRate) || asset.sampleCount < 1 || asset.sampleRate < 1 || !Number.isFinite(asset.durationSeconds)) throw new Error("旁白信息无效。");
        const prefix = `/api/creation/jobs/${asset.assetJobId}/narration-files/`;
        for (const [value, name] of [[asset.audioUrl, "narration.wav"], [asset.textUrl, "narration.txt"]]) {
            const url = new URL(value, location.origin);
            if (url.origin !== location.origin || url.pathname !== prefix + name || url.search || url.hash) throw new Error("旁白地址无效。");
        }
        return asset;
    }
    const safeAsset = (asset) => { try { return asset ? checkedAsset(asset) : null; } catch { return null; } };
    function fitWarning(editor, asset, startFrame) {
        if (!asset) return "";
        const total = outputFrameCount(editor);
        if (startFrame >= total || asset.sampleCount * editor.fps > (total - startFrame) * asset.sampleRate) return `旁白长 ${asset.durationSeconds.toFixed(3)} 秒，起点后成片只剩 ${(Math.max(0, total - startFrame) / editor.fps).toFixed(3)} 秒；保存时服务器会拒绝，不会自动截断。请改短文字、调整起点或移除旁白。`;
        return "";
    }
    const refreshNarration = () => { if (state.editor) showNarration(state.editor); };
    function showNarration(editor) {
        if (narr.draftFor !== editor) {
            narr.draftFor = editor; narr.scriptNote = ""; const n = editor.narration;
            narr.startFrame = n ? n.startFrame : 0; narr.gainDb = n ? n.gainDb : 0; narr.ducking = n ? n.ducking === "narration-v1" : false;
        }
        const active = document.activeElement?.closest?.("#narration-controls") ? document.activeElement : null, focusId = active?.id, caret = active?.selectionStart;
        let panel = $("narration-controls");
        if (!panel) { panel = node("section", ""); panel.id = "narration-controls"; const anchor = $("audio-controls"); if (anchor) anchor.after(panel); else $("editor-rows").before(panel); }
        const fps = editor.fps, locked = () => state.busy || state.editing, job = narr.job;
        const running = Boolean(job && (job.submitting || ["pending", "running"].includes(job.status)));
        const candidate = safeAsset(narr.asset) || safeAsset(editor.narrationAsset), current = editor.narration ? safeAsset(editor.narrationAsset) : null;
        panel.replaceChildren(node("h3", "旁白（本地配音）"));
        const note = node("p", narr.voices.length ? "声音商用许可未核实：电脑里有这个声音，不代表可以商用。" : narr.notice); note.id = "narration-notice"; panel.append(note);
        const voice = document.createElement("select"); voice.id = "narration-voice"; voice.disabled = !narr.voices.length;
        // SAPI reports hex LCIDs; show common ones by name and keep the raw code otherwise.
        const languages = {"804": "中文（简体）", "404": "中文（繁体）", "409": "英语（美国）", "809": "英语（英国）", "411": "日语", "412": "韩语"};
        for (const v of narr.voices) voice.append(new Option(`${v.description} · ${String(v.language).split(";").map((code) => languages[code] || `语言 ${code}`).join("/")}`, v.voiceId));
        voice.value = narr.voiceId; voice.addEventListener("change", () => { narr.voiceId = voice.value; update(); });
        const voiceLabel = node("label", "本地声音"); voiceLabel.append(voice); panel.append(voiceLabel);
        const text = document.createElement("textarea"); text.id = "narration-text"; text.rows = 4; text.maxLength = 10000; text.value = narr.text;
        const count = node("p", ""); count.id = "narration-count";
        text.addEventListener("input", () => { narr.text = text.value; update(); });
        const textLabel = node("label", "旁白文字（1–10000 字，纯文本）"); textLabel.append(text); panel.append(textLabel, count);
        const draft = node("button", "按已保存镜头生成解说草稿"); draft.id = "narration-script"; draft.type = "button"; draft.disabled = running;
        const draftNote = node("p", narr.scriptNote || "草稿只用已保存的镜头描述和时长，离线模板生成，不调用模型；未保存的修改不计入。"); draftNote.id = "narration-script-note"; draftNote.setAttribute("role", "status");
        draft.addEventListener("click", () => { if (!locked()) void draftNarration(editor); });
        panel.append(draft, draftNote);
        const generate = node("button", "生成试听"); generate.id = "narration-generate"; generate.type = "button"; generate.addEventListener("click", () => { void generateNarration(); });
        const cancel = node("button", "取消生成"); cancel.id = "narration-cancel"; cancel.type = "button"; cancel.hidden = !running; cancel.addEventListener("click", () => { void cancelNarration(); });
        const status = node("p", ""); status.id = "narration-status"; status.setAttribute("role", "status");
        if (job) status.textContent = job.submitting ? "正在提交旁白任务…" : job.status === "completed" ? "旁白已生成，可试听。" : running ? `旁白${job.cancelRequested ? "正在取消" : "正在合成"}…` : `旁白未完成：${job.error || labels[job.status] || job.status}`;
        panel.append(generate, cancel, status);
        if (narr.asset && safeAsset(narr.asset)) {
            const asset = narr.asset, preview = node("div", ""); preview.id = "narration-preview";
            const audio = document.createElement("audio"); audio.id = "narration-audio"; audio.controls = true; audio.preload = "none"; audio.src = asset.audioUrl;
            const link = node("a", "下载旁白文本"); link.id = "narration-text-link"; link.href = asset.textUrl; link.download = "narration.txt";
            preview.append(node("p", `试听：${asset.voice?.description || "本地声音"} · 时长 ${asset.durationSeconds.toFixed(3)} 秒 · ${asset.sampleRate} Hz`), audio, link); panel.append(preview);
        }
        const now = node("div", ""); now.id = "narration-current";
        if (editor.narration && current) {
            const audio = document.createElement("audio"); audio.id = "narration-current-audio"; audio.controls = true; audio.preload = "none"; audio.src = current.audioUrl;
            const link = node("a", "下载已挂接旁白文本"); link.id = "narration-current-text"; link.href = current.textUrl; link.download = "narration.txt";
            now.append(node("p", `当前已挂接旁白：起点第 ${editor.narration.startFrame} 帧（${(editor.narration.startFrame / fps).toFixed(3)} 秒） · 音量 ${editor.narration.gainDb} dB · ${editor.narration.ducking === "narration-v1" ? "旁白时压低原声和配乐" : "不压低"} · 时长 ${current.durationSeconds.toFixed(3)} 秒`), audio, link);
        } else if (editor.narration) now.append(node("p", "已挂接旁白，但旁白信息无法读取；可移除后重新生成。"));
        else now.append(node("p", editor.narrationChanged ? "旁白将被移除，保存新版本后生效。" : "当前没有挂接旁白。"));
        panel.append(now);
        const startLabel = node("label", "旁白起点（成片秒数）"), start = document.createElement("input"); start.id = "narration-start"; start.type = "number"; start.min = "0"; start.step = "any"; start.required = true; start.value = String(Number((narr.startFrame / fps).toFixed(6))); startLabel.append(start);
        const frameText = node("p", ""); frameText.id = "narration-start-frame";
        const gainLabel = node("label", "旁白音量（dB，0 为原音量）"), gain = document.createElement("input"); gain.id = "narration-gain"; gain.type = "number"; gain.min = "-60"; gain.max = "0"; gain.step = "any"; gain.required = true; gain.value = String(narr.gainDb); gainLabel.append(gain);
        const duckLabel = node("label", "旁白时压低原声和配乐"), duck = document.createElement("input"); duck.id = "narration-ducking"; duck.type = "checkbox"; duck.checked = narr.ducking; duckLabel.prepend(duck);
        const fit = node("p", ""); fit.id = "narration-fit"; fit.setAttribute("role", "status");
        const attach = node("button", "挂接到剪辑"); attach.id = "narration-attach"; attach.type = "button";
        const remove = node("button", "移除旁白"); remove.id = "narration-remove"; remove.type = "button";
        panel.append(startLabel, frameText, gainLabel, duckLabel, fit, attach, remove);
        const valid = () => start.checkValidity() && gain.checkValidity();
        function update() {
            frameText.textContent = `起点对应成片第 ${narr.startFrame} 帧（${(narr.startFrame / fps).toFixed(3)} 秒，帧率 ${fps}）`;
            const length = [...text.value].length; count.textContent = `${length} / 10000 字`;
            generate.disabled = running || !state.project || !narr.voiceId || !text.value.trim() || length > 10000;
            attach.disabled = !candidate || !valid(); remove.disabled = !editor.narration;
            const warnings = [];
            if (editor.narration && current) warnings.push(["已挂接", current]);
            if (candidate && (!current || candidate.assetJobId !== current.assetJobId || candidate.receiptSha256 !== current.receiptSha256)) warnings.push(["待挂接", candidate]);
            fit.textContent = warnings.map(([name, asset]) => fitWarning(editor, asset, narr.startFrame) && `${name}：${fitWarning(editor, asset, narr.startFrame)}`).filter(Boolean).join("\n");
        }
        function changed(message) { editor.narrationChanged = true; state.dirty = true; $("editor-summary").textContent = message; controls(); }
        function mirror() {
            if (!editor.narration) return;
            editor.narration = {...editor.narration, startFrame: narr.startFrame, gainDb: narr.gainDb, ducking: narr.ducking ? "narration-v1" : "off"};
            changed("旁白设置已修改，请保存新版本后生成视频。"); update();
        }
        start.addEventListener("input", () => {
            if (locked()) return; start.setCustomValidity("");
            const frame = Math.round(Number(start.value) * fps);
            if (start.validity.valid && Number.isSafeInteger(frame) && frame >= 0) { narr.startFrame = frame; mirror(); }
            else { start.setCustomValidity("请填写不小于 0 的起点秒数。"); if (editor.narration) { state.dirty = true; controls(); } }
            update();
        });
        gain.addEventListener("input", () => {
            if (locked()) return; gain.setCustomValidity("");
            if (gain.validity.valid) { narr.gainDb = Number(gain.value); mirror(); }
            else { gain.setCustomValidity("请填写 -60 到 0 的音量。"); if (editor.narration) { state.dirty = true; controls(); } }
            update();
        });
        duck.addEventListener("change", () => { if (locked()) return; narr.ducking = duck.checked; mirror(); update(); });
        attach.addEventListener("click", () => {
            if (locked() || !candidate || !valid()) return;
            editor.narration = {assetJobId: candidate.assetJobId, receiptSha256: candidate.receiptSha256, startFrame: narr.startFrame, gainDb: narr.gainDb, ducking: narr.ducking ? "narration-v1" : "off"};
            editor.narrationAsset = candidate; changed("旁白已挂接，请保存新版本后生成视频。"); showNarration(editor);
        });
        remove.addEventListener("click", () => { if (locked() || !editor.narration) return; editor.narration = null; changed("旁白将被移除，请保存新版本后生成视频。"); showNarration(editor); });
        update();
        if (focusId && $(focusId)) { $(focusId).focus(); if (Number.isInteger(caret)) try { $(focusId).setSelectionRange(caret, caret); } catch { /* Number inputs have no caret. */ } }
    }
    async function loadVoices() {
        try {
            const data = await api("/api/creation/voices");
            if (!Array.isArray(data.voices) || data.voices.some((v) => typeof v.voiceId !== "string" || !v.voiceId)) throw new Error("声音列表无效。");
            narr.voices = data.voices; narr.license = data.licenseStatus; narr.voiceId = (data.voices.find((v) => String(v.language).split(";").includes("804")) || data.voices[0])?.voiceId || ""; narr.notice = data.voices.length ? "" : "此电脑没有可用的本地声音，可继续其他编辑。";
        } catch { narr.voices = []; narr.voiceId = ""; narr.notice = "本地声音不可用，可继续其他编辑"; }
        refreshNarration();
    }
    async function draftNarration(editor) {
        const epoch = state.epoch;
        try {
            const data = await api(`/api/creation/jobs/${encodeURIComponent(editor.parentJobId)}/narration-script?planId=${encodeURIComponent(editor.planId)}`);
            if (epoch !== state.epoch || state.editor !== editor) return;
            if (typeof data.text !== "string" || !data.text) { narr.scriptNote = "已保存镜头没有可用描述，无法生成草稿；可直接手写旁白。"; showNarration(editor); return; }
            narr.text = data.text;
            narr.scriptNote = `模板草稿，待人工核对：按约 ${data.charactersPerSecond} 字/秒估算朗读约 ${data.estimatedSeconds.toFixed(1)} 秒，成片 ${data.outputSeconds.toFixed(1)} 秒${data.omittedClips ? `；${data.omittedClips} 个镜头因时长或描述缺失未写入` : ""}。请修改后再生成试听。`;
        } catch (error) { if (epoch !== state.epoch) return; narr.scriptNote = `草稿生成失败：${error.message}`; }
        showNarration(editor);
    }
    async function generateNarration() {
        const text = narr.text, voiceId = narr.voiceId;
        if (!state.project || !voiceId || !text.trim() || [...text].length > 10000 || (narr.job && (narr.job.submitting || ["pending", "running"].includes(narr.job.status)))) return;
        const epoch = state.epoch, payload = {projectId: state.project, text, voiceId}, job = {jobId: "", status: "pending", submitting: true, error: "", cancelRequested: false};
        clearTimeout(narr.timer); narr.job = job; refreshNarration();
        try {
            const result = await api("/api/creation/narrations", {...payload, requestId: requestId("narration", payload)});
            if (epoch !== state.epoch || narr.job !== job) return;
            delete state.intents.narration; job.jobId = result.jobId; job.submitting = false; job.status = result.status || "pending"; refreshNarration(); pollNarration(job, epoch);
        } catch (error) { if (epoch === state.epoch && narr.job === job) { job.submitting = false; job.status = "failed"; job.error = error.message; refreshNarration(); } }
    }
    function pollNarration(job, epoch) {
        const tick = async () => {
            try {
                const data = await api(`/api/creation/jobs/${encodeURIComponent(job.jobId)}`);
                if (epoch !== state.epoch || narr.job !== job) return;
                if (data.kind !== "narration" || data.jobId !== job.jobId || data.projectId !== state.project) throw new Error("旁白任务不属于当前项目。");
                job.status = data.status; job.error = data.error ? data.error.message : "";
                if (data.status === "completed") { const asset = checkedAsset(data.narrationAsset); if (asset.assetJobId !== job.jobId) throw new Error("旁白信息与任务不匹配。"); narr.asset = asset; }
                else if (["pending", "running"].includes(data.status)) narr.timer = setTimeout(tick, 1000);
                refreshNarration();
            } catch (error) { if (epoch === state.epoch && narr.job === job) { job.status = "failed"; job.error = error.message; refreshNarration(); } }
        };
        clearTimeout(narr.timer); void tick();
    }
    async function cancelNarration() {
        const job = narr.job; if (!job?.jobId) return;
        try { await api("/api/creation/narration-cancel", {jobId: job.jobId}); job.cancelRequested = true; } catch (error) { job.error = error.message; notice(`取消失败：${error.message}`); }
        refreshNarration();
    }
    let replacementToken = 0, replacement = null;
    function closeReplacement() {
        replacementToken++; replacement = null;
        $("replacement-panel").hidden = true; $("confirm-replacement").disabled = true;
        const video = $("replacement-preview"); video.pause(); video.removeAttribute("src"); video.load(); video.ontimeupdate = null;
    }
    async function openReplacement(targetClipId) {
        if (state.busy || state.editing) return;
        closeReplacement(); const token = replacementToken, epoch = state.epoch, view = state.view, editor = state.editor;
        const current = () => token === replacementToken && epoch === state.epoch && view === state.view && editor === state.editor;
        $("replacement-panel").hidden = false; $("replacement-status").textContent = "正在读取根请求已选录像的事件…";
        $("replacement-candidates").replaceChildren();
        try {
            const data = await api(`/api/creation/jobs/${encodeURIComponent(editor.parentJobId)}/candidates?planId=${encodeURIComponent(editor.planId)}`);
            if (!current()) return;
            if (!/^[a-f0-9]{64}$/.test(data.candidateManifestSha256) || (editor.candidateManifestSha256 && editor.candidateManifestSha256 !== data.candidateManifestSha256)) throw new Error("候选清单身份不匹配，请重新读取版本。");
            replacement = {editor, targetClipId, data, candidate: null};
            for (const c of data.candidates) $("replacement-candidates").append(new Option(`${c.sourceName || "已选录像"} · ${(c.startUs / 1e6).toFixed(3)}–${(c.endUs / 1e6).toFixed(3)} 秒 · ${c.scriptDraft || "无描述"}${c.uncertainty ? ` · ${c.uncertainty}` : ""}`, c.candidateId));
            if (data.candidates.length) void previewReplacement();
            else $("replacement-status").textContent = "此根请求没有可替换事件。";
        } catch (error) { if (current()) $("replacement-status").textContent = error.message; }
    }
    async function previewReplacement() {
        const session = replacement; if (!session) return;
        const token = ++replacementToken, epoch = state.epoch, view = state.view;
        const current = () => token === replacementToken && epoch === state.epoch && view === state.view && session === replacement && session.editor === state.editor;
        const video = $("replacement-preview"); video.pause(); video.removeAttribute("src"); video.load(); video.ontimeupdate = null;
        $("confirm-replacement").disabled = true; session.candidate = null;
        const c = session.data.candidates.find((item) => item.candidateId === $("replacement-candidates").value);
        try {
            const url = new URL(c.previewUrl, location.origin), expected = `/api/creation/jobs/${encodeURIComponent(session.editor.parentJobId)}/candidate-video`;
            if (url.origin !== location.origin || url.pathname !== expected || url.hash || url.username || url.password || url.searchParams.size !== 3 || url.searchParams.get("planId") !== session.editor.planId || url.searchParams.get("candidateManifestSha256") !== session.data.candidateManifestSha256 || url.searchParams.get("candidateId") !== c.candidateId) throw new Error("候选预览地址身份不匹配。");
            const old = session.editor.clips.find((clip) => clip.clipId === session.targetClipId), fps = session.editor.fps;
            const frames = Math.min(clipFrames(old, fps), Math.floor((c.endUs - c.startUs) * fps / 1e6));
            if (frames < 1) throw new Error("候选不足一个输出帧。");
            const endUs = c.startUs + Math.ceil(frames * 1e6 / fps);
            session.candidate = {...c, endUs};
            const description = `${frames} 帧，比原镜头${frames >= clipFrames(old, fps) ? "增加" : "减少"} ${Math.abs(frames - clipFrames(old, fps))} 帧。旧手写字幕不移到新画面；两侧转场归直接切换；替换后速度为1x。`;
            $("replacement-status").textContent = description + "正在校验原片时钟…";
            $("confirm-replacement").disabled = state.busy;
            const result = await SourceClock.establish(SourceClock.clockCandidates(c), url.href, 10000);
            if (!current()) return;
            if (!result.established || !SourceClock.intervalReplayable(result.clock, c.startUs, endUs)) { $("replacement-status").textContent = description + "原片预览不可用；仍可明确选择并在成片中复核。"; return; }
            await SourceClock.prepare(video, url.href); if (!current()) return;
            const position = await SourceClock.settle(video, SourceClock.sourceUsToPlayerSeconds(result.clock, c.startUs), 10000);
            if (!current()) return;
            if (position === null) throw new Error("原片预览定位失败；可选择后复核成片。");
            const end = SourceClock.sourceUsToPlayerSeconds(result.clock, endUs);
            video.ontimeupdate = () => { if (!current() || video.currentTime >= end) video.pause(); };
            $("replacement-status").textContent = description + "原片时钟已核对。";
            await video.play(); if (!current()) video.pause();
        } catch (error) { if (current()) $("replacement-status").textContent = error.message; }
    }
    $("replacement-candidates").addEventListener("change", () => { void previewReplacement(); });
    $("confirm-replacement").addEventListener("click", () => {
        const session = replacement; if (!session?.candidate || session.editor !== state.editor || state.busy || state.editing) return;
        const editor = session.editor, index = editor.clips.findIndex((c) => c.clipId === session.targetClipId), c = session.candidate;
        if (index < 0) return;
        const clip = editor.clips[index];
        Object.assign(clip, {startUs: c.startUs, endUs: c.endUs, speed: {numerator: 1, denominator: 1}, transitionIn: {type: "cut", frames: 0}, scriptDraft: c.scriptDraft});
        clip.outputFrames = clipFrames(clip, editor.fps); editor.bounds[clip.clipId] = {startUs: c.startUs, endUs: c.endUs};
        if (editor.clips[index + 1]) editor.clips[index + 1].transitionIn = {type: "cut", frames: 0};
        editor.subtitleOverrides = editor.subtitleOverrides.filter((item) => item.clipId !== clip.clipId);
        editor.candidateManifestSha256 = session.data.candidateManifestSha256;
        editor.replacements.push({targetClipId: clip.clipId, candidateId: c.candidateId});
        closeReplacement(); state.dirty = true; showEditor(); controls(); notice("镜头已替换，请保存新版本后再编辑新镜头字幕、速度和两侧转场。");
    });
    const clipFrames = (clip, fps) => {
        if (![clip.startUs, clip.endUs, fps, clip.speed.numerator, clip.speed.denominator].every(Number.isSafeInteger)) return NaN;
        return Number(BigInt(clip.endUs - clip.startUs) * BigInt(fps) * BigInt(clip.speed.denominator) / (1000000n * BigInt(clip.speed.numerator)));
    };
    function transitionError(editor) {
        if (!editor) return "";
        for (let i = 0; i < editor.clips.length; i++) {
            const clip = editor.clips[i], t = clip.transitionIn;
            if (!t || !Number.isSafeInteger(t.frames) || (t.type === "cut" ? t.frames !== 0 : t.type !== "crossfade" || t.frames <= 0) || (i === 0 && (t.type !== "cut" || t.frames !== 0))) return "转场帧数须为正整数；直接切换和首镜头固定为 0 帧。";
            if (t.frames + (editor.clips[i + 1]?.transitionIn.frames || 0) >= clipFrames(clip, editor.fps)) return "每个镜头的入场与出场转场帧数之和必须小于镜头输出帧数，至少保留一帧独占，不能三重重叠。";
        }
        return "";
    }
    function showEditor() {
        const editor = state.editor;
        showAudio(editor); showNarration(editor);
        $("editor-rows").replaceChildren(); $("ancestry").replaceChildren();
        const totalFrames = editor.clips.reduce((n, c) => n + clipFrames(c, editor.fps) - c.transitionIn.frames, 0);
        const totalSeconds = totalFrames / editor.fps;
        const error = transitionError(editor);
        const target = editor.targetDuration;
        const difference = Number.isFinite(target) ? ` · 原目标 ${target} 秒，实际${totalSeconds > target ? "超出" : "少于"} ${Math.abs(totalSeconds - target).toFixed(3)} 秒（允许手动编辑，原需求不变）` : "";
        $("editor-summary").textContent = `${editor.clips.length} 个镜头 · ${totalSeconds.toFixed(3)} 秒 · ${totalFrames} 帧（扣除转场重叠）${difference}${state.dirty ? " · 有未保存修改，请保存新版本后生成视频" : " · 已保存"}`;
        if (error) $("editor-summary").textContent += ` · ${error}`;
        let startFrame = 0;
        editor.clips.forEach((clip, index) => {
            if (index) startFrame -= clip.transitionIn.frames;
            const clipStart = startFrame;
            startFrame += clipFrames(clip, editor.fps);
            const row = node("article", ""); row.dataset.clipId = clip.clipId; row.className = "clip-row";
            row.append(node("h3", `镜头 ${index + 1}`), node("p", clip.scriptDraft || "无描述"));
            const original = editor.bounds[clip.clipId];
            for (const field of ["start", "end"]) {
                const label = node("label", field === "start" ? "入点（原录像秒数）" : "出点（原录像秒数）");
                const input = document.createElement("input"); input.type = "number"; input.step = "0.000001"; input.min = original.startUs / 1e6; input.max = original.endUs / 1e6;
                input.dataset.field = field; input.value = String((field === "start" ? clip.startUs : clip.endUs) / 1e6);
                input.addEventListener("change", () => {
                    if (state.busy || state.editing) return;
                    const startUs = Math.round(Number(row.querySelector('[data-field="start"]').value) * 1e6);
                    const endUs = Math.round(Number(row.querySelector('[data-field="end"]').value) * 1e6);
                    const frames = clipFrames({...clip, startUs, endUs}, editor.fps);
                    if (!Number.isSafeInteger(startUs) || !Number.isSafeInteger(endUs) || startUs < original.startUs || endUs > original.endUs || frames < 1) { notice("入点和出点需在父版本范围内，并至少保留一帧。"); showEditor(); return; }
                    clip.startUs = startUs; clip.outputFrames = frames; clip.endUs = endUs;
                    state.dirty = true; showEditor(); controls();
                });
                label.append(input); row.append(label);
            }
            const speedLabel = node("label", "播放速度"), speed = document.createElement("select");
            speed.dataset.field = "speed"; speed.disabled = state.busy || editor.replacements.some((r) => r.targetClipId === clip.clipId);
            for (const value of ["0.5", "1", "2"]) speed.append(new Option(`${value}x`, value));
            speed.value = String(clip.speed.numerator / clip.speed.denominator);
            speed.addEventListener("change", () => {
                if (state.busy || state.editing) return;
                const selected = {"0.5": {numerator: 1, denominator: 2}, "1": {numerator: 1, denominator: 1}, "2": {numerator: 2, denominator: 1}}[speed.value];
                const frames = clipFrames({...clip, speed: selected}, editor.fps);
                if (frames < 1) { notice("此速度下不足一输出帧，请保留更长的源片段。"); showEditor(); return; }
                clip.speed = selected; clip.outputFrames = frames;
                state.dirty = true; showEditor(); controls();
            });
            speedLabel.append(speed); row.append(speedLabel);
            const transitionLabel = node("label", "与上一镜头连接"), transition = document.createElement("select");
            transition.dataset.field = "transition"; transition.append(new Option("直接切换", "cut"), new Option("交叉淡化", "crossfade"));
            const replacementConnection = editor.replacements.some((r) => r.targetClipId === clip.clipId || r.targetClipId === editor.clips[index - 1]?.clipId);
            transition.value = clip.transitionIn.type; transition.disabled = index === 0 || state.busy || replacementConnection;
            const framesLabel = node("label", "转场帧数"), frames = document.createElement("input");
            frames.type = "number"; frames.step = "1"; frames.min = "1"; frames.dataset.field = "transition-frames";
            frames.value = String(clip.transitionIn.frames); frames.disabled = index === 0 || transition.value === "cut" || state.busy || replacementConnection;
            transition.addEventListener("change", () => {
                if (state.busy || state.editing || index === 0) return;
                clip.transitionIn = {type: transition.value, frames: transition.value === "cut" ? 0 : 1};
                state.dirty = true; showEditor(); controls();
            });
            frames.addEventListener("change", () => {
                if (state.busy || state.editing || index === 0) return;
                clip.transitionIn.frames = frames.value === "" ? NaN : Number(frames.value);
                state.dirty = true; showEditor(); controls();
            });
            transitionLabel.append(transition); framesLabel.append(frames); row.append(transitionLabel, framesLabel);
            row.append(node("p", `输出起点 ${clipStart} 帧 · ${(clipStart / editor.fps).toFixed(3)} 秒`));
            row.append(node("p", `输出 ${clip.outputFrames} 帧 · ${(clip.outputFrames / editor.fps).toFixed(3)} 秒；源出点 ${(clip.endUs / 1e6).toFixed(6)} 秒保持不变。舍弃尾部不足一输出帧的余量。`));
            const override = editor.subtitleOverrides.find((item) => item.clipId === clip.clipId);
            const subtitleLabel = node("label", "手写字幕（替换该镜头语音字幕）");
            const toggle = document.createElement("input"); toggle.type = "checkbox"; toggle.dataset.field = "subtitle-override"; toggle.checked = Boolean(override);
            toggle.disabled = state.busy || editor.replacements.some((r) => r.targetClipId === clip.clipId); subtitleLabel.prepend(toggle);
            const subtitle = document.createElement("textarea"); subtitle.dataset.field = "subtitle-text"; subtitle.maxLength = 2000; subtitle.rows = 3;
            subtitle.setAttribute("aria-label", `镜头 ${index + 1} 手写字幕`); subtitle.value = override?.text || ""; subtitle.disabled = !override || state.busy;
            const source = node("p", ""); source.className = "subtitle-source";
            function updateSubtitle() {
                if (state.busy || state.editing) return;
                editor.subtitleOverrides = editor.subtitleOverrides.filter((item) => item.clipId !== clip.clipId);
                if (toggle.checked) editor.subtitleOverrides.push({clipId: clip.clipId, text: subtitle.value});
                subtitle.disabled = !toggle.checked; state.dirty = true;
                $("editor-summary").textContent = "有未保存的字幕修改，请保存新版本后生成视频。";
                describeSource(); controls();
            }
            function describeSource() { source.textContent = toggle.checked ? (subtitle.value ? "字幕来源：你的手写文字，覆盖整个镜头。" : "已勾选但文字为空：此镜头不显示字幕。") : "字幕来源：此分析版本已有语音；无语音则无字幕。画面描述不会自动用作字幕。"; }
            toggle.addEventListener("change", updateSubtitle); subtitle.addEventListener("input", updateSubtitle); describeSource();
            row.append(subtitleLabel, subtitle, source);

            const replace = node("button", "选择其他事件替换"); replace.type = "button"; replace.dataset.action = "replace";
            replace.disabled = state.busy || editor.replacements.some((r) => r.targetClipId === clip.clipId);
            replace.addEventListener("click", () => { void openReplacement(clip.clipId); }); row.append(replace);
            for (const [action, text] of [["up", "上移"], ["down", "下移"], ["delete", "删除镜头"]]) {
                const button = node("button", text); button.type = "button"; button.dataset.action = action;
                button.disabled = state.busy || (action === "up" && index === 0) || (action === "down" && index === editor.clips.length - 1) || (action === "delete" && editor.clips.length === 1);
                button.addEventListener("click", () => {
                    if (state.busy || state.editing) return;
                    closeReplacement();
                    const predecessors = new Map(editor.clips.map((c, i) => [c.clipId, editor.clips[i - 1]?.clipId]));
                    if (action === "delete") editor.clips.splice(index, 1);
                    else { const next = index + (action === "up" ? -1 : 1); [editor.clips[index], editor.clips[next]] = [editor.clips[next], editor.clips[index]]; }
                    editor.clips.forEach((c, i) => { if (i === 0 || predecessors.get(c.clipId) !== editor.clips[i - 1]?.clipId) c.transitionIn = {type: "cut", frames: 0}; });
                    state.dirty = true; showEditor(); controls();
                }); row.append(button);
            }
            $("editor-rows").append(row);
        });
        for (const ancestor of editor.ancestry || []) {
            const button = node("button", `选择祖先${kindLabel(ancestor.kind)}（撤销到此版本）`); button.type = "button"; button.dataset.jobId = ancestor.jobId;
            button.addEventListener("click", () => { void loadEditor(ancestor.jobId, ancestor.planId, ancestor.kind === "revision"); }); $("ancestry").append(button);
        }
    }
    function showArtifact(artifact, renderId = state.job) {
        const video = document.createElement("video"); video.controls = true; video.preload = "metadata";
        const download = node("a", artifact.sizeBytes ? `下载 MP4（${(artifact.sizeBytes / 1048576).toFixed(2)} MB）` : "下载 MP4");
        // Only serve artifacts through the workspace's job media endpoint.
        const prefix = `/api/creation/jobs/${encodeURIComponent(renderId)}/video`;
        for (const value of [artifact.previewUrl, artifact.downloadUrl]) {
            const url = new URL(value, location.origin);
            if (url.origin !== location.origin || url.pathname !== prefix) throw new Error("成片地址无效，请刷新任务。");
        }
        video.src = artifact.previewUrl; download.href = artifact.downloadUrl; download.download = "video.mp4";
        $("artifact").append(video, download);
        if (artifact.subtitleUrl) {
            const url = new URL(artifact.subtitleUrl, location.origin);
            if (url.origin !== location.origin || url.pathname !== `/api/creation/jobs/${encodeURIComponent(renderId)}/subtitles` || url.search || url.hash) throw new Error("字幕地址无效，请刷新任务。");
            const link = node("a", "下载 SRT 字幕"); link.id = "download-subtitles"; link.href = artifact.subtitleUrl; link.download = "subtitles.srt";
            $("artifact").append(node("p", artifact.subtitleCueCount === 0 ? "字幕 0 条：所选片段无可用的已保存语音，SRT 为空。" : `字幕 ${artifact.subtitleCueCount} 条 · ${artifact.subtitleMode === "burn" ? "已烧入视频" : "独立导出"}`), link);
        }
        if (artifact.narrationTextUrl) {
            const url = new URL(artifact.narrationTextUrl, location.origin);
            if (url.origin !== location.origin || url.pathname !== `/api/creation/jobs/${encodeURIComponent(renderId)}/narration-text` || url.search || url.hash) throw new Error("旁白文本地址无效，请刷新任务。");
            const link = node("a", "下载旁白文本"); link.id = "download-narration-text"; link.href = artifact.narrationTextUrl; link.download = "narration.txt";
            $("artifact").append(link);
        }
    }
    const platformNames = {bilibili: "B站", douyin: "抖音", kuaishou: "快手", xiaohongshu: "小红书"};
    const packageFields = [
        ["video-width", "视频宽度", "video", "width"], ["video-height", "视频高度", "video", "height"],
        ["video-fit", "视频画面适配", "video", "fit"], ["cover-width", "封面宽度", "cover", "width"],
        ["cover-height", "封面高度", "cover", "height"], ["cover-fit", "封面画面适配", "cover", "fit"],
        ["max-bytes", "最大文件字节数（留空不配置）", "limits", "maxBytes"],
        ["min-duration-ms", "最短毫秒数（留空不配置）", "limits", "minDurationMs"],
        ["max-duration-ms", "最长毫秒数（留空不配置）", "limits", "maxDurationMs"],
        ["title-max-chars", "标题最多字数（留空不配置）", "limits", "titleMaxChars"],
        ["description-max-chars", "简介最多字数（留空不配置）", "limits", "descriptionMaxChars"],
        ["tag-max-count", "最多标签数（留空不配置）", "limits", "tagMaxCount"],
        ["required-tags", "必需标签（每行一个，留空不配置）", "limits", "requiredTags"]
    ];
    function fillProfile(profile) {
        packageProfile = structuredClone(profile);
        const select = $("package-platform");
        if (!Array.from(select.options).some((o) => o.value === profile.Platform)) select.append(new Option(platformNames[profile.Platform] || profile.Platform, profile.Platform));
        select.value = profile.Platform;
        $("package-version").textContent = `本地配置版本：${profile.RuleVersion} · ${profile.UpdatedAt}`;
        $("package-fields").replaceChildren();
        for (const [id, title, group, key] of packageFields) {
            const label = node("label", title), input = document.createElement(key === "fit" ? "select" : key === "requiredTags" ? "textarea" : "input");
            input.id = id;
            if (key === "fit") { input.append(new Option("完整画面（补边）", "pad"), new Option("填满画面（裁切）", "crop")); }
            else if (key !== "requiredTags") { input.type = "number"; input.step = "1"; input.min = group === "limits" ? "0" : "2"; input.required = group !== "limits"; }
            input.value = key === "requiredTags" ? profile.Fields[group][key].join("\n") : profile.Fields[group][key] ?? "";
            label.append(input); $("package-fields").append(label);
        }
        controls();
    }
    async function loadProfiles() {
        try {
            const data = await api("/api/creation/platform-profiles"); platformProfiles = data.profiles;
            $("package-platform").replaceChildren();
            for (const profile of platformProfiles) $("package-platform").append(new Option(platformNames[profile.Platform] || profile.Platform, profile.Platform));
            if (!packageProfile && platformProfiles.length) fillProfile(platformProfiles[0]);
            else if (packageProfile) $("package-platform").value = packageProfile.Platform;
            $("package-profile-notice").textContent = platformProfiles.length ? "本地预设可修改；修改后生成独立版本，原包保留。" : "平台预设暂不可用，已有创作功能仍可使用。";
        } catch { $("package-profile-notice").textContent = "平台预设暂不可用，已有创作功能仍可使用。"; }
    }
    function showPackage(data, id) {
        fillProfile(data.profile); $("package-result").hidden = false;
        $("package-status").textContent = `生成：${data.generationStatus === "completed" ? "成功，文件可下载" : "尚未完成"}；本地限值：${({pass: "通过", fail: "未通过", unknown: "未知"})[data.localChecks] || "未知"}；发布资格：${data.publicationEligibility === "blocked" ? "受阻（仅供测试音乐或其他限制）" : "未核实"}。官方规则、素材权利和真人质量尚未核实。`;
        const validation = data.validation || {}, statuses = {pass: "通过", fail: "未通过", unknown: "未知", not_configured: "未配置"};
        const checkNames = {width: "视频宽度", height: "视频高度", codec: "编码", pixelFormat: "像素格式", frames: "帧数", fps: "帧率", maxBytes: "文件大小上限", minDurationMs: "最短时长", maxDurationMs: "最长时长", titleMaxChars: "标题字数", descriptionMaxChars: "简介字数", tagMaxCount: "标签数量", requiredTags: "必需标签"};
        const lines = Object.entries(validation.checks || {}).map(([key, status]) => `${checkNames[key] || key}：${statuses[status] || "未知"}`);
        lines.push(`官方规则：${statuses[validation.platformRules] || "未知"}；素材权利：${statuses[validation.sourceRights] || "未知"}；真人质量：${statuses[validation.humanQuality] || "未知"}`);
        $("package-validation").textContent = lines.join("；");
        $("package-downloads").replaceChildren(); $("package-preview").replaceChildren();
        const prefix = `/api/creation/jobs/${encodeURIComponent(id)}/package-files/`;
        for (const file of ["video.mp4", "cover.png", "title.txt", "description.txt", "tags.json", "platform.json", "validation.json", "package.zip"]) {
            const url = prefix + file;
            const parsed = new URL(url, location.origin);
            if (parsed.origin !== location.origin || parsed.pathname !== url || parsed.search || parsed.hash) throw new Error("预览包地址无效。");
            const link = node("a", `下载 ${file}`); link.href = url; link.download = file; link.dataset.file = file; $("package-downloads").append(link);
            if (file === "video.mp4" || file === "cover.png") { const media = document.createElement(file === "video.mp4" ? "video" : "img"); media.src = url; if (file === "video.mp4") { media.controls = true; media.preload = "metadata"; } else media.alt = "平台预览包封面"; $("package-preview").append(media); }
        }
    }
    async function loadPublication(id, kind, epoch, view) {
        const data = await api(`/api/creation/jobs/${encodeURIComponent(id)}/publication`);
        if (epoch !== state.epoch || view !== state.view) return;
        const rate = data.fps;
        const fps = typeof rate === "number" ? rate : (Number.isSafeInteger(rate?.numerator) && rate.numerator > 0 && Number.isSafeInteger(rate?.denominator) && rate.denominator > 0 ? rate.numerator / rate.denominator : NaN);
        if (!/^[a-f0-9]{32}$/.test(data.renderJobId) || (kind === "render" && data.renderJobId !== id) || !Number.isSafeInteger(data.frames) || data.frames < 1 || !Number.isFinite(fps) || fps <= 0) throw new Error("成片信息无效。");
        const video = new URL(data.videoUrl, location.origin);
        if (video.origin !== location.origin || video.pathname !== `/api/creation/jobs/${data.renderJobId}/video` || video.search || video.hash) throw new Error("成片地址无效。");
        if (kind === "publication") showArtifact({previewUrl: data.videoUrl, downloadUrl: data.videoUrl, sizeBytes: 0}, data.renderJobId);
        state.publication = {...data, fps};
        $("package-form").hidden = !(kind === "publication" && data.publicationJobId && data.publicationReceiptSha256);
        $("cover-frame").max = data.frames - 1; $("cover-frame").value = data.coverFrame;
        $("publication-title").value = data.title; $("publication-description").value = data.description; $("publication-tags").value = data.tags.join(", ");
        $("publication-form").hidden = false;
        if (kind === "publication") {
            const prefix = `/api/creation/jobs/${encodeURIComponent(id)}/publication-files/`;
            $("publication-cover").src = prefix + "cover.png"; $("publication-cover").hidden = false;
            for (const file of ["cover.png", "title.txt", "description.txt", "tags.json", "publication.json"]) {
                const link = node("a", `下载 ${file}`); link.href = prefix + file; link.download = file; link.dataset.file = file; $("publication-downloads").append(link);
            }
        }
        controls();
    }
    async function openJob(id) {
        clearTimeout(state.timer); const epoch = state.epoch, view = ++state.view;
        state.job = id; save(); clearView();
        async function poll() {
            try {
                const job = await api(`/api/creation/jobs/${encodeURIComponent(id)}`);
                if (epoch !== state.epoch || view !== state.view) return;
                if (job.projectId !== state.project || job.jobId !== id) throw new Error("任务不属于当前项目。");
                $("job-status").textContent = `${kindLabel(job.kind)} · ${labels[job.status] || job.status}${job.error ? `：${job.error.message}（${job.error.code}）` : ""}`;
                if (job.status === "completed") {
                    if (job.kind === "package") {
                        const data = job.package || await api(`/api/creation/jobs/${encodeURIComponent(id)}/package`);
                        if (epoch !== state.epoch || view !== state.view) return;
                        if (data.publicationJobId) await loadPublication(data.publicationJobId, "publication", epoch, view);
                        if (epoch !== state.epoch || view !== state.view) return;
                        showPackage(data, id);
                    }
                    else if (job.kind === "narration") { narr.asset = checkedAsset(job.narrationAsset); notice("旁白已读取。选择方案或剪辑版本后，可在“旁白”面板挂接。"); }
                    else if (job.kind === "plan") showPlans(job);
                    else if (job.kind === "revision") { const editor = job.editor || await api(`/api/creation/jobs/${encodeURIComponent(id)}/edit?planId=${encodeURIComponent(job.planId || "")}`); if (epoch !== state.epoch || view !== state.view) return; await loadEditor(id, editor.planId, true); }
                    else if (["render", "publication"].includes(job.kind)) {
                        if (job.kind === "render" && job.artifact) showArtifact(job.artifact);
                        await loadPublication(id, job.kind, epoch, view);
                    }
                    void history(epoch);
                }
                else if (["pending", "running"].includes(job.status)) state.timer = setTimeout(poll, 1000);
            } catch (error) { if (epoch === state.epoch && view === state.view) notice(`任务回查失败：${error.message}。可从历史重新打开。`); }
        }
        await poll();
    }
    async function history(epoch = state.epoch) {
        const project = state.project; if (!project) return;
        try {
            const data = await api(`/api/creation/jobs?projectId=${encodeURIComponent(project)}`);
            if (epoch !== state.epoch) return;
            $("history").replaceChildren();
            for (const job of data.jobs.slice(0, 100)) {
                const button = node("button", `${kindLabel(job.kind)} · ${labels[job.status] || job.status} · ${humanTime(job.createdAt)}${job.error ? ` · ${job.error.message}` : ""}`);
                button.type = "button"; button.addEventListener("click", () => { void openJob(job.jobId); }); $("history").append(button);
            }
            if (!data.jobs.length) $("history").append(node("p", "此项目暂无创作任务。"));
        } catch (error) { if (epoch === state.epoch) notice(error.message); }
    }
    async function projectChanged(restoreJob = "") {
        const epoch = ++state.epoch; ++state.view; clearTimeout(state.timer);
        state.project = $("project").value; state.job = restoreJob; state.intents = {}; state.busy = false; clearTimeout(narr.timer); narr.job = null; narr.asset = null; save(); clearView(); $("runs").replaceChildren(); $("history").replaceChildren();
        if (!state.project) return;
        notice("正在读取可用素材…");
        try {
            const data = await api(`/api/runs?project=${encodeURIComponent(state.project)}`);
            if (epoch !== state.epoch) return;
            for (const run of data.runs.filter((r) => r.completedEligible === true)) {
                const label = node("label", ""), check = document.createElement("input"); check.type = "checkbox"; check.value = run.id; check.addEventListener("change", controls);
                label.append(check, document.createTextNode(`${run.sourceName} · 版本 ${run.id.slice(0, 8)}`)); $("runs").append(label);
            }
            notice($("runs").childElementCount ? "请选择素材，填写需求后生成方案。" : "此项目没有已完成分析的录像，暂不能生成方案。"); controls();
            void history(epoch); if (restoreJob && epoch === state.epoch) await openJob(restoreJob);
        } catch (error) { if (epoch === state.epoch) notice(error.message); }
    }
    async function submit(kind, payload) {
        if (state.busy) return;
        const epoch = state.epoch, view = state.view; state.busy = true; controls(); notice("正在提交任务…");
        try {
            const result = await api(`/api/creation/${{plan: "plans", revision: "revisions", render: "renders", publication: "publications", package: "packages"}[kind]}`, {...payload, requestId: requestId(kind, payload)});
            if (epoch !== state.epoch || view !== state.view) return;
            delete state.intents[kind]; notice("任务已保存，可刷新页面继续查看。"); await openJob(result.jobId); void history(epoch);
        } catch (error) { if (epoch === state.epoch && view === state.view) notice(`${error.message}。再次提交相同内容会复用请求，不重复创建任务。`); }
        finally { if (epoch === state.epoch) { state.busy = false; if (state.editor) showEditor(); controls(); } }
    }
    $("package-platform").addEventListener("change", () => { const profile = platformProfiles.find((p) => p.Platform === $("package-platform").value); if (profile) fillProfile(profile); });
    $("package-form").addEventListener("submit", (event) => {
        event.preventDefault(); const publication = state.publication; if (!publication?.publicationJobId || !publication.publicationReceiptSha256 || !packageProfile) return;
        const profile = structuredClone(packageProfile);
        for (const [id, , group, key] of packageFields) {
            const value = $(id).value;
            profile.Fields[group][key] = key === "fit" ? value : key === "requiredTags" ? [...new Set(value.split(/\n/).map((s) => s.trim()).filter(Boolean))] : value === "" ? null : Number(value);
        }
        if (JSON.stringify(profile.Fields) !== JSON.stringify(packageProfile.Fields)) { profile.RuleVersion = packageProfile.RuleVersion + "-edited-" + requestId("profile", profile.Fields).slice(0, 8); state.intents.profile.updatedAt ||= new Date().toISOString(); profile.UpdatedAt = state.intents.profile.updatedAt; }
        void submit("package", {publicationJobId: publication.publicationJobId, expectedPublicationReceiptSha256: publication.publicationReceiptSha256, profile});
    });
    $("use-cover-frame").addEventListener("click", () => {
        const video = $("artifact").querySelector("video"), data = state.publication;
        if (!data || !video || state.busy) return;
        $("cover-frame").value = Math.min(data.frames - 1, Math.max(0, Math.floor(video.currentTime * data.fps)));
    });
    $("publication-tags").addEventListener("input", () => $("publication-tags").setCustomValidity(""));
    $("publication-form").addEventListener("submit", (event) => {
        event.preventDefault(); const data = state.publication; if (!data) return;
        const tagText = $("publication-tags").value;
        const tags = tagText === data.tags.join(", ") ? [...data.tags] : [...new Set(tagText.split(/[,，\n]/).map((s) => s.trim()).filter(Boolean))];
        if (tags.length > 20 || tags.some((tag) => tag.length > 50)) { $("publication-tags").setCustomValidity("最多20项，每项最多50字。"); $("publication-tags").reportValidity(); return; }
        const coverFrame = Number($("cover-frame").value);
        if (!Number.isSafeInteger(coverFrame) || coverFrame < 0 || coverFrame >= data.frames) return;
        void submit("publication", {renderJobId: data.renderJobId, expectedRenderReceiptSha256: data.expectedRenderReceiptSha256, coverFrame, title: $("publication-title").value, description: $("publication-description").value, tags});
    });
    $("brief").addEventListener("submit", (event) => {
        event.preventDefault(); const brief = Object.fromEntries(new FormData(event.target));
        for (const key of ["platforms", "mandatoryTopics", "exclude"]) brief[key] = [...new Set(brief[key].split(/[,，\n]/).map((s) => s.trim()).filter(Boolean))];
        brief.targetDuration = Number(brief.targetDuration);
        void submit("plan", {projectId: state.project, runIds: Array.from($("runs").querySelectorAll("input:checked"), (c) => c.value), brief, fps: Number($("fps").value)});
    });
    $("render-form").addEventListener("submit", (event) => { event.preventDefault(); if (!state.selected || state.dirty || transitionError(state.editor)) return; const [width, height] = $("size").value.split(",").map(Number); void submit("render", {...state.selected, width, height, subtitleMode: $("subtitles").value}); });
    $("save-revision").addEventListener("click", () => {
        if (!state.editor || state.editing || transitionError(state.editor)) return;
        const editor = state.editor;
        if (Array.from([...($("audio-controls")?.querySelectorAll("input") || []), ...(editor.narrationChanged && editor.narration ? $("narration-controls")?.querySelectorAll("input") || [] : [])]).some((input) => !input.reportValidity())) return;
        const replacementFields = editor.candidateManifestSha256 ? {candidateManifestSha256: editor.candidateManifestSha256, replacements: editor.replacements.filter((r) => editor.clips.some((c) => c.clipId === r.targetClipId))} : {};
        void submit("revision", {...replacementFields, parentJobId: editor.parentJobId, planId: editor.planId, expectedParentReceiptSha256: editor.expectedParentReceiptSha256, clips: editor.clips.map(({clipId, startUs, endUs, speed, transitionIn}) => ({clipId, startUs, endUs, speed, transitionIn})), audioMix: editor.audioMix, ...(editor.narrationChanged ? {narration: editor.narration ?? null} : {}), subtitleOverrides: editor.subtitleOverrides.filter((item) => editor.clips.some((clip) => clip.clipId === item.clipId))});
    });
    $("project").addEventListener("change", () => { void projectChanged(); }); $("refresh").addEventListener("click", () => { void history(); if (state.job) void openJob(state.job); });
    void (async () => {
        try {
            let saved = {}; try { saved = JSON.parse(localStorage.getItem("creation-workspace-v1") || "{}"); } catch { /* Ignore an invalid saved selection. */ }
            void loadMusic(); void loadVoices(); void loadProfiles();
            const data = await api("/api/projects");
            for (const project of data.projects) { const option = node("option", project.name || project.path); option.value = project.path; $("project").append(option); }
            $("project").value = data.projects.some((p) => p.path === saved.project) ? saved.project : (data.projects[0]?.path || "");
            await projectChanged($("project").value === saved.project ? saved.job : "");
            if (!data.projects.length) notice("尚未发现已有项目，请先在素材工作台准备素材。");
        } catch (error) { notice(`无法读取项目：${error.message}`); }
    })();
})();
