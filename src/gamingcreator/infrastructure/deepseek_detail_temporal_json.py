"""Explicit JSON output instructions without altering frozen v4 identities or payloads."""

import hashlib

from gamingcreator.application.detail_refinement import (
    REFINEMENT_TEMPORAL_SCHEMA_VERSION,
    DetailRefinementRequest,
    RefinementIdentity,
)
from gamingcreator.domain.actor_details import CandidateDetail
from gamingcreator.infrastructure.deepseek_detail_temporal import (
    PROMPT as TEMPORAL_PROMPT,
)
from gamingcreator.infrastructure.deepseek_detail_temporal import (
    DeepSeekDetailTemporalProvider,
    _parse_temporal_detail,
)

PROMPT_VERSION = "actor-detail-refinement-v5"
PROMPT = (
    "Return exactly one valid JSON object, without Markdown fences or extra text.\n"
    "Its only top-level keys are transitions, entities, owners, environment, notes; "
    "all five values are JSON arrays.\n" + TEMPORAL_PROMPT
)


def provider_temporal_json_identity() -> RefinementIdentity:
    return RefinementIdentity(
        PROMPT_VERSION,
        hashlib.sha256(PROMPT.encode()).hexdigest(),
        REFINEMENT_TEMPORAL_SCHEMA_VERSION,
        "deepseek",
        "deepseek-flash",
    )


def parse_temporal_json_detail(content: str, request: DetailRefinementRequest) -> CandidateDetail:
    return _parse_temporal_detail(content, request, provider_temporal_json_identity())


class DeepSeekDetailTemporalJsonProvider(DeepSeekDetailTemporalProvider):
    """Reuse registered frame ordering and strict entity parsing under a new prompt identity."""

    _prompt = PROMPT
    _identity = staticmethod(provider_temporal_json_identity)
    _parse = staticmethod(parse_temporal_json_detail)
