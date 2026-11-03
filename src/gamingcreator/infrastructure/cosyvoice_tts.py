"""Paid cloud speech synthesis through Alibaba Cloud Model Studio (CosyVoice), plain HTTP.

The key is read only from the sending process's DASHSCOPE_API_KEY and never written anywhere.
Callers own the fee gate: this module sends exactly one request per call and reports the
billed character count the provider returns (None when it returns none).
"""

import os
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

MODEL = "cosyvoice-v3-flash"
YUAN_PER_10K_CHARACTERS = 1.0  # Beijing list price, 2026-11; the console is authoritative.
MAX_TEXT = 2000
MAX_AUDIO_BYTES = 50 * 1024 * 1024
# System voices for cosyvoice-v3-flash suited to Chinese narration (provider voice list, 2026-11).
VOICES = {
    "longanyang": "龙安洋 · 阳光大男孩",
    "longxiu_v3": "龙修 · 博才说书男",
    "longyue_v3": "龙悦 · 温暖磁性女",
    "longshuo_v3": "龙硕 · 博才干练男（新闻）",
    "longmiao_v3": "龙妙 · 抑扬顿挫女",
    "longxiaochun_v3": "龙小淳 · 知性积极女",
}


@dataclass(frozen=True, slots=True)
class CloudSpeech:
    audio: bytes
    billed_characters: int | None
    request_id: str


def endpoint() -> str:
    workspace = os.environ.get("DASHSCOPE_WORKSPACE_ID", "").strip()
    host = f"{workspace}.cn-beijing.maas.aliyuncs.com" if workspace else "dashscope.aliyuncs.com"
    if workspace and not workspace.replace("-", "").isalnum():
        raise ValueError("DASHSCOPE_WORKSPACE_ID must be a plain workspace identifier.")
    return f"https://{host}/api/v1/services/audio/tts/SpeechSynthesizer"


def estimated_characters(text: str) -> int:
    """Upper bound used for the fee gate: CJK characters count twice."""
    return sum(2 if "⺀" <= char <= "鿿" or "豈" <= char <= "￯" else 1 for char in text)


def synthesize(
    text: str, voice: str, timeout: float = 60.0, transport: httpx.BaseTransport | None = None
) -> CloudSpeech:
    if voice not in VOICES:
        raise ValueError("Unknown CosyVoice system voice.")
    if not text.strip() or len(text) > MAX_TEXT:
        raise ValueError(f"Text must contain 1..{MAX_TEXT} characters.")
    key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not key.strip() or any(c in key for c in "\r\n"):
        raise ValueError("Set DASHSCOPE_API_KEY in this terminal first.")
    body = {
        "model": MODEL,
        "input": {"text": text, "voice": voice, "format": "wav", "sample_rate": 24000},
    }
    with httpx.Client(
        trust_env=False, follow_redirects=False, timeout=timeout, transport=transport
    ) as client:
        response = client.post(endpoint(), json=body, headers={"Authorization": "Bearer " + key})
        if response.status_code != 200:
            # The provider's message is safe to show; the key is never part of it.
            raise ValueError(f"CosyVoice HTTP {response.status_code}: {response.text[:300]}")
        data = response.json()
        url = data["output"]["audio"]["url"]
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not (parsed.hostname or "").endswith(
            ".aliyuncs.com"
        ):
            raise ValueError("Unexpected audio location in the provider response.")
        audio = client.get(url)
        if audio.status_code != 200 or len(audio.content) > MAX_AUDIO_BYTES:
            raise ValueError(f"Audio download failed (HTTP {audio.status_code}).")
    usage = data.get("usage", {}).get("characters")
    return CloudSpeech(
        audio.content, usage if type(usage) is int else None, str(data.get("request_id", ""))
    )
