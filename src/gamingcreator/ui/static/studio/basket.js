// Clip basket and clip search for the Assets workspace. The basket is the user's pick of analysed
// events; a plan generated "from the basket" may use only those events (plan request eventIds).
// Search filters the analysis descriptions of every finished recording locally: nothing is
// recorded and no model is called.
import {h} from "../vendor/preact.module.js";
import {useCallback, useEffect, useMemo, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";
import {clipSelection, recordingRuns} from "./recordings.js";

const html = htm.bind(h);
const STORE = "studio-basket-v1";
const MAX_ITEMS = 500; // the server's limit for one plan

const timecode = (us) => { const s = Math.max(0, Math.floor(us / 1e6)); return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };
const read = () => { try { return JSON.parse(localStorage.getItem(STORE) || "{}") || {}; } catch { return {}; } };
const write = (value) => { try { localStorage.setItem(STORE, JSON.stringify(value)); } catch { /* Storage may be disabled. */ } };
export const factsOf = (event) => event.displayFacts || event.observableFacts || [];

export function useBasket(project) {
    const [items, setItems] = useState(() => read()[project] || []);
    useEffect(() => { setItems(read()[project] || []); }, [project]);
    const save = useCallback((next) => { setItems(next); write({...read(), [project]: next}); }, [project]);
    const ids = useMemo(() => new Set(items.map((i) => i.eventId)), [items]);
    return {
        items, ids,
        totalUs: items.reduce((sum, i) => sum + (i.endUs - i.startUs), 0),
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
        clear: () => save([]),
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
            const images = Object.fromEntries((view.evidence || []).filter((e) => e.kind === "image").map((e) => [e.id, client.sameOrigin(e.url, "/api/evidence")]));
            for (const event of view.timeline || []) rows.push({run, event: {...event, sourceDurationUs: view.media?.durationUs || run.durationUs}, thumb: images[event.evidenceIds?.[0]] || null});
        }
        if (request === generation.current) setState({loading: false, loaded: true, rows});
    }, [project, runs]);
    // A different project or recording list invalidates what was loaded.
    useEffect(() => { generation.current += 1; setState({loading: false, loaded: false, rows: []}); return () => { generation.current += 1; }; }, [project, runs]);
    return {...state, load};
}

export function ClipSearch({project, runs, runId, basket, onShow}) {
    const [query, setQuery] = useState("");
    const [scope, setScope] = useState("current");
    const scopedRuns = useMemo(() => scope === "all" ? recordingRuns(runs, runId) : runs.filter((r) => r.id === runId), [runs, runId, scope]);
    const all = useAllTimelines(project, scopedRuns);
    useEffect(() => { if (query.trim() && !all.loaded && !all.loading) void all.load(); }, [query, all.loaded, all.loading, all.load]);
    const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const hits = useMemo(() => (terms.length ? all.rows.filter(({event}) => {
        const text = [...factsOf(event), ...(event.mechanicTags || []), event.uncertainty || ""].join(" ").toLowerCase();
        return terms.every((t) => text.includes(t));
    }) : []), [all.rows, query]);
    return html`<div class="clip-search">
        <label class="form-row">搜索范围<select class="select" aria-label="搜索范围" value=${scope} onChange=${(e) => setScope(e.currentTarget.value)}>
            <option value="current">当前录像</option><option value="all">全部录像（可跨游戏）</option>
        </select></label>
        <input class="input" type="search" value=${query} onInput=${(e) => setQuery(e.currentTarget.value)} placeholder="搜索片段，例如：跳跃 金币" aria-label="搜索片段" />
        ${terms.length ? html`<div class="hits">
            ${all.loading || !all.loaded ? html`<p class="note">正在读取所有录像的分析片段…</p>`
                : html`<p class="hint">${hits.length ? `找到 ${hits.length} 段（按分析描述匹配，未经人工核对）` : "没有匹配的片段，换个词试试。"}</p>`}
            ${hits.slice(0, 60).map(({run, event, thumb}) => html`<div class="hit">
                <button class="hit-main" onClick=${() => onShow(run, event)} title=${factsOf(event).join("；")}>
                    <span class="hit-thumb" style=${{backgroundImage: thumb ? `url("${thumb}")` : "none"}}></span>
                    <span class="hit-text"><span class="meta">${(run.sourceName || "").slice(0, 14)} · ${timecode(event.startUs)} · 取景 ${((clipSelection(event, event.sourceDurationUs).endUs - clipSelection(event, event.sourceDurationUs).startUs) / 1e6).toFixed(1)} 秒</span>${factsOf(event)[0] || ""}</span>
                </button>
                <button class="icon-btn" aria-pressed=${basket.ids.has(event.eventId)} aria-label=${basket.ids.has(event.eventId) ? "移出片段篮" : "加入片段篮"} title=${basket.ids.has(event.eventId) ? "移出片段篮" : "加入片段篮"}
                    onClick=${() => basket.toggle(event, run, thumb)}>${basket.ids.has(event.eventId) ? "✓" : "+"}</button>
            </div>`)}
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
            : html`<p class="note">搜索或在时间轴上选中片段，点“加入片段篮”（快捷键 B）。生成方案时可以只用篮里的片段。</p>`}
    </div>`;
}
