"""Human-readable projections of legacy visual observations, without invented clocks."""

import re

FACTS_PROJECTION_VERSION = "legacy-frame-alias-neutral-v1"
# Lower-case aliases belong to a model input window, not a persisted event's
# evidence subset. Do not guess their source time from an event's evidence IDs.
# ASCII identifier boundaries preserve names such as run:f0, image-f1 and f0o.
_FRAME_ALIASES = re.compile(
    r"(?<![A-Za-z0-9_:/.-])f[0-8]"
    r"(?:\s*(?:[-–—→~～至到、，,/与和])\s*f[0-8])*"
    r"(?!(?:[A-Za-z0-9_:/]|[.-][A-Za-z0-9_]))"
)


def clean_observation_text(text: str) -> str:
    """Replace leaked window aliases with neutral prose; preserve source facts."""
    return _FRAME_ALIASES.sub(
        lambda match: (
            "对应画面序列" if len(re.findall(r"f[0-8]", match.group())) > 1 else "对应画面"
        ),
        text,
    )


def display_facts(facts: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(clean_observation_text(text) for text in facts)
