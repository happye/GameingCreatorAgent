# Testing and benchmark guide

No test framework is configured yet. F001 should establish a .NET test project and document the command that runs it. Add unit tests for domain logic and input validation, integration tests for FFmpeg/SQLite boundaries, and a CLI smoke test when the commands exist. Name tests by behavior, such as `Search_ReturnsTimestampedClips_ForMechanicQuery`.

For retrieval quality, build a local benchmark from representative game recordings. The source plan suggests 10–20 recordings; keep raw footage outside Git. Store only permitted fixture metadata and human labels. Each benchmark case should capture a query, relevant time ranges, judged results, reviewer/date, provider/model/prompt version, runtime, and cost.

Compute Top-10 Useful Rate as human-judged usable or highly relevant returned clips divided by returned clips among the top ten. Report the denominator, query count, empty results, and per-query scores so the 70% Phase 0 gate cannot be hidden by an aggregate. Track timecode errors and false positives as secondary evidence. If the gate fails, record the concrete failures before changing the pipeline.

Do not mark a feature passed because code compiles alone. Attach the feature's test evidence to `progress.md` or a sprint evaluation file.
