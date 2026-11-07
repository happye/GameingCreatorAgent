"""Local asset registration and source-bound overlay selection validation."""

import asyncio
import base64
from typing import Any
from urllib.parse import urlencode

from gamingcreator.domain.creation_overlays import (
    CreationOverlays,
    OverlayAssetMetadata,
    validate_asset_budget,
)
from gamingcreator.infrastructure.overlay_assets import (
    MAX_PNG_BYTES,
    OverlayAsset,
    OverlayAssetLibrary,
)


def public_asset(asset: OverlayAsset) -> dict[str, Any]:
    return {
        **asset.public(),
        "imageUrl": f"/api/creation/overlay-assets/{asset.asset_id}/image?"
        + urlencode({"receipt": asset.receipt_sha256}),
    }


def register_asset(library: OverlayAssetLibrary, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Expected an overlay asset request.")
    if value.get("kind") == "text" and set(value) == {"kind", "text"}:
        return public_asset(asyncio.run(library.register_text(value["text"])))
    if value.get("kind") != "image" or set(value) != {"kind", "fileName", "dataBase64"}:
        raise ValueError("Unexpected overlay asset fields.")
    name, encoded = value["fileName"], value["dataBase64"]
    if not isinstance(name, str) or not 1 <= len(name) <= 255:
        raise ValueError("Expected a bounded filename.")
    if not isinstance(encoded, str) or len(encoded) > ((MAX_PNG_BYTES + 2) // 3) * 4:
        raise ValueError("Overlay image exceeds the byte budget.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, UnicodeError) as error:
        raise ValueError("Expected a base64 PNG.") from error
    return public_asset(asyncio.run(library.register_png(raw, name)))


def resolve_assets(
    library: OverlayAssetLibrary, overlays: CreationOverlays
) -> tuple[OverlayAsset, ...]:
    assets = tuple(library.resolve(i.asset_id, i.asset_receipt_sha256) for i in overlays.items)
    for item, asset in zip(overlays.items, assets, strict=True):
        if item.kind != asset.kind or item.text != asset.text:
            raise ValueError("Overlay text or kind differs from its asset receipt.")
    validate_asset_budget(
        overlays,
        tuple(
            OverlayAssetMetadata(
                a.asset_id, a.receipt_sha256, a.path.stat().st_size, a.width, a.height
            )
            for a in assets
        ),
    )
    return assets
