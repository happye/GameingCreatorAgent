"""CosyVoice HTTP adapter against a mock transport; no network, no key on disk."""

import json

import httpx
import pytest

from gamingcreator.infrastructure import cosyvoice_tts as tts


def transport(
    seen, status=200, url="https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/a.wav"
):
    def handle(request):
        seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, content=b"RIFFwav")
        body = {"request_id": "r1", "output": {"audio": {"url": url}}, "usage": {"characters": 12}}
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handle)


def test_synthesize_posts_voice_and_downloads_audio(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "k")
    monkeypatch.delenv("DASHSCOPE_WORKSPACE_ID", raising=False)
    seen = []
    speech = tts.synthesize("你好", "longxiu_v3", transport=transport(seen))
    assert speech.audio == b"RIFFwav" and speech.billed_characters == 12
    post = seen[0]
    assert post.url == "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer"
    assert post.headers["Authorization"] == "Bearer k"
    assert json.loads(post.content)["input"] == {
        "text": "你好",
        "voice": "longxiu_v3",
        "format": "wav",
        "sample_rate": 24000,
    }


@pytest.mark.parametrize(
    "env, voice, url, status",
    [
        ({}, "longxiu_v3", None, 200),  # no key
        ({"DASHSCOPE_API_KEY": "k"}, "nobody", None, 200),  # unknown voice
        ({"DASHSCOPE_API_KEY": "k"}, "longxiu_v3", "https://evil.example/a.wav", 200),
        ({"DASHSCOPE_API_KEY": "k"}, "longxiu_v3", None, 401),
    ],
)
def test_refusals(monkeypatch, env, voice, url, status):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    kwargs = {} if url is None else {"url": url}
    with pytest.raises(ValueError):
        tts.synthesize("你好", voice, transport=transport([], status, **kwargs))


def test_fee_estimate_counts_chinese_twice():
    assert tts.estimated_characters("你好ab") == 6
