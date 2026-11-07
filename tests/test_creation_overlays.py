"""Output-timeline overlay contract, geometry and bounded asset identities."""

from dataclasses import replace
from fractions import Fraction

import pytest

from gamingcreator.domain.creation_overlays import (
    CreationOverlays,
    OverlayAssetMetadata,
    OverlayItem,
    overlay_pixel_geometry,
    validate_asset_budget,
    validate_overlay_text,
)


def item(**changes: object) -> OverlayItem:
    payload = {
        "overlayId": "a" * 32,
        "kind": "text",
        "startFrame": 30,
        "endFrame": 90,
        "x": 1000,
        "y": 2000,
        "width": 3000,
        "fadeInFrames": 10,
        "fadeOutFrames": 20,
        "assetId": "b" * 32,
        "assetReceiptSha256": "c" * 64,
        "text": "精彩时刻",
    }
    payload.update(changes)
    return OverlayItem.from_json(payload)


def test_canonical_identity_and_layer_order() -> None:
    bottom = item()
    top = item(overlayId="d" * 32, kind="text", text="第二层")
    overlays = CreationOverlays((bottom, top))
    payload = overlays.to_json()
    reordered_keys = {key: payload[key] for key in reversed(payload)}
    assert CreationOverlays.from_json(reordered_keys) == overlays
    assert CreationOverlays.from_json(reordered_keys).sha256() == overlays.sha256()
    assert len(overlays.sha256()) == 64
    assert CreationOverlays((top, bottom)).sha256() != overlays.sha256()
    assert CreationOverlays((replace(bottom, text="新文字"), top)).sha256() != overlays.sha256()
    assert payload["schemaVersion"] == "creation-overlays-v1"
    assert payload["items"][0]["overlayId"] == bottom.overlay_id


def test_shared_text_validator_preserves_text_and_rejects_cross_layer_hazards() -> None:
    text = "  精彩时刻  "
    assert validate_overlay_text(text) == text
    assert item(text=text).text == text
    for invalid in ("<title>", "a\u200db", "a\u0085b", "a\u2028b", "{x}", "a\\b"):
        with pytest.raises(ValueError):
            validate_overlay_text(invalid)
        with pytest.raises(ValueError):
            item(text=invalid)


@pytest.mark.parametrize(
    "changes",
    [
        {"unknown": 1},
        {"startFrame": True},
        {"endFrame": 30},
        {"x": -1},
        {"x": 8000},
        {"width": 0},
        {"y": 10001},
        {"fadeInFrames": 41},
        {"assetId": "../asset.png"},
        {"assetReceiptSha256": "C" * 64},
        {"overlayId": "A" * 32},
        {"text": ""},
        {"text": "a\nb"},
        {"text": "{\\an7}text"},
        {"text": "<b>text</b>"},
        {"text": "a\u2028b"},
        {"text": "x" * 121},
        {"kind": "image"},
    ],
)
def test_reject_invalid_protocol(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        item(**changes)


def test_empty_image_and_structural_constraints() -> None:
    empty = CreationOverlays.from_json({"schemaVersion": "creation-overlays-v1", "items": []})
    assert empty.items == ()
    assert empty.sha256() == "7832ed7a66665b5370e062d011e9689705c28e52bcc048a3280acfd9b885c0d9"
    empty.validate_duration(0)
    payload = item().to_json()
    payload["kind"] = "image"
    del payload["text"]
    assert "text" not in OverlayItem.from_json(payload).to_json()
    with pytest.raises(ValueError):
        CreationOverlays((item(), item()))
    with pytest.raises(ValueError):
        CreationOverlays(tuple(item(overlayId=f"{i:032x}") for i in range(17)))
    for invalid in (
        None,
        {},
        {"schemaVersion": "v2", "items": []},
        {"schemaVersion": "creation-overlays-v1", "items": [], "extra": 0},
    ):
        with pytest.raises(ValueError):
            CreationOverlays.from_json(invalid)


@pytest.mark.parametrize("source_speed", [Fraction(1, 2), Fraction(1), Fraction(2)])
def test_output_frames_independent_of_source_speed(source_speed: Fraction) -> None:
    # Source range changes with speed; the same 120-frame output retains this overlay.
    source_frames = 120 * source_speed
    output_frames = source_frames / source_speed
    assert output_frames.denominator == 1
    overlays = CreationOverlays((item(),))
    overlays.validate_duration(int(output_frames))
    assert [item().opacity_at(frame) for frame in (29, 30, 35, 40, 70, 80, 89, 90)] == [
        0,
        0,
        Fraction(1, 2),
        1,
        1,
        Fraction(1, 2),
        Fraction(1, 20),
        0,
    ]
    with pytest.raises(ValueError, match="beyond"):
        overlays.validate_duration(89)
    overlays.validate_duration(90)


def test_fade_edges_and_pixel_rounding() -> None:
    assert item(fadeInFrames=0, fadeOutFrames=0).opacity_at(30) == 1
    assert item(fadeInFrames=60, fadeOutFrames=0).opacity_at(89) == Fraction(59, 60)
    assert overlay_pixel_geometry(item(), 1920, 1080, 600, 100) == (192, 216, 576, 96)
    assert overlay_pixel_geometry(item(x=500, y=500, width=2500), 10, 10, 1, 1) == (1, 1, 3, 3)
    with pytest.raises(ValueError, match="canvas"):
        overlay_pixel_geometry(item(y=10000), 1920, 1080, 600, 100)
    with pytest.raises(ValueError, match="canvas"):
        overlay_pixel_geometry(item(), 1920, 1080, 100, 600)


def test_asset_budget_and_receipt_binding() -> None:
    asset = OverlayAssetMetadata("b" * 32, "c" * 64, 8 * 1024 * 1024, 4000, 4000)
    overlays = CreationOverlays((item(), item(overlayId="d" * 32)))
    validate_asset_budget(overlays, (asset, asset))  # Shared sprite counted once.
    with pytest.raises(ValueError, match="receipt"):
        validate_asset_budget(overlays, (replace(asset, asset_receipt_sha256="e" * 64),))
    with pytest.raises(ValueError, match="Conflicting"):
        validate_asset_budget(overlays, (asset, replace(asset, byte_size=1)))
    with pytest.raises(ValueError, match="references"):
        validate_asset_budget(overlays, ())
    three = tuple(replace(asset, asset_id=f"{i:032x}") for i in range(3))
    layers = CreationOverlays(
        tuple(replace(item(), overlay_id=a.asset_id, asset_id=a.asset_id) for a in three)
    )
    with pytest.raises(ValueError, match="decoded"):
        validate_asset_budget(layers, three)
    for changes in (
        {"byte_size": 8 * 1024 * 1024 + 1},
        {"width": 4097},
        {"width": 4096, "height": 4096},
        {"media_type": "image/jpeg"},
        {"height": True},
    ):
        with pytest.raises(ValueError):
            replace(asset, **changes)
