"""Read bounded local records and exclusively write a new review bundle; no provider."""

import hashlib
import json
from pathlib import Path
from typing import cast

from gamingcreator.application.detail_pilot_review import (
    MAX_REVIEW_BYTES,
    PilotReview,
    review_entity_ids,
    validate_pilot_review,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_pilot_review_file(path: Path) -> bytes:
    if not path.is_absolute():
        raise ValueError("人工记录须使用明确的绝对文件路径。")
    with path.open("rb") as stream:
        data = stream.read(MAX_REVIEW_BYTES + 1)
    if len(data) > MAX_REVIEW_BYTES:
        raise ValueError("人工记录不能超过1MiB。")
    return data


def write_pilot_review_bundle(
    *,
    comparison: dict[str, object],
    expected_template: dict[str, object],
    input_path: Path,
    input_bytes: bytes,
    output_dir: Path,
    summary_html: str,
) -> dict[str, str]:
    """The comparison must have just been regenerated against the original frozen sources."""
    review: PilotReview = validate_pilot_review(
        input_bytes.decode("utf-8-sig"),
        expected_template=expected_template,
        entity_ids_by_case=review_entity_ids(comparison),
    )
    if not output_dir.is_absolute():
        raise ValueError("人工记录输出须使用明确的绝对新目录。")
    output_dir = output_dir.resolve()
    project = Path(cast(str, comparison["project"])).resolve()
    sources = [input_path.resolve(), *map(Path, cast(dict[str, str], comparison["inputSha256"]))]
    if output_dir.is_relative_to(project) or any(
        source.resolve().is_relative_to(output_dir) for source in sources
    ):
        raise ValueError("人工记录输出不能覆盖或包含源资料。")
    if read_pilot_review_file(input_path) != input_bytes:
        raise ValueError("待保存的人工记录在核验期间已改变。")
    canonical = review.payload_json.encode("utf-8")
    comparison_bytes = (
        json.dumps(comparison, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    provenance = {
        "schemaVersion": "detail-pilot-review-provenance-v1",
        "comparisonSha256": _sha(comparison_bytes),
        "inputRecordSha256": _sha(input_bytes),
        "savedRecordSha256": _sha(canonical),
        "proposalSha256": comparison["proposalSha256"],
        "judgedCaseIds": list(review.judged_case_ids),
        "humanLabels": None,
        "phase0QualityGate": None,
        "paidRequestsSent": 0,
        "realV4RecognitionVerified": False,
    }
    outputs = {
        "comparison.json": comparison_bytes,
        "review-input.json": input_bytes,
        "human-review-record.json": canonical,
        "review-summary.html": summary_html.encode("utf-8"),
        "review-provenance.json": (
            json.dumps(provenance, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        ).encode("utf-8"),
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir()
    for name, content in outputs.items():
        with (output_dir / name).open("xb") as stream:
            stream.write(content)
    return {str(output_dir / name): _sha(content) for name, content in outputs.items()}
