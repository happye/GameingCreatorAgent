"""Verified overlay timing proposals, versioned snapshots and fake-only execution."""

# ruff: noqa: F811

import asyncio
import json
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256

import pytest
from test_creation_jobs import service  # noqa: F401
from test_creation_proposals import fixture, output
from test_creation_reasoning_service import Transport
from test_creation_revision_jobs import revisions  # noqa: F401
from test_overlay_revisions import save, selected  # noqa: F401

from gamingcreator.application.creation_overlay_proposals import (
    SCHEMA_VERSION,
    create_overlay_snapshot,
)
from gamingcreator.application.creation_proposals import (
    canonical,
    create_snapshot,
    validate_proposal,
)
from gamingcreator.application.creation_reasoning import reasoning_request
from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.ui.creation_reasoning_service import CreationReasoningService
from gamingcreator.ui.revision_jobs import load_chain


def response(selection):
    return dict(
        schemaVersion=SCHEMA_VERSION,
        kind="overlay_edit_proposal",
        message="延长并慢慢淡出",
        questions=[],
        clips=[],
        citations=[selection["items"][0]["overlayId"]],
        overlayEdit=dict(
            overlayId=selection["items"][0]["overlayId"], endFrame=15, fadeOutFrames=5
        ),
    )


@pytest.fixture
def overlay_context(selected):  # noqa: F811
    jobs, root, asset, selection = selected
    parent, _ = save(jobs, root, "b", selection)
    chain = load_chain(jobs, parent, "hook-first")
    transport = Transport(response(selection))
    service = CreationReasoningService(
        jobs, price_snapshot=DEEPSEEK_FLASH_20261004, transport=transport
    )
    return jobs, parent, chain, transport, service


def test_v1_request_and_snapshot_bytes_remain_frozen():
    snapshot = fixture()[0]
    assert (
        snapshot.fingerprint == "1a58000386d9a10762d0666f91fda5478c7f393bf6f3b4ea774dd11de01cfa50"
    )
    request = asdict(reasoning_request(snapshot, "旧请求恢复"))
    assert (
        sha256(canonical(request).encode()).hexdigest()
        == "cef972c35b563acfab844584efd8dbc69f0f95be3ca85f0ec761e91952fad201"
    )


def test_snapshot_binds_layers_and_public_assets(overlay_context):
    _, parent, chain, _, _ = overlay_context
    base = create_snapshot(parent, chain.plan_id, chain.digest, chain.root_sha, chain.edl)
    assets = [a.public() for a in chain.overlay_assets]
    original = chain.overlays.to_json()
    current = create_overlay_snapshot(base, original, assets)
    changed = json.loads(json.dumps(original))
    changed["items"][0]["endFrame"] = 3
    assert create_overlay_snapshot(base, changed, assets).fingerprint != current.fingerprint
    assert (
        create_overlay_snapshot(base, original, [{**assets[0], "width": 3}]).fingerprint
        != current.fingerprint
    )
    request = reasoning_request(current, "这个logo消失太快了")
    assert chain.overlay_assets[0].asset_id not in request.user
    assert chain.overlay_assets[0].receipt_sha256 not in request.user
    assert "Never claim to see/remove a logo baked into source footage" in request.system
    with pytest.raises(ValueError, match="exactly match"):
        create_overlay_snapshot(base, original, [])


@pytest.mark.parametrize(
    "patch",
    [
        {"endFrame": True},
        {"endFrame": 0},
        {"endFrame": 999999},
        {"fadeOutFrames": -1},
        {"fadeOutFrames": 31},
        {"assetId": "forged"},
        {"overlayId": "unknown"},
        {"endFrame": 2, "fadeOutFrames": 0},
    ],
)
def test_invalid_or_injected_overlay_patch_rejected(overlay_context, patch):
    _, parent, chain, _, _ = overlay_context
    base = create_snapshot(parent, chain.plan_id, chain.digest, chain.root_sha, chain.edl)
    snapshot = create_overlay_snapshot(
        base, chain.overlays.to_json(), [a.public() for a in chain.overlay_assets]
    )
    data = response(chain.overlays.to_json())
    data["overlayEdit"].update(patch)
    with pytest.raises(ValueError):
        validate_proposal(snapshot, data)


def test_fake_proposal_validates_and_saves_without_changing_clips(overlay_context):
    jobs, parent, chain, transport, service = overlay_context
    prepared = service.prepare(parent, "hook-first", "让这张独立图片多留一会儿，然后慢慢消失")
    assert prepared["schemaVersion"] == SCHEMA_VERSION and not transport.calls
    validate_proposal(
        service._current(service._prepared(prepared["preparedHash"])), transport.content
    )
    result = asyncio.run(
        service.execute(
            prepared["preparedHash"],
            prepared["snapshotFingerprint"],
            Decimal(prepared["maxCostCny"]),
        )
    )
    assert result["status"] == "completed", result
    assert len(transport.calls) == 1
    proposed = service.proposal_for_editor(
        prepared["preparedHash"], parent, "hook-first", chain.digest
    )
    assert proposed["overlays"]["items"][0]["endFrame"] == 15
    before = jobs.edit(parent, "hook-first")
    assert proposed["clips"] == [
        {
            **{k: r[k] for k in ("clipId", "startUs", "endUs")},
            "speed": r.get("speed", {"numerator": 1, "denominator": 1}),
            "transitionIn": r.get("transitionIn", {"type": "cut", "frames": 0}),
        }
        for r in before["clips"]
    ]
    saved, _ = save(jobs, parent, "c", proposed["overlays"])
    after = jobs.edit(saved, "hook-first")
    assert after["overlays"] == proposed["overlays"]
    assert after["audioMix"] == before["audioMix"]
    assert service.read_result(prepared["preparedHash"]) == result and len(transport.calls) == 1


def test_legacy_prepared_request_with_layer_parent_recovers_without_upgrade(overlay_context):
    _, parent, chain, transport, service = overlay_context
    old = create_snapshot(parent, chain.plan_id, chain.digest, chain.root_sha, chain.edl)
    transport.content = output(old)
    prepared = service._prepare(old, chain.project_id, parent, chain.plan_id, "旧请求恢复")
    assert prepared["schemaVersion"] == "creation-reasoning-v1"
    result = asyncio.run(
        service.execute(prepared["preparedHash"], old.fingerprint, Decimal(prepared["maxCostCny"]))
    )
    assert result["status"] == "completed", result
    assert (
        service._current(service._prepared(prepared["preparedHash"])).fingerprint == old.fingerprint
    )
    assert service.read_result(prepared["preparedHash"]) == result and len(transport.calls) == 1


def test_overlay_v4_preserves_manifest_and_original_clips(overlay_context, monkeypatch):
    from dataclasses import replace

    from gamingcreator.application.creation_proposals import clip_rows
    from gamingcreator.application.creation_replacements import (
        build_revision_v4,
        candidate_manifest_sha,
    )
    from gamingcreator.ui import creation_reasoning_service as module

    jobs, parent, chain, _, service = overlay_context
    manifest = {
        "schemaVersion": "creation-candidates-v1",
        "rootReceiptSha256": chain.root_sha,
        "candidates": [],
    }
    edl = {
        **chain.edl,
        "schemaVersion": "edit-decision-revision-v4",
        "candidateManifestSha256": candidate_manifest_sha(manifest),
        "replacements": [],
    }
    current = replace(chain, edl=edl, manifest=manifest)
    monkeypatch.setattr(module, "load_chain", lambda *_args: current)
    prepared = service.prepare(parent, "hook-first", "让这个独立图层慢慢消失")
    result = asyncio.run(
        service.execute(
            prepared["preparedHash"],
            prepared["snapshotFingerprint"],
            Decimal(prepared["maxCostCny"]),
        )
    )
    assert result["status"] == "completed", result
    seen = []

    def prepare_revision(received_jobs, request, received_chain):
        assert received_jobs is jobs and received_chain is current
        assert request["candidateManifestSha256"] == candidate_manifest_sha(manifest)
        assert request["replacements"] == []
        seen.append(request)
        return build_revision_v4(
            edl, chain.root_sha, chain.digest, request["clips"], [], manifest
        ), manifest

    monkeypatch.setattr(module, "prepare_revision", prepare_revision)
    proposed = service.proposal_for_editor(
        prepared["preparedHash"], parent, "hook-first", chain.digest
    )
    before = create_snapshot(parent, chain.plan_id, chain.digest, chain.root_sha, edl)
    assert len(seen) == 1 and proposed["clips"] == clip_rows(before)
    assert proposed["overlays"]["items"][0]["endFrame"] == 15
    assert current.edl == edl and current.manifest == manifest


def test_overlay_request_rejects_unknown_version_pair_without_send(overlay_context):
    _, parent, _, transport, service = overlay_context
    prepared = service.prepare(parent, "hook-first", "改淡出")
    record = service._prepared(prepared["preparedHash"])
    record["request"]["prompt_version"] = "creation-reasoning-prompt-v1"
    with pytest.raises(ValueError, match="version pair"):
        service._current(record)
    assert transport.calls == []
