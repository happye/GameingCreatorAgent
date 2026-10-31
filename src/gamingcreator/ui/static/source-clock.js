"use strict";

// Shared browser-clock semantics for both acceptance pages. The page context carries one
// pure JSON document per media (built by application/browser_source_clock.py); this module
// only multiplies, rounds and validates, so the two pages cannot drift apart. See
// docs/design-docs/browser-source-clock-spec.md for the measured Chromium evidence.
(() => {
    const CLOCK_VERSION = "browser-source-clock-v1";
    const QUANTUM_US = 1000000;
    const MAX_SAFE = 9007199254740991;
    const AXIS_TOLERANCE_US = 2000;
    const DURATION_TOLERANCE_US = 50000;

    const isSafeInteger = (value) => typeof value === "number" && Number.isSafeInteger(value);
    const isFiniteNumber = (value) => typeof value === "number" && Number.isFinite(value);

    function clockFromDocument(document) {
        if (!document || typeof document !== "object" || Array.isArray(document)) return null;
        if (document.schemaVersion !== CLOCK_VERSION) return null;
        const {originUs, durationUs, videoStartUs, videoEndUs, audioStartUs, audioEndUs,
            axisToleranceUs, durationToleranceUs} = document;
        if (![originUs, durationUs, videoStartUs, videoEndUs, axisToleranceUs, durationToleranceUs].every(isSafeInteger)) return null;
        if (originUs < 0 || durationUs <= 0 || axisToleranceUs <= 0 || durationToleranceUs <= 0) return null;
        if (videoStartUs < 0 || videoEndUs > durationUs || videoStartUs >= videoEndUs) return null;
        if (audioStartUs !== null || audioEndUs !== null) {
            if (!isSafeInteger(audioStartUs) || !isSafeInteger(audioEndUs)) return null;
            if (audioStartUs < 0 || audioEndUs > durationUs || audioStartUs >= audioEndUs) return null;
        }
        return Object.freeze({
            schemaVersion: CLOCK_VERSION, originUs, durationUs, videoStartUs, videoEndUs,
            audioStartUs, audioEndUs, axisToleranceUs, durationToleranceUs,
        });
    }

    function legacyClock(media) {
        // Stored contexts built before this feature carry only the old zero-origin eligibility
        // flags. They may still be used, but only as a secondary candidate that the same
        // runtime observation has to confirm. The old reference flag itself means "all
        // streams start at zero", so its origin is known even though the old media row never
        // stored one.
        const referenceEligible = media.automaticTimeCapture === true;
        const candidateEligible = media.automaticPlaybackSupported === true;
        if (!referenceEligible && !candidateEligible) return null;
        if (!isSafeInteger(media.durationUs)) return null;
        let originUs = 0;
        if (!referenceEligible) {
            const origin = typeof media.originSeconds === "string" ? Number(media.originSeconds) : Number.NaN;
            if (!Number.isFinite(origin) || origin < 0) return null;
            originUs = Math.floor(origin * QUANTUM_US + 0.5);
        }
        return clockFromDocument({
            schemaVersion: CLOCK_VERSION,
            originUs,
            durationUs: media.durationUs,
            videoStartUs: 0,
            videoEndUs: media.durationUs,
            audioStartUs: null,
            audioEndUs: null,
            axisToleranceUs: AXIS_TOLERANCE_US,
            durationToleranceUs: DURATION_TOLERANCE_US,
        });
    }

    const sameClock = (left, right) => left !== null && right !== null
        && left.originUs === right.originUs && left.durationUs === right.durationUs
        && left.videoStartUs === right.videoStartUs && left.videoEndUs === right.videoEndUs
        && left.audioStartUs === right.audioStartUs && left.audioEndUs === right.audioEndUs;

    function clockCandidates(media) {
        if (!media || typeof media !== "object" || Array.isArray(media)) return [];
        const candidates = [];
        if (Object.hasOwn(media, "sourceClock")) {
            const primary = clockFromDocument(media.sourceClock);
            if (primary) candidates.push(primary);
        }
        const legacy = legacyClock(media);
        if (legacy && !candidates.some((clock) => sameClock(clock, legacy))) candidates.push(legacy);
        return candidates;
    }

    function playerToSourceUs(clock, seconds) {
        if (!clock || typeof seconds !== "number" || !Number.isFinite(seconds)) return null;
        const scaled = seconds * QUANTUM_US;
        if (!Number.isFinite(scaled) || Math.abs(scaled) > MAX_SAFE) return null;
        const source = Math.floor(scaled + 0.5) - clock.originUs;
        if (source < -clock.axisToleranceUs || source > clock.durationUs + clock.axisToleranceUs) return null;
        return Math.min(Math.max(source, 0), clock.durationUs);
    }

    function sourceUsToPlayerSeconds(clock, sourceUs) {
        if (!clock || !isSafeInteger(sourceUs) || sourceUs < 0 || sourceUs > clock.durationUs) return null;
        return (sourceUs + clock.originUs) / QUANTUM_US;
    }

    function intervalReplayable(clock, startUs, endUs) {
        if (!clock || !isSafeInteger(startUs) || !isSafeInteger(endUs)) return false;
        if (startUs < 0 || startUs >= endUs || endUs > clock.durationUs) return false;
        return startUs >= clock.videoStartUs && endUs <= clock.videoEndUs;
    }

    function captureSourceUs(clock, seconds) {
        const source = playerToSourceUs(clock, seconds);
        if (source === null || source < clock.videoStartUs || source > clock.videoEndUs) return null;
        return source;
    }

    function durationChangeVerdict(clock, durationSeconds, seeked) {
        // Returns null while the reported duration is acceptable, else a reason code.
        // A non-zero-PTS MP4 measured in this project legitimately grows its *reported*
        // duration after seeks; that single case may stay bounded by the absolute axis end.
        // Every other growth, any shrink and any non-finite value revokes the capability.
        if (!clock) return "clock_unavailable";
        if (!isFiniteNumber(durationSeconds) || durationSeconds <= 0) return "duration_unavailable";
        const reported = durationSeconds * QUANTUM_US;
        if (reported < clock.durationUs - clock.durationToleranceUs) return "duration_mismatch";
        if (reported <= clock.durationUs + clock.durationToleranceUs) return null;
        if (seeked === true && clock.originUs > 0
            && reported <= clock.originUs + clock.durationUs + clock.durationToleranceUs) return null;
        return "duration_changed";
    }

    function validate(clock, observation) {
        if (!clock || !observation || typeof observation !== "object") return {established: false, reason: "observation_invalid"};
        if (typeof observation.seekable !== "boolean") return {established: false, reason: "observation_invalid"};
        if (!observation.seekable) return {established: false, reason: "seek_unavailable"};
        if (!isFiniteNumber(observation.durationSeconds) || observation.durationSeconds <= 0) return {established: false, reason: "duration_unavailable"};
        if (Math.abs(observation.durationSeconds * QUANTUM_US - clock.durationUs) > clock.durationToleranceUs) return {established: false, reason: "duration_mismatch"};
        // A first clamped seek alone does not prove the element can seek across the media;
        // the intermediate observation must have completed or the mapping is not accepted.
        if (!isFiniteNumber(observation.middleSeconds)) return {established: false, reason: "seek_incomplete"};
        const axis = observation.axisStartsSeconds;
        if (!Array.isArray(axis) || axis.length < 2) return {established: false, reason: "axis_unavailable"};
        if (!axis.every(isFiniteNumber)) return {established: false, reason: "axis_unavailable"};
        if ((Math.max(...axis) - Math.min(...axis)) * QUANTUM_US > clock.axisToleranceUs) return {established: false, reason: "axis_unstable"};
        if (Math.abs(axis[0] * QUANTUM_US - clock.originUs) > clock.axisToleranceUs) return {established: false, reason: "axis_mismatch"};
        return {established: true, reason: null};
    }

    function validateSeekTimeout(seekTimeoutMs) {
        if (!Number.isInteger(seekTimeoutMs) || seekTimeoutMs <= 0 || seekTimeoutMs > 15000) throw new RangeError("Invalid seek timeout.");
    }

    function settle(video, seconds, seekTimeoutMs = 3000) {
        validateSeekTimeout(seekTimeoutMs);
        // Fail closed: a value is only accepted after the browser reported `seeked` for this
        // request (or no seek was needed) and the element has decoded data. A timeout, a
        // missing `seeked` event or a value that was merely assigned resolves null instead of
        // a possibly stale position.
        return new Promise((resolve) => {
            let timer = null;
            let finished = false;
            let seeked = false;
            let requiresSeek = true;
            const finish = (value) => {
                if (finished) return;
                finished = true;
                if (timer !== null) clearTimeout(timer);
                video.removeEventListener("seeked", onSeeked);
                video.removeEventListener("loadeddata", onData);
                video.removeEventListener("canplay", onData);
                video.removeEventListener("error", onError);
                resolve(value);
            };
            const position = () => {
                if (video.seeking || video.readyState < 2 || !Number.isFinite(video.currentTime)) return null;
                return video.currentTime;
            };
            const confirm = () => {
                const value = position();
                if (value !== null) finish(value);
            };
            const onSeeked = () => { seeked = true; confirm(); };
            const onData = () => { if (!requiresSeek || seeked) confirm(); };
            const onError = () => finish(null);
            video.addEventListener("seeked", onSeeked);
            video.addEventListener("loadeddata", onData);
            video.addEventListener("canplay", onData);
            video.addEventListener("error", onError);
            timer = setTimeout(() => finish(null), seekTimeoutMs);
            // Only a genuinely idle element already at the target may skip the seek; even then
            // the frame data has to be ready.
            if (!video.seeking && Math.abs(video.currentTime - seconds) < 1e-9) {
                requiresSeek = false;
                confirm();
                return;
            }
            try {
                video.currentTime = seconds;
            } catch (error) {
                finish(null);
            }
        });
    }

    function prepare(video, url) {
        if (video.currentSrc === url && video.readyState >= 1) return Promise.resolve();
        return new Promise((resolve, reject) => {
            let timer = null;
            let finished = false;
            const finish = (error) => {
                if (finished) return;
                finished = true;
                clearTimeout(timer);
                video.removeEventListener("loadedmetadata", ready);
                video.removeEventListener("error", failed);
                if (error) reject(error);
                else resolve();
            };
            const ready = () => {
                if (video.currentSrc !== url) return;
                finish(null);
            };
            const failed = () => finish(new Error("media_error"));
            video.addEventListener("loadedmetadata", ready);
            video.addEventListener("error", failed);
            timer = setTimeout(() => finish(new Error("metadata_timeout")), 15000);
            try {
                video.src = url;
                video.load();
            } catch (error) {
                finish(new Error("media_error"));
            }
        });
    }

    async function observe(video, seekTimeoutMs = 3000) {
        validateSeekTimeout(seekTimeoutMs);
        // Read the header duration before any seek: a non-zero-PTS MP4 reported its header
        // duration (2.022 s) first and then grew seekable/duration estimates with each seek
        // (2.867 s, 3.133 s, 3.267 s), so only the pre-seek metadata is comparable with the
        // probed asset span. The offset itself comes from the settled axis, never from those
        // ranges.
        const duration = video.duration;
        const first = await settle(video, 0.000001, seekTimeoutMs);
        let middle = null;
        if (first !== null && Number.isFinite(duration) && duration > 0) {
            middle = await settle(video, first + duration / 2, seekTimeoutMs);
        }
        const second = await settle(video, 0.000001, seekTimeoutMs);
        return Object.freeze({
            seekable: video.seekable.length > 0,
            durationSeconds: Number.isFinite(duration) && duration > 0 ? duration : null,
            // Kept explicitly: the validation rejects a mapping when this seek did not
            // complete, instead of silently ignoring the intermediate observation.
            middleSeconds: Number.isFinite(middle) ? middle : null,
            axisStartsSeconds: [first, second],
        });
    }

    async function establish(candidates, url, seekTimeoutMs = 3000) {
        validateSeekTimeout(seekTimeoutMs);
        if (!Array.isArray(candidates) || !candidates.length) return {established: false, clock: null, reason: "clock_unavailable"};
        // A detached element is enough for Chromium to parse metadata and resolve seeks and
        // keeps the review page's DOM untouched (no second <video> element, no layout, no
        // disturbance of the visible player position). One retry covers a seek that was still
        // loading when the first observation window closed; a real mismatch fails both times.
        let reason = null;
        for (let attempt = 0; attempt < 2; attempt += 1) {
            const element = document.createElement("video");
            element.preload = "metadata";
            element.muted = true;
            element.playsInline = true;
            try {
                await prepare(element, url);
                const observation = await observe(element, seekTimeoutMs);
                for (const clock of candidates) {
                    const verdict = validate(clock, observation);
                    if (verdict.established) return {established: true, clock, reason: null};
                    if (reason === null) reason = verdict.reason;
                }
            } catch (error) {
                if (reason === null) reason = "media_unavailable";
            } finally {
                element.removeAttribute("src");
                element.load();
            }
        }
        return {established: false, clock: null, reason: reason || "axis_unavailable"};
    }

    globalThis.SourceClock = Object.freeze({
        version: CLOCK_VERSION,
        clockCandidates,
        playerToSourceUs,
        sourceUsToPlayerSeconds,
        intervalReplayable,
        captureSourceUs,
        durationChangeVerdict,
        validate,
        settle,
        prepare,
        observe,
        establish,
    });
})();
