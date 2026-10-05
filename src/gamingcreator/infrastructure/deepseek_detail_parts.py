"""Versioned nested parts bind each visible item's attributes before offline matching."""

import hashlib
import json

from gamingcreator.application.detail_refinement import (
    REFINEMENT_SCHEMA_VERSION,
    DetailRefinementRequest,
    RefinementIdentity,
)
from gamingcreator.domain.actor_details import MAX_ACTOR_ATTRIBUTES, CandidateDetail
from gamingcreator.infrastructure.deepseek_detail_refinement import (
    DeepSeekDetailRefinementProvider,
    _list,
    _object,
    _string,
    parse_detail,
)
from gamingcreator.infrastructure.deepseek_vision import _json
from gamingcreator.infrastructure.http_transport import MAX_RESPONSE_BYTES

PROMPT_VERSION = "actor-detail-refinement-v3"
PROMPT = """Observe only the supplied registered image IDs within one candidate.
Return JSON with exactly shots and notes arrays; never return source times or base identities.
shots has at most 9 objects with exactly shotId, evidenceIds, environment, actors.
Use distinct local shot IDs; each frame belongs to at most one continuous shot.
Keep cuts separate; never link actor identity across shots. Frames may remain unassigned.
actors has at most 8 objects with exactly actorId, description, parts.
Use distinct actor IDs within each shot and a neutral visible description of at most 500 characters.
Do not infer a controlled player, character name, weapon class, or action from game context.
parts has at most 16 objects with exactly partId, partGroup, attributes.
Each part is one visible body feature, garment, held object, action, or effect within one actor.
Use a distinct local partId for each actual item and keep all its supported attributes together.
For example a red coat has one clothing part containing clothing_shape=coat and clothing_color=red.
Do not create separate parts for the shape and color of that same coat.
A red scarf and a red coat are distinct clothing parts even though their colors match.
Never borrow another actor's attributes, merge two garments, or reuse a partId for different items.
partGroup is exactly hair, clothing, held_item, action, or effect.
hair permits only hair_color; clothing permits clothing_color and clothing_shape;
held_item permits held_shape and held_class; action permits only action; effect permits only effect.
Each part has a nonempty attributes array; total attributes across one actor are at most 16.
Each nested attribute has exactly kind, value, status, evidenceIds; do not repeat partId there.
environment has at most 16 attributes with exactly partId, kind, value, status, evidenceIds.
Only shot environment may use kind=environment. No actor part may contain environment.
All evidenceIds must be supplied IDs, ordered by source time and within their shot.
status is observed or uncertain. Omit invisible/unknown attributes; uncertain is never a positive fact.
hair_color and clothing_color values: white, black, red, blue, brown, orange, gray, green, yellow, purple, light, dark.
clothing_shape values: upper_garment, coat, scarf, shorts, trousers, armor, gloves.
held_shape values: flat_object, blue_flat_object, long_rod, curved_object.
held_class values: weapon, staff, tool; shape alone does not establish class.
action values: look_up, move, run, jump, raise_item, shoot; cite at least two different frames showing the action.
effect values: light_arc, light_ring, projectile.
environment values: water, stone_platform, sandy_ground, indoors, outdoors.
Static attributes may cite one frame; never extrapolate an attribute across unsupported frames or gaps.
Each attribute must cite its own supporting frames; sharing a part does not supply missing evidence.
notes has at most 16 nonempty strings of at most 500 characters. Use Chinese descriptions/notes.
When evidence is insufficient return {"shots":[],"notes":["视觉证据不足，待核对。"]}.
"""

_PART_KINDS = {
    "hair": frozenset({"hair_color"}),
    "clothing": frozenset({"clothing_color", "clothing_shape"}),
    "held_item": frozenset({"held_shape", "held_class"}),
    "action": frozenset({"action"}),
    "effect": frozenset({"effect"}),
}


def provider_parts_identity() -> RefinementIdentity:
    return RefinementIdentity(
        PROMPT_VERSION,
        hashlib.sha256(PROMPT.encode()).hexdigest(),
        REFINEMENT_SCHEMA_VERSION,
        "deepseek",
        "deepseek-flash",
    )


def parse_parts_detail(content: str, request: DetailRefinementRequest) -> CandidateDetail:
    """Flatten explicitly bound parts; reuse frozen validation without guessing any identity."""
    if request.identity != provider_parts_identity():
        raise ValueError("Unsupported nested-parts refinement identity.")
    if type(content) is not str or len(content.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError("Invalid or oversized nested-parts response.")
    value = _object(_json(content), {"shots", "notes"})
    shots: list[dict[str, object]] = []
    for item in _list(value["shots"], 9):
        shot = _object(item, {"shotId", "evidenceIds", "environment", "actors"})
        actors: list[dict[str, object]] = []
        for raw_actor in _list(shot["actors"], 8):
            actor = _object(raw_actor, {"actorId", "description", "parts"})
            attributes: list[dict[str, object]] = []
            part_ids: set[str] = set()
            for raw_part in _list(actor["parts"], MAX_ACTOR_ATTRIBUTES):
                part = _object(raw_part, {"partId", "partGroup", "attributes"})
                part_id = _string(part["partId"])
                group = _string(part["partGroup"])
                if part_id in part_ids or group not in _PART_KINDS:
                    raise ValueError("Duplicate part identity or unknown part group.")
                part_ids.add(part_id)
                part_attributes = _list(part["attributes"], MAX_ACTOR_ATTRIBUTES)
                if (
                    not part_attributes
                    or len(attributes) + len(part_attributes) > MAX_ACTOR_ATTRIBUTES
                ):
                    raise ValueError("Actor parts require bounded nonempty attributes.")
                for raw_attribute in part_attributes:
                    attribute = _object(raw_attribute, {"kind", "value", "status", "evidenceIds"})
                    if _string(attribute["kind"]) not in _PART_KINDS[group]:
                        raise ValueError("Attribute kind does not belong to its part group.")
                    attributes.append({"partId": part_id, **attribute})
            actors.append(
                {
                    "actorId": actor["actorId"],
                    "description": actor["description"],
                    "attributes": attributes,
                }
            )
        shots.append({**shot, "actors": actors})
    return parse_detail(json.dumps({"shots": shots, "notes": value["notes"]}), request)


class DeepSeekDetailPartsProvider(DeepSeekDetailRefinementProvider):
    """Reuse the single-send transport, input validation, cancellation, usage and metadata path."""

    _prompt = PROMPT
    _identity = staticmethod(provider_parts_identity)
    _parse = staticmethod(parse_parts_detail)
