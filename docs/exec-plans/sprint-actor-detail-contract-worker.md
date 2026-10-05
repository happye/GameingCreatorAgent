# Actor detail contracts and offline matcher worker

2026-10-05. Owner: `detail_v6_completion`, isolated worktree
`.worktrees/actor-detail-contract`, branch `codex/actor-detail-contract`, base
`00bc88f`. Root specification froze as `b1d91bc`, integrated as `a7789b4`.

Own only `domain/actor_details.py`, `application/actor_detail_matching.py`,
`test_actor_detail_matching.py` and this record. Root reassigned independent
`test_actor_details.py` to the audit worker in `.worktrees/actor-detail-tests`;
it has never been edited here and will be independently committed/integrated.
Other agents own root/provider/sidecar/CLI/UI; do not overwrite their changes.
Old detail-v6 remains frozen. No API calls, installations or global configuration.

## Scope and approach

Frozen typed candidate-local contracts validate run/media/event/candidate identity,
actual evidence clocks/hashes, shot partition, actor/part scope, bounded collections,
observed/uncertain values and multi-frame actions. Query uses a small explicit
versioned vocabulary and canonical positive typed constraints, not free text.
Matcher anchors candidate combinations on a shared registered supporting frame,
binds each part_group to one part on one actor in one shot, and retains structural
conflicts. No-match requires reliable observed opposition for every potential actor;
missing/uncertain/unassigned subjects are not negative evidence.

Implementation in progress. Root scaffold check passes. Next: matcher, fixtures
1–5, default mypy, Ruff and architecture tests using root env/Python `-B`; unique
root-cache pytest parent must be created before invocation. Record all failures
and verified results before committing only these four owned files and freezing.

## Validated implementation checkpoint

The two source modules and development fixtures 1–5 are implemented. Versions:
`actor-details-v1`, `actor-detail-vocabulary-v1`, `actor-detail-query-schema-v1`,
`actor-detail-query-v1`, `actor-detail-matcher-v1`. `canonical_constraint_json`
and `constraint_hash` normalize only explicit synonyms and sort positive typed
conditions; all future value extensions require a vocabulary version change.

Candidate includes base prompt/hash and nonempty `detail_identity_hash`; the
subsequent sidecar/application must compute/recheck that identity plus Completed
timeline registration. Domain checks the program-supplied frozen registry, not
the existence of footage on disk. Attributes cannot invent references, source
clocks/durations, action motion or cross-shot identity. Original event/basket
models and all existing search/provider/store modules are unchanged.

Early review found and corrected the candidate formula: production retrieval uses
`sha256(run_id + ':event:' + event_id)[:24]`, including its Document namespace.
It also found unsafe global-kind opposition; matcher now proves opposition at
every shot support frame, with actual part scope and positive garment-shape
anchors. A missing later hair observation and blue scarf/unknown coat remain
unverified/partial. `counter_evidence` preserves the per-frame/part proof.
Different action/effect/environment/held-shape/class values are not assumed
exclusive; only explicit hue/lightness and concrete garment alternatives are.

Review also closed empty matched-support and fabricated common-range/duration
constructors. Supported conditions in one part group must cite the same part.
Full results need shared actual frame IDs and a nonempty common source range;
conflicts and uncertain classifications cannot supply full support.

Root scaffold and full toolchain/media checks pass. Latest preliminary checks:
Ruff format/lint on 3 owned Python files pass; configured mypy passes 51 files;
18 matcher fixtures plus 3 architecture tests pass (21 total, 0.15 seconds).
All commands use root `scripts/env.ps1`, root isolated Python `-B`, only current
process worker `PYTHONPATH`, and unique root `.cache` pytest parents.

Failures retained: first mypy exposed missing vocabulary annotations and an
optional-part list type; next pass exposed reused local set/list variable naming.
First fixture batch had 20 pass/1 fail: dataclass replacement retained derived
unassigned IDs when shots changed; the fixture now explicitly resets that derived
input. Ruff reported one unused test import, removed. One patch attempt used a
pre-format context and applied nothing; rereading the formatted lines resolved it.
These were repaired without changing acceptance or source-time protections.

Final focused checks after the report-part validation pass: Ruff on all three
owned Python files, configured mypy on 51 files plus strict mypy of the new test,
and 21 matcher/architecture pytest cases (0.15 seconds). Independent audit worker
reports 73 domain cases passing this source, with hand-written canonical JSON and
literal constraint hash; those tests remain in its separate worktree/commit.
Save this local implementation checkpoint, then audit performs final independent
contract/matcher/architecture review. Any material finding requires a follow-up
owned-file commit; otherwise freeze. Root owns complete integration verification,
ports/sidecar/provider and future UI/CLI/query parsing.
No API calls, installations, paid experiments or quality acceptance occurred.
