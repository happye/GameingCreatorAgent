# Coding standards

The repository has no C# code or analyzer configuration yet. `.editorconfig` establishes UTF-8, final newlines, and four-space C# indentation. When F001 creates the first project, add a formatter/analyzer and document its exact command in `AGENTS.md`.

- Name C# types and public members in PascalCase, local variables and parameters in camelCase. Match domain concepts from the product plan; avoid generic names for semantic events or clips.
- Keep domain contracts independent of FFmpeg, SQLite, model SDKs, and the future UI. Make dependencies point toward domain/application contracts.
- Validate external input and file paths at the boundary. Pass structured arguments to FFmpeg and database APIs; never assemble untrusted shell or SQL text.
- Emit structured, useful diagnostics without secrets or raw user media. Include the operation, media identifier, model/provider, timing, and failure reason where relevant.
- Prefer small cohesive files and functions. Split a file when its responsibility becomes hard to describe; do not force an arbitrary line-count limit.
- Version prompt text and output schemas, and include the version in each stored analysis record.

Keep these rules executable through tooling once code exists; until then, review them during each feature's verification.
