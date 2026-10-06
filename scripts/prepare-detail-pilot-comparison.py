"""Read exact frozen v2/v4 cases into an offline comparison; never send or reserve."""

import argparse
import asyncio
import base64
import hashlib
import html
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import cast

from gamingcreator.application.detail_description_feedback import (
    decode_description_feedback,
    project_description_feedback,
)
from gamingcreator.application.detail_description_report import validate_description_report
from gamingcreator.application.detail_pilot_review import review_entity_ids, validate_pilot_review
from gamingcreator.application.detail_query import loads_constraint, match_report, query_options
from gamingcreator.application.detail_refinement import canonical_request_json
from gamingcreator.application.detail_refinement_budget import canonical_detail_json, payload_hash
from gamingcreator.application.storage import RunStatus
from gamingcreator.application.temporal_scene_codec import scene_payload
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.deepseek_detail_refinement import provider_refinement_identity
from gamingcreator.infrastructure.deepseek_detail_temporal import (
    PROMPT,
    provider_temporal_identity,
    temporal_refinement_settings,
)
from gamingcreator.infrastructure.deepseek_vision import _jpeg_width, _json, _SchemaError
from gamingcreator.infrastructure.detail_pilot_review_files import (
    read_pilot_review_file,
    write_pilot_review_bundle,
)
from gamingcreator.infrastructure.detail_refinement_sidecar import reuse_or_refuse
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.pilot_review import render_review_editor, render_review_summary

_MAX_JSON_BYTES = 1_048_576
_CASES = {"actor-separation", "held-item-shape"}
OUTPUT_FILES = ("comparison.html", "comparison.json", "human-review-template.json")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> tuple[dict[str, object], bytes]:
    with path.open("rb") as stream:
        data = stream.read(_MAX_JSON_BYTES + 1)
    if len(data) > _MAX_JSON_BYTES:
        raise ValueError("Comparison input exceeds 1MiB.")
    return _json(data), data


def _object(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError("Comparison requires correctly typed JSON objects.")
    return value


def _string(value: object) -> str:
    if type(value) is not str:
        raise ValueError("Comparison requires correctly typed strings.")
    return value


def _rows(value: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = value.get("cases")
    if type(rows) is not list or len(rows) != 2:
        raise ValueError("Comparison requires exactly the two frozen cases.")
    result = {}
    for raw in rows:
        row = _object(raw)
        key = _string(row.get("caseId"))
        if key not in _CASES or key in result:
            raise ValueError("Comparison case identity is unknown or duplicated.")
        result[key] = row
    return result


def _snapshot(project: Path) -> dict[str, str]:
    database = project / "timeline.sqlite3"
    if not database.is_file():
        raise FileNotFoundError("The source project database is missing.")
    paths = {database}
    for suffix in ("-wal", "-shm"):
        path = database.with_name(database.name + suffix)
        if path.exists():
            paths.add(path)
    paths.update(path for path in project.glob("runs/*/detail-refinements/**/*") if path.is_file())
    budget = project / "detail-refinement-budgets"
    if budget.exists():
        paths.update(path for path in budget.rglob("*") if path.is_file())
    return {str(path.relative_to(project)): _sha(path.read_bytes()) for path in sorted(paths)}


def _dimensions(data: bytes) -> tuple[int, int]:
    width = _jpeg_width(data)
    position = 2
    while position + 4 <= len(data):
        while data[position] == 255:
            position += 1
        marker = data[position]
        position += 1
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            continue
        length = int.from_bytes(data[position : position + 2], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            return width, int.from_bytes(data[position + 3 : position + 5], "big")
        position += length
    raise ValueError("Registered JPEG dimensions are missing.")


async def prepare_comparison(
    project: Path,
    proposal_path: Path,
    expected_sha256: str,
    report_path: Path,
    feedback_path: Path,
) -> dict[str, object]:
    """Validate saved exact identities and copy only local evidence into a review snapshot."""
    project = project.resolve()
    inputs = [path.resolve() for path in (proposal_path, report_path, feedback_path)]
    proposal, proposal_bytes = _read_json(inputs[0])
    if (
        not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
        or _sha(proposal_bytes) != expected_sha256
    ):
        raise ValueError("Frozen proposal SHA-256 mismatch.")
    identity = provider_temporal_identity()
    if (
        proposal.get("schemaVersion") != "actor-detail-temporal-pilot-proposal-v1"
        or Path(_string(proposal.get("project"))).resolve() != project
        or (
            proposal.get("provider"),
            proposal.get("requestedModel"),
            proposal.get("promptVersion"),
            proposal.get("promptHash"),
            proposal.get("schema"),
            proposal.get("systemPrompt"),
            proposal.get("destination"),
        )
        != (
            identity.provider,
            identity.requested_model,
            identity.prompt_version,
            identity.prompt_hash,
            identity.schema_version,
            PROMPT,
            "https://api.deepseek.com/chat/completions",
        )
    ):
        raise ValueError("Frozen proposal belongs to another project or v4 identity.")
    rows = _rows(proposal)
    report, report_bytes = _read_json(inputs[1])
    _, feedback_bytes = _read_json(inputs[2])
    feedback = decode_description_feedback(feedback_bytes.decode("utf-8"))
    validate_description_report(feedback, report_bytes.decode("utf-8"))
    old_rows = _rows(report)
    if report.get("humanLabels") is not None or report.get("qualityGate") is not None:
        raise ValueError("A comparison report cannot claim human retrieval acceptance.")
    source_hashes = {
        str(path): _sha(data)
        for path, data in zip(inputs, (proposal_bytes, report_bytes, feedback_bytes), strict=True)
    }
    before = _snapshot(project)
    store = await SqliteTimelineStore.open(project, read_only=True)
    cases: list[dict[str, object]] = []
    try:
        for case_id, row in rows.items():
            run_id, event_id = _string(row.get("runId")), _string(row.get("eventId"))
            old_row = old_rows[case_id]
            if old_row.get("humanLabels") is not None or old_row.get("qualityGate") is not None:
                raise ValueError("A comparison case cannot claim human retrieval acceptance.")
            if (old_row.get("runId"), old_row.get("eventId"), old_row.get("requestHash")) != (
                run_id,
                event_id,
                row.get("legacyRequestHash"),
            ):
                raise ValueError("Legacy report candidate/request differs from the frozen case.")
            timeline = await store.load_completed_timeline(run_id)
            if timeline.run.run_id != run_id or timeline.run.status != RunStatus.COMPLETED:
                raise ValueError("Comparison requires the exact Completed source run.")
            legacy = reuse_or_refuse(
                project, timeline, event_id, identity=provider_refinement_identity()
            )
            current = reuse_or_refuse(
                project,
                timeline,
                event_id,
                identity=identity,
                settings=temporal_refinement_settings(),
            )
            if legacy.request is None or legacy.detail is None or current.request is None:
                raise ValueError("The exact legacy result or registered candidate is missing.")
            request = current.request
            if (
                legacy.request_hash != row.get("legacyRequestHash")
                or current.request_hash != row.get("requestHash")
                or json.loads(canonical_request_json(request)) != row.get("canonicalRequest")
                or request.candidate_id != row.get("candidateId")
                or request.event_fingerprint != row.get("eventFingerprint")
                or request.base_prompt_version != row.get("basePromptVersion")
                or request.base_prompt_hash != row.get("basePromptHash")
                or request.evidence != legacy.request.evidence
                or len(request.evidence) != 3
            ):
                raise ValueError("Current canonical request differs from the frozen candidate.")
            attempt = _object(old_row.get("attempt"))
            if (
                attempt.get("status") != "completed"
                or attempt.get("requestHash") != legacy.request_hash
                or attempt.get("payloadHash") != payload_hash(legacy.detail)
                or attempt.get("payloadJson") != canonical_detail_json(legacy.detail)
            ):
                raise ValueError("The exact legacy report payload differs from its saved result.")
            raw_frames = row.get("inputFrames")
            if type(raw_frames) is not list or len(raw_frames) != 3:
                raise ValueError("Comparison needs the original three frozen frames only.")
            registered = {
                item.evidence_id: item for item in timeline.evidence if item.kind == "image"
            }
            frames = []
            for frame, raw_frame in zip(request.evidence, raw_frames, strict=True):
                saved = _object(raw_frame)
                path = registered[frame.evidence_id].artifact_path.resolve()
                with path.open("rb") as stream:
                    data = stream.read(request.settings.max_image_bytes + 1)
                width, height = _dimensions(data)
                checked = {
                    "evidenceId": frame.evidence_id,
                    "sourceUs": frame.source_time.time_us,
                    "durationUs": frame.source_time.duration_us,
                    "sha256": frame.image_sha256,
                    "width": width,
                    "height": height,
                    "bytes": len(data),
                    "path": str(path),
                }
                if (
                    saved != checked
                    or _sha(data) != frame.image_sha256
                    or len(data) > request.settings.max_image_bytes
                    or width > request.settings.max_image_width
                ):
                    raise ValueError(
                        "Registered frame identity, bytes, clock or dimensions changed."
                    )
                source_hashes[str(path)] = frame.image_sha256
                frames.append(
                    dict(
                        checked,
                        imageDataUrl="data:image/jpeg;base64,"
                        + base64.b64encode(data).decode("ascii"),
                    )
                )
            old_match = _object(old_row.get("match"))
            constraint = loads_constraint(_string(old_match.get("constraintJson")))
            checked_match = match_report(
                legacy.request,
                legacy.detail,
                constraint,
                run_id=run_id,
                event_id=event_id,
                request_digest=legacy.request_hash,
            )
            for key in (
                "schemaVersion",
                "runId",
                "eventId",
                "candidateId",
                "sourceRange",
                "eventFingerprint",
                "refinementRequestHash",
                "refinementPayloadHash",
                "constraintJson",
                "result",
                "humanLabels",
                "qualityGate",
            ):
                if old_match.get(key) != checked_match[key]:
                    raise ValueError(
                        "Legacy query report identity differs from the exact saved result."
                    )
            reviews = project_description_feedback(
                feedback,
                pilot_report_sha256=_sha(report_bytes),
                run_id=run_id,
                event_id=event_id,
                request_hash=_string(legacy.request_hash),
                detail=legacy.detail,
            )
            descriptions = [
                {
                    "shotId": shot.shot_id,
                    "actorId": actor.actor_id,
                    "description": actor.description,
                    "feedback": [
                        asdict(review)
                        for review in reviews
                        if (review.shot_id, review.actor_id) == (shot.shot_id, actor.actor_id)
                    ],
                }
                for shot in legacy.detail.shots
                for actor in shot.actors
            ]
            scene = None if current.detail is None else current.detail.temporal_scene
            if current.detail is not None and scene is None:
                raise ValueError("A saved v4 result must retain its validated temporal scene.")
            cases.append(
                {
                    "caseId": case_id,
                    "reviewPurpose": row.get("reviewPurpose"),
                    "runId": run_id,
                    "eventId": event_id,
                    "candidateId": request.candidate_id,
                    "sourceRange": json.loads(canonical_request_json(request))["interval"],
                    "frames": frames,
                    "legacy": {
                        "requestHash": legacy.request_hash,
                        "payloadHash": payload_hash(legacy.detail),
                        "descriptions": descriptions,
                        "match": old_match,
                    },
                    "temporal": {
                        "requestHash": current.request_hash,
                        "payloadHash": None
                        if current.detail is None
                        else payload_hash(current.detail),
                        "state": "no_saved_result" if current.detail is None else "saved_result",
                        "message": "未执行/暂无结果（没有此精确请求的已发布结果）"
                        if current.detail is None
                        else "已有保存结果，内容仍待人工核对",
                        "scene": None if scene is None else scene_payload(scene),
                        "match": match_report(
                            request,
                            current.detail,
                            constraint,
                            run_id=run_id,
                            event_id=event_id,
                            request_digest=current.request_hash,
                        ),
                        "humanReview": None,
                    },
                }
            )
    finally:
        await store.close()
    after = _snapshot(project)
    if before != after or any(
        _sha(Path(path).read_bytes()) != digest for path, digest in source_hashes.items()
    ):
        raise ValueError("Comparison source database, sidecars, ledger or frozen inputs changed.")
    return {
        "schemaVersion": "detail-pilot-comparison-v1",
        "project": str(project),
        "inputSha256": source_hashes,
        "proposalSha256": expected_sha256,
        "sourceDatabaseSidecarsAndLedgersUnchanged": True,
        "paidRequestsSent": 0,
        "humanLabels": None,
        "qualityGate": None,
        "realV4RecognitionVerified": False,
        "cases": cases,
    }


def review_template(comparison: dict[str, object]) -> dict[str, object]:
    cases = []
    for raw in cast(list[object], comparison["cases"]):
        case = _object(raw)
        legacy, temporal = _object(case["legacy"]), _object(case["temporal"])
        cases.append(
            {
                "caseId": case["caseId"],
                "runId": case["runId"],
                "eventId": case["eventId"],
                "legacyRequestHash": legacy["requestHash"],
                "legacyPayloadHash": legacy["payloadHash"],
                "temporalRequestHash": temporal["requestHash"],
                "temporalPayloadHash": temporal["payloadHash"],
                "frames": [
                    {key: frame[key] for key in ("evidenceId", "sourceUs", "durationUs", "sha256")}
                    for frame in cast(list[dict[str, object]], case["frames"])
                ],
                "objectMistakenForActor": None,
                "shotBoundariesAreReal": None,
                "positiveDescriptionsRetained": None,
                "queriedClipUsable": None,
                "reviewedTemporalEntityIds": None,
                "statement": None,
            }
        )
    return {
        "schemaVersion": "detail-pilot-comparison-review-template-v1",
        "proposalSha256": comparison["proposalSha256"],
        "inputSha256": comparison["inputSha256"],
        "instructions": "各维度独立填写 true/false/null；未核对保持 null。新版无已保存结果时不可评价新版。新版 entityId 不沿用旧 actorId。此模板不代表 U10 或质量门槛通过。",
        "cases": cases,
        "recordedOn": None,
        "reviewer": None,
        "humanLabels": None,
        "phase0QualityGate": None,
        "newProviderCalls": 0,
    }


def render_html(comparison: dict[str, object]) -> str:
    def escape(value: object) -> str:
        return html.escape(str(value), quote=True)

    def details(title: str, value: object) -> str:
        return f"<details><summary>{escape(title)}</summary><pre>{escape(json.dumps(value, ensure_ascii=False, indent=2))}</pre></details>"

    def download(name: str, label: str, value: object) -> str:
        data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
            "utf-8"
        )
        href = "data:application/json;base64," + base64.b64encode(data).decode("ascii")
        return f'<a download="{escape(name)}" href="{href}">{escape(label)}</a>'

    def matching_summary(report: dict[str, object]) -> str:
        result = _object(report["result"])
        labels = {
            "full": "全部符合",
            "partial": "部分符合",
            "no_match": "不符合",
            "unverified": "尚无法核验",
        }
        status = str(result["status"])  # Fresh match reports retain a typed StrEnum until encoding.
        return f"<p><b>这次查询：{labels[status]}</b>（程序判断，未替代人工确认）</p>"

    kinds = cast(list[dict[str, object]], query_options()["kinds"])
    query_kind_labels = {_string(kind["kind"]): _string(kind["label"]) for kind in kinds}
    value_labels = {
        (_string(kind["kind"]), _string(value["value"])): _string(value["label"])
        for kind in kinds
        for value in cast(list[dict[str, object]], kind["values"])
    }
    case_titles = {
        "actor-separation": "三个角色的描述保留正例",
        "held-item-shape": "物品靠近镜头的误认反例",
    }
    sections = []
    for raw in cast(list[object], comparison["cases"]):
        case = _object(raw)
        legacy, temporal = _object(case["legacy"]), _object(case["temporal"])
        old_match = _object(legacy["match"])
        constraint = loads_constraint(_string(old_match["constraintJson"]))
        query_label = " + ".join(
            query_kind_labels[condition.kind.value]
            + "："
            + value_labels[(condition.kind.value, condition.value)]
            for condition in (*constraint.actor_all, *constraint.environment_all)
        )
        interval = _object(case["sourceRange"])
        frames = "".join(
            f'<figure><img src="{escape(frame["imageDataUrl"])}" alt="源视频 {cast(int, frame["sourceUs"]) / 1_000_000:g} 秒原画面"><figcaption>{cast(int, frame["sourceUs"]) / 1_000_000:g} 秒</figcaption>{details("画面身份", {key: value for key, value in frame.items() if key != "imageDataUrl"})}</figure>'
            for frame in cast(list[dict[str, object]], case["frames"])
        )
        descriptions = []
        for actor in cast(list[dict[str, object]], legacy["descriptions"]):
            reviews = cast(list[dict[str, object]], actor["feedback"])
            label = "尚未人工判定"
            if reviews:
                label = (
                    "用户已确认此描述"
                    if reviews[0]["verdict"] == "accepted"
                    else "用户指出此描述错误"
                )
            statements = "".join(
                f'<p class="feedback">{escape(review["statement"])}</p>' for review in reviews
            )
            descriptions.append(
                f'<li><b>{escape(actor["shotId"])}/{escape(actor["actorId"])}</b>：{escape(actor["description"])}<p class="label">{label}</p>{statements}</li>'
            )
        new_text = f'<p class="notice">{escape(temporal["message"])}</p>'
        if temporal["scene"] is not None:
            scene = _object(temporal["scene"])
            entities = []
            kind_labels = {"actor": "角色", "object": "物品", "unknown": "暂无法确定"}
            for raw_entity in cast(list[object], scene["entities"]):
                entity = _object(raw_entity)
                classification = _object(entity["classification"])
                kind = _string(classification["kind"])
                classification_label = (
                    "有画面依据，仍待人工确认"
                    if classification["status"] == "observed"
                    else "不确定"
                )
                entities.append(
                    f"<li><b>{escape(entity['entityId'])}</b> · {kind_labels[kind]} · {classification_label}<p>{escape(entity['description'])}</p><p>判断依据：{escape(classification['reason'])}</p>{details('逐帧可见/遮挡与部件', {'observations': entity['observations'], 'parts': entity['parts']})}</li>"
                )
            new_text += (
                "<ul>"
                + "".join(entities)
                + "</ul>"
                + details("相邻画面的连续/切镜判断", scene["transitions"])
                + details("谁持有什么物品", scene["owners"])
                + details("完整新版画面记录", scene)
            )
        sections.append(
            f'<section><h2>{escape(case_titles[_string(case["caseId"])])} · {cast(int, interval["startUs"]) / 1_000_000:g}–{(cast(int, interval["endUs"]) - 1) / 1_000_000:g} 秒</h2><p>{escape(case["reviewPurpose"])}</p><p>两版对照使用同一个查询：{escape(query_label)}。角色条件须由同一角色和共同画面支持；同组衣物或持有物的形状、颜色还须属于同一部件。</p><div class="frames">{frames}</div><div class="versions"><article><h3>旧版 v2</h3><ul>{"".join(descriptions)}</ul>{matching_summary(old_match)}{details("旧版当时的检索结果（仅程序判断）", old_match)}</article><article><h3>新版 v4</h3>{new_text}{matching_summary(_object(temporal["match"]))}{details("同一查询的新版检索结果（仅程序判断）", temporal["match"])}</article></div>{details("本候选精确绑定身份", {"runId": case["runId"], "eventId": case["eventId"], "legacyRequestHash": legacy["requestHash"], "legacyPayloadHash": legacy["payloadHash"], "temporalRequestHash": temporal["requestHash"], "temporalPayloadHash": temporal["payloadHash"]})}</section>'
        )
    downloads = download(
        "human-review-template.json", "下载人工记录模板", review_template(comparison)
    )
    downloads += " · " + download("comparison.json", "下载对照数据", comparison)
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'\"><title>同源画面 · v2/v4 人工对照</title><style>body{margin:0;background:#f4f7fb;color:#203047;font:16px/1.65 system-ui,sans-serif}main{max-width:1200px;margin:auto;padding:24px}h1{font-size:28px}section,header{background:white;border:1px solid #dce3ee;border-radius:14px;padding:24px;margin-bottom:24px}.frames{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.versions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}figure{margin:0}img{width:100%;height:auto;border-radius:8px}figcaption,.label{font-weight:600}.notice,.feedback{background:#fff5d8;padding:12px;border-radius:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:#f3f6fa;padding:12px}details{margin:12px 0}summary{cursor:pointer}article{min-width:0}li{margin-bottom:16px;overflow-wrap:anywhere}a{color:#1758a8}@media(max-width:700px){main{padding:12px}section,header{padding:16px}.versions,.frames{grid-template-columns:1fr}h1{font-size:23px}}</style></head><body><main><header><h1>同源画面 · v2/v4 人工对照</h1><p>两版共用每组原来的三张画面。旧反馈只评价旧版对应的描述，新版人工结论全部留空。</p><p>本次只读本地已保存资料，发送请求 0 次。新版无保存结果时无法判断识别是否改好；检索质量仍需独立人工验收。</p><p>"
        + downloads
        + "</p><p>请分别核对：物品是否被误当角色、切镜是否真实、原来的正确描述是否保留、同一查询找到的片段是否可用。尚未核对或没有新版结果的项目请留空。</p></header>"
        + "".join(sections)
        + "</main></body></html>"
    )


def write_comparison(comparison: dict[str, object], output_dir: Path) -> dict[str, str]:
    if not output_dir.is_absolute():
        raise ValueError("Use an explicit absolute output directory.")
    output_dir = output_dir.resolve()
    project = Path(_string(comparison["project"])).resolve()
    inputs = _object(comparison["inputSha256"])
    if output_dir.is_relative_to(project) or any(
        Path(path).resolve().is_relative_to(output_dir) for path in inputs
    ):
        raise ValueError("Comparison output cannot contain or overwrite source files.")
    encoded = {
        OUTPUT_FILES[0]: render_html(comparison).encode("utf-8"),
        OUTPUT_FILES[1]: (
            json.dumps(comparison, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        ).encode("utf-8"),
        OUTPUT_FILES[2]: (
            json.dumps(review_template(comparison), ensure_ascii=False, indent=2, allow_nan=False)
            + "\n"
        ).encode("utf-8"),
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir()  # A new directory only; never replace an existing review or source.
    for name, data in encoded.items():
        with (output_dir / name).open("xb") as stream:
            stream.write(data)
    return {str(output_dir / name): _sha(data) for name, data in encoded.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--proposal-sha256", required=True)
    parser.add_argument("--legacy-report", type=Path, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--output-dir", type=Path)
    review_mode = parser.add_mutually_exclusive_group()
    review_mode.add_argument("--review-editor", action="store_true")
    review_mode.add_argument("--review-file", type=Path)
    args = parser.parse_args(argv)
    if args.review_editor and args.dry_run:
        parser.error("--review-editor requires --output-dir.")
    try:
        comparison = asyncio.run(
            prepare_comparison(
                args.project, args.proposal, args.proposal_sha256, args.legacy_report, args.feedback
            )
        )
        summary = {
            "paidRequestsSent": 0,
            "dryRun": args.dry_run,
            "sourceDatabaseSidecarsAndLedgersUnchanged": True,
            "cases": [
                {"caseId": case["caseId"], "temporal": _object(case["temporal"])["state"]}
                for case in cast(list[dict[str, object]], comparison["cases"])
            ],
        }
        if args.review_file is not None:
            input_bytes = read_pilot_review_file(args.review_file)
            template = review_template(comparison)
            review = validate_pilot_review(
                input_bytes.decode("utf-8-sig"),
                expected_template=template,
                entity_ids_by_case=review_entity_ids(comparison),
            )
            summary["judgedCaseIds"] = list(review.judged_case_ids)
            summary["phase0QualityGate"] = None
            if args.output_dir is not None:
                summary["outputs"] = write_pilot_review_bundle(
                    comparison=comparison,
                    expected_template=template,
                    input_path=args.review_file,
                    input_bytes=input_bytes,
                    output_dir=args.output_dir,
                    summary_html=render_review_summary(comparison, review),
                )
        elif args.output_dir is not None:
            editor = (
                render_review_editor(comparison, review_template(comparison))
                if args.review_editor
                else None
            )
            summary["outputs"] = write_comparison(comparison, args.output_dir)
            if editor is not None:
                path = args.output_dir / "review-editor.html"
                with path.open("xb") as stream:
                    stream.write(editor.encode("utf-8"))
                summary["outputs"][str(path)] = _sha(editor.encode("utf-8"))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, ValueError, KeyError, AppError, _SchemaError) as error:
        print(f"Comparison preparation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
