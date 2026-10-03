# Phase 0 execution plan

Work through `feature_list.json` in priority order, one feature per sprint. F000 is a written reverse review of the product plan and must precede implementation. It should identify overly optimistic assumptions, model and video-processing limits, cost risks, maintenance burden, and the smallest useful technical loop.

For each feature, use `sprint-template.md` to record the expected behavior and verification before editing code. After implementation, run the checks available for that feature and record evidence in `progress.md`. A feature passes only when its stated criteria are met; incomplete work remains `passes: false`.

When the CLI and benchmark exist, use 10–20 representative local recordings if available, annotate useful time ranges, and evaluate Top-10 Useful Rate, retrieval misses, timecode error, elapsed time, and cost. The 70% target is the gate for moving beyond retrieval into a creative planner or UI.

Do not expand the feature list to 200 speculative items at initialization. The source plan explicitly keeps Phase 0 narrow. Add later-phase features only after the feasibility gate and a reviewed product decision.
