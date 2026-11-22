// Clip basket and clip search for the Assets workspace. The basket is the user's pick of analysed
// events; a plan generated "from the basket" may use only those events (plan request eventIds).
// Search can filter analysis descriptions or request ranked sentence matches from the local API.
import {h} from "../vendor/preact.module.js";
import {useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";
import {clipSelection, recordingRuns} from "./recordings.js";

const html = htm.bind(h);
const STORE = "studio-basket-v1";
const MAX_ITEMS = 500; // the server's limit for one plan
const SENTENCE_TOP = 10;

const timecode = (us) => { const s = Math.max(0, Math.floor(us / 1e6)); return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };
const read = () => { try { return JSON.parse(localStorage.getItem(STORE) || "{}") || {}; } catch { return {}; } };
const write = (value) => { try { localStorage.setItem(STORE, JSON.stringify(value)); } catch { /* Storage may be disabled. */ } };
export const factsOf = (event) => event.displayFacts || event.observableFacts || [];

function viewRows(run, view) {
    const images = Object.fromEntries((view.evidence || []).filter((e) => e.kind === "image").map((e) => [e.id, client.sameOrigin(e.url, "/api/evidence")]));
    return (view.timeline || []).map((event) => ({run, event: {...event, sourceDurationUs: view.media?.durationUs || run.durationUs}, thumb: images[event.evidenceIds?.[0]] || null}));
}

// Seconds of distinct footage: overlapping picks from one recording count once (the planner
// plays each source second at most once).
export function uniqueLength(items) {
    const byRun = new Map();
    for (const i of items) byRun.set(i.runId, [...(byRun.get(i.runId) || []), [i.startUs, i.endUs]]);
    let total = 0;
    for (const ranges of byRun.values()) {
        let end = -Infinity;
        for (const [s, e] of ranges.sort((a, b) => a[0] - b[0])) { if (e > end) { total += e - Math.max(s, end); end = e; } }
    }
    return total;
}

export function useBasket(project) {
    const [items, setItems] = useState(() => read()[project] || []);
    // The last cleared basket stays restorable until something new goes in (one misclick is cheap).
    const slot = `cleared:${project}`;
    const [cleared, setCleared] = useState(() => read()[slot] || []);
    useEffect(() => { setItems(read()[project] || []); setCleared(read()[slot] || []); }, [project]);
    const save = useCallback((next, keepCleared = false) => {
        setItems(next);
        const stored = {...read(), [project]: next};
        if (!keepCleared) { delete stored[slot]; setCleared([]); }
        write(stored);
    }, [project, slot]);
    const ids = useMemo(() => new Set(items.map((i) => i.eventId)), [items]);
    return {
        items, ids,
        totalUs: items.reduce((sum, i) => sum + (i.endUs - i.startUs), 0),
        uniqueUs: uniqueLength(items),
        toggle: (event, run, thumb) => {
            if (ids.has(event.eventId)) return save(items.filter((i) => i.eventId !== event.eventId));
            if (items.length >= MAX_ITEMS) return;
            const selected = clipSelection(event, event.sourceDurationUs || run.durationUs);
            if (selected.endUs <= selected.startUs) return;
            save([...items, {eventId: event.eventId, runId: run.id, runName: run.sourceName || "", startUs: selected.startUs, endUs: selected.endUs,
                analysisStartUs: selected.analysisStartUs, analysisEndUs: selected.analysisEndUs, sourceDurationUs: selected.sourceDurationUs,
                fact: factsOf(event)[0] || "", thumb: thumb || null}]);
        },
        updateRange: (eventId, range) => save(items.map((i) => i.eventId === eventId ? {...i, ...range} : i)),
        remove: (eventId) => save(items.filter((i) => i.eventId !== eventId)),
        cleared: cleared.length,
        clear: () => { const kept = items; save([], true); setCleared(kept); write({...read(), [slot]: kept}); },
        restore: () => { if (!items.length && cleared.length) save(cleared.slice(0, MAX_ITEMS)); },
    };
}

// Timelines of every finished recording, loaded once per project when search is first used.
function useAllTimelines(project, runs) {
    const cache = useRef(new Map());
    const generation = useRef(0);
    const [state, setState] = useState({loading: false, loaded: false, rows: []});
    const load = useCallback(async () => {
        const request = generation.current;
        const usable = runs.filter((r) => r.completedEligible);
        setState((s) => ({...s, loading: true}));
        const rows = [];
        for (const run of usable) {
            const key = `${project}|${run.id}`;
            if (!cache.current.has(key)) cache.current.set(key, client.inspect(project, run.id).catch(() => null));
            const view = await cache.current.get(key);
            if (!view || view.runId !== run.id) continue;
            for (const row of viewRows(run, view)) rows.push(row);
        }
        if (request === generation.current) setState({loading: false, loaded: true, rows});
    }, [project, runs]);
    // A different project or recording list invalidates what was loaded.
    useEffect(() => { generation.current += 1; setState({loading: false, loaded: false, rows: []}); return () => { generation.current += 1; }; }, [project, runs]);
    return {...state, load};
}

function rankedCandidates(result, project, runs, query) {
    const known = new Map(runs.map((run) => [run.id, run]));
    if (result?.schemaVersion !== "project-search-v1" || result.project !== project || result.query !== query
        || result.mode !== "hybrid" || result.topK !== SENTENCE_TOP || !Array.isArray(result.sources)
        || result.sources.length !== runs.length || !Array.isArray(result.candidates) || result.candidates.length > SENTENCE_TOP) {
        throw new Error("返回的搜索范围或排名不一致，请重新搜索。");
    }
    const sources = new Map();
    for (const source of result.sources) {
        const run = known.get(source?.runId);
        if (!run || sources.has(run.id) || source.mediaId !== run.mediaId || source.sourceSha256 !== run.sourceSha256
            || source.sourceName !== run.sourceName || source.durationUs !== run.durationUs) {
            throw new Error("返回的录像来源不一致，请刷新项目后重试。");
        }
        sources.set(run.id, run);
    }
    return result.candidates.map((candidate, index) => {
        const run = sources.get(candidate?.runId);
        if (!run || candidate.rank !== index + 1 || candidate.mediaId !== run.mediaId
            || candidate.sourceSha256 !== run.sourceSha256 || candidate.sourceName !== run.sourceName
            || !Number.isSafeInteger(candidate.startUs) || !Number.isSafeInteger(candidate.endUs)
            || candidate.startUs < 0 || candidate.endUs <= candidate.startUs || candidate.endUs > run.durationUs
            || typeof candidate.candidateId !== "string" || !candidate.candidateId
            || (candidate.eventId !== null && (typeof candidate.eventId !== "string" || !candidate.eventId))) {
            throw new Error("返回的片段来源或排名不一致，请重新搜索。");
        }
        return {candidate, run};
    });
}

async function sentenceHits(project, runs, query, signal) {
    const result = await client.searchProject(project, runs.map((run) => run.id), query, SENTENCE_TOP, signal);
    const ranked = rankedCandidates(result, project, runs, query);
    if (signal.aborted) return [];
    const needed = new Map(ranked.map(({run}) => [run.id, run]));
    const timelines = new Map(await Promise.all([...needed.values()].map(async (run) => {
        const view = await client.inspect(project, run.id, signal).catch(() => null);
        return [run.id, client.matchesInspection(view, project, run) ? new Map(viewRows(run, view).map((row) => [row.event.eventId, row])) : null];
    })));
    return ranked.map(({candidate, run}) => {
        const timeline = timelines.get(run.id);
        if (candidate.eventId === null) return timeline ? {candidate, run, transcript: true}
            : {candidate, run, unavailable: "无法核对语音转录对应的录像，刷新项目后重试。"};
        const row = timeline?.get(candidate.eventId);
        if (!row || row.event.startUs !== candidate.startUs || row.event.endUs !== candidate.endUs) {
            return {candidate, run, unavailable: "无法核对这段画面的时间线，刷新项目后重试。"};
        }
        return {...row, candidate};
    });
}

function useSentenceSearch(project, runs, query, scope, mode) {
    const runIdentity = JSON.stringify(runs.map((run) => [run.id, run.mediaId, run.sourceSha256, run.sourceName, run.durationUs]));
    // In all-recordings scope, opening a hit may change the current run without changing the search scope.
    const context = useMemo(() => ({}), [project, runIdentity, query, scope, mode]);
    const active = useRef(null);
    const [result, setResult] = useState(null);
    useLayoutEffect(() => () => active.current?.abort(), [context]);
    const submit = async () => {
        active.current?.abort();
        if (!query || !project || !runs.length) return;
        if (runs.length > 100) {
            setResult({context, error: "一句话搜索每次最多支持 100 段录像，请改选当前录像。"});
            return;
        }
        const controller = new AbortController();
        active.current = controller;
        setResult({context, loading: true});
        try {
            const hits = await sentenceHits(project, runs, query, controller.signal);
            if (!controller.signal.aborted) setResult({context, hits});
        } catch (error) {
            if (!controller.signal.aborted) setResult({context, error: `一句话搜索失败，请重试。${error.message}`});
        } finally {
            if (active.current === controller) active.current = null;
        }
    };
    return {result: result?.context === context ? result : null, submit};
}

function SearchHit({hit: {run, event, thumb, candidate, unavailable, transcript}, basket, onShow, onShowTranscript}) {
    const time = timecode(event?.startUs ?? candidate.startUs);
    const prefix = `${candidate ? `第 ${candidate.rank} 名 · ` : ""}${(run.sourceName || "").slice(0, 14)} · ${time}`;
    const selected = event ? clipSelection(event, event.sourceDurationUs) : null;
    const picked = !!event && basket.ids.has(event.eventId);
    const label = picked ? "移出片段篮" : "加入片段篮";
    const transcriptText = transcript && [candidate.displayFacts, candidate.observableFacts]
        .find((facts) => Array.isArray(facts) && typeof facts[0] === "string" && facts[0].trim())?.[0];
    return html`<div class="hit" data-rank=${candidate?.rank} data-run-id=${run.id} data-event-id=${event?.eventId ?? candidate?.eventId}>
        ${unavailable ? html`<span class="hit-text"><span class="meta">${prefix}</span>${unavailable}</span>` : transcript ? html`
            <button class="hit-main" type="button" aria-label="回看语音转录片段" title=${transcriptText || "仅命中语音转录"}
                onClick=${() => onShowTranscript(run, candidate)}>
                <span class="hit-text"><span class="meta">${prefix} · 仅命中语音转录</span>${transcriptText || "回看语音转录片段"}</span>
            </button>` : html`
            <button class="hit-main" onClick=${() => onShow(run, event)} title=${factsOf(event).join("；")}>
                <span class="hit-thumb" style=${{backgroundImage: thumb ? `url("${thumb}")` : "none"}}></span>
                <span class="hit-text"><span class="meta">${prefix} · 取景 ${((selected.endUs - selected.startUs) / 1e6).toFixed(1)} 秒</span>${factsOf(event)[0] || ""}</span>
            </button>
            <button class="icon-btn" aria-pressed=${picked} aria-label=${label} title=${label}
                onClick=${() => basket.toggle(event, run, thumb)}>${picked ? "✓" : "+"}</button>`}
    </div>`;
}

export function ClipSearch({project, runs, runId, basket, onShow, onShowTranscript, seed = null}) {
    const [query, setQuery] = useState("");
    useEffect(() => { if (seed?.text) setQuery(seed.text); }, [seed?.at]);
    const [scope, setScope] = useState("current");
    const [mode, setMode] = useState("literal");
    const scopedRuns = useMemo(() => scope === "all" ? recordingRuns(runs, runId) : runs.filter((r) => r.id === runId), [runs, runId, scope]);
    const all = useAllTimelines(project, scopedRuns);
    const searchText = query.trim();
    const sentenceMode = mode === "sentence";
    const usable = scopedRuns.filter((run) => run.completedEligible);
    const sentence = useSentenceSearch(project, usable, searchText, scope, mode);
    useEffect(() => { if (!sentenceMode && searchText && !all.loaded && !all.loading) void all.load(); }, [sentenceMode, searchText, all.loaded, all.loading, all.load]);
    const terms = searchText.toLowerCase().split(/\s+/).filter(Boolean);
    const hits = useMemo(() => (terms.length ? all.rows.filter(({event}) => {
        const text = [...factsOf(event), ...(event.mechanicTags || []), event.uncertainty || ""].join(" ").toLowerCase();
        return terms.every((t) => text.includes(t));
    }) : []), [all.rows, query]);
    return html`<div class="clip-search">
        <label class="form-row">搜索范围<select class="select" aria-label="搜索范围" value=${scope} onChange=${(e) => setScope(e.currentTarget.value)}>
            <option value="current">当前录像</option><option value="all">全部录像（可跨游戏）</option>
        </select></label>
        <label class="form-row">搜索方式<select class="select" aria-label="搜索方式" value=${mode} onChange=${(e) => setMode(e.currentTarget.value)}>
            <option value="literal">关键词匹配</option><option value="sentence">一句话搜索</option>
        </select></label>
        <input class="input" type="search" value=${query} onInput=${(e) => setQuery(e.currentTarget.value)}
            onKeyDown=${(e) => { if (sentenceMode && e.key === "Enter" && !e.isComposing && !sentence.result?.loading) { e.preventDefault(); void sentence.submit(); } }}
            placeholder=${sentenceMode ? "例如：角色开大招击倒对手" : "搜索片段，例如：跳跃 金币"} aria-label="搜索片段" />
        ${sentenceMode ? html`
            <button class="btn" type="button" onClick=${sentence.submit} disabled=${!searchText || !project || !usable.length || !!sentence.result?.loading}>一句话搜索</button>
            ${!usable.length ? html`<p class="note">所选范围没有分析完成的录像，请切换范围或先完成分析。</p>` : null}
            ${sentence.result ? html`<div class="hits" aria-live="polite">
                ${sentence.result.loading ? html`<p class="note">正在本机搜索片段…</p>` : sentence.result.error ? html`<p class="note" role="alert">${sentence.result.error}</p>`
                    : html`<p class="hint">${sentence.result.hits.length ? `找到 ${sentence.result.hits.length} 条候选，按检索排名显示，请回看确认。` : "没有找到合适的片段，试试描述可见动作，或切换录像范围。"}</p>`}
                ${(sentence.result.hits || []).map((hit) => html`<${SearchHit} key=${hit.candidate.candidateId} hit=${hit} basket=${basket} onShow=${onShow} onShowTranscript=${onShowTranscript} />`)}
            </div>` : null}` : terms.length ? html`<div class="hits">
            ${all.loading || !all.loaded ? html`<p class="note">正在读取所有录像的分析片段…</p>`
                : html`<p class="hint">${hits.length ? `找到 ${hits.length} 段（按分析描述匹配，未经人工核对）` : "没有匹配的片段，换个词试试。"}</p>`}
            ${hits.slice(0, 60).map((hit) => html`<${SearchHit} key=${hit.event.eventId} hit=${hit} basket=${basket} onShow=${onShow} />`)}
        </div>` : null}
    </div>`;
}

export function BasketList({basket, onShow, onUse}) {
    return html`<div class="basket">
        <div class="section-label">片段篮（${basket.items.length} 段 · ${(basket.totalUs / 1e6).toFixed(1)} 秒）</div>
        ${basket.items.length ? html`
            ${basket.items.map((item) => html`<div class="hit">
                <button class="hit-main" onClick=${() => onShow(item)} title=${item.fact}>
                    <span class="hit-thumb" style=${{backgroundImage: item.thumb ? `url("${item.thumb}")` : "none"}}></span>
                    <span class="hit-text"><span class="meta">${item.runName.slice(0, 14)} · ${timecode(item.startUs)} · ${((item.endUs - item.startUs) / 1e6).toFixed(1)} 秒</span>${item.fact}</span>
                </button>
                <button class="icon-btn" aria-label="移出片段篮" title="移出片段篮" onClick=${() => basket.remove(item.eventId)}>×</button>
            </div>`)}
            <p class="hint">短观察点建议取前后画面作为选段；点开可回看并调整入点、出点。描述只对应分析区间，扩展画面请回看确认。</p>
            <div class="actions-row"><button class="btn" onClick=${onUse}>用片段篮生成方案</button><button class="btn ghost" onClick=${basket.clear}>清空</button></div>`
            : html`<p class="note">搜索或在时间轴上选中片段，点“加入片段篮”（快捷键 B）。生成方案时可以只用篮里的片段。</p>
                ${basket.cleared ? html`<p class="hint">已清空 ${basket.cleared} 段 · <button type="button" class="btn ghost" onClick=${basket.restore}>恢复</button></p>` : null}`}
    </div>`;
}
