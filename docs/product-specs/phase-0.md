# Phase 0: semantic retrieval feasibility

Status: engineering baseline after the 2026-10-03 review; retrieval quality remains unverified. Source: product plan sections 58–59 and 69–71. Python implementation follows `docs/design-docs/adr-001-phase-0-language.md`, superseding the optional C# recommendation. Contracts: `docs/design-docs/phase-0-engineering-spec.md`; evidence: `docs/exec-plans/phase-0-validation-2026-10-03.md`.

## Goal

Given a local game video, create a `Video Semantic Timeline` and return timestamped clips for a natural-language query. The prototype is a developer-facing CLI. Do not build the desktop UI, publishing flow, billing, or a general video editor in this phase.

## Required behavior

1. Accept a local video path and validate that it is readable. Keep full video files on the user's machine.
2. Extract visual and audio evidence, run local ASR and a replaceable vision provider, and retain source timestamps and references. No-audio/no-speech inputs continue through visual analysis.
3. Persist semantic events and analysis metadata in SQLite; keep large media in the file system.
4. Expose model work behind replaceable provider interfaces. Record provider, model, prompt version, token usage, estimated cost, and processing time.
5. Search for a clearly described game mechanic and return ranked clips with start/end timecodes and relevance evidence.
6. Run a repeatable benchmark using representative, human-labeled clips.

## Go / no-go

For clear game-mechanic queries, at least 70% of ten ranked slots must contain independent clips judged usable or highly relevant by a human. Missing or duplicate-event slots count zero. Freeze main queries with enough labeled events before inference; report sparse and negative queries separately. Follow `docs/references/phase-0-benchmark.md`. Report queries, labels, misses, timecode errors, runtime, and cold model cost. If quality fails, improve understanding/retrieval before starting the UI.

All packages and runtimes must be project-isolated under `.tools/`, `.venv/`, and `.cache/`; never install into the host system. F000 records review decisions; its document acceptance does not mark F001–F006 or the Phase 0 gate passed.
