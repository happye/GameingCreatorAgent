# Provisional architecture

This is a working map derived from the source plan, not an approved implementation design. F000 must test its assumptions before modules are created.

## Phase 0 data flow

`Local video → FFmpeg preprocessing → audio/visual evidence → semantic events → SQLite timeline → natural-language retrieval → ranked timestamped clips`

The CLI is an orchestration boundary. Keep domain records (`MediaAsset`, `SemanticEvent`, `VideoSegment`, `CandidateClip`) independent of storage, FFmpeg, and model SDKs. Infrastructure adapters may depend on domain contracts; the domain must not depend on provider SDKs or a future UI. A future desktop client should call application services rather than access SQLite or model providers directly.

## Invariants

- Process large source media locally by default. Remote requests should contain only the evidence required for a model call.
- Store media paths and analysis metadata in SQLite; do not put full video bytes in the database.
- Define provider interfaces before choosing a model implementation, so a provider can be replaced without changing domain logic.
- Make analysis artifacts traceable to source timecodes, model/version, prompt version, cost, and elapsed time.
- Keep platform profiles as versioned data if that later layer is built; no Phase 0 platform adapters are required.

## Proposed layout when coding starts

`src/` may contain CLI, Application, Domain, Infrastructure, Media, SemanticTimeline, and Retrieval projects. `tests/` should mirror those boundaries. Create the smallest set needed for the current feature and record the actual layout here. No project files or enforced dependency tests exist yet.
