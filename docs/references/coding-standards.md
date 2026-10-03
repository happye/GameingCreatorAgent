# Coding standards

Phase 0 follows [ADR-001](../design-docs/adr-001-phase-0-language.md). `.editorconfig` establishes UTF-8, final newlines and four-space Python indentation. `pyproject.toml` configures Ruff (100-column formatting) and strict mypy; `uv.lock` pins them. Run `./scripts/verify.ps1` before review, or dot-source `scripts/env.ps1` and invoke project Python for focused checks.

- Use PascalCase for Python types, snake_case for modules/functions/variables, and UPPER_SNAKE_CASE for constants. Mirror domain concepts; explicitly map external JSON field names to internal names.
- Type public contracts and domain logic; use dataclass records and Protocol ports with strict type checks. Validate external dictionaries at boundaries; do not pass unvalidated model output through the core.
- Keep domain contracts independent of FFmpeg, SQLite, model SDKs, and the future UI. Make dependencies point toward domain/application contracts.
- Validate external input and file paths at the boundary. Pass structured arguments to FFmpeg and database APIs; never assemble untrusted shell or SQL text.
- Emit structured, useful diagnostics without secrets or raw user media. Include the operation, media identifier, model/provider, timing, and failure reason where relevant.
- Prefer small cohesive files and functions. Split a file when its responsibility becomes hard to describe; do not force an arbitrary line-count limit.
- Version prompt text and output schemas, and include the version in each stored analysis record.

`tests/test_architecture.py` checks static package imports, including relative and package alias imports. This is an import guard, not a complete sandbox; avoid dynamic import workarounds and review new dependencies.
