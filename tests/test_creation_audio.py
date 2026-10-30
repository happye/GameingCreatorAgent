from dataclasses import FrozenInstanceError

import pytest

from gamingcreator.domain.creation_audio import AudioMix, BgmSelection


def test_roundtrip_defaults_and_frozen():
    mix = AudioMix(BgmSelection("a" * 32, "b" * 64, -6), -3, "source-v1")
    assert AudioMix.from_json(mix.to_json()) == mix
    assert AudioMix.from_json(AudioMix().to_json()) == AudioMix()
    with pytest.raises(FrozenInstanceError):
        mix.ducking = "off"


@pytest.mark.parametrize(
    "gain", [True, False, "0", None, float("nan"), float("inf"), -61, 1, 10**1000]
)
def test_invalid_gain(gain):
    with pytest.raises(ValueError):
        AudioMix(source_gain_db=gain)
    with pytest.raises(ValueError):
        BgmSelection("a" * 32, "b" * 64, gain)


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        [],
        {"bgm": None, "sourceGainDb": 0, "ducking": "loud"},
        {"bgm": {}, "sourceGainDb": 0, "ducking": "off"},
        {
            "bgm": {"trackId": "../foreign", "trackReceiptSha256": "b" * 64, "gainDb": 0},
            "sourceGainDb": 0,
            "ducking": "off",
        },
    ],
)
def test_invalid_json(value):
    with pytest.raises(ValueError):
        AudioMix.from_json(value)
