import {h} from "../vendor/preact.module.js";
import {useCallback, useLayoutEffect, useMemo, useRef, useState} from "../vendor/hooks.module.js";
import htm from "../vendor/htm.module.js";
import * as client from "./api.js";

const html = htm.bind(h);

function checkedReport(report, project, view, scanning) {
    if (report?.schemaVersion !== "shot-boundaries-v1" || report.project !== project || report.runId !== view.runId) {
        throw new Error("镜头报告与当前项目或录像不一致。");
    }
    if (!scanning && report.available === false) return null;
    const {id, sha256, durationUs} = view.media;
    if (report.available !== true || report.mediaId !== id || report.sourceSha256 !== sha256 || report.durationUs !== durationUs
        || report.readOnly !== true || report.paidRequests !== 0 || report.humanReviewed !== false
        || !Array.isArray(report.cuts) || !report.cuts.every((cut) => Number.isSafeInteger(cut?.timeUs) && cut.timeUs > 0 && cut.timeUs < durationUs)
        || !Array.isArray(report.blackIntervals) || !report.blackIntervals.every((range) => Number.isSafeInteger(range?.startUs)
            && Number.isSafeInteger(range?.endUs) && range.startUs >= 0 && range.endUs > range.startUs && range.endUs <= durationUs)) {
        throw new Error("镜头报告来源或源时间有误，请重新检测。");
    }
    return report;
}

export function useShotBoundaries(project, view) {
    const scope = useMemo(() => view && {project, view}, [project, view]);
    const [result, setResult] = useState(null);
    const active = useRef(null);
    const load = useCallback(async (scanning = false) => {
        if (!scope || active.current?.scanning) return;
        active.current?.controller.abort();
        const controller = new AbortController();
        active.current = {controller, scanning};
        const update = (values) => setResult((previous) => ({report: previous?.scope === scope ? previous.report : null, ...values, scope}));
        update({status: scanning ? "scanning" : "loading"});
        try {
            const request = scanning ? client.detectShots : client.shotBoundaries;
            const payload = await request(scope.project, scope.view.runId, controller.signal);
            if (controller.signal.aborted) return;
            const report = checkedReport(payload, scope.project, scope.view, scanning);
            update({status: report ? "ready" : "empty", report});
        } catch (error) {
            if (!controller.signal.aborted) update({status: "error", error: `镜头报告${scanning ? "检测" : "读取"}失败。${error.message}`});
        } finally {
            if (active.current?.controller === controller) active.current = null;
        }
    }, [scope]);
    useLayoutEffect(() => {
        void load();
        return () => { active.current?.controller.abort(); active.current = null; };
    }, [load]);
    const current = scope && result?.scope === scope ? result : {status: scope ? "loading" : "idle"};
    return {...current, detect: () => void load(true)};
}

export function ShotStatus({status, report, error, seekReady}) {
    const messages = {idle: "选择录像后可检测镜头切换和黑场。", loading: "正在读取保存的镜头报告…",
        empty: "尚无保存的镜头报告。", scanning: "正在本机检测镜头切换和黑场…"};
    const counts = report && `镜头切换 ${report.cuts.length} 处 · 黑场 ${report.blackIntervals.length} 段 · 本机启发式，未经人评。`;
    return html`<p class="shot-status" role="status" data-shot-status=${status}>${error || messages[status]}${counts ? html`<span>
        ${counts}${!seekReady && report.cuts.length + report.blackIntervals.length > 0 ? " 源时间校准后可定位。" : ""}</span>` : null}</p>`;
}

export function ShotMarkers({report, scale, timecode, seekReady, onSeek}) {
    const {cuts, blackIntervals} = report;
    if (!cuts.length && !blackIntervals.length) return null;
    return html`<div class="shot-boundaries" role="group" aria-label="镜头切换与黑场">
        ${cuts.map(({timeUs}, index) => html`<button type="button" class="shot-cut" key=${`cut:${index}`} data-cut-us=${timeUs}
            style=${{left: `${timeUs * scale}px`}} disabled=${!seekReady} aria-label=${`镜头切换 ${timecode(timeUs)}`}
            title=${`镜头切换 ${timecode(timeUs)}`} onClick=${() => onSeek(timeUs)}></button>`)}
        ${blackIntervals.map(({startUs, endUs}, index) => html`<button type="button" class="shot-black" key=${`black:${index}`}
            data-black-start-us=${startUs} data-black-end-us=${endUs}
            style=${{left: `${startUs * scale}px`, width: `${(endUs - startUs) * scale}px`}} disabled=${!seekReady}
            aria-label=${`黑场 ${timecode(startUs)} 至 ${timecode(endUs)}`} title=${`黑场 ${timecode(startUs)} 至 ${timecode(endUs)}`}
            onClick=${() => onSeek(startUs)}></button>`)}
    </div>`;
}
