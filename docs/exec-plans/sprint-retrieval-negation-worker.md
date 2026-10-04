# Bounded action-negation retrieval correction

## Ownership and checkpoint

Worker branch `codex/retrieval-negation`, baseline `0cc2c2f`. Own only
`src/gamingcreator/application/retrieval.py`, `tests/test_retrieval_negation.py`,
and this log. Other agents own the launcher, providers, root documentation and
real validation artifacts; their files must remain untouched.

## Problem and intended behavior

The new temporal Atom analysis contains an event describing slight movement
but explicitly denying attacks, jumps and interaction. A positive jump query
currently matches the denied word. Correct only bounded, explicit Chinese and
English action negation during ranking; retain affirmative clauses, uncertain
language, non-action searches and queries requesting absence. Do not change
source facts, embedding passage text/hashes, thresholds or persisted searches.
Version new retrieval behavior separately. This is not general language or
gameplay understanding, and F006 still requires human acceptance.

## Completed behavior

New retrieval version is `bm25-e5-rrf-v4`. Query-time exclusion recognizes a
small vocabulary of jump, shoot, attack, fight, interact and move actions.
Chinese explicit prefixes and conjunction lists (`无明确攻击、跳跃或交互动作`)
and bounded English equivalents cannot supply positive action hits when all
query-action mentions in the document occur in such denials. Separate
affirmative or unknown mentions keep the event. An English photographic
`shot` query is deliberately outside this action vocabulary.

The guard applies before lexical/semantic fusion and semantic truncation;
passage strings, embedding subject associations, exported event embeddings,
facts, thresholds and old saved search results remain intact. Queries with
explicit absence intent bypass the guard as compatibility behavior; absence
understanding has not been added. Uncertain or double-negative prefixes also
retain eligibility. Non-action searches do not discard these events.

## Verification and limits

Ruff format/check passed; strict mypy passed on both owned Python files.
Existing retrieval, persistence and search CLI tests plus new public-behavior
tests: **167 passed in 1.31s**, `-W error`. Tests exercise lexical, hybrid and
semantic denial rejection, mixed clauses, Chinese lists, English contractions,
uncertainty, generic searches, absence intent and unchanged passage hashes.
Root-local `.venv` tools were used with worktree `src` on process-only
`PYTHONPATH`; caches remain in root `.cache/pytest-runs/retrieval-negation-*`.
No paid API calls, dependency installation or global configuration changes.

The first test batch had six fixture assertions that accidentally required
English stemming (`jump` matching `jumps`/`jumped`); vocabulary was corrected
without expanding retrieval scope. Ruff also caught an unnecessary UTF-8
encoding argument. All corrected checks above passed.

This bounded guard does not parse arbitrary negation, actor attribution,
long-range discourse or contradictory tags. Unrecognized wording remains
eligible; any unnegated recognized occurrence retains the event. Generic
semantic false positives can remain. A real local-model rerun and human F006
acceptance belong to the root task. The root engineering spec still says v3
and must be aligned when integrating this commit.
