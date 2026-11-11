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


def test_source_envelope_roundtrip_interpolation_and_expression():
    """Stage C keyframes: optional key, strict points, dB-linear curve, FFmpeg twin."""
    from gamingcreator.domain.creation_audio import envelope_db, envelope_expression

    base = {"bgm": None, "sourceGainDb": -3, "ducking": "off"}
    assert AudioMix.from_json(base).to_json() == base  # unchanged JSON without keyframes
    points = [{"frame": 30, "gainDb": 0}, {"frame": 60, "gainDb": -12}, {"frame": 90, "gainDb": -6}]
    mix = AudioMix.from_json({**base, "sourceEnvelope": points})
    assert mix.to_json()["sourceEnvelope"] == points
    curve = mix.source_envelope
    assert [envelope_db(curve, f) for f in (0, 30, 45, 60, 75, 90, 200)] == [
        0,
        0,
        -6,
        -12,
        -9,
        -6,
        -6,
    ]
    expression = envelope_expression(curve, 30)
    # Evaluate FFmpeg's if()/lt() with Python stand-ins: the expression must equal the curve.
    python = expression.replace("if(", "IF(").replace("lt(", "LT(")
    names = {"IF": lambda c, a, b: a if c else b, "LT": lambda a, b: a < b}
    for t in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 5.0):
        value = eval(python, {"__builtins__": {}}, {**names, "t": t})  # noqa: S307
        assert value == pytest.approx(envelope_db(curve, t * 30), abs=1e-3)
    for bad in (
        [],
        [{"frame": 1, "gainDb": 0}, {"frame": 1, "gainDb": -1}],
        [{"frame": -1, "gainDb": 0}],
        [{"frame": 1, "gainDb": 3}],
        [{"frame": 1.5, "gainDb": 0}],
        [{"frame": 1}],
        [{"frame": i, "gainDb": 0} for i in range(65)],
    ):
        with pytest.raises(ValueError):
            AudioMix.from_json({**base, "sourceEnvelope": bad})
