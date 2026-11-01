"""Third-party notices collector covers packaged dist-info from on-disk files only."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/collect-third-party-notices.py"


def _load():
    spec = importlib.util.spec_from_file_location("collect_third_party_notices", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_collector_covers_every_packaged_dist_info(tmp_path: Path) -> None:
    module = _load()
    output = tmp_path / "licenses"
    rows, gaps = module.collect(ROOT, output)
    assert (output / "THIRD-PARTY-NOTICES.md").is_file()
    assert (output / "notices.json").is_file()
    names = {row.name.lower() for row in rows}
    site = ROOT / ".venv/Lib/site-packages"
    packaged = module._packaged_dist_infos(site)
    assert packaged, "expected a local venv site-packages for this offline test"
    for dist_info in packaged:
        meta_name, _, _ = module._read_metadata(dist_info)
        assert meta_name.lower() in names, dist_info.name
    missing = [row for row in rows if row.status == "missing_license_file"]
    gap_text = " ".join(gap["component"].lower() for gap in gaps)
    for row in missing:
        tokens = [
            row.name.lower(),
            row.name.split("/")[-1].lower(),
            row.name.replace("/", " ").lower(),
        ]
        assert any(token and token in gap_text for token in tokens), (row.name, gap_text)


def test_collector_copies_pep639_license_tree(tmp_path: Path) -> None:
    module = _load()
    anyio = ROOT / ".venv/Lib/site-packages/anyio-4.15.1.dist-info"
    if not anyio.is_dir():
        pytest.skip("anyio dist-info missing")
    files = module._license_files(anyio)
    assert any(path.name.upper().startswith("LICEN") for path in files)
    output = tmp_path / "licenses"
    module.collect(ROOT, output)
    copied = list((output / "sources/python").rglob("LICENSE*")) + list(
        (output / "sources/python").rglob("LICENCE*")
    )
    assert copied, "expected copied LICENSE/LICENCE files under sources/python"


def test_install_fixture_requires_licenses_part() -> None:
    text = (ROOT / "scripts/install-app.ps1").read_text(encoding="utf-8")
    assert "'licenses'" in text
    build = (ROOT / "scripts/build-app.ps1").read_text(encoding="utf-8")
    assert "'licenses'" in build
    assert "collect-third-party-notices.py" in build
