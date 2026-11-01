"""T28: unified content-mode honesty copy on planner payloads (P043-P049)."""

from __future__ import annotations

from pathlib import Path

from tests.test_creation_modes import brief, material

from gamingcreator.application.creation_modes import (
    CREATION_GUIDE_REL,
    MODE_HONESTY_HELP,
    MODE_HONESTY_SHORT,
    MODE_LABELS,
)
from gamingcreator.application.creative_planner import plan_creation


def test_honesty_constants_stable() -> None:
    assert MODE_HONESTY_SHORT == "描述代理评分、非画面理解／未做人评／投放未验证"
    assert "非画面理解" in MODE_HONESTY_HELP
    assert "投放" in MODE_HONESTY_HELP
    assert CREATION_GUIDE_REL == "docs/references/creation-guide.md"
    assert Path(CREATION_GUIDE_REL).is_file()
    guide = Path(CREATION_GUIDE_REL).read_text(encoding="utf-8")
    assert MODE_HONESTY_SHORT in guide


def test_all_modes_attach_honesty_on_recommended_plan() -> None:
    facts = [
        ["角色奔跑"],
        ["角色跳跃", "空中旋转", "落地特效"],
        ["开场"],
        ["拾取道具"],
        ["结算画面"],
    ]
    clips = material(facts)
    for mode in MODE_LABELS:
        report = plan_creation(brief(mode), clips, 30)
        assert report["understandingVerified"] is False
        assert report.get("modeHonesty") == MODE_HONESTY_SHORT
        recommended = next(p for p in report["plans"] if p.get("mode") == mode)
        assert recommended["modeLabel"] == MODE_LABELS[mode]
        assert recommended["honesty"] == MODE_HONESTY_SHORT
        generics = [p for p in report["plans"] if "mode" not in p]
        assert generics
        assert all("honesty" not in p for p in generics)
