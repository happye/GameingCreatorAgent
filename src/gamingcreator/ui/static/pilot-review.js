"use strict";
const dimensions = Object.keys(context.labels);
const editable = new Set([...dimensions, "reviewedTemporalEntityIds", "statement"]);
const rootEditable = new Set(["recordedOn", "reviewer", "cases"]);
const controls = new Map();
const status = document.getElementById("status");
const clone = value => JSON.parse(JSON.stringify(value));
const canonical = value => JSON.stringify(value, (key, item) => {
  if (item && !Array.isArray(item) && typeof item === "object") {
    return Object.fromEntries(Object.keys(item).sort().map(name => [name, item[name]]));
  }
  return item;
});
const same = (left, right) => canonical(left) === canonical(right);
const readonly = (row, excluded) => Object.fromEntries(Object.entries(row).filter(([key]) => !excluded.has(key)));
function add(parent, tag, text) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  parent.append(element);
  return element;
}
function fail(message) { throw new Error(message); }
function strictJson(text) {
  const value = JSON.parse(text);
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
        names.add(name);
        cursor++;
        walk(depth + 1);
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
      if (!JSON.parse(token).isWellFormed()) fail("文字包含无效Unicode。");
    } else if (!["true", "false", "null"].includes(token) && !Number.isFinite(JSON.parse(token))) {
      fail("记录包含无效数字。");
    }
  }
  walk(0);
  return value;
}
function validate(record) {
  const expected = context.template;
  if (!record || Array.isArray(record) || typeof record !== "object" ||
      !same(Object.keys(record).sort(), Object.keys(expected).sort()) ||
      !same(readonly(record, rootEditable), readonly(expected, rootEditable))) {
    fail("记录来源或字段与本页不一致，请使用对应的记录。");
  }
  const hasDate = record.recordedOn !== null;
  if (hasDate !== (record.reviewer !== null)) fail("日期和填写人须同时填写或同时留空。");
  if (hasDate) {
    if (typeof record.recordedOn !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(record.recordedOn) ||
        Number(record.recordedOn.slice(0, 4)) < 1) fail("日期格式不正确。");
    const date = new Date(record.recordedOn + "T00:00:00Z");
    if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== record.recordedOn) fail("日期不存在。");
    if (typeof record.reviewer !== "string" || !record.reviewer.trim() || Array.from(record.reviewer).length > 120) fail("请填写长度合适的填写人。");
  }
  if (!Array.isArray(record.cases) || record.cases.length !== expected.cases.length) fail("须保留原来的两个候选。");
  const seen = new Set();
  for (const row of record.cases) {
    const source = expected.cases.find(item => item.caseId === row?.caseId);
    if (!source || seen.has(row.caseId) || !same(Object.keys(row).sort(), Object.keys(source).sort()) ||
        !same(readonly(row, editable), readonly(source, editable))) fail("候选、模型结果或原画面已改变。");
    seen.add(row.caseId);
    if (dimensions.some(key => row[key] !== null && typeof row[key] !== "boolean")) fail("判断只可选是、否或未核对。");
    const targets = row.reviewedTemporalEntityIds;
    const allowed = controls.get(row.caseId).entityIds;
    if (targets !== null && (!Array.isArray(targets) || !targets.length || targets.length > 72 ||
        targets.some(id => typeof id !== "string" || !allowed.includes(id)) || new Set(targets).size !== targets.length)) fail("核对实体须属于当前新版结果且不能重复。");
    if (row.statement !== null && (typeof row.statement !== "string" || !row.statement.trim() || Array.from(row.statement).length > 2048)) fail("说明须为1–2048字的文字。");
    const judged = dimensions.some(key => row[key] !== null);
    const filled = judged || targets !== null || row.statement !== null;
    if (source.temporalPayloadHash === null && filled) fail("新版暂无结果，这组判断须留空。");
    if (filled && !hasDate) fail("填写核对内容前须登记日期和填写人。");
    if (judged && row.statement === null) fail("填写判断时请说明画面依据。");
  }
  return record;
}
for (const caseData of context.comparison.cases) {
  const section = add(document.getElementById("cases"), "section");
  const interval = caseData.sourceRange;
  add(section, "h2", `${interval.startUs / 1000000}–${(interval.endUs - 1) / 1000000} 秒`);
  add(section, "p", caseData.reviewPurpose);
  add(section, "p", "本组查询：" + context.queryLabels[caseData.caseId]);
  const frames = add(section, "div"); frames.className = "frames";
  for (const frame of caseData.frames) {
    const figure = add(frames, "figure");
    const img = add(figure, "img"); img.src = frame.imageDataUrl;
    img.alt = `源视频 ${frame.sourceUs / 1000000} 秒原画面`;
    add(figure, "figcaption", `${frame.sourceUs / 1000000} 秒`);
  }
  const old = add(section, "details"); add(old, "summary", "旧版描述及已有意见");
  const descriptions = add(old, "ul");
  for (const actor of caseData.legacy.descriptions) {
    const li = add(descriptions, "li", actor.description);
    if (!actor.feedback.length) add(li, "p", "尚未人工判定");
    for (const feedback of actor.feedback) add(li, "p", feedback.statement);
  }
  const saved = caseData.temporal.payloadHash !== null;
  const entities = caseData.temporal.scene?.entities || [];
  const fieldset = add(section, "fieldset"); fieldset.disabled = !saved;
  add(fieldset, "legend", "新版人工判断");
  const rowControls = {fields: {}, entityIds: entities.map(entity => entity.entityId), checkboxes: [], statement: null};
  for (const key of dimensions) {
    const label = add(fieldset, "label", context.labels[key][0]);
    const select = add(label, "select"); select.dataset.dimension = key;
    for (const [value, text] of [["", "未核对"], ["true", context.labels[key][1]], ["false", context.labels[key][2]]]) {
      const option = add(select, "option", text); option.value = value;
    }
    rowControls.fields[key] = select;
  }
  for (const entity of entities) {
    const label = add(fieldset, "label");
    const checkbox = add(label, "input"); checkbox.type = "checkbox"; checkbox.value = entity.entityId;
    const kind = {actor: "角色", object: "物品", unknown: "未确定"}[entity.classification.kind];
    label.append(document.createTextNode(` ${entity.entityId}：${entity.description}（${kind}）`));
    rowControls.checkboxes.push(checkbox);
  }
  const note = add(fieldset, "label", "画面依据与说明");
  rowControls.statement = add(note, "textarea");
  controls.set(caseData.caseId, rowControls);
  if (!saved) { const message = add(section, "p", "未执行／暂无新版结果，这组暂不能填写判断。"); message.className = "notice"; }
  const details = add(section, "details"); add(details, "summary", "新版分类、遮挡与切镜依据");
  if (!saved) add(details, "p", "暂无真实结果");
  else {
    const scene = caseData.temporal.scene;
    const times = new Map(caseData.frames.map(frame => [frame.evidenceId, frame.sourceUs / 1000000]));
    const visibility = {visible: "可见", partially_occluded: "部分遮挡", occluded: "被遮挡", unknown: "不确定"};
    const kinds = {actor: "角色", object: "物品", unknown: "未确定"};
    for (const entity of entities) {
      add(details, "p", `${entity.description}；分类：${kinds[entity.classification.kind]}。依据：${entity.classification.reason}`);
      for (const observation of entity.observations) add(details, "p", `${times.get(observation.evidenceId)} 秒：${visibility[observation.visibility]}；${observation.location}`);
    }
    for (const boundary of scene.transitions) {
      const state = {continuous: "连续画面", cut: "切镜", unknown: "不确定"}[boundary.state];
      add(details, "p", `${times.get(boundary.beforeId)}→${times.get(boundary.afterId)} 秒：${state}。${boundary.reason}`);
    }
    for (const owner of scene.owners) {
      const support = owner.status === "observed" ? "有画面支持的持有关系" : "待核对的持有关系";
      add(details, "p", `${support}：${owner.actorId} 与 ${owner.objectId}。${owner.reason}`);
    }
  }
}
document.getElementById("download-record").addEventListener("click", () => {
  try {
    const record = clone(context.template);
    record.recordedOn = document.getElementById("recordedOn").value || null;
    record.reviewer = document.getElementById("reviewer").value || null;
    for (const row of record.cases) {
      const input = controls.get(row.caseId);
      for (const key of dimensions) row[key] = input.fields[key].value === "" ? null : input.fields[key].value === "true";
      const targets = input.checkboxes.filter(item => item.checked).map(item => item.value);
      row.reviewedTemporalEntityIds = targets.length ? targets : null;
      row.statement = input.statement.value || null;
    }
    validate(strictJson(JSON.stringify(record)));
    const text = JSON.stringify(record, null, 2) + "\n";
    if (new TextEncoder().encode(text).length > 1048576) fail("记录不能超过1MiB。");
    const url = URL.createObjectURL(new Blob([text], {type: "application/json;charset=utf-8"}));
    const link = document.createElement("a"); link.href = url; link.download = "human-review-record.json";
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = "记录已下载，可再次载入继续填写；未核对项目仍留空。";
  } catch (error) { status.textContent = error.message; }
});
document.getElementById("load-record").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    if (file.size > 1048576) fail("记录不能超过1MiB。");
    const record = validate(strictJson(await file.text()));
    document.getElementById("recordedOn").value = record.recordedOn || "";
    document.getElementById("reviewer").value = record.reviewer || "";
    for (const row of record.cases) {
      const input = controls.get(row.caseId);
      for (const key of dimensions) input.fields[key].value = row[key] === null ? "" : String(row[key]);
      for (const checkbox of input.checkboxes) checkbox.checked = (row.reviewedTemporalEntityIds || []).includes(checkbox.value);
      input.statement.value = row.statement || "";
    }
    status.textContent = "记录已载入，可继续填写；没有自动通过任何验收。";
  } catch (error) { status.textContent = "无法载入：" + error.message; }
  finally { event.target.value = ""; }
});
