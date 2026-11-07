"""Output-frame overlay composition; input indices follow all soundtrack inputs."""

from gamingcreator.domain.creation_overlays import CreationOverlays, overlay_pixel_geometry
from gamingcreator.infrastructure.overlay_assets import OverlayAsset


def overlay_filters(
    overlays: CreationOverlays,
    assets: tuple[OverlayAsset, ...],
    first_input: int,
    frames: int,
    fps: int,
    width: int,
    height: int,
    prefix: str,
    suffix: str,
) -> tuple[list[str], str]:
    overlays.validate_duration(frames)
    inputs: list[str] = []
    filters = [f"[0:v:0]{prefix}[overlay-base]"]
    base = "overlay-base"
    for index, (item, asset) in enumerate(zip(overlays.items, assets, strict=True)):
        x, y, w, h = overlay_pixel_geometry(item, width, height, asset.width, asset.height)
        inputs.extend(
            [
                "-protocol_whitelist",
                "file",
                "-loop",
                "1",
                "-framerate",
                str(fps),
                "-i",
                str(asset.path),
            ]
        )
        sprite = (
            f"[{first_input + index}:v:0]format=rgba,scale={w}:{h},"
            f"trim=end_frame={frames},settb=expr=1/{fps},setpts=N"
        )
        if item.fade_in_frames:
            sprite += (
                f",fade=t=in:start_frame={item.start_frame}:nb_frames={item.fade_in_frames}:alpha=1"
            )
        if item.fade_out_frames:
            sprite += (
                f",fade=t=out:start_frame={item.end_frame - item.fade_out_frames}:"
                f"nb_frames={item.fade_out_frames}:alpha=1"
            )
        filters.append(sprite + f"[sprite-{index}]")
        output = f"layer-{index}"
        filters.append(
            f"[{base}][sprite-{index}]overlay=x={x}:y={y}:format=rgb:"
            f"enable='gte(n,{item.start_frame})*lt(n,{item.end_frame})':"
            f"eof_action=pass[{output}]"
        )
        base = output
    filters.append(f"[{base}]{suffix.lstrip(',') or 'null'}[overlay-video]")
    return inputs, ";".join(filters)
