"use strict";
const context = source.context;
const expected = source.template;
const controls = new Map();
const status = document.getElementById("status");
const video = document.getElementById("source-video");
const playState = document.getElementById("play-state");
const clockState = document.getElementById("clock-state");
const openSource = document.getElementById("open-source");
source.context.media.forEach(media => { media.videoUrl = new URL(media.videoUrl, location.href).href; });
let editRevision = 0, loadRevision = 0, playToken = 0, playing = null, preparing = 0;
let visibleGeneration = 0, visibleHeaderDuration = null, visibleValidatedGeneration = -1;
let visibleSeekedGeneration = -1, visibleDurationInvalid = false, visibleDurationReason = null, visibleClock = null;
const clocks = new Map();
const replayButtons = [];
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
  observation_invalid: "浏览器返回的原片时间信息不完整",
  clock_unavailable: "这段原片的时间不能建立浏览器映射",
};
const clone = value => JSON.parse(JSON.stringify(value));
const canonical = value => JSON.stringify(value, (key, item) => item && !Array.isArray(item) && typeof item === "object" ? Object.fromEntries(Object.keys(item).sort().map(name => [name, item[name]])) : item);
const same = (left, right) => canonical(left) === canonical(right);
const omit = (row, names) => Object.fromEntries(Object.entries(row).filter(([key]) => !names.includes(key)));
const fail = message => { throw new Error(message); };
function add(parent, tag, text) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  parent.append(node);
  return node;
}
function strictJson(text) {
  const result = JSON.parse(text);
  const tokens = text.match(/"(?:\\.|[^"\\])*"|[{}\[\],:]|true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g);
  let cursor = 0;
  function walk(depth) {
    if (depth > 64) fail("记录嵌套过深。");
    const token = tokens[cursor++];
    if (token === "{") {
      const names = new Set();
      while (tokens[cursor] !== "}") {
        const name = JSON.parse(tokens[cursor++]);
        if (names.has(name)) fail("记录包含重复字段。");
        names.add(name); cursor++; walk(depth + 1);
        if (tokens[cursor] === ",") cursor++;
      }
      cursor++;
    } else if (token === "[") {
      while (tokens[cursor] !== "]") {
        walk(depth + 1);
        if (tokens[cursor] === ",") cursor++;
      }
      cursor++;
    } else if (token.startsWith('"')) {
      if (!JSON.parse(token).isWellFormed()) fail("文字不是有效Unicode。");
    } else if (!["true", "false", "null"].includes(token) && !Number.isFinite(JSON.parse(token))) fail("记录包含无效数字。");
  }
  walk(0);
  return result;
}
function validate(record) {
  const rootEditable = ["recordedOn", "reviewer", "reviewed", "queries"];
  if (!record || Array.isArray(record) || typeof record !== "object" || !same(Object.keys(record).sort(), Object.keys(expected).sort()) || !same(omit(record, rootEditable), omit(expected, rootEditable))) fail("记录不属于这份固定结果。");
  if (typeof record.reviewed !== "boolean") fail("复核状态必须为是或否。");
  const metadata = record.recordedOn !== null;
  if (metadata !== (record.reviewer !== null)) fail("日期和填写人须同时填写或同时留空。");
  if (metadata) {
    if (typeof record.recordedOn !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(record.recordedOn) || Number(record.recordedOn.slice(0, 4)) < 1) fail("日期格式无效。");
    const date = new Date(record.recordedOn + "T00:00:00Z");
    if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== record.recordedOn) fail("日期不存在。");
    if (typeof record.reviewer !== "string" || !record.reviewer.trim() || Array.from(record.reviewer).length > 120) fail("请填写长度合适的填写人。");
  }
  if (!Array.isArray(record.queries) || record.queries.length !== expected.queries.length) fail("须保留全部固定查询。");
  record.queries.forEach((query, index) => {
    const original = expected.queries[index], definition = context.queries[index];
    if (!query || !same(Object.keys(query).sort(), ["queryId", "slots"]) || query.queryId !== original.queryId || !Array.isArray(query.slots) || query.slots.length !== 10) fail("查询或十个位置不同。");
    const references = definition.references.map(row => row.humanEventId);
    query.slots.forEach((row, position) => {
      const basis = original.slots[position];
      if (!row || !same(Object.keys(row).sort(), Object.keys(basis).sort()) || !same(omit(row, ["grade", "humanEventId", "reason"]), omit(basis, ["grade", "humanEventId", "reason"]))) fail("候选身份、区间或位置已改变。");
      if (basis.state !== "candidate" && [row.grade, row.humanEventId, row.reason].some(value => value !== null)) fail("缺位和已知重复不能补位判分。");
      if (row.grade !== null && (!Number.isInteger(row.grade) || row.grade < 0 || row.grade > 3)) fail("评分只能为0–3或未判定。");
      if (row.humanEventId !== null && (typeof row.humanEventId !== "string" || !references.includes(row.humanEventId))) fail("独立事件不属于该查询的冻结参考。");
      if (row.grade === null && row.humanEventId !== null) fail("未判分不能指定独立事件。");
      if (row.reason !== null && (typeof row.reason !== "string" || !row.reason.trim() || Array.from(row.reason).length > 4096)) fail("理由须为1–4096字。");
      if (row.grade !== null && (row.reason === null || row.grade >= 2 && row.humanEventId === null)) fail("评分需要理由，2/3还需要独立事件。");
      if ((row.grade !== null || row.reason !== null || record.reviewed) && !metadata) fail("请先填写日期和填写人。");
    });
  });
  return record;
}
function clockStateOf(media) {
  return clocks.get(media.runId) || {state: "probing", clock: null, reason: null};
}
function clockReason(state) {
  if (state.state === "probing") return "正在核对原片时钟…";
  if (state.reason === "clock_unavailable") return REASONS.clock_unavailable + "，请打开本机原片手动核对；评分仍按原区间。";
  return `${REASONS[state.reason] || "浏览器时间无法核对为规范源时间"}，请打开本机原片手动核对；评分仍按原区间。`;
}
function refreshClockState() {
  const states = context.media.map(media => ({media, state: clockStateOf(media)}));
  if (states.some(row => row.state.state === "probing")) clockState.textContent = "正在核对这段原片的浏览器时钟；核对完成前不能自动播放。";
  else if (states.some(row => row.state.state !== "ready")) clockState.textContent = "有原片的浏览器时间无法核对为规范源时间；请打开本机原片手动核对，评分仍按原区间。";
  else clockState.textContent = "已把浏览器播放位置核对为规范源时间，可以自动播放规范区间；评分仍须人工判断。";
  const unavailable = states.find(row => row.state.state !== "ready");
  if (unavailable) { openSource.href = unavailable.media.videoUrl; openSource.hidden = false; }
  for (const entry of replayButtons) {
    const state = clockStateOf(entry.media);
    const ready = state.state === "ready" && state.clock;
    const replayable = ready && SourceClock.intervalReplayable(state.clock, entry.startUs, entry.endUs);
    entry.button.disabled = !replayable;
    if (!ready) entry.note.textContent = clockReason(state);
    else if (!replayable) entry.note.textContent = "此规范区间超出原片有画面的部分，不能可靠自动回看；请打开本机原片手动核对。";
    else entry.note.textContent = "";
  }
  const blocked = replayButtons.find(entry => entry.button.disabled);
  if (blocked && !unavailable) { openSource.href = blocked.media.videoUrl; openSource.hidden = false; }
}
function play(media, slot, query) {
  const token = ++playToken;
  video.pause(); playing = null;
  openSource.href = media.videoUrl; openSource.hidden = false;
  const state = clockStateOf(media);
  if (state.state !== "ready" || !state.clock) { playState.textContent = clockReason(state); return; }
  const clock = state.clock;
  if (!SourceClock.intervalReplayable(clock, slot.startUs, slot.endUs)) { playState.textContent = "此规范区间超出原片有画面的部分，不能可靠自动回看；请打开本机原片手动核对。"; return; }
  const start = SourceClock.sourceUsToPlayerSeconds(clock, slot.startUs);
  const end = SourceClock.sourceUsToPlayerSeconds(clock, slot.endUs);
  if (start === null || end === null) { playState.textContent = "规范源区间不能换算为浏览器位置，请打开本机原片手动核对。"; return; }
  void startPlayback(token, media, clock, slot, query, start, end);
}
function durationProblemMessage(reason) {
  if (reason === "duration_unavailable") return "浏览器读到的原片时长无效，请重新载入原片或打开本机原片手动核对。";
  return "浏览器读到的原片时长发生了意外变化，请重新载入原片或打开本机原片手动核对。";
}
async function startPlayback(token, media, clock, slot, query, start, end) {
  const expectedUrl = media.videoUrl;
  let generation = visibleGeneration;
  const current = () => token === playToken
    && generation === visibleGeneration
    && video.currentSrc === expectedUrl;
  try {
    preparing += 1;
    try {
      await SourceClock.prepare(video, expectedUrl);
    } finally {
      preparing -= 1;
    }
    // Freeze the load generation produced by this prepare; every later await has to still be
    // on it, so a reload (even of the same URL) cannot let a late seek validate a new element
    // and play the older request.
    generation = visibleGeneration;
    if (token !== playToken) return;
    if (!current()) return;
    if (visibleDurationInvalid) {
      playState.textContent = durationProblemMessage(visibleDurationReason);
      return;
    }
    if (visibleValidatedGeneration !== generation || video.currentSrc !== expectedUrl) {
      // Validate the element that will really play this interval, bound to the frozen load
      // generation: the header duration recorded when that load's metadata arrived (before
      // any seek could legitimately change it) and the position it clamps a low seek to.
      if (video.currentSrc !== expectedUrl) {
        playState.textContent = "浏览器实际载入的原片与当前查询的原片不同，请重新选择查询或打开本机原片核对。";
        return;
      }
      if (!Number.isFinite(visibleHeaderDuration) || Math.abs(visibleHeaderDuration * 1000000 - clock.durationUs) > clock.durationToleranceUs) {
        playState.textContent = "浏览器的原片时长与保存的原片不一致，请打开本机原片手动核对。";
        return;
      }
      const axis = await SourceClock.settle(video, 0.000001);
      if (!current()) return;
      if (axis === null || Math.abs(axis * 1000000 - clock.originUs) > clock.axisToleranceUs) {
        playState.textContent = "浏览器的播放起点与保存的原片起点不一致，请打开本机原片手动核对。";
        return;
      }
      if (!(video.videoWidth > 0)) {
        playState.textContent = "浏览器还没有准备好这段原片的画面，请稍后重试或打开本机原片手动核对。";
        return;
      }
      visibleValidatedGeneration = generation;
      visibleClock = clock;
    }
    const settled = await SourceClock.settle(video, start);
    if (!current()) return;
    if (settled === null || Math.abs(settled - start) > clock.axisToleranceUs / 1000000) {
      playState.textContent = "浏览器未能定位到规范区间起点，请打开本机原片手动核对。";
      return;
    }
    if (video.seeking) {
      playState.textContent = "浏览器仍在定位原片，请稍后重试或打开本机原片手动核对。";
      return;
    }
  } catch (error) {
    if (token === playToken && generation === visibleGeneration) playState.textContent = "浏览器不能读取这段原片，请用本机播放器核对；评分保持原区间。";
    return;
  }
  if (!current()) return;
  playing = {url: expectedUrl, end, token, generation, reachesEnd: clock.durationUs - slot.endUs <= 1000};
  playState.textContent = `${query.text} · ${slot.label || `第${slot.slot}位`} · 规范源 ${(slot.startUs / 1000000).toFixed(3)}–${(slot.endUs / 1000000).toFixed(3)}秒`;
  try {
    await video.play();
  } catch (error) {
    if (token === playToken) { playing = null; playState.textContent = "浏览器未能播放，请打开本机原片核对这段区间。"; }
  }
}
video.addEventListener("timeupdate", () => {
  if (playing && playing.token === playToken && playing.generation === visibleGeneration && video.currentSrc === playing.url && video.currentTime >= playing.end) { video.pause(); playing = null; }
});
video.addEventListener("ended", () => {
  if (playing && playing.token === playToken && playing.generation === visibleGeneration && video.currentSrc === playing.url) {
    const reached = playing.reachesEnd;
    playing = null;
    playState.textContent = reached ? "已播放到原片结尾，请核对是否覆盖完整区间。" : "播放到原片结尾前未能按区间末尾暂停，请打开本机原片手动核对。";
  }
});
video.addEventListener("seeking", () => {
  if (playing && playing.token === playToken && playing.generation === visibleGeneration && video.currentSrc === playing.url && video.currentTime > playing.end) { video.pause(); playing = null; }
});
video.addEventListener("error", () => { playing = null; playState.textContent = "浏览器不能播放此原片，请用本机播放器核对；评分保持原区间。"; });
video.addEventListener("loadstart", () => {
  // A new load generation: forget the previous element validation and its pre-seek duration.
  // A load the page did not ask for is an external reload: cancel in-flight requests and any
  // interval state so a late seek from the old request can never act on the new element.
  visibleGeneration += 1; visibleHeaderDuration = null; visibleValidatedGeneration = -1;
  visibleSeekedGeneration = -1; visibleDurationInvalid = false; visibleDurationReason = null;
  if (preparing === 0) { playToken += 1; playing = null; }
});
video.addEventListener("loadedmetadata", () => {
  if (visibleHeaderDuration === null && Number.isFinite(video.duration) && video.duration > 0) visibleHeaderDuration = video.duration;
});
video.addEventListener("emptied", () => {
  visibleGeneration += 1; visibleHeaderDuration = null; visibleValidatedGeneration = -1;
  visibleSeekedGeneration = -1; visibleDurationInvalid = false; visibleDurationReason = null;
  if (preparing === 0) { playToken += 1; playing = null; }
});
video.addEventListener("seeked", () => { visibleSeekedGeneration = visibleGeneration; });
video.addEventListener("durationchange", () => {
  // Recheck every reported change against the clock; only the measured bounded non-zero-PTS
  // growth after a seek on this element may stay valid. Any shrink, non-finite value or
  // unexpected growth revokes the generation before a replay can use it.
  if (visibleValidatedGeneration !== visibleGeneration || !visibleClock) return;
  const verdict = SourceClock.durationChangeVerdict(visibleClock, video.duration, visibleSeekedGeneration === visibleGeneration);
  if (verdict === null) return;
  visibleDurationInvalid = true; visibleDurationReason = verdict;
  visibleValidatedGeneration = -1; visibleClock = null;
});
for (const media of context.media) {
  const candidates = SourceClock.clockCandidates(media);
  if (!candidates.length) { clocks.set(media.runId, {state: "unavailable", clock: null, reason: "clock_unavailable"}); continue; }
  clocks.set(media.runId, {state: "probing", clock: null, reason: null});
  SourceClock.establish(candidates, media.videoUrl).then(verdict => {
    clocks.set(media.runId, {state: verdict.established ? "ready" : "unavailable", clock: verdict.clock, reason: verdict.reason});
    refreshClockState();
  });
}
const container = document.getElementById("queries");
context.queries.forEach(query => {
  const section = add(container, "section"); section.dataset.query = query.queryId;
  add(section, "h2", query.text);
  add(section, "p", `${query.kind === "main" ? "主查询" : query.kind === "sparse" ? "少例查询" : "负例查询"} · 已冻结参考 ${query.references.length} 个 · 十个位置`);
  if (query.status === "failed") add(section, "p", "原查询执行失败；这些位置不可判分，不当作成功零命中。").className = "notice";
  const details = add(section, "details"); add(details, "summary", "查看已冻结的人工参考");
  const queryMedia = context.media.find(row => row.runId === query.runId);
  query.references.forEach(reference => {
    const p = add(details, "p", `${reference.humanEventId} · ${reference.reason}`);
    add(p, "span", " · " + reference.usableRanges.map(range => `${seconds(range.startUs)}–${seconds(range.endUs)}秒`).join("、"));
    // Replays a frozen reference range through the same clock-verified player as candidates.
    reference.usableRanges.forEach(range => {
      const replay = add(details, "button", `回看参考 ${reference.humanEventId} ${seconds(range.startUs)}–${seconds(range.endUs)}秒`);
      replay.type = "button"; replay.disabled = true; replay.className = "reference-replay";
      const target = {label: `参考 ${reference.humanEventId}`, startUs: range.startUs, endUs: range.endUs};
      replay.addEventListener("click", () => play(queryMedia, target, query));
      const note = add(details, "p", ""); note.className = "empty"; note.dataset.clock = "reference-note";
      replayButtons.push({button: replay, note, media: queryMedia, startUs: range.startUs, endUs: range.endUs});
    });
  });
  const tally = add(section, "p", ""); tally.className = "tally"; tally.dataset.tally = query.queryId;
  query.slots.forEach(slot => {
    const card = add(section, "div"); card.className = "slot"; card.dataset.slot = slot.slot;
    add(card, "h3", `第${slot.slot}位`);
    if (slot.state === "missing") { add(card, "p", "缺位，保留固定位置。没有候选可判分。").className = "empty"; return; }
    add(card, "p", `${(slot.startUs / 1000000).toFixed(3)}–${(slot.endUs / 1000000).toFixed(3)}秒 · 原排名 ${slot.reportedRank}`);
    add(card, "p", "模型描述（需回看）：" + slot.facts.join("；"));
    const overlaps = query.references.flatMap(reference => reference.usableRanges
      .filter(range => range.startUs < slot.endUs && slot.startUs < range.endUs)
      .map(range => `${reference.humanEventId}（${seconds(range.startUs)}–${seconds(range.endUs)}秒）`));
    if (overlaps.length) add(card, "p", `与冻结参考在时间上重叠：${overlaps.join("、")}。只是时间重叠，请回看后自己判断，不会自动填写。`).className = "overlap";
    const media = context.media.find(row => row.runId === query.runId);
    const button = add(card, "button", "播放此区间"); button.type = "button"; button.disabled = true;
    button.addEventListener("click", () => play(media, slot, query));
    const note = add(card, "p", "正在核对原片时钟…"); note.className = "empty"; note.dataset.clock = "note";
    replayButtons.push({button, note, media, startUs: slot.startUs, endUs: slot.endUs});
    if (slot.state === "known_duplicate") { add(card, "p", "已知重复事件，保留此位，不再填写第二份评分。").className = "empty"; return; }
    const fields = add(card, "div"); fields.className = "fields";
    const gradeLabel = add(fields, "label", "评分"); const grade = add(gradeLabel, "select"); grade.dataset.field = "grade";
    [["", "未判定"], ["0", "0 · 无关"], ["1", "1 · 相关但不可用"], ["2", "2 · 可用"], ["3", "3 · 高度相关"]].forEach(([value, label]) => { const option = add(grade, "option", label); option.value = value; if (!query.references.length && ["2", "3"].includes(value)) option.disabled = true; });
    const humanLabel = add(fields, "label", "对应的独立事件"); const human = add(humanLabel, "select"); human.dataset.field = "humanEventId";
    add(human, "option", "未指定").value = "";
    query.references.forEach(reference => { add(human, "option", `${reference.humanEventId} · ${reference.reason}`).value = reference.humanEventId; });
    const reasonLabel = add(card, "label", "理由／待核对备注"); const reason = add(reasonLabel, "textarea"); reason.dataset.field = "reason";
    const warning = add(card, "p", ""); warning.className = "slot-warning"; warning.hidden = true;
    controls.set(`${query.queryId}:${slot.slot}`, {grade, human, reason, warning, card});
  });
});
function seconds(microseconds) { return (microseconds / 1000000).toFixed(3); }
function tallyQuery(query) {
  const references = new Map(query.references.map(reference => [reference.humanEventId, reference]));
  const duration = context.media.find(row => row.runId === query.runId)?.durationUs;
  const seenEvents = new Set(), usableGroups = new Map(), usefulEvents = new Set(), warnings = new Map();
  let duplicates = 0, unjudged = 0, missing = 0, needsEvent = 0;
  for (const slot of query.slots) {
    if (slot.state === "missing") { missing += 1; continue; }
    const input = controls.get(`${query.queryId}:${slot.slot}`);
    const grade = input && input.grade.value !== "" ? Number(input.grade.value) : null;
    const reference = grade === null ? undefined : references.get(input.human.value);
    const group = reference ? reference.independenceGroup : null;
    const duplicate = seenEvents.has(slot.eventId) || (group !== null && usableGroups.has(group));
    seenEvents.add(slot.eventId);
    if (duplicate) {
      duplicates += 1;
      if (group !== null && usableGroups.has(group) && grade >= 2) warnings.set(slot.slot, `这一位与第${usableGroups.get(group)}位选了同一个独立事件（或同一动作归组）。如果确实是同一个动作，保持即可，第8步按重复处理。`);
    } else if (grade === null) unjudged += 1;
    if (grade !== null && grade >= 2 && !reference) { needsEvent += 1; warnings.set(slot.slot, "评2或3分时还要选择对应的独立事件，否则不能保存。"); }
    const useful = grade !== null && grade >= 2 && !duplicate && Number.isSafeInteger(duration) && slot.endUs <= duration;
    if (useful && group !== null && !usableGroups.has(group)) usableGroups.set(group, slot.slot);
    if (useful && reference) usefulEvents.add(reference.humanEventId);
  }
  return {useful: usefulEvents.size, duplicates, unjudged, missing, needsEvent, warnings};
}
function refreshTallies() {
  context.queries.forEach(query => {
    const line = document.querySelector(`[data-tally="${CSS.escape(query.queryId)}"]`);
    if (!line) return;
    const result = tallyQuery(query);
    Object.assign(line.dataset, {useful: result.useful, duplicates: result.duplicates, unjudged: result.unjudged, missing: result.missing});
    // Neutral counts only: no pass threshold or "how many more" while a person is grading,
    // so the count can never pull a borderline clip toward "usable".
    line.textContent = query.status === "failed"
      ? "原查询执行失败，这些位置不计分。"
      : `当前填写计数：评为可用的不同独立事件 ${result.useful} 个；未判定 ${result.unjudged} 位，重复 ${result.duplicates} 位，缺位 ${result.missing} 位${result.needsEvent ? `，${result.needsEvent} 位评了2/3分但没选独立事件` : ""}。请只按画面判断，计分以第8步报告为准。`;
    query.slots.forEach(slot => {
      const input = controls.get(`${query.queryId}:${slot.slot}`);
      if (!input) return;
      const message = result.warnings.get(slot.slot);
      input.warning.hidden = !message; input.warning.textContent = message || "";
    });
  });
}
// Keyboard: J/K move between scorable positions, P replays the current one. Grade selects
// keep their own type-ahead (digits 0-3); text fields never trigger shortcuts.
const scorable = [];
context.queries.forEach(query => query.slots.forEach(slot => { const input = controls.get(`${query.queryId}:${slot.slot}`); if (input) scorable.push({query, slot, input}); }));
let currentSlot = -1;
document.addEventListener("focusin", event => {
  const index = scorable.findIndex(entry => entry.input.card.contains(event.target));
  if (index >= 0) currentSlot = index;
});
document.addEventListener("keydown", event => {
  if (event.defaultPrevented || event.repeat || event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return;
  const target = event.target;
  if (target instanceof HTMLElement && (target.isContentEditable || target.tagName === "TEXTAREA" || (target.tagName === "INPUT" && !["checkbox", "file", "button"].includes(target.type)))) return;
  // The event drop-down keeps its own type-ahead: event names may start with J, K or P.
  if (target instanceof HTMLElement && target.dataset.field === "humanEventId") return;
  if (!scorable.length) return;
  if (event.code === "KeyJ" || event.code === "KeyK") {
    currentSlot = Math.max(0, Math.min(scorable.length - 1, currentSlot + (event.code === "KeyK" ? 1 : -1)));
    const entry = scorable[currentSlot];
    entry.input.grade.focus(); entry.input.card.scrollIntoView({block: "center"});
  } else if (event.code === "KeyP" && currentSlot >= 0) {
    const entry = scorable[currentSlot];
    play(context.media.find(row => row.runId === entry.query.runId), entry.slot, entry.query);
  } else return;
  event.preventDefault();
});
refreshClockState();
refreshTallies();
document.addEventListener("input", () => { editRevision++; refreshTallies(); });
document.addEventListener("change", refreshTallies);
document.getElementById("reviewed").addEventListener("change", () => { editRevision++; });
function collect() {
  const record = clone(expected);
  record.recordedOn = document.getElementById("recordedOn").value || null;
  record.reviewer = document.getElementById("reviewer").value.trim() || null;
  record.reviewed = document.getElementById("reviewed").checked;
  record.queries.forEach(query => query.slots.forEach(row => {
    const input = controls.get(`${query.queryId}:${row.slot}`);
    if (!input) return;
    row.grade = input.grade.value === "" ? null : Number(input.grade.value);
    row.humanEventId = input.human.value || null;
    row.reason = input.reason.value.trim() || null;
  }));
  return validate(record);
}
document.getElementById("download-record").addEventListener("click", () => {
  try {
    const record = collect(), text = JSON.stringify(record, null, 2) + "\n";
    if (new TextEncoder().encode(text).length > 4194304) fail("记录不能超过4MiB。");
    const url = URL.createObjectURL(new Blob([text], {type: "application/json;charset=utf-8"}));
    const link = add(document.body, "a"); link.href = url; link.download = "benchmark-review-record.json"; link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    const count = record.queries.reduce((total, query) => total + query.slots.filter(slot => slot.grade !== null).length, 0);
    status.textContent = `记录已下载，${count}个位置已填写评分；未判定仍为空，不自动通过验收。`;
  } catch (error) { status.textContent = error.message; }
});
document.getElementById("load-record").addEventListener("change", async event => {
  const file = event.target.files[0]; if (!file) return;
  const token = ++loadRevision, edits = editRevision;
  try {
    if (file.size > 4194304) fail("记录不能超过4MiB。");
    const record = validate(strictJson(await file.text()));
    if (token !== loadRevision || edits !== editRevision) fail("载入期间已有新编辑，保留当前填写内容。");
    document.getElementById("recordedOn").value = record.recordedOn || "";
    document.getElementById("reviewer").value = record.reviewer || "";
    document.getElementById("reviewed").checked = record.reviewed;
    record.queries.forEach(query => query.slots.forEach(row => {
      const input = controls.get(`${query.queryId}:${row.slot}`); if (!input) return;
      input.grade.value = row.grade === null ? "" : String(row.grade); input.human.value = row.humanEventId || ""; input.reason.value = row.reason || "";
    }));
    refreshTallies();
    editRevision++; status.textContent = "记录已载入，可以继续填写；没有新增验收结论。";
  } catch (error) { status.textContent = "无法载入：" + error.message; }
  finally { if (token === loadRevision) event.target.value = ""; }
});
