// Read-only A/B entry for two already generated plans. Does not adopt, score, or call a model.
import {h} from "../vendor/preact.module.js";
import {useEffect, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";

const html = htm.bind(h);
const CONTIGUOUS_GAP_US = 250000;

function asInt(value) {
    if (value == null || value === true || value === false) return null;
    const number = Number(value);
    return Number.isFinite(number) ? Math.trunc(number) : null;
}

function positiveFps(fps) {
    return typeof fps === "number" && Number.isFinite(fps) && fps > 0 ? fps : null;
}

export function sourceIdentity(segment) {
    if (!segment || typeof segment !== "object") return null;
    const sha = segment.sourceSha256;
    if (typeof sha !== "string" || !sha) return null;
    if (segment.runId == null) return {runId: null, sourceSha256: sha};
    if (typeof segment.runId === "boolean") return null;
    if (typeof segment.runId !== "string" && typeof segment.runId !== "number") return null;
    return {runId: String(segment.runId), sourceSha256: sha};
}

function sameIdentity(a, b) {
    return a && b && a.runId === b.runId && a.sourceSha256 === b.sourceSha256;
}

function sameContiguous(previous, segment) {
    const prev = sourceIdentity(previous);
    const cur = sourceIdentity(segment);
    if (!prev || !sameIdentity(prev, cur)) return false;
    const startUs = asInt(segment.startUs);
    const prevEnd = asInt(previous.endUs);
    return startUs != null && prevEnd != null && startUs >= prevEnd && startUs - prevEnd <= CONTIGUOUS_GAP_US;
}

export function listSourceShots(segments) {
    if (!Array.isArray(segments)) return null;
    const shots = [];
    let current = null;
    let cursor = 0;
    for (const segment of segments) {
        if (!segment || typeof segment !== "object") return null;
        const frames = asInt(segment.outputFrames);
        if (!current || !sameContiguous(current.last, segment)) {
            const start = cursor;
            const end = cursor == null || frames == null ? null : cursor + frames;
            current = {identity: sourceIdentity(segment), startFrame: start, endFrame: end, frames, last: segment};
            shots.push(current);
        } else {
            if (current.frames == null || frames == null) {
                current.frames = null;
                current.endFrame = null;
            } else {
                current.frames += frames;
                if (current.endFrame != null) current.endFrame += frames;
            }
            current.last = segment;
        }
        if (frames == null) cursor = null;
        else if (cursor != null) cursor += frames;
    }
    return shots.map((shot, index) => ({
        identity: shot.identity,
        shotIndex: index + 1,
        startFrame: shot.startFrame,
        endFrame: shot.endFrame,
    }));
}

export function shotCount(segments) {
    const shots = listSourceShots(segments);
    return shots == null ? null : shots.length;
}

export function totalOutputFrames(segments) {
    if (!Array.isArray(segments)) return null;
    let total = 0;
    for (const segment of segments) {
        if (!segment || typeof segment !== "object") return null;
        const frames = asInt(segment.outputFrames);
        if (frames == null) return null;
        total += frames;
    }
    return total;
}

export function planSideMetrics(plan, fps) {
    const segments = plan && typeof plan === "object" ? plan.segments : null;
    const frames = totalOutputFrames(segments);
    const rate = positiveFps(fps);
    const gaps = plan && typeof plan === "object" && Array.isArray(plan.gaps) ? plan.gaps.slice() : null;
    return {
        totalFrames: frames,
        durationSeconds: frames == null || rate == null ? null : frames / rate,
        shotCount: shotCount(segments),
        gaps,
    };
}

function positionOf(shot, fps) {
    const rate = positiveFps(fps);
    return {
        shotIndex: shot.shotIndex,
        startFrame: shot.startFrame,
        endFrame: shot.endFrame,
        startSeconds: shot.startFrame == null || rate == null ? null : shot.startFrame / rate,
        endSeconds: shot.endFrame == null || rate == null ? null : shot.endFrame / rate,
    };
}

export function alignSourceShots(leftSegments, rightSegments, fps) {
    const leftShots = listSourceShots(leftSegments);
    const rightShots = listSourceShots(rightSegments);
    if (leftShots == null || rightShots == null) return null;
    const keyOf = (identity) => (identity ? `${identity.runId ?? ""}:${identity.sourceSha256}` : null);
    const group = (shots) => {
        const map = new Map();
        for (const shot of shots) {
            const key = keyOf(shot.identity);
            if (!key) continue;
            const bucket = map.get(key) || [];
            bucket.push(shot);
            map.set(key, bucket);
        }
        return map;
    };
    const leftGroups = group(leftShots);
    const rightGroups = group(rightShots);
    const seen = new Set();
    const rows = [];
    const makeRow = (identity, left, right, reason) => {
        const row = {
            runId: identity ? identity.runId : null,
            sourceSha256: identity ? identity.sourceSha256 : null,
            left: left ? positionOf(left, fps) : null,
            right: right ? positionOf(right, fps) : null,
        };
        if (reason) row.reason = reason;
        return row;
    };
    for (const left of leftShots) {
        if (!left.identity) {
            rows.push(makeRow(null, left, null));
            continue;
        }
        const key = keyOf(left.identity);
        if (seen.has(key)) continue;
        seen.add(key);
        const leftGroup = leftGroups.get(key) || [];
        const rightGroup = rightGroups.get(key) || [];
        if (leftGroup.length && rightGroup.length && leftGroup.length !== rightGroup.length) {
            for (const shot of leftGroup) rows.push(makeRow(left.identity, shot, null, "split"));
            for (const shot of rightGroup) rows.push(makeRow(left.identity, null, shot, "split"));
        } else if (rightGroup.length) {
            leftGroup.forEach((shot, index) => rows.push(makeRow(left.identity, shot, rightGroup[index])));
        } else {
            for (const shot of leftGroup) rows.push(makeRow(left.identity, shot, null));
        }
    }
    for (const right of rightShots) {
        if (!right.identity) {
            rows.push(makeRow(null, null, right));
            continue;
        }
        const key = keyOf(right.identity);
        if (seen.has(key)) continue;
        seen.add(key);
        for (const shot of (rightGroups.get(key) || [right])) rows.push(makeRow(right.identity, null, shot));
    }
    return rows;
}



function gcd(a, b) {
    a = Math.abs(a);
    b = Math.abs(b);
    while (b) {
        const next = a % b;
        a = b;
        b = next;
    }
    return a || 1;
}

export function formatExactUs(us) {
    const g = gcd(us, 1000000);
    const numerator = us / g;
    const denominator = 1000000 / g;
    return denominator === 1 ? `${us} 微秒（${numerator} 秒）` : `${us} 微秒（${numerator}/${denominator} 秒）`;
}

export function formatExactSpeed(sourceUs, outputFrames, fps) {
    if (!(sourceUs > 0) || !(outputFrames > 0)) return null;
    const rate = positiveFps(fps);
    if (rate == null || !Number.isInteger(rate)) return null;
    const numerator = sourceUs * rate;
    const denominator = outputFrames * 1000000;
    const g = gcd(numerator, denominator);
    const n = numerator / g;
    const d = denominator / g;
    return d === 1 ? String(n) : `${n}/${d}`;
}

export function trimSpeedMetrics(startUs, endUs, outputFrames, fps) {
    const sourceUs = startUs == null || endUs == null ? null : endUs - startUs;
    const rate = positiveFps(fps);
    let outputUs = null;
    if (outputFrames != null && rate != null && Number.isInteger(rate)) {
        const numerator = outputFrames * 1000000;
        const g = gcd(numerator, rate);
        const n = numerator / g;
        const d = rate / g;
        outputUs = d === 1 ? n : `${n}/${d}`;
    }
    return {
        startUs,
        endUs,
        sourceUs,
        outputFrames,
        outputUs,
        speed: sourceUs == null || outputFrames == null ? null : formatExactSpeed(sourceUs, outputFrames, fps),
    };
}

function formatTrim(trim, side) {
    if (!trim) return `${side}：没有这段，无法比较裁剪和速度`;
    const source = (trim.startUs == null || trim.endUs == null)
        ? "原片起止未知"
        : `原片 ${formatExactUs(trim.startUs)} 到 ${formatExactUs(trim.endUs)}`;
    let output = "成片时长未知";
    if (trim.outputFrames != null) {
        output = trim.outputUs == null ? `成片 ${trim.outputFrames} 帧` : `成片 ${trim.outputFrames} 帧（${typeof trim.outputUs === "number" ? formatExactUs(trim.outputUs) : trim.outputUs + " 微秒"}）`;
    }
    const speed = trim.speed == null ? "速度未知" : `速度 ${trim.speed}（原片时长÷成片时长）`;
    return `${side}：${source} · ${output} · ${speed}`;
}

export function intervalIdentity(segment) {
    const source = sourceIdentity(segment);
    if (!source || !segment || typeof segment !== "object") return null;
    const startUs = asInt(segment.startUs);
    const endUs = asInt(segment.endUs);
    if (startUs == null || endUs == null) return null;
    return {runId: source.runId, sourceSha256: source.sourceSha256, startUs, endUs};
}

function sameInterval(a, b) {
    return a && b && a.runId === b.runId && a.sourceSha256 === b.sourceSha256 && a.startUs === b.startUs && a.endUs === b.endUs;
}

function intervalKey(identity) {
    return identity ? `${identity.runId ?? ""}|${identity.sourceSha256}|${identity.startUs}|${identity.endUs}` : null;
}

export function listIntervalShots(segments) {
    if (!Array.isArray(segments)) return null;
    const shots = [];
    let cursor = 0;
    for (const segment of segments) {
        if (!segment || typeof segment !== "object") return null;
        const frames = asInt(segment.outputFrames);
        const start = cursor;
        const end = cursor == null || frames == null ? null : cursor + frames;
        shots.push({
            identity: intervalIdentity(segment),
            startFrame: start,
            endFrame: end,
            outputFrames: frames,
            shotIndex: shots.length + 1,
            startUs: asInt(segment.startUs),
            endUs: asInt(segment.endUs),
        });
        if (frames == null) cursor = null;
        else if (cursor != null) cursor += frames;
    }
    return shots;
}

function sharedKeyOrder(shots, otherIdentities) {
    const remaining = new Map();
    for (const identity of otherIdentities) {
        if (!identity) continue;
        const key = intervalKey(identity);
        remaining.set(key, (remaining.get(key) || 0) + 1);
    }
    const order = [];
    for (const shot of shots) {
        const key = intervalKey(shot.identity);
        if (!key || !remaining.get(key)) continue;
        remaining.set(key, remaining.get(key) - 1);
        order.push(key);
    }
    return order;
}

export function classifyShotChanges(leftSegments, rightSegments, fps) {
    const leftShots = listIntervalShots(leftSegments);
    const rightShots = listIntervalShots(rightSegments);
    if (leftShots == null || rightShots == null) return null;
    const statusFor = (identity, left, right) => {
        if (!identity || (!left && !right)) return "unknown";
        if (!left) return "added";
        if (!right) return "missing";
        if (left.shotIndex !== right.shotIndex) return "reordered";
        return "same";
    };
    const makeRow = (identity, left, right, status) => ({
        runId: identity ? identity.runId : null,
        sourceSha256: identity ? identity.sourceSha256 : null,
        startUs: identity ? identity.startUs : null,
        endUs: identity ? identity.endUs : null,
        status,
        left: left ? positionOf(left, fps) : null,
        right: right ? positionOf(right, fps) : null,
        leftTrim: left ? trimSpeedMetrics(left.startUs, left.endUs, left.outputFrames, fps) : null,
        rightTrim: right ? trimSpeedMetrics(right.startUs, right.endUs, right.outputFrames, fps) : null,
    });
    const used = new Set();
    const rows = [];
    for (const left of leftShots) {
        let match = -1;
        if (left.identity) {
            match = rightShots.findIndex((right, index) => !used.has(index) && sameInterval(right.identity, left.identity));
        }
        if (match >= 0) used.add(match);
        const right = match >= 0 ? rightShots[match] : null;
        rows.push(makeRow(left.identity, left, right, statusFor(left.identity, left, right)));
    }
    rightShots.forEach((right, index) => {
        if (used.has(index)) return;
        rows.push(makeRow(right.identity, null, right, statusFor(right.identity, null, right)));
    });
    return rows;
}



export function locatePreviewTarget(plan, position, fps) {
    if (!plan || typeof plan.id !== "string" || !plan.id || !position) return null;
    const rate = positiveFps(fps);
    if (position.startFrame != null && Number.isFinite(position.startFrame) && rate) {
        return {planId: plan.id, outStartUs: Math.round((position.startFrame / rate) * 1e6), startFrame: position.startFrame};
    }
    if (position.startSeconds != null && Number.isFinite(position.startSeconds)) {
        return {planId: plan.id, outStartUs: Math.round(position.startSeconds * 1e6)};
    }
    return null;
}

function LocateButton({side, plan, position, fps, onLocate, locateBlocked}) {
    const target = locatePreviewTarget(plan, position, fps);
    if (!target || typeof onLocate !== "function") return null;
    const label = side === "left" ? "定位方案 A 预览" : "定位方案 B 预览";
    return html`<button type="button" class="plan-compare-locate" data-side=${side} disabled=${!!locateBlocked} title=${locateBlocked || label} onClick=${() => { if (!locateBlocked) onLocate({...target, side}); }}>${label}</button>`;
}

export function listThemeReasons(plan) {
    const uses = [];
    const segments = plan && Array.isArray(plan.segments) ? plan.segments : [];
    segments.forEach((segment, index) => {
        if (!segment || !Array.isArray(segment.topicUses)) return;
        segment.topicUses.forEach((item) => {
            if (!item || typeof item !== "object") return;
            const topic = typeof item.topic === "string" && item.topic.trim() ? item.topic : null;
            const rationale = typeof item.rationale === "string" && item.rationale.trim() ? item.rationale : null;
            const observationQuote = typeof item.observationQuote === "string" && item.observationQuote.trim() ? item.observationQuote : null;
            if (!topic && !rationale && !observationQuote) return;
            uses.push({shotIndex: index + 1, topic, rationale, observationQuote});
        });
    });
    return {provided: uses.length > 0, uses};
}

export function openPlanComparison(plans, leftId, rightId, fps) {
    if (!leftId || !rightId) throw new Error("对照需要两个已生成方案。");
    if (leftId === rightId) throw new Error("对照需要两个不同的已生成方案。");
    const left = (plans || []).find((plan) => plan.id === leftId);
    const right = (plans || []).find((plan) => plan.id === rightId);
    if (!left || !right) throw new Error("只能对照已经生成的方案。");
    const result = {
        schemaVersion: "plan-comparison-v1",
        readonly: true,
        left: JSON.parse(JSON.stringify(left)),
        right: JSON.parse(JSON.stringify(right)),
        leftMetrics: planSideMetrics(left, fps),
        rightMetrics: planSideMetrics(right, fps),
        sourceAlignment: alignSourceShots(left.segments, right.segments, fps),
        shotChanges: classifyShotChanges(left.segments, right.segments, fps),
        leftThemeReasons: listThemeReasons(left),
        rightThemeReasons: listThemeReasons(right),
    };
    const rate = positiveFps(fps);
    if (rate != null) result.fps = rate;
    return result;
}

function sideLabel(plan) {
    return plan.structure || plan.title || plan.id;
}

function metricsItems(metrics) {
    const items = [];
    if (metrics.durationSeconds == null) {
        items.push(metrics.totalFrames == null ? "总长未知" : `总长未知（${metrics.totalFrames} 帧，缺帧率）`);
    } else {
        items.push(`总长 ${metrics.durationSeconds.toFixed(1)} 秒（${metrics.totalFrames} 帧）`);
    }
    items.push(metrics.shotCount == null ? "镜头数未知" : `镜头数 ${metrics.shotCount}`);
    if (metrics.gaps == null) items.push("缺口未知");
    else if (!metrics.gaps.length) items.push("没有缺口");
    else items.push(...metrics.gaps.map((gap) => `缺口：${gap}`));
    return items;
}

function formatPosition(side, position, reason) {
    if (!position) {
        if (reason === "split") return `${side}：同一来源在这一侧的切分不同，不是缺少这趟素材`;
        return `${side}：这一侧没有这个来源`;
    }
    const shot = `第 ${position.shotIndex} 镜`;
    if (position.startSeconds == null || position.endSeconds == null) {
        if (position.startFrame == null || position.endFrame == null) return `${side}：${shot} · 成片位置未知`;
        return `${side}：${shot} · 成片 ${position.startFrame}–${position.endFrame} 帧`;
    }
    return `${side}：${shot} · 成片 ${position.startSeconds.toFixed(1)}–${position.endSeconds.toFixed(1)} 秒（${position.startFrame}–${position.endFrame} 帧）`;
}

function sourceLabel(row) {
    if (!row.sourceSha256) return "来源未知，无法按素材身份对齐";
    return row.runId ? `来源 ${row.sourceSha256}（分析 ${row.runId}）` : `来源 ${row.sourceSha256}`;
}

function Side({label, plan, metrics}) {
    return html`<section aria-label=${label}>
        <h3>${sideLabel(plan)}</h3>
        <p>${plan.ready ? "可生成视频" : "有缺口"} · ${plan.id}</p>
        <ul class="plan-compare-metrics">${metricsItems(metrics).map((item) => html`<li>${item}</li>`)}</ul>
    </section>`;
}

function Alignment({rows, leftPlan, rightPlan, fps, onLocate, locateBlocked}) {
    if (rows == null) return html`<p class="note" id="plan-compare-alignment">两侧片段不完整，来源对齐未知。</p>`;
    if (!rows.length) return html`<p class="note" id="plan-compare-alignment">两侧都还没有镜头，没有可对齐的来源。</p>`;
    return html`<div id="plan-compare-alignment">
        <p class="note">按真实素材身份对齐相同来源，并标出各自在成片里的位置。不对角色或说明文字做猜测。</p>
        <ol class="plan-compare-alignment">${rows.map((row) => html`<li>
            <strong>${sourceLabel(row)}</strong>
            <p>${formatPosition("方案 A", row.left, row.reason)}</p>
            <p>${formatPosition("方案 B", row.right, row.reason)}</p>
            <${LocateButton} side="left" plan=${leftPlan} position=${row.left} fps=${fps} onLocate=${onLocate} locateBlocked=${locateBlocked} />
            <${LocateButton} side="right" plan=${rightPlan} position=${row.right} fps=${fps} onLocate=${onLocate} locateBlocked=${locateBlocked} />
        </li>`)}</ol>
    </div>`;
}


function changeLabel(status) {
    if (status === "added") return "方案 B 新增";
    if (status === "missing") return "方案 B 缺少";
    if (status === "reordered") return "换序";
    if (status === "unknown") return "无法判断增减，来源区间不完整";
    return "两边都有，顺序一致";
}

function intervalLabel(row) {
    if (!row.sourceSha256 || row.startUs == null || row.endUs == null) return "来源区间未知";
    const source = row.runId ? `来源 ${row.sourceSha256}（分析 ${row.runId}）` : `来源 ${row.sourceSha256}`;
    return `${source} · 原片 ${(row.startUs / 1e6).toFixed(1)}–${(row.endUs / 1e6).toFixed(1)} 秒`;
}

function ShotChanges({rows, leftPlan, rightPlan, fps, onLocate, locateBlocked}) {
    if (rows == null) return html`<p class="note" id="plan-compare-changes">两侧片段不完整，增减和换序未知。</p>`;
    if (!rows.length) return html`<p class="note" id="plan-compare-changes">两侧都还没有镜头，没有可比较的增减。</p>`;
    return html`<div id="plan-compare-changes">
        <p class="note">新增、缺少和换序按素材的真实来源区间比较。相同素材的不同截取会分开看，不会把重复的镜头编号当成同一段。</p>
        <ol class="plan-compare-changes">${rows.map((row) => html`<li data-change=${row.status} class=${"plan-compare-change plan-compare-change-" + row.status}>
            <strong>${changeLabel(row.status)}</strong>
            <p>${intervalLabel(row)}</p>
            <p>${formatPosition("方案 A", row.left)}</p>
            <p>${formatPosition("方案 B", row.right)}</p>
            <p class="plan-compare-trim">${formatTrim(row.leftTrim, "方案 A")}</p>
            <p class="plan-compare-trim">${formatTrim(row.rightTrim, "方案 B")}</p>
            <${LocateButton} side="left" plan=${leftPlan} position=${row.left} fps=${fps} onLocate=${onLocate} locateBlocked=${locateBlocked} />
            <${LocateButton} side="right" plan=${rightPlan} position=${row.right} fps=${fps} onLocate=${onLocate} locateBlocked=${locateBlocked} />
        </li>`)}</ol>
    </div>`;
}


function reasonField(label, value, missing) {
    return value ? `${label}：${value}` : `${label}：${missing}`;
}

function ReasonSide({label, reasons}) {
    if (!reasons || !reasons.provided || !reasons.uses.length) {
        return html`<section aria-label=${"主题理由与原始说明（" + (label === "方案 A" ? "左侧" : "右侧") + "）"}>
            <h3>${label}</h3>
            <p class="plan-compare-reason">未提供主题理由与原始说明</p>
        </section>`;
    }
    return html`<section aria-label=${"主题理由与原始说明（" + (label === "方案 A" ? "左侧" : "右侧") + "）"}>
        <h3>${label}</h3>
        <ol class="plan-compare-reasons">${reasons.uses.map((use) => html`<li class="plan-compare-reason">
            <p>镜头 ${use.shotIndex}${use.topic ? " · 主题 " + use.topic : " · 主题未提供"}</p>
            <p>${reasonField("主题理由", use.rationale, "未提供")}</p>
            <blockquote>${reasonField("引用的原始说明", use.observationQuote, "未提供")}</blockquote>
        </li>`)}</ol>
    </section>`;
}

function ThemeReasons({left, right}) {
    return html`<div id="plan-compare-reasons">
        <p class="note">主题理由和引用的原始说明只展示方案里已经记下的内容。没有记录就标明未提供，不会按模板或规则补写成解释。</p>
        <${ReasonSide} label="方案 A" reasons=${left} />
        <${ReasonSide} label="方案 B" reasons=${right} />
    </div>`;
}


export const COMPARISON_EXPORT_NOTE = "只包含这次对照的差异和来源，不会写回报告、证据或偏好。";

function exportSide(plan, metrics, reasons) {
    const side = {
        planId: plan && typeof plan.id === "string" && plan.id ? plan.id : null,
        metrics: metrics == null ? null : JSON.parse(JSON.stringify(metrics)),
        themeReasons: reasons == null ? null : JSON.parse(JSON.stringify(reasons)),
    };
    if (plan && typeof plan.contentSignature === "string" && plan.contentSignature) {
        side.contentSignature = plan.contentSignature;
    }
    return side;
}

export function listComparisonSources(alignment, changes) {
    const sources = [];
    const seen = new Set();
    const add = (runId, sourceSha256, startUs, endUs) => {
        if (runId == null && sourceSha256 == null && startUs == null && endUs == null) return;
        const key = `${runId ?? ""}\0${sourceSha256 ?? ""}\0${startUs ?? ""}\0${endUs ?? ""}`;
        if (seen.has(key)) return;
        seen.add(key);
        const item = {};
        if (runId != null) item.runId = runId;
        if (sourceSha256 != null) item.sourceSha256 = sourceSha256;
        if (startUs != null) item.startUs = startUs;
        if (endUs != null) item.endUs = endUs;
        sources.push(item);
    };
    if (Array.isArray(changes)) {
        for (const row of changes) {
            if (!row || typeof row !== "object") continue;
            add(row.runId, row.sourceSha256, row.startUs, row.endUs);
        }
    }
    if (Array.isArray(alignment)) {
        for (const row of alignment) {
            if (!row || typeof row !== "object") continue;
            if (sources.some((item) => item.runId === row.runId && item.sourceSha256 === row.sourceSha256)) continue;
            add(row.runId, row.sourceSha256);
        }
    }
    return sources;
}

export function comparisonExportDocument(pair) {
    if (!pair || typeof pair !== "object" || pair.readonly !== true || !("left" in pair) || !("right" in pair)) {
        throw new Error("只能下载已经打开的只读对照。");
    }
    const document = {
        schemaVersion: "plan-comparison-export-v1",
        readonly: true,
        note: COMPARISON_EXPORT_NOTE,
        left: exportSide(pair.left, pair.leftMetrics, pair.leftThemeReasons),
        right: exportSide(pair.right, pair.rightMetrics, pair.rightThemeReasons),
        sources: listComparisonSources(pair.sourceAlignment, pair.shotChanges),
        sourceAlignment: pair.sourceAlignment == null ? pair.sourceAlignment : JSON.parse(JSON.stringify(pair.sourceAlignment)),
        shotChanges: pair.shotChanges == null ? pair.shotChanges : JSON.parse(JSON.stringify(pair.shotChanges)),
    };
    if ("fps" in pair) document.fps = pair.fps;
    return document;
}

export function comparisonExportFilename(pair) {
    const token = (value, fallback) => {
        const text = typeof value === "string" && value ? value : fallback;
        const cleaned = text.replace(/[^A-Za-z0-9._-]/g, "_");
        return cleaned || fallback;
    };
    return `plan-comparison-${token(pair && pair.left && pair.left.id, "left")}-${token(pair && pair.right && pair.right.id, "right")}.json`;
}

export function downloadPlanComparison(pair) {
    const exported = comparisonExportDocument(pair);
    const url = URL.createObjectURL(new Blob([JSON.stringify(exported, null, 2) + "\n"], {type: "application/json;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = comparisonExportFilename(pair);
    link.rel = "noopener";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return true;
}

export function PlanCompare({plans, adoptedId, fps, onLocate, locateBlocked, onClose, compareScope = ""}) {
    const [leftId, setLeftId] = useState("");
    const [rightId, setRightId] = useState("");
    const [pair, setPair] = useState(null);
    const [error, setError] = useState("");
    const planIds = (plans || []).map((plan) => plan.id).join("\0");
    useEffect(() => {
        setLeftId("");
        setRightId("");
        setPair(null);
        setError("");
        if (typeof onClose === "function") onClose();
    }, [compareScope, planIds]);
    const open = () => {
        try {
            setPair(openPlanComparison(plans, leftId, rightId, fps));
            setError("");
        } catch (caught) {
            setPair(null);
            setError(caught.message || String(caught));
        }
    };
    const options = (plans || []).map((plan) => html`<option value=${plan.id}>${sideLabel(plan)}</option>`);
    return html`<div class="plan-compare" id="plan-compare" data-compare-scope=${compareScope || ""}>
        <p class="note">对照两个已生成方案，只看差异，不会改当前已采用的方案，也不会评分或调用模型。</p>
        <div class="actions-row">
            <label>方案 A <select id="plan-compare-left" value=${leftId} onChange=${(event) => setLeftId(event.target.value)}>
                <option value="">请选择</option>${options}
            </select></label>
            <label>方案 B <select id="plan-compare-right" value=${rightId} onChange=${(event) => setRightId(event.target.value)}>
                <option value="">请选择</option>${options}
            </select></label>
            <button id="plan-compare-open" class="btn ghost" type="button" disabled=${!leftId || !rightId || leftId === rightId} onClick=${open}>开始对照</button>
        </div>
        ${error ? html`<p class="note" id="plan-compare-error">${error}</p>` : null}
        ${pair ? html`<div id="plan-compare-view" class="plan-compare-view" data-readonly="true" data-adopted=${adoptedId || ""}>
            <p class="note">当前已采用方案：${adoptedId || "尚未采用"}（对照不会改它）</p>
            <div class="plan-compare-sides">
                <${Side} label="方案 A" plan=${pair.left} metrics=${pair.leftMetrics} />
                <${Side} label="方案 B" plan=${pair.right} metrics=${pair.rightMetrics} />
            </div>
            <${Alignment} rows=${pair.sourceAlignment} leftPlan=${pair.left} rightPlan=${pair.right} fps=${fps} onLocate=${onLocate} locateBlocked=${locateBlocked} />
            <${ShotChanges} rows=${pair.shotChanges} leftPlan=${pair.left} rightPlan=${pair.right} fps=${fps} onLocate=${onLocate} locateBlocked=${locateBlocked} />
            <${ThemeReasons} left=${pair.leftThemeReasons} right=${pair.rightThemeReasons} />
            <button id="plan-compare-download" class="btn ghost" type="button" onClick=${() => downloadPlanComparison(pair)}>下载对照 JSON</button>
            <button id="plan-compare-close" class="btn ghost" type="button" onClick=${() => { setPair(null); if (typeof onClose === "function") onClose(); }}>关闭对照</button>
        </div>` : null}
    </div>`;
}
