# Testing and benchmark guide

No test framework is configured yet. F001 should establish a .NET test project and document the command that runs it. Add unit tests for domain logic and input validation, integration tests for FFmpeg/SQLite boundaries, and a CLI smoke test when the commands exist. Name tests by behavior, such as `Search_ReturnsTimestampedClips_ForMechanicQuery`.

For retrieval quality, build a local benchmark from representative game recordings. The source plan suggests 10–20 recordings; keep raw footage outside Git. Store only permitted fixture metadata and human labels. Each benchmark case should capture a query, relevant time ranges, judged results, reviewer/date, provider/model/prompt version, runtime, and cost.

Compute Top-10 Useful Rate with a fixed denominator of ten; missing and duplicate-event slots count zero. Human-judged usable/highly relevant independent events count toward the numerator. Main, sparse-positive, and negative queries are frozen before inference and reported separately. Follow [phase-0-benchmark.md](./phase-0-benchmark.md) for full contracts and executable metric regression. Track timecode errors and false positives; report every query rather than hiding failures in an aggregate.

Do not mark a feature passed because code compiles alone. Attach the feature's test evidence to `progress.md` or a sprint evaluation file.
