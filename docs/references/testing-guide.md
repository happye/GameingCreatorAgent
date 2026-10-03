# Testing and benchmark guide

No Python test framework is configured yet. F001 establishes pytest, Ruff, mypy and import-direction checks inside `.venv`, with fixed versions. Planned commands after F001: `./.venv/Scripts/python.exe -m pytest`, `-m ruff check .`, `-m ruff format --check .`, and `-m mypy src`. Configure pytest/type/format caches under `.cache`; these commands are not available before environment setup.

Add domain/input unit tests, FFmpeg/SQLite integration tests and CLI smoke tests when commands exist. Use `tests/test_<module>.py` or mirrored subdirectories and behavior names such as `test_search_returns_source_intervals_for_mechanic_query`. Integration tests using real models are explicitly selected, never silently paid during ordinary unit runs. No percentage coverage target is set; failure behavior and declared feature criteria determine required checks.

For retrieval quality, build a local benchmark from representative game recordings. The source plan suggests 10–20 recordings; keep raw footage outside Git. Store only permitted fixture metadata and human labels. Each benchmark case should capture a query, relevant time ranges, judged results, reviewer/date, provider/model/prompt version, runtime, and cost.

Compute Top-10 Useful Rate with a fixed denominator of ten; missing and duplicate-event slots count zero. Human-judged usable/highly relevant independent events count toward the numerator. Main, sparse-positive, and negative queries are frozen before inference and reported separately. Follow [phase-0-benchmark.md](./phase-0-benchmark.md) for full contracts and executable metric regression. Track timecode errors and false positives; report every query rather than hiding failures in an aggregate.

Do not mark a feature passed because code compiles alone. Attach the feature's test evidence to `progress.md` or a sprint evaluation file.
