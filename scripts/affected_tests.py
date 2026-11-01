"""Pick the pytest files affected by the current change, and optionally run them.

Tier 1 of docs/references/testing-guide.md: iterate on affected tests only; the full
suite (verify.ps1) runs once at a milestone. Selection is a static heuristic:

- a changed test file selects itself;
- a changed src module selects tests that import it (--deep adds tests of src modules
  that import it, one level of reverse dependency);
- a changed static UI file or script selects tests that mention its file name (a UI
  file nobody names selects every browser test);
- tests/conftest.py, pyproject.toml or uv.lock select the full suite.

Exit codes: 0 ok (or nothing to run), 1 pytest failed, 2 usage error.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"
FULL_TRIGGERS = {"tests/conftest.py", "pyproject.toml", "uv.lock"}
DEFAULT_MARKS = "not browser and not local_data"


def _git(*args: str) -> list[str]:
    out = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def changed_files(base: str) -> list[str]:
    files = set(_git("diff", "--name-only", base))
    files |= set(_git("diff", "--name-only", "--cached"))
    files |= set(_git("ls-files", "--others", "--exclude-standard"))
    return sorted(f.replace("\\", "/") for f in files)


def _module_name(path: str) -> str | None:
    if not (path.startswith("src/gamingcreator/") and path.endswith(".py")):
        return None
    parts = path[len("src/") : -len(".py")].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _import_pattern(module: str) -> re.Pattern[str]:
    parent, _, stem = module.rpartition(".")
    name = re.escape(stem)
    return re.compile(
        rf"\b{re.escape(module)}\b"
        rf"|from\s+{re.escape(parent)}\s+import\s+(?:\([^)]*\b{name}\b[^)]*\)|[^\n(]*\b{name}\b)"
    )


def _texts(paths: list[Path]) -> dict[Path, str]:
    return {p: p.read_text(encoding="utf-8", errors="replace") for p in paths}


def select(changed: list[str], deep: bool = False) -> tuple[list[str], bool, bool]:
    """Return (test files, full_suite, touches_ui)."""
    if FULL_TRIGGERS & set(changed):
        return [], True, False
    test_texts = _texts(sorted(TESTS.glob("test_*.py")))
    src_texts = _texts(sorted(SRC.rglob("*.py"))) if deep else {}
    picked: set[Path] = set()
    touches_ui = False
    for path in changed:
        file = ROOT / path
        if path.startswith("tests/") and Path(path).name.startswith("test_") and file.exists():
            picked.add(file)
            continue
        if path.startswith("tests/") and path.endswith(".py"):
            stem = Path(path).stem
            pattern = re.compile(rf"\b{re.escape(stem)}\b")
            picked |= {t for t, text in test_texts.items() if pattern.search(text)}
            continue
        module = _module_name(path)
        if module:
            touches_ui = touches_ui or module.startswith("gamingcreator.ui")
            modules = {module}
            pattern = _import_pattern(module)
            for src_file, text in src_texts.items():
                dependent = _module_name(src_file.relative_to(ROOT).as_posix())
                if dependent and dependent != module and pattern.search(text):
                    modules.add(dependent)
            for name in modules:
                pattern = _import_pattern(name)
                picked |= {t for t, text in test_texts.items() if pattern.search(text)}
            continue
        if path.startswith(("src/gamingcreator/ui/", "scripts/")):
            is_ui = path.startswith("src/gamingcreator/ui/")
            touches_ui = touches_ui or is_ui
            name = Path(path).name
            named = {t for t, text in test_texts.items() if name in text}
            if is_ui and not named:
                # Nothing names this static file: every browser test may render it.
                named = {t for t, text in test_texts.items() if "playwright" in text}
            picked |= named
    return sorted(p.relative_to(ROOT).as_posix() for p in picked), False, touches_ui


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="HEAD", help="git ref to diff against (default HEAD)")
    parser.add_argument("--run", action="store_true", help="run pytest on the selection")
    parser.add_argument(
        "--browser", action="store_true", help="include browser tests (auto when UI changed)"
    )
    parser.add_argument(
        "--deep", action="store_true", help="also select tests of modules importing the change"
    )
    parser.add_argument("pytest_args", nargs="*", help="extra pytest arguments after --")
    args = parser.parse_args(argv)
    changed = changed_files(args.base)
    tests, full, touches_ui = select(changed, deep=args.deep)
    marks = None if (args.browser or touches_ui) else DEFAULT_MARKS
    print(f"changed files: {len(changed)}")
    if full:
        print("selection: FULL suite (conftest/pyproject/lock changed)")
    else:
        print(f"selection: {len(tests)} test files")
        for test in tests:
            print(f"  {test}")
    print(f"marker filter: {marks or '(none, browser tests included)'}")
    if not args.run or (not full and not tests):
        return 0
    command = [sys.executable, "-B", "-m", "pytest", *([] if full else tests)]
    if marks:
        command += ["-m", marks]
    command += args.pytest_args
    print("running:", " ".join(command[1:]))
    code = subprocess.run(command, cwd=ROOT).returncode
    if code == 5:
        print("all selected tests were filtered out by the marker filter (use -Browser)")
        return 0
    return 1 if code else 0


if __name__ == "__main__":
    raise SystemExit(main())
