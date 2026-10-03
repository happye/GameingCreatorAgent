"""Download/hash/extract pinned local ASR assets. Never run an installer."""

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from zipfile import ZipFile


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def download(url: str, destination: Path, size: int, sha256: str, offline: bool) -> None:
    if destination.is_file():
        if destination.stat().st_size == size and digest(destination) == sha256:
            return
        raise ValueError("Existing asset failed hash verification")
    if offline:
        raise ValueError("Pinned asset missing in offline mode")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    request = urllib.request.Request(url, headers={"User-Agent": "GamingCreator-Phase0"})
    with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
        received = 0
        while chunk := response.read(1024 * 1024):
            received += len(chunk)
            if received > size:
                raise ValueError("Asset larger than pinned size")
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    if received != size or digest(temporary) != sha256:
        raise ValueError("Downloaded asset failed verification")
    temporary.replace(destination)


def prepare_native(repository: Path, offline: bool) -> Path:
    pin: dict[str, Any] = json.loads(
        (repository / "docs/references/asr-native-toolchain.json").read_text()
    )
    archive = repository / ".cache/native" / f"msvc-{pin['version']}.vsix"
    download(pin["url"], archive, pin["size"], pin["sha256"], offline)
    directory = repository / ".tools/native/msvc" / pin["version"]
    if directory.exists():
        if all(digest(directory / name) == sha for name, sha in pin["files"].items()):
            return directory
        raise ValueError("Existing native runtime failed verification")
    staging = directory.with_name(directory.name + ".partial")
    staging.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as bundle:
        # No extractall: only the pinned retail files, never debug_nonredist or paths.
        for name, expected in pin["files"].items():
            content = bundle.read(pin["archivePrefix"] + name)
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError("Native library hash mismatch")
            destination = staging / name
            with destination.open("wb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
    (staging / "receipt.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "archiveSha256": pin["sha256"],
                "files": pin["files"],
                "usageScope": pin["usageScope"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    staging.replace(directory)
    return directory


def prepare_model(repository: Path, offline: bool) -> Path:
    pin: dict[str, Any] = json.loads((repository / "docs/references/asr-models.json").read_text())
    directory = repository / ".cache/models/faster-whisper/tiny" / pin["revision"]
    for artifact in pin["files"]:
        download(
            f"https://huggingface.co/{pin['model']}/resolve/{pin['revision']}/{artifact['name']}",
            directory / artifact["name"],
            artifact["size"],
            artifact["sha256"],
            offline,
        )
    (directory / "receipt.json").write_text(json.dumps(pin, indent=2), encoding="utf-8")
    return directory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--native-only", action="store_true")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    try:
        native = prepare_native(repository, args.offline)
        model = None if args.native_only else prepare_model(repository, args.offline)
        print(
            json.dumps(
                {
                    "nativeDirectory": str(native),
                    "modelDirectory": None if model is None else str(model),
                }
            )
        )
        return 0
    except (OSError, ValueError, urllib.error.URLError):
        # Never echo a raw network/proxy/credential exception.
        print(
            "Pinned ASR assets unavailable or failed verification; no installer was run.",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
