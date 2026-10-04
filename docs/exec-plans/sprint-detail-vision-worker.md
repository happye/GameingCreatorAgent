# Detail vision worker — 2026-10-05

## Ownership and acceptance

Own only `src/gamingcreator/infrastructure/deepseek_vision.py`, new
`tests/test_detailed_vision.py`, and this record on `codex/detail-vision`.
Other agents own integration/configuration, retrieval, UI and shared documents;
their changes must not be reverted. Root will merge the frozen commit.

Implement V5 as a new prompt identity with the existing six-field temporal schema.
Describe visible actor attributes, held equipment, other actors, environment and
supported action progression together; never invent official names or mechanics.
Require changing evidence at two source instants. Keep legacy V1–V4 frozen.
V5 accepts up to nine JPEGs, width 1,280 and three MiB each, with `detail: original`.
Resolve leaked lowercase frame aliases through the actual supplied source clock
before creating event identity; unsupported aliases fail a finite diagnostic.

## Current state

Implemented V5 with prompt hash
`c64c644e9889fcfd91cc0e9a26d8bf1b9546ce73c548e6ac056a5067498ff98a`.
Schema remains `temporal-actions-v1`; V1–V4 original prompt hashes are unchanged.
V5 bounds facts to six items and 1,000 characters total (prompt target about 250
Chinese characters); normalized facts are checked again before event hashing.
Known prose aliases in facts, tags and uncertainty resolve through actual source
instants to `HH:mm:ss.mmm`. Unknown exact lowercase `fN` fails `event_prose_alias`.
ASCII words, uppercase keyboard names and ordinary compound identifiers stay
unchanged; ranges consisting solely of frame aliases still resolve.

No paid calls or installs occurred. Checks used root `.venv` and `.cache`, root
`scripts/env.ps1`, Python `-B`, and process-only worktree `PYTHONPATH`.

## Verification and handoff

Ruff format/check and strict mypy of the provider plus new test file passed.
Joint V5/legacy DeepSeek/temporal contracts: **226 passed, four deselected**.
The four older tests embed feature expectations invalidated by adding V5:
two expect the provider capability to remain width 512, and two expect V5 to be
unsupported. Root owns updating those assertions to width 1,280/V6; payload tests
confirm all legacy inputs still enforce width 512, one MiB, and no detail field.
The new file includes 52 passing cases covering exact bounds, temporal guards,
empty observations, actor-bound prompt requirements and alias normalization.

Initial Ruff check found one unused test import; it was removed and checks passed.
A compound-guard patch initially missed Ruff's reformatted context and applied
no changes; the patch was reapplied against current text and verified.

Root must integrate V5 config, exact fingerprint, detail pipeline identity,
media width and bounded real experiments. Historical stored text stays frozen;
the UI's treatment of old-run aliases is owned elsewhere. Passing contracts
do not establish visual quality, true Boss identity, or F006 acceptance.
