"""One-off narration voice audition: the same lines in several CosyVoice voices plus the local voice.

Usage (in a terminal where you set the key yourself; it is never written to disk):
    . ./scripts/env.ps1
    $env:DASHSCOPE_API_KEY = '<your key>'          # Beijing region key
    $env:DASHSCOPE_WORKSPACE_ID = '<workspace id>'  # optional; legacy domain when absent
    python -B scripts/tts-audition.py               # dry run: prints characters and cost
    python -B scripts/tts-audition.py --send        # paid: about 0.06 yuan for 4 voices

Writes artifacts/tts-audition/<voice>.wav, a local sample, audition.json (billing record, one
row per paid call, written before and after sending) and index.html to listen side by side.
Voices that already have audio are skipped, so a rerun never pays twice. Refuses to send more
than MAX_CHARACTERS in total.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gamingcreator.infrastructure import cosyvoice_tts as tts  # noqa: E402

LINES = (
    "三对三的卷轴争夺战，开局三十秒就打出了第一波团战！"
    "看这一套连招，控制接爆发，对面直接被打懵。"
    "喜欢这类玩法的朋友，记得点赞关注，下期带你上分。"
)
DEFAULT_VOICES = ("longxiu_v3", "longyue_v3", "longanyang", "longshuo_v3")
MAX_CHARACTERS = 1000  # about 0.1 yuan at list price


def record(path: Path, row: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def local_sample(out: Path) -> str | None:
    """The free Windows voice for comparison; skipped when unavailable."""
    from gamingcreator.application.narration import NarrationRequest
    from gamingcreator.application.providers import CancellationContext
    from gamingcreator.infrastructure.sapi_narration import (
        list_local_voices,
        synthesize_local_narration,
    )

    target = out / "local"
    if (target / "narration.wav").exists():
        return "local/narration.wav"
    try:
        voices = asyncio.run(list_local_voices(CancellationContext("audition-voices", 60)))
        voice = next((v for v in voices if v.language == "804"), None)
        if voice is None:
            return None
        request = NarrationRequest("audition", "audition", LINES, voice.voice_id)
        asyncio.run(
            synthesize_local_narration(request, target, CancellationContext("audition", 120))
        )
        return "local/narration.wav"
    except (OSError, ValueError) as error:
        print(f"local voice skipped: {error}")
        return None


def page(out: Path, rows: list[tuple[str, str]]) -> None:
    items = "".join(
        f'<section><h2>{html.escape(title)}</h2><audio controls preload="none" src="{html.escape(src)}"></audio></section>'
        for title, src in rows
    )
    out.joinpath("index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>旁白音色试听</title>"
        "<style>body{font:16px system-ui;max-width:720px;margin:32px auto;padding:0 16px}"
        "section{margin:16px 0;padding:12px;border:1px solid #ccc;border-radius:8px}audio{width:100%}</style>"
        f"<h1>旁白音色试听</h1><p>{html.escape(LINES)}</p>{items}",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--send", action="store_true", help="make the paid calls")
    parser.add_argument(
        "--voices", nargs="+", default=list(DEFAULT_VOICES), choices=sorted(tts.VOICES)
    )
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/tts-audition")
    args = parser.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    pending = [v for v in args.voices if not (out / f"{v}.wav").exists()]
    each = tts.estimated_characters(LINES)
    total = each * len(pending)
    cost = total / 10000 * tts.YUAN_PER_10K_CHARACTERS
    print(
        f"model {tts.MODEL}; {len(pending)} voice(s) to synthesize, about {total} billed characters, about {cost:.3f} yuan"
    )
    if total > MAX_CHARACTERS:
        print(f"refused: more than {MAX_CHARACTERS} characters")
        return 2
    if pending and not args.send:
        print("dry run: add --send to make the paid calls")
    ledger = out / "audition.json"
    for voice in pending if args.send else []:
        stamp = datetime.now(UTC).isoformat()
        record(
            ledger,
            {
                "at": stamp,
                "event": "planned",
                "model": tts.MODEL,
                "voice": voice,
                "estimatedCharacters": each,
            },
        )
        try:
            speech = tts.synthesize(LINES, voice)
        except (ValueError, KeyError) as error:
            record(
                ledger,
                {
                    "at": datetime.now(UTC).isoformat(),
                    "event": "failed",
                    "voice": voice,
                    "error": str(error)[:300],
                },
            )
            print(f"{voice}: failed: {error}")
            return 1
        (out / f"{voice}.wav").write_bytes(speech.audio)
        record(
            ledger,
            {
                "at": datetime.now(UTC).isoformat(),
                "event": "completed",
                "model": tts.MODEL,
                "voice": voice,
                "billedCharacters": speech.billed_characters,
                "requestId": speech.request_id,
            },
        )
        print(f"{voice}: {len(speech.audio)} bytes, billed characters {speech.billed_characters}")
    rows = [(tts.VOICES[v], f"{v}.wav") for v in args.voices if (out / f"{v}.wav").exists()]
    local = local_sample(out)
    if local:
        rows.append(("Windows 本机语音 Huihui（免费，对照）", local))
    page(out, rows)
    print(f"listen: {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
