"""Exclusively publish local review artifacts; do not write the source project."""

import hashlib
from pathlib import Path

from gamingcreator.application.benchmark_preparation import canonical_json


def publish_review_bundle(
    output: Path, files: dict[str, bytes], protected: list[Path]
) -> dict[str, str]:
    output = output.resolve()
    if any(
        output.is_relative_to(path.resolve()) or path.resolve().is_relative_to(output)
        for path in protected
    ):
        raise ValueError("新输出不能覆盖或位于原项目／报告／绑定／记录中。")
    if any(len(data) > 16_777_216 for data in files.values()):
        raise ValueError("验收输出超过16MiB单文件上限。")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    for name, data in files.items():
        with (output / name).open("xb") as stream:
            stream.write(data)
    with (output / "receipt.json").open("xb") as stream:
        stream.write(
            canonical_json(
                {
                    "schemaVersion": "benchmark-review-receipt-v1",
                    "files": hashes,
                    "qualityGate": None,
                    "paidRequestsSent": 0,
                }
            )
        )
    return hashes
