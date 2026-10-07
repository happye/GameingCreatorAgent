"use strict";
const context = source.context;
const expected = source.template;
const controls = new Map();
const status = document.getElementById("status");
const video = document.getElementById("source-video");
const playState = document.getElementById("play-state");
let editRevision = 0, loadRevision = 0, playRevision = 0, playing = null;
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
function play(media, slot, query) {
  const revision = ++playRevision;
  video.pause(); playing = null;
  const link = document.getElementById("open-source");
  link.href = media.videoUrl; link.hidden = false;
  if (!media.automaticPlaybackSupported) { playState.textContent = "这段原片的时钟尚未联调，请手动核对原区间。"; return; }
  const start = slot.startUs / 1000000, end = slot.endUs / 1000000;
  const ready = () => {
    if (revision !== playRevision || video.currentSrc !== media.videoUrl) return;
    playing = {url: media.videoUrl, end};
    video.currentTime = start;
    playState.textContent = `${query.text} · 第${slot.slot}位 · ${start.toFixed(3)}–${end.toFixed(3)}秒`;
    video.play().catch(() => { if (revision === playRevision) playState.textContent = "浏览器未能播放，请打开本机原片核对这段区间。"; });
  };
  if (video.currentSrc === media.videoUrl && video.readyState >= 1) ready();
  else { video.addEventListener("loadedmetadata", ready, {once: true}); video.src = media.videoUrl; video.load(); }
}
video.addEventListener("timeupdate", () => { if (playing && video.currentSrc === playing.url && video.currentTime >= playing.end) { video.pause(); playing = null; } });
video.addEventListener("error", () => { playing = null; playState.textContent = "浏览器不能播放此原片，请用本机播放器核对；评分保持原区间。"; });
video.addEventListener("seeking", () => { if (playing && video.currentTime > playing.end) { video.pause(); playing = null; } });
const container = document.getElementById("queries");
context.queries.forEach(query => {
  const section = add(container, "section"); section.dataset.query = query.queryId;
  add(section, "h2", query.text);
  add(section, "p", `${query.kind === "main" ? "主查询" : query.kind === "sparse" ? "少例查询" : "负例查询"} · 已冻结参考 ${query.references.length} 个 · 十个位置`);
  if (query.status === "failed") add(section, "p", "原查询执行失败；这些位置不可判分，不当作成功零命中。").className = "notice";
  const details = add(section, "details"); add(details, "summary", "查看已冻结的人工参考");
  query.references.forEach(reference => { const p = add(details, "p", `${reference.humanEventId} · ${reference.reason}`); add(p, "span", " · " + reference.usableRanges.map(range => `${(range.startUs / 1000000).toFixed(3)}–${(range.endUs / 1000000).toFixed(3)}秒`).join("、")); });
  query.slots.forEach(slot => {
    const card = add(section, "div"); card.className = "slot"; card.dataset.slot = slot.slot;
    add(card, "h3", `第${slot.slot}位`);
    if (slot.state === "missing") { add(card, "p", "缺位，保留固定位置。没有候选可判分。").className = "empty"; return; }
    add(card, "p", `${(slot.startUs / 1000000).toFixed(3)}–${(slot.endUs / 1000000).toFixed(3)}秒 · 原排名 ${slot.reportedRank}`);
    add(card, "p", "模型描述（需回看）：" + slot.facts.join("；"));
    const media = context.media.find(row => row.runId === query.runId);
    const button = add(card, "button", "播放此区间"); button.type = "button";
    button.addEventListener("click", () => play(media, slot, query));
    if (slot.state === "known_duplicate") { add(card, "p", "已知重复事件，保留此位，不再填写第二份评分。").className = "empty"; return; }
    const fields = add(card, "div"); fields.className = "fields";
    const gradeLabel = add(fields, "label", "评分"); const grade = add(gradeLabel, "select"); grade.dataset.field = "grade";
    [["", "未判定"], ["0", "0 · 无关"], ["1", "1 · 相关但不可用"], ["2", "2 · 可用"], ["3", "3 · 高度相关"]].forEach(([value, label]) => { const option = add(grade, "option", label); option.value = value; if (!query.references.length && ["2", "3"].includes(value)) option.disabled = true; });
    const humanLabel = add(fields, "label", "对应的独立事件"); const human = add(humanLabel, "select"); human.dataset.field = "humanEventId";
    add(human, "option", "未指定").value = "";
    query.references.forEach(reference => { add(human, "option", `${reference.humanEventId} · ${reference.reason}`).value = reference.humanEventId; });
    const reasonLabel = add(card, "label", "理由／待核对备注"); const reason = add(reasonLabel, "textarea"); reason.dataset.field = "reason";
    controls.set(`${query.queryId}:${slot.slot}`, {grade, human, reason});
  });
});
document.addEventListener("input", () => { editRevision++; });
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
    editRevision++; status.textContent = "记录已载入，可以继续填写；没有新增验收结论。";
  } catch (error) { status.textContent = "无法载入：" + error.message; }
  finally { if (token === loadRevision) event.target.value = ""; }
});
