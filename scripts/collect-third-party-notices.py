"""Collect third-party license texts that already exist on disk into licenses/.

Does not download anything. Missing license files are listed for human-inputs.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

DEVELOPER_DIST_PREFIXES = (
    "mypy-",
    "mypyc-",
    "pytest-",
    "ruff-",
    "hatchling-",
    "iniconfig-",
    "pluggy-",
    "pathspec-",
    "trove_classifiers-",
    "gamingcreator-",  # first-party; not third-party
)

LICENSE_NAME_RE = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE)([.-].*)?$", re.IGNORECASE)


@dataclass(frozen=True)
class NoticeRow:
    name: str
    version: str
    license_type: str
    source_file: str
    copied_to: str
    status: str  # ok | missing_license_file | noted_without_file


def _safe_name(value: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", value).strip("_") or "item"


def _read_metadata(dist_info: Path) -> tuple[str, str, str]:
    meta = dist_info / "METADATA"
    name = dist_info.name.split("-")[0]
    version = ""
    license_type = ""
    if not meta.is_file():
        return name, version, license_type
    for line in meta.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("Name:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("Version:"):
            version = line.split(":", 1)[1].strip()
        elif line.startswith("License-Expression:"):
            license_type = line.split(":", 1)[1].strip()
        elif line.startswith("License:") and not license_type:
            license_type = line.split(":", 1)[1].strip()
        elif line.startswith("Classifier: License ::") and not license_type:
            license_type = line.split("License ::", 1)[1].strip()
    return name, version, license_type or "UNKNOWN"


def _license_files(directory: Path) -> list[Path]:
    """Top-level LICENSE* plus PEP 639 licenses/ trees under a dist-info directory."""
    if not directory.is_dir():
        return []
    found: list[Path] = []
    for path in directory.iterdir():
        if path.is_file() and LICENSE_NAME_RE.match(path.name):
            found.append(path)
    nested = directory / "licenses"
    if nested.is_dir():
        for path in nested.rglob("*"):
            if path.is_file() and LICENSE_NAME_RE.match(path.name):
                found.append(path)
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in sorted(found, key=lambda item: str(item).lower()):
        if path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return ordered


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _packaged_dist_infos(site: Path) -> list[Path]:
    if not site.is_dir():
        return []
    rows = []
    for path in sorted(site.glob("*.dist-info")):
        lower = path.name.lower()
        if any(lower.startswith(prefix) for prefix in DEVELOPER_DIST_PREFIXES):
            continue
        if lower.startswith("_editable_impl_"):
            continue
        rows.append(path)
    return rows


def collect(repository: Path, output: Path) -> tuple[list[NoticeRow], list[dict[str, str]]]:
    repository = repository.resolve()
    output = output.resolve()
    if output.exists():
        shutil.rmtree(output)
    sources = output / "sources"
    sources.mkdir(parents=True)

    rows: list[NoticeRow] = []
    gaps: list[dict[str, str]] = []

    # CPython
    python_roots = sorted((repository / ".tools/python").glob("cpython-*")) if (repository / ".tools/python").is_dir() else []
    if python_roots:
        py = python_roots[0]
        license_txt = py / "LICENSE.txt"
        dest = sources / "cpython" / "LICENSE.txt"
        if license_txt.is_file():
            _copy_file(license_txt, dest)
            rows.append(
                NoticeRow(
                    "CPython",
                    py.name,
                    "PSF / historical (see LICENSE.txt)",
                    str(license_txt.relative_to(repository)).replace("\\", "/"),
                    str(dest.relative_to(output)).replace("\\", "/"),
                    "ok",
                )
            )
        else:
            gaps.append({"component": "CPython", "reason": "LICENSE.txt missing under .tools/python"})
            rows.append(NoticeRow("CPython", py.name, "UNKNOWN", "", "", "missing_license_file"))
    else:
        gaps.append({"component": "CPython", "reason": ".tools/python runtime directory missing"})

    # FFmpeg — production tree has binaries only; do not invent a LICENSE from another build.
    ffmpeg_bin = repository / ".tools/ffmpeg/bin"
    media_pin = repository / "docs/references/media-toolchain.json"
    ffmpeg_note = sources / "ffmpeg" / "BUILD-AND-PROVENANCE.txt"
    ffmpeg_note.parent.mkdir(parents=True, exist_ok=True)
    note_lines = [
        "FFmpeg binaries shipped under .tools/ffmpeg/bin.",
        "No LICENSE.txt sits next to the production binaries in this checkout.",
        "",
    ]
    if media_pin.is_file():
        _copy_file(media_pin, sources / "ffmpeg" / "media-toolchain.json")
        pin = json.loads(media_pin.read_text(encoding="utf-8"))
        note_lines.append(f"Pinned version field: {pin.get('version')}")
        note_lines.append(f"Provenance note: {pin.get('provenance')}")
        note_lines.append(
            "Download/distribution provenance and GPL obligations must be resolved before packaging."
        )
    note_lines.append("")
    note_lines.append("ffmpeg -version (captured at collect time when binary exists):")
    version_path = ffmpeg_bin / "ffmpeg.exe"
    if version_path.is_file():
        import subprocess

        proc = subprocess.run(
            [str(version_path), "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        note_lines.extend((proc.stdout or proc.stderr or "").splitlines()[:8])
    ffmpeg_note.write_text("\n".join(note_lines) + "\n", encoding="utf-8")
    rows.append(
        NoticeRow(
            "FFmpeg",
            (json.loads(media_pin.read_text(encoding="utf-8")).get("version") if media_pin.is_file() else ""),
            "GPL (enabled in build flags); production LICENSE.txt missing on disk",
            str(media_pin.relative_to(repository)).replace("\\", "/") if media_pin.is_file() else "",
            str(ffmpeg_note.relative_to(output)).replace("\\", "/"),
            "noted_without_file",
        )
    )
    gaps.append(
        {
            "component": "FFmpeg",
            "reason": (
                "Production .tools/ffmpeg/bin has no LICENSE/COPYING; media-toolchain.json says "
                "GPL obligations must be resolved before packaging. Do not treat a different "
                "candidate build's LICENSE.txt as this pin without user review."
            ),
        }
    )

    # WebView2
    wv_license = repository / ".tools/webview2/1.0.4314.35/files/LICENSE.txt"
    wv_pin = repository / "docs/references/webview2-sdk.json"
    if wv_license.is_file():
        dest = sources / "webview2" / "LICENSE.txt"
        _copy_file(wv_license, dest)
        version = "1.0.4314.35"
        license_type = "Microsoft WebView2 SDK license (see LICENSE.txt)"
        if wv_pin.is_file():
            _copy_file(wv_pin, sources / "webview2" / "webview2-sdk.json")
            pin = json.loads(wv_pin.read_text(encoding="utf-8"))
            version = str(pin.get("version") or version)
            license_type = str(pin.get("license") or license_type)
        rows.append(
            NoticeRow(
                "Microsoft.Web.WebView2",
                version,
                license_type,
                str(wv_license.relative_to(repository)).replace("\\", "/"),
                str(dest.relative_to(output)).replace("\\", "/"),
                "ok",
            )
        )
        gaps.append(
            {
                "component": "Microsoft.Web.WebView2",
                "reason": (
                    "LICENSE.txt is bundled from the NuGet package; redistribution terms must still "
                    "be reviewed before shipping an installer (see docs/references/webview2-sdk.json)."
                ),
            }
        )
    else:
        gaps.append({"component": "WebView2", "reason": "LICENSE.txt missing under .tools/webview2"})
        rows.append(NoticeRow("Microsoft.Web.WebView2", "", "UNKNOWN", "", "", "missing_license_file"))

    # MSVC native redistributables (shipped; typically no LICENSE file in tree)
    native = repository / ".tools/native"
    if native.is_dir():
        receipt = next(native.rglob("receipt.json"), None)
        dest_dir = sources / "msvc-native"
        dest_dir.mkdir(parents=True, exist_ok=True)
        if receipt and receipt.is_file():
            _copy_file(receipt, dest_dir / "receipt.json")
        note = dest_dir / "README.txt"
        note.write_text(
            "Microsoft Visual C++ redistributable DLLs under .tools/native/msvc.\n"
            "No LICENSE file is present next to these DLLs in this checkout.\n"
            "Redistribution must follow Microsoft Visual C++ Redistributable terms.\n",
            encoding="utf-8",
        )
        rows.append(
            NoticeRow(
                "Microsoft Visual C++ Redistributable (local pin)",
                receipt.parent.name if receipt else "",
                "Microsoft redistributable terms (file missing locally)",
                str(receipt.relative_to(repository)).replace("\\", "/") if receipt else "",
                str(note.relative_to(output)).replace("\\", "/"),
                "noted_without_file",
            )
        )
        gaps.append(
            {
                "component": "MSVC native (.tools/native)",
                "reason": "DLL pin present but no Microsoft license text file alongside it.",
            }
        )

    # Models
    embed_receipt = next(
        (repository / ".cache/models/multilingual-e5-small").rglob("receipt.json"),
        None,
    ) if (repository / ".cache/models/multilingual-e5-small").is_dir() else None
    embed_pin = repository / "docs/references/embedding-model.json"
    if embed_pin.is_file():
        dest = sources / "models/multilingual-e5-small" / "embedding-model.json"
        _copy_file(embed_pin, dest)
        pin = json.loads(embed_pin.read_text(encoding="utf-8"))
        rows.append(
            NoticeRow(
                str(pin.get("model") or "multilingual-e5-small"),
                str(pin.get("revision") or ""),
                str(pin.get("license") or "UNKNOWN"),
                str(embed_pin.relative_to(repository)).replace("\\", "/"),
                str(dest.relative_to(output)).replace("\\", "/"),
                "noted_without_file",
            )
        )
    gaps.append(
        {
            "component": "multilingual-e5-small model weights",
            "reason": (
                "No LICENSE/model card file under .cache/models/multilingual-e5-small; "
                "embedding-model.json notes MIT (base model) and exported artifact needs release review."
            ),
        }
    )

    asr_pin = repository / "docs/references/asr-models.json"
    if asr_pin.is_file():
        dest = sources / "models/faster-whisper-tiny" / "asr-models.json"
        _copy_file(asr_pin, dest)
        pin = json.loads(asr_pin.read_text(encoding="utf-8"))
        rows.append(
            NoticeRow(
                str(pin.get("model") or "faster-whisper-tiny"),
                str(pin.get("revision") or ""),
                "UNKNOWN (no LICENSE file next to model weights)",
                str(asr_pin.relative_to(repository)).replace("\\", "/"),
                str(dest.relative_to(output)).replace("\\", "/"),
                "missing_license_file",
            )
        )
    gaps.append(
        {
            "component": "faster-whisper-tiny model weights",
            "reason": (
                "No LICENSE/model card under .cache/models/faster-whisper; only weight files + receipt. "
                "Need user confirmation of redistribution terms before shipping."
            ),
        }
    )

    # Python runtime dependencies (packaged set)
    site = repository / ".venv/Lib/site-packages"
    for dist_info in _packaged_dist_infos(site):
        name, version, license_type = _read_metadata(dist_info)
        folder = sources / "python" / _safe_name(f"{name}-{version or dist_info.name}")
        license_paths = _license_files(dist_info)
        if license_paths:
            copied_names = []
            for path in license_paths:
                if path.parent == dist_info:
                    target = folder / path.name
                elif (dist_info / "licenses") in path.parents or path.parent == (dist_info / "licenses"):
                    target = folder / "licenses" / path.relative_to(dist_info / "licenses")
                else:
                    target = folder / "licenses" / path.name
                _copy_file(path, target)
                copied_names.append(str(target.relative_to(output)).replace("\\", "/"))
            # also keep METADATA for version/license field traceability
            meta = dist_info / "METADATA"
            if meta.is_file():
                _copy_file(meta, folder / "METADATA")
            rows.append(
                NoticeRow(
                    name,
                    version,
                    license_type or "see LICENSE file",
                    str(license_paths[0].relative_to(repository)).replace("\\", "/"),
                    copied_names[0],
                    "ok",
                )
            )
        else:
            meta = dist_info / "METADATA"
            if meta.is_file():
                _copy_file(meta, folder / "METADATA")
            rows.append(
                NoticeRow(
                    name,
                    version,
                    license_type or "UNKNOWN",
                    str(meta.relative_to(repository)).replace("\\", "/") if meta.is_file() else "",
                    str((folder / "METADATA").relative_to(output)).replace("\\", "/")
                    if meta.is_file()
                    else "",
                    "missing_license_file",
                )
            )
            gaps.append(
                {
                    "component": f"{name} {version}".strip(),
                    "reason": (
                        f"No LICENSE/COPYING/NOTICE under {dist_info.name}; "
                        f"METADATA license field is {license_type or 'missing'}."
                    ),
                }
            )

    # Summary markdown
    lines = [
        "# Third-Party Notices",
        "",
        "This folder lists license texts that were **already present on disk** when the portable app "
        "was assembled. Nothing here was downloaded by the collector.",
        "",
        "First-party code (`gamingcreator`) and developer-only packages (pytest/mypy/ruff/…) are omitted.",
        "",
        "| Component | Version | License (as found) | Source file | Copied to | Status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {name} | {version} | {license_type} | {source_file} | {copied_to} | {status} |".format(
                **asdict(row)
            ).replace("\n", " ")
        )
    lines.extend(
        [
            "",
            "## Gaps (need user confirmation before relying on redistribution)",
            "",
        ]
    )
    if gaps:
        for gap in gaps:
            lines.append(f"- **{gap['component']}**: {gap['reason']}")
    else:
        lines.append("- None.")
    lines.append("")
    (output / "THIRD-PARTY-NOTICES.md").write_text("\n".join(lines), encoding="utf-8")
    (output / "gaps.json").write_text(
        json.dumps(gaps, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "notices.json").write_text(
        json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return rows, gaps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    repository = args.repository.resolve()
    output = (args.output or (repository / "licenses")).resolve()
    rows, gaps = collect(repository, output)
    missing = sum(1 for row in rows if row.status == "missing_license_file")
    print(
        f"Wrote {output} with {len(rows)} notice rows; "
        f"{missing} missing license files; {len(gaps)} gap notes."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
