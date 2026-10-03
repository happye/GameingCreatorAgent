import ast
from pathlib import Path

import pytest


def imported_modules(source: str, package_parts: list[str]) -> list[str]:
    modules = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package_parts[: len(package_parts) - node.level + 1] if node.level else []
            parent = [*base, *(node.module.split(".") if node.module else [])]
            modules.append(".".join(parent))
            modules.extend(".".join([*parent, alias.name]) for alias in node.names)
    return modules


@pytest.mark.parametrize(
    "source",
    ["from gamingcreator import infrastructure", "from .. import infrastructure"],
)
def test_import_check_detects_package_aliases(source: str) -> None:
    assert "gamingcreator.infrastructure" in imported_modules(source, ["gamingcreator", "domain"])


def test_imports_follow_layer_direction_and_domain_has_no_io_dependencies() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src" / "gamingcreator"
    allowed = {
        "domain": {"domain"},
        "application": {"application", "domain"},
        "infrastructure": {"infrastructure", "application", "domain"},
        "cli": {"cli", "infrastructure", "application", "domain"},
    }
    forbidden_domain = {"sqlite3", "subprocess", "httpx", "requests", "faster_whisper"}
    violations = []
    for path in source_root.rglob("*.py"):
        relative = path.relative_to(source_root)
        layer = relative.parts[0]
        if layer not in allowed:
            continue
        package_parts = ["gamingcreator", *relative.parts[:-1]]
        for imported in imported_modules(path.read_text(encoding="utf-8"), package_parts):
            if imported == "gamingcreator.__version__" and layer == "cli":
                continue
            parts = imported.split(".")
            if layer == "domain" and parts[0] in forbidden_domain:
                violations.append(f"{relative}: domain imports {imported}")
            if len(parts) >= 2 and parts[0] == "gamingcreator" and parts[1] not in allowed[layer]:
                violations.append(f"{relative}: forbidden layer import {imported}")
    assert not violations, "\n".join(violations)
