"""Source inventory: hash, probe and compare local videos for shared footage evidence.

The report is evidence for a human grouping decision. It never assigns or suggests a
recordingGroup and never changes a frozen plan.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.footage_overlap import (
    CropBox,
    OverlapParameters,
    SharedFootage,
    find_shared_footage,
)
from gamingcreator.domain.media import LOCAL_VIDEO_SUFFIXES, MediaAsset

SCHEMA = "source-inventory-v2"
SCHEMA_V1 = "source-inventory-v1"
DEFAULT_TIMEOUT_SECONDS = 3600.0
LIMITATIONS = (
    "匹配是共用画面的证据；未匹配不证明独立。",
    "裁切（非均匀黑边）、大面积叠字、变速及很短的低动作镜头仍可能漏检。",
    "票数是相邻偏移上的相关投票，概率只是名义排序分数，不是精确概率。",
    "本报告不自动分配录制组，也不改变冻结计划，分组须人工决定。",
)
# Texts of reports already written as source-inventory-v1; they stay valid for freezing.
LIMITATIONS_V1 = (
    "匹配是共用画面的证据；未匹配不证明独立。",
    "裁切、黑边、镜像、大面积叠字、变速可能导致漏检。",
    "票数是相邻偏移上的相关投票，概率只是名义排序分数，不是精确概率。",
    "本报告不自动分配录制组，也不改变冻结计划，分组须人工决定。",
)


@dataclass(frozen=True, slots=True)
class VideoStreamInfo:
    codec: str
    width: int
    height: int
    frame_rate: str


@dataclass(frozen=True, slots=True)
class SignatureIdentity:
    """What the extractor actually used; the report records exactly these values."""

    hash_name: str
    sampling_filter: str
    min_stdev: float
    samples_per_second: int
    crop_detect_filter: str
    crop_filter: str
    min_crop_area_fraction: float
    min_crop_removed_fraction: float
    mirror: bool


@dataclass(frozen=True, slots=True)
class SourceSignature:
    """Hashes sampled at ``samples_per_second``; ``None`` marks a low-information frame."""

    hashes: tuple[int | None, ...]
    samples_per_second: int
    mirrored_hashes: tuple[int | None, ...]
    crop: CropBox | None

    def __post_init__(self) -> None:
        if len(self.mirrored_hashes) != len(self.hashes):
            raise ValueError("Mirrored hashes must align with the hashes.")

    @property
    def sampled_frames(self) -> int:
        return len(self.hashes)

    @property
    def informative_frames(self) -> int:
        return sum(1 for value in self.hashes if value is not None)


class MediaProber(Protocol):
    async def probe(self, source: Path, context: CancellationContext) -> MediaAsset: ...


class SignatureSource(Protocol):
    @property
    def identity(self) -> SignatureIdentity: ...

    async def tool_version(self, context: CancellationContext) -> str: ...

    async def video_info(self, source: Path, context: CancellationContext) -> VideoStreamInfo: ...

    async def signature(
        self, source: Path, duration_us: int, context: CancellationContext
    ) -> SourceSignature: ...


def discover_sources(inputs: Sequence[Path]) -> tuple[Path, ...]:
    """Explicit files and recursive local videos under directories, de-duplicated and sorted."""
    found: dict[str, Path] = {}
    for item in inputs:
        try:
            resolved = item.resolve(strict=True)
            if resolved.is_dir():
                candidates = [
                    path.resolve()
                    for path in resolved.rglob("*")
                    if path.is_file() and path.suffix.lower() in LOCAL_VIDEO_SUFFIXES
                ]
            elif resolved.is_file():
                candidates = [resolved]
            else:
                raise OSError
        except OSError:
            raise AppError(
                "input.inventory_source", "素材路径不存在或无法读取。", ExitCode.INPUT
            ) from None
        for path in candidates:
            found[str(path).casefold()] = path
    if not found:
        raise AppError("input.inventory_source", "没有找到可盘点的 MP4 素材。", ExitCode.INPUT)
    return tuple(sorted(found.values(), key=lambda path: str(path).casefold()))


def ensure_output_outside_sources(
    output: Path, inputs: Sequence[Path], sources: Sequence[Path]
) -> None:
    """The report must never be written beside or into the source footage."""
    target = output.resolve()
    directories = [item.resolve() for item in inputs if item.resolve().is_dir()]
    if any(target == source or target.parent == source.parent for source in sources) or any(
        directory in (target, *target.parents) for directory in directories
    ):
        raise AppError("input.inventory_output", "盘点报告不能写入素材所在目录。", ExitCode.INPUT)


def _context(timeout_seconds: float) -> CancellationContext:
    return CancellationContext("source-inventory", timeout_seconds)


def _candidate(
    source_a: str, source_b: str, paths: tuple[str, str], footage: SharedFootage
) -> dict[str, object]:
    shared = footage.shared
    return {
        "sourceA": source_a,
        "sourceB": source_b,
        "pathA": paths[0],
        "pathB": paths[1],
        "offsetSamples": shared.offset_samples,
        "offsetSeconds": shared.offset_seconds,
        "comparedVotes": shared.compared_votes,
        "matchedVotes": shared.matched_votes,
        "matchRate": shared.matched_votes / shared.compared_votes,
        "matchedFramesA": shared.matched_frames_a,
        "clusterCount": shared.cluster_count,
        "backgroundMatchRate": shared.background_rate,
        "correctedPValue": shared.corrected_p,
        "log10CorrectedPValue": shared.log10_corrected_p,
        "aFirstSeconds": shared.a_first_seconds,
        "aLastSeconds": shared.a_last_seconds,
        "bFirstSeconds": shared.b_first_seconds,
        "bLastSeconds": shared.b_last_seconds,
        "mirrored": footage.mirrored,
    }


async def build_source_inventory(
    sources: Sequence[Path],
    prober: MediaProber,
    signer: SignatureSource,
    parameters: OverlapParameters | None = None,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    settings = parameters or OverlapParameters()
    identity = signer.identity
    if identity.samples_per_second != settings.samples_per_second:
        raise AppError("media.signature", "采样率与检测参数不一致。", ExitCode.ENVIRONMENT)
    version = await signer.tool_version(_context(timeout_seconds))
    entries: list[dict[str, object]] = []
    signatures: list[SourceSignature | None] = []
    failed: list[dict[str, object]] = []
    not_comparable: list[dict[str, object]] = []
    for index, source in enumerate(sources, start=1):
        source_id = f"source-{index:03d}"
        try:
            asset = await prober.probe(source, _context(timeout_seconds))
            info = await signer.video_info(asset.source_path, _context(timeout_seconds))
            signature = await signer.signature(
                asset.source_path, asset.duration_us, _context(timeout_seconds)
            )
            byte_size = asset.source_path.stat().st_size
        except (AppError, OSError) as error:
            failed.append(
                {
                    "sourceId": source_id,
                    "path": str(source),
                    "code": error.code if isinstance(error, AppError) else "input.video",
                    "message": error.message if isinstance(error, AppError) else "无法读取源文件。",
                }
            )
            continue
        if signature.samples_per_second != settings.samples_per_second:
            raise AppError("media.signature", "采样率与检测参数不一致。", ExitCode.ENVIRONMENT)
        entry: dict[str, object] = {
            "sourceId": source_id,
            "path": str(asset.source_path),
            "byteSize": byte_size,
            "sha256": asset.sha256,
            "durationUs": asset.duration_us,
            "video": {
                "codec": info.codec,
                "width": info.width,
                "height": info.height,
                "frameRate": info.frame_rate,
            },
            "sampledFrames": signature.sampled_frames,
            "informativeFrames": signature.informative_frames,
            "crop": None if signature.crop is None else signature.crop.to_dict(),
        }
        entries.append(entry)
        if signature.informative_frames < settings.min_compared:
            not_comparable.append(
                {
                    "sourceId": source_id,
                    "path": entry["path"],
                    "informativeFrames": signature.informative_frames,
                    "sampledFrames": signature.sampled_frames,
                    "reason": f"有效画面不足 {settings.min_compared} 个采样，未参与比较。",
                }
            )
            signatures.append(None)
        else:
            signatures.append(signature)
    usable = [
        (entry, signature)
        for entry, signature in zip(entries, signatures, strict=True)
        if signature is not None
    ]
    by_hash: dict[str, list[int]] = {}
    for position, entry in enumerate(entries):
        by_hash.setdefault(str(entry["sha256"]), []).append(position)
    duplicates = [
        {
            "sha256": digest,
            "sourceIds": [entries[p]["sourceId"] for p in positions],
            "paths": [entries[p]["path"] for p in positions],
        }
        for digest, positions in by_hash.items()
        if len(positions) > 1
    ]
    candidates: list[dict[str, object]] = []
    for first in range(len(usable)):
        for second in range(first + 1, len(usable)):
            (entry_a, signature_a), (entry_b, signature_b) = usable[first], usable[second]
            if entry_a["sha256"] == entry_b["sha256"]:
                continue
            for footage in find_shared_footage(
                signature_a.hashes,
                signature_b.hashes,
                signature_b.mirrored_hashes if identity.mirror else None,
                settings,
            ):
                candidates.append(
                    _candidate(
                        str(entry_a["sourceId"]),
                        str(entry_b["sourceId"]),
                        (str(entry_a["path"]), str(entry_b["path"])),
                        footage,
                    )
                )
    return {
        "schemaVersion": SCHEMA,
        "humanDecisionRequired": True,
        "parameters": {
            **settings.to_dict(),
            "hash": identity.hash_name,
            "samplingFilter": identity.sampling_filter,
            "minFrameStdev": identity.min_stdev,
            "cropDetectFilter": identity.crop_detect_filter,
            "cropFilter": identity.crop_filter,
            "minCropAreaFraction": identity.min_crop_area_fraction,
            "minCropRemovedFraction": identity.min_crop_removed_fraction,
            "mirror": identity.mirror,
            "sampleTimeBasis": (
                "序号/采样率，相对首个视频帧的近似秒；不代表逐帧 PTS 精度。"
                "offsetSeconds = A 时间 - B 时间。"
            ),
        },
        "ffmpegVersion": version,
        "sources": entries,
        "duplicateGroups": duplicates,
        "notComparable": not_comparable,
        "failedSources": failed,
        "sharedFootageCandidates": candidates,
        "limitations": list(LIMITATIONS),
    }


def inventory_summary(report: dict[str, object]) -> list[str]:
    """Short Chinese console summary."""
    sources = report["sources"]
    duplicates = report["duplicateGroups"]
    candidates = report["sharedFootageCandidates"]
    skipped = report["notComparable"]
    failed = report["failedSources"]
    assert isinstance(sources, list) and isinstance(duplicates, list)
    assert isinstance(candidates, list) and isinstance(skipped, list) and isinstance(failed, list)
    lines = [
        f"已盘点 {len(sources)} 个素材；同字节重复组 {len(duplicates)} 个；"
        f"疑似共用画面 {len(candidates)} 处。",
    ]
    for item in candidates:
        lines.append(
            f"  {item['sourceA']} 与 {item['sourceB']}："
            f"{'镜像，' if item['mirrored'] else ''}偏移 {item['offsetSeconds']:+.1f} 秒，"
            f"{item['matchedVotes']} 票／{item['comparedVotes']} 票，"
            f"A 方 {item['matchedFramesA']} 个不同采样。"
        )
    for item in skipped:
        lines.append(
            f"{item['sourceId']} 有效画面不足（{item['informativeFrames']}/"
            f"{item['sampledFrames']}），未参与比较。"
        )
    for item in failed:
        lines.append(f"{item['sourceId']} 处理失败（{item['code']}）：{item['path']}，已跳过。")
    lines.append("匹配只是证据，未匹配不证明独立；录制组须人工决定。")
    return lines
