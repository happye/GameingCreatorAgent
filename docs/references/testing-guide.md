# Testing guide

Old per-run records and module-by-module notes are archived in [testing-guide-2026-10](../archive/history/testing-guide-2026-10.md). Do not add run results here: put them in the commit message, or in a sprint for milestones.

## Three tiers

| Tier | When | Command | Typical cost |
| --- | --- | --- | --- |
| 1 Affected | every iteration | `./scripts/test-affected.ps1` | 10–40 files, about 1–2 minutes |
| 2 Full | milestone end, before merge | `./scripts/verify.ps1` | lock, ruff, mypy, all ~4,600 tests; about 20+ minutes |
| 3 Release | before distributing an installer | `./scripts/verify.ps1 -Release` | tier 2 plus two reproducible offline wheel builds |

`test-affected.ps1` diffs against `HEAD` (pass `-Base <ref>` for a branch) and selects:
- changed test files;
- tests that import a changed module (`-Deep` adds tests of the modules that import it);
- tests that name a changed script or static UI file. A UI file nobody names selects every browser test.

Changes to `tests/conftest.py`, `pyproject.toml` or `uv.lock` select the full suite. `-ListOnly` prints the selection without running it; pass simple extra pytest options as one string, e.g. `-PytestArgs '-x -rfE'` (quoted expressions such as `-k "a and b"`: call `python -B scripts/affected_tests.py --run -- -k "a and b"`).

## Markers

`tests/conftest.py` applies these automatically from each module's source, so nobody tags tests by hand:
- `browser`: imports Playwright or `importorskip`s it (42 files).
- `local_data`: reads real dated `artifacts/<name>-YYYYMMDD` folders or `GameVideos/` and skips when absent (3 files).
- `ffmpeg`: mentions ffmpeg/ffprobe (55 files).
- `media`: the explicit project-FFmpeg integration marker.

Tier 1 runs with `-m "not browser and not local_data"` unless UI files changed or `-Browser` is given. Run `local_data` tests explicitly when acceptance evidence matters: `pytest -m local_data`.

## Rules

- Known failures: mark `@pytest.mark.xfail(strict=False, reason="TDxxx")` and add a tech-debt row. Remove the marker when the fix lands. The full suite must otherwise be green.
- Failures: rerun only the failed tests with `pytest --lf` (the cache is `.cache/pytest-cache`). Do not rerun the whole suite to "check it is still the same failures".
- Do not create new `.cache/<name>` basetemp or JUnit folders per run. `verify.ps1` deletes its run folder when the run passes; a failing run keeps its folder and prints the path, and leftovers older than a day are pruned. Set `GC_KEEP_TEST_MEDIA=1` to keep media.
- Tests assert behavior: inputs, source-time bounds, persistence, errors. A passing compile is not feature evidence; attach test evidence to the feature's sprint or commit.

## Browser setup (once per machine)

```powershell
. ./scripts/env.ps1
./.tools/uv/uv.exe --no-config sync --locked --extra asr --extra retrieval --extra ui-test --python ./.venv/Scripts/python.exe --no-python-downloads
./.venv/Scripts/python.exe -B -m playwright install chromium
```

## Retrieval benchmark

The quality gate is in [phase-0-benchmark](phase-0-benchmark.md). Top-10 Useful Rate always uses ten slots; missing and duplicate events score zero; independent human-judged usable events must reach ≥70%. Main, sparse-positive and negative queries are frozen before results are viewed. Keep raw footage outside Git.
