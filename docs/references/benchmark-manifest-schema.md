# Benchmark manifest v1

`application/benchmark.py` consumes a strict JSON manifest and an injected search function. The CLI owner connects `gamingcreator benchmark --input <manifest.json> --project <project> --output <report.json>`. This document supplements `phase-0-benchmark.md`; its human-quality threshold is unchanged.

The optional local [preparation workflow](./benchmark-preparation-guide.md) freezes original footage identities, recording/partition/query families and human references before binding Completed runs to this unchanged v1 format. Generated candidateLabels remain empty. `benchmark --binding <bound-directory>` verifies the immutable template before opening storage or loading retrieval models; only candidateLabels and humanLabels.reviewed may change. Reference confirmation or independence cannot be added after viewing results under the same binding. Preparation readiness records declarations and consistency, not authenticated human acceptance. Legacy manifests without this option keep their original behavior.

## Prepare an unlabelled run

Copy `templates/phase0-benchmark.example.json`. Replace each source's `mediaId`, Completed `runId`, lowercase 64-character `sha256`, and positive `durationUs` with actual timeline metadata. Query source pairs must match `media`. Durations and all interval endpoints are source-relative Int64 integer microseconds. JSON booleans, floats and numeric strings cannot stand in for integers. Duplicate identities, unknown fields and duplicate JSON keys are rejected.

Leave `humanLabels.confirmed: false` until a person has watched and judged the source clips. An unlabelled manifest runs and reports timing/results, with quality metrics and `qualityGate: null`. The example has placeholder source metadata and must be edited before a verified CLI run.

## Freeze references and judge candidates

Record `datasetId`, `labelVersion`, human `annotators`, timezone-qualified ISO `frozenAt`, `reviewed`, and `independentTestSet`. Freeze queries and references before inspecting model results; keep same-session recordings and query families together. `confirmed: true` requires annotators, label version and frozen timestamp. This declaration is recorded, not authenticated by the tool.

Each query has `id`, `text`, `kind`, `mediaId`, `runId`, `referenceEvents`, and `candidateLabels`. Each reference has:

- `humanEventId`: human-defined event identity, separate from model event IDs.
- `independenceGroup`: one real action/event; reference groups must be unique.
- `usableRanges`: nonempty array of `{startUs, endUs}` source intervals.
- `reason`: human explanation.

Confirmed `main` queries require at least **10 independent useful references**; `sparse` queries require 1–9; `negative` queries require zero. Main references are required before inference; reaching seven returned useful events is the pass threshold.

After viewing returned clips, add candidate judgments:

```json
{
  "eventId": "actual-model-event-id",
  "humanEventId": null,
  "startUs": 0,
  "endUs": 1000000,
  "grade": 0,
  "reason": "Replace with the person's assessment of this exact clip."
}
```

Grades are integer 0 (irrelevant), 1 (related but unusable), 2 (usable), 3 (highly relevant). Grades 2/3 require a matching human reference ID. Each model event may have one judgment; bind it to the exact reviewed start/end. Changed boundaries need fresh review. Different model events mapped to the same human event count as duplicates.

## Scoring and report

The returned tuple order defines ten slots; rank is retained for diagnostics and never causes reordering or replacement from the eleventh result. Missing and duplicate slots are zero. Unjudged clips keep metrics/gates null. Every query is reported; a failed or unjudged query prevents a passing aggregate gate. Main queries each require U10 ≥0.70. Sparse recall/precision and negative returns remain separate. The negative-alert threshold is not frozen, so its gate stays null.

The root adapter must verify each Completed source/run, SHA256, duration and storage integrity through `verify_media`. Without this verifier, the aggregate quality gate remains null. Human declarations must also identify an independent test set. The report includes ten slots, missed human references, duplicates, source bounds errors, endpoint error median/P90, search wall-clock timing and caller-supplied model/config versions. Human selection time and hardware cost remain null unless separately measured.

`BenchmarkCosts` accepts Decimal cold/hot CNY totals. Unknown is null, never zero. Cold cost/hour uses all unique source durations; its `<¥5/h` gate requires complete attempt accounting, estimated/confirmed status, a price version and verified source identities. Search timing excludes analysis. A metric unit test cannot establish real Phase 0 acceptance.

## Integration contract

```python
manifest = loads_manifest(json_text)
report = await run_benchmark(
    manifest,
    search,  # async (BenchmarkQuery) -> tuple[BenchmarkHit, ...]
    verify_media=verify,  # async (BenchmarkMedia) -> None; raise on invalid source/run
    runner_metadata={"retrievalVersion": "actual-version", "configHash": "actual-hash"},
    costs=BenchmarkCosts(),  # default unknown cost
)
```

`BenchmarkHit(event_id, start_us, end_us, rank)` is independent of the retrieval implementation. Cancellation propagates; failed search/source checks yield stable error codes without raw exception text. The runner performs no file I/O, installation or paid model request.
