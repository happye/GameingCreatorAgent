"""Fixed nonzero-MP4 generator expectations; never derive answers from a probe.

Evidence: 2026-10-29 matrix-{cached-old,candidate}-input-{old,new}-probe.json,
matrix-summary.json and matrix-commands.json. Both probe versions read identical
clocks for each saved input; the encoder changes AAC priming. Input SHA below is
historical evidence, not a hash required of newly generated clips.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeneratorClock:
    origin_us: int
    duration_us: int
    absolute_video_start_us: int
    head_hint_seconds: str

    @property
    def relative_video_start_us(self) -> int:
        return self.absolute_video_start_us - self.origin_us


RECORDS = {
    "fbf93c7f66b9194a236ecacbc2cb011ad91b704c87f7dba673efbf5800f8c67a": {
        "version": "N-123317-gc1be2107c9-20260310",
        "files": {
            "avcodec-62.dll": "64cffbcd72d2fc34228f283cc1c6b2565c6c41b9efbcc9935b9cec45e73dc5fd",
            "avdevice-62.dll": "ff2dee6076215395cfd4b077af420eda524ca8398b110d1aef57b9312b8d8dcd",
            "avfilter-11.dll": "aba6252cee805146002202cdd922596a1d0f6ba217130af7f8d820483b2ec33b",
            "avformat-62.dll": "70a12ed7b6b02fc4fea07734be9ff9e74ac3392fba88a81dc78fe2f66cc41d09",
            "avutil-60.dll": "9a909fa9611b5122c296bc3114a99799946932fc727d866a1201c65476fd9f87",
            "ffmpeg.exe": "fbf93c7f66b9194a236ecacbc2cb011ad91b704c87f7dba673efbf5800f8c67a",
            "ffprobe.exe": "837958d75a2b8640dd86117fe6c6ac4aedfdf8ef302d2753a4e4914f82c8e0f1",
            "swresample-6.dll": "a3998f5b07259584bceba0519d6d36f252879f796a1e09cf936157a0ee212997",
            "swscale-9.dll": "1d9816ece474e931f7a7d7b5ccc3912b5539961a2965a106bd64c9c588277170",
        },
        "origin_us": 2478000,
        "duration_us": 2022000,
        "absolute_video_start_us": 2500000,
        "head_hint_seconds": "0.022",
        "evidence_input_sha256": "00d33703acfa0c4093a410f85c92eaf9cc6f8700360bf9ecab5d872d6223c811",
    },
    "ea76d0cbcacb1a44870c6ea98af2f83661b4a445eaa39ddb7a5c63bf63d611b7": {
        "version": "N-127021-ge0c94b2d1c",
        "files": {
            "avcodec-63.dll": "86ba8724220b580a9a9ddde33d45115042b78017fc5085418e60d9d6e786de31",
            "avdevice-63.dll": "1481ce7211c93c558c1be762f8b3bedd11cba307404a1dfeaac64d6f5efa3bc2",
            "avfilter-12.dll": "8eec192f848a77eae8d20c86c21029a53cccc56f01dd4dedbebbbdb731093027",
            "avformat-63.dll": "eb1568c37d483719e73694454fb21488d229d64d283ed7e4250ad8886ded54fc",
            "avutil-61.dll": "870c9493bb6c1778ae2b95d66fb0d59bbef97d87ff95215bbdbcea83cf24cd2c",
            "ffmpeg.exe": "ea76d0cbcacb1a44870c6ea98af2f83661b4a445eaa39ddb7a5c63bf63d611b7",
            "ffplay.exe": "2ce0524d0540e23cbf765a10138832688f75b0b818e145f8a0fc00adc03c44e7",
            "ffprobe.exe": "afa08d4e0606d26a124debaca1ab842f7b644a480ba02b3666daf0575f237ab1",
            "swresample-7.dll": "92cbd7597bebb9e887ef0e50ee6a48c14d59f89d76e7411bdc7cacb1bc524592",
            "swscale-10.dll": "7816f44093199193598b7d480f4121444a2316cf97cdc1eeb14426f4fe65b849",
        },
        "origin_us": 2478667,
        "duration_us": 2026667,
        "absolute_video_start_us": 2500000,
        "head_hint_seconds": "0.021",
        "evidence_input_sha256": "b76bf4ab8a6c6ea762e3015772299b97a48d86e9367bb7fbec198511bfadd5a4",
    },
}


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def generator_clock(ffmpeg: Path) -> GeneratorClock:
    """Accept only the two reviewed complete tool sets, independent of manifests."""
    identity = _sha256(ffmpeg)
    if identity not in RECORDS:
        raise AssertionError(f"Unknown synthetic media generator SHA256: {identity}")
    record = RECORDS[identity]
    for name, expected in record["files"].items():
        if _sha256(ffmpeg.parent / name) != expected:
            raise AssertionError(f"Synthetic media generator tool/DLL SHA256 mismatch: {name}")
    return GeneratorClock(
        record["origin_us"],
        record["duration_us"],
        record["absolute_video_start_us"],
        record["head_hint_seconds"],
    )
