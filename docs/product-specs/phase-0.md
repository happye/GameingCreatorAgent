# Phase 0: semantic retrieval feasibility

2026-10-30 scope extension: full product implementation now proceeds alongside Phase 0 quality validation under [ADR-003](../design-docs/adr-003-full-product-delivery.md). Pending human quality blocks only the corresponding acceptance/release claims, not downstream implementation. Existing Phase 0 quality and cost contracts remain unchanged.

Status: engineering baseline after the 2026-10-03 review; retrieval quality remains unverified. Source: product plan sections 58–59 and 69–71. Python implementation follows `docs/design-docs/adr-001-phase-0-language.md`, superseding the optional C# recommendation. Contracts: `docs/design-docs/phase-0-engineering-spec.md`; evidence: `docs/exec-plans/phase-0-validation-2026-10-03.md`.

## Goal

Given a local game video, create a `Video Semantic Timeline` and return timestamped clips for a natural-language query. Analysis and benchmarking use the developer-facing CLI. On 2026-10-04 the user authorized an existing local inspection workspace with preview, evidence, filtering and selected-interval JSON/CSV exports; see [ADR-002](../design-docs/adr-002-local-inspection-ui.md). The formal desktop UI, publishing flow, billing and general video editor remain outside this phase.

## Required behavior

1. Accept a local video path and validate that it is readable. Keep full video files on the user's machine.
2. Extract visual and audio evidence, run local ASR and a replaceable vision provider, and retain source timestamps and references. No-audio/no-speech inputs continue through visual analysis.
3. Persist semantic events and analysis metadata in SQLite; keep large media in the file system.
4. Expose model work behind replaceable provider interfaces. Record provider, model, prompt version, token usage, estimated cost, and processing time.
5. Search for a clearly described game mechanic and return ranked clips with start/end timecodes and relevance evidence.
6. Run a repeatable benchmark using representative, human-labeled clips.

Developer cost records may retain an additive human zero-charge confirmation for an explicitly identified ended detail attempt. Keep original API usage, unknown counts, ledger and send limits; expose the original and reconciled display values separately. This extends invocation observability within Phase 0. See [confirmation guide](../references/detail-billing-confirmation-guide.md); commercial billing remains outside the accepted phase.

## Go / no-go

For clear game-mechanic queries, at least 70% of ten ranked slots must contain independent clips judged usable or highly relevant by a human. Missing or duplicate-event slots count zero. Freeze main queries with enough labeled events before inference; report sparse and negative queries separately. Follow `docs/references/phase-0-benchmark.md`. Report queries, labels, misses, timecode errors, runtime, and cold model cost. If quality fails, improve understanding/retrieval before starting the formal desktop and commercial stages. The authorized local inspection workspace helps inspect evidence; its selections do not constitute human quality labels.

All packages and runtimes must be project-isolated under `.tools/`, `.venv/`, and `.cache/`; never install into the host system. F000 records review decisions; its document acceptance does not mark F001–F006 or the Phase 0 gate passed.
