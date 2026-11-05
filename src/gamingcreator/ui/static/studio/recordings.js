// A recording is identified by its source bytes; analysis attempts remain separate versions.
export function groupRecordings(runs) {
    const groups = new Map();
    for (const run of runs) {
        const key = run.sourceSha256 || run.mediaId || run.id;
        if (!groups.has(key)) groups.set(key, {key, runs: []});
        groups.get(key).runs.push(run);
    }
    return [...groups.values()];
}

export function recordingRuns(runs, selectedId) {
    const selected = new Set(Array.isArray(selectedId) ? selectedId : [selectedId]);
    return groupRecordings(runs).map((group) => group.runs.find((r) => selected.has(r.id) && r.completedEligible)
        || group.runs.find((r) => r.completedEligible)).filter(Boolean);
}

// A cut is an editable choice around an observation, never a change to model evidence.
export function clipSelection(event, durationUs) {
    if (event.analysisStartUs !== undefined) return event;
    const selection = {...event, analysisStartUs: event.startUs, analysisEndUs: event.endUs, sourceDurationUs: durationUs};
    if (!Number.isSafeInteger(durationUs) || durationUs <= 0 || event.endUs - event.startUs >= 3000000) return selection;
    const width = Math.min(3000000, durationUs), middle = Math.floor((event.startUs + event.endUs) / 2);
    selection.startUs = Math.min(Math.max(0, middle - Math.floor(width / 2)), durationUs - width);
    selection.endUs = selection.startUs + width;
    return selection;
}
