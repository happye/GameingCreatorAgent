# Step2 local branch bundle inventory (2026-11-01)

Bundle (outside the repo since 2026-11-01 21:10 — `.cache/scratch` is deletable; restore with `git fetch <bundle> <branch>:<branch>`):
`G:\Tools\ChatGPTRepo\GameingCreatorAgent-archive\2026-11-01-branch-backup\step2-local-branches-20261101-171840.bundle`
The eight orphan worktree copies (`orphan-wt-*`) moved to the same folder. 40 of the bundled snapshot branches differ from `main`; this bundle is their only copy.
Size bytes: 3855281

Deleted local branches after successful `git bundle verify` (main kept). Remote-tracking branches on origin were not deleted.
claude/harness-adapter
codex/F001-core
codex/F002-job
codex/F002-media
codex/F003-asr
codex/F003-models
codex/F003-transcript-storage
codex/F003-vision
codex/F004-process
codex/F004-schema
codex/F004-storage
codex/actor-detail-contract
codex/actor-detail-spec
codex/actor-detail-tests
codex/audio-mix-render
codex/audio-mix-workspace
codex/benchmark-result-cards
codex/billing-confirmation-20261011
codex/caption-editing-backend
codex/caption-editing-frontend
codex/clip-speed-core
codex/clip-speed-frontend
codex/clip-speed-render
codex/clip-transition-render
codex/creation-editing-backend
codex/creation-editing-core
codex/creation-editing-frontend
codex/creation-planner-20261030
codex/creation-render-20261030
codex/creation-subtitles
codex/creation-workspace-backend
codex/creation-workspace-frontend
codex/demo-benchmark
codex/demo-pricing
codex/demo-retrieval
codex/detail-cost-history
codex/detail-feedback
codex/detail-parts-v3
codex/detail-pilot
codex/detail-pilot-compare
codex/detail-presentation
codex/detail-query-draft
codex/detail-temporal-entities
codex/detail-v4-proposal
codex/detail-v6
codex/detail-vision
codex/ffmpeg-candidate-validation
codex/inspection-frontend
codex/inspection-workspace
codex/local-narration-assets
codex/media-clock-expectations
codex/music-library
codex/narration-integration
codex/narration-mix
codex/offline-media-setup
codex/phase0-demo
codex/platform-package-backend
codex/platform-package-frontend
codex/publication-assets-backend
codex/publication-assets-frontend
codex/replacement-backend
codex/replacement-core
codex/replacement-ui
codex/retrieval-negation
codex/subtitle-render-public
codex/subtitle-workspace-public
codex/temporal-frame-contract
codex/temporal-gameplay
codex/temporal-pilot
codex/temporal-vision
codex/transition-core-resume
codex/transition-render-resume
codex/transition-ui-resume
codex/visual-details
codex/workflow-status-retry
codex/workspace-launcher
codex/workspace-layout
codex/workspace-usability

## Orphan worktree directories removed (not registered in `git worktree list`; no `.git` file; dirty=false)
demo-retrieval
f002-job
f003-asr
f003-vision
f004-process
f004-schema
temporal-frame-contract
temporal-vision

## Orphan worktree directories

Not registered in `git worktree list` (no `.git` file). Could not hard-delete some nested locked `.cache` dirs; moved entire trees to ignored `.cache/scratch/orphan-wt-*` (safe to delete when unlocked):

- demo-retrieval, f002-job, f003-asr, f003-vision, f004-process, f004-schema, temporal-frame-contract, temporal-vision

`.worktrees/` directory cleared.
