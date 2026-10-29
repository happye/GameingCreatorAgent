"""Exclusive output directory publication; receipt is written last."""

import hashlib
import json
from pathlib import Path

from gamingcreator.infrastructure.local_paths import is_link, resolve_existing


def write_creation(
    output: Path, documents: dict[str, object], protected: tuple[Path, ...]
) -> dict[str, str]:
    target = resolve_existing(output)
    if is_link(output) or any(
        target == resolve_existing(path) or target.is_relative_to(resolve_existing(path))
        for path in protected
    ):
        raise ValueError("Output must be outside the input project and media paths.")
    # The explicit version directory must not exist, including on retries.
    target.mkdir(parents=True, exist_ok=False)
    digests: dict[str, str] = {}
    for name, document in documents.items():
        encoded = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        with (target / name).open("xb") as handle:
            handle.write(encoded)
        digests[name] = hashlib.sha256(encoded).hexdigest()
    with (target / "receipt.json").open("x", encoding="utf-8") as handle:
        json.dump({"schemaVersion": "creation-receipt-v1", "files": digests}, handle, indent=2)
    return {"output": str(target), "receipt": str(target / "receipt.json")}
