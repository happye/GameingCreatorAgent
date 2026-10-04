"""Prepare pinned E5 files only under the repository's ignored model cache."""

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def prepare(repository: Path, offline: bool) -> Path:
    pin: dict[str, Any] = json.loads(
        (repository / "docs/references/embedding-model.json").read_text(encoding="utf-8")
    )
    revision = pin["revision"]
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Invalid model revision")
    root = repository.resolve()
    directory = root / ".cache/models/multilingual-e5-small" / revision
    for artifact in pin["files"]:
        destination = (directory / artifact["name"]).resolve()
        if not destination.is_relative_to(directory) or not destination.is_relative_to(root):
            raise ValueError("Invalid asset path")
        size, expected = artifact["size"], artifact["sha256"]
        if type(size) is not int or size <= 0 or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError("Invalid asset metadata")
        if destination.is_file():
            if destination.stat().st_size != size or digest(destination) != expected:
                raise ValueError("Existing model asset failed verification")
            continue
        if offline:
            raise ValueError("Pinned model asset missing in offline mode")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".partial")
        if not temporary.resolve().is_relative_to(root):
            raise ValueError("Invalid partial path")
        url = f"https://huggingface.co/{pin['model']}/resolve/{revision}/{artifact['name']}"
        request = urllib.request.Request(url, headers={"User-Agent": "GamingCreator-Phase0"})
        received = 0
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                received += len(chunk)
                if received > size:
                    raise ValueError("Downloaded model asset exceeds pinned size")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if received != size or digest(temporary) != expected:
            raise ValueError("Downloaded model asset failed verification")
        temporary.replace(destination)
    (directory / "receipt.json").write_text(json.dumps(pin, indent=2), encoding="utf-8")
    return directory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        directory = prepare(Path(__file__).resolve().parents[1], args.offline)
        print(json.dumps({"modelDirectory": str(directory)}, ensure_ascii=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
        print("embedding.assets_failed: pinned local model could not be prepared")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
