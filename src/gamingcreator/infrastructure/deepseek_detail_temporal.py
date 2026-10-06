"""Versioned entity and continuity evidence; reuse single-send accounting and transport."""

import hashlib
import json
from typing import cast

from gamingcreator.application.detail_refinement import (
    REFINEMENT_TEMPORAL_SCHEMA_VERSION,
    DetailRefinementRequest,
    RefinementIdentity,
    RefinementSettings,
)
from gamingcreator.application.temporal_entity_projection import project_temporal_scene
from gamingcreator.application.temporal_scene_codec import scene_from_model
from gamingcreator.domain.actor_details import DETAIL_TEMPORAL_SCHEMA_VERSION, CandidateDetail
from gamingcreator.infrastructure.deepseek_detail_refinement import DeepSeekDetailRefinementProvider
from gamingcreator.infrastructure.deepseek_vision import _json
from gamingcreator.infrastructure.http_transport import MAX_RESPONSE_BYTES

PROMPT_VERSION = "actor-detail-refinement-v4"
PROMPT = """Observe the supplied source-ordered registered frames within one candidate only.
Input sequenceVersion=registered-frame-sequence-v1 contains candidateInterval and frameCount.
Each image's preceding text gives frameIndex, evidenceId, sourceUs and deltaFromPreviousUs.
Use these registered times to compare visible changes; never return clocks or base identities.
Return exactly transitions, entities, owners, environment, notes arrays. Do not return shots.
First distinguish a character from an object and insufficient evidence, then report attributes.
An object approaching the camera, rotating, growing in screen area, or covering a character
must not become a new character merely because it looks large, colorful, or face-like.
Characters can be humans, animals, monsters or robots; human anatomy is not required.
Face designs or decorations on a carried object alone do not establish a character.
Do not infer player control, character names, weapon use or skills from game knowledge.

transitions contains exactly one entry for each adjacent input-frame pair, in source order:
{beforeId,afterId,state,basis,reason}. state/basis pairs are continuous/visual_continuity,
cut/scene_change, unknown/insufficient_evidence. reason is a short concrete visible explanation.
For cut cite the actual background/scene-composition change on its two sides. Object size,
perspective, character occlusion, camera movement, zoom, rotation or effects alone are not cuts.
Use continuous when visible scene evidence supports continuity, including foreground occlusion.
Use unknown when the boundary cannot be established. Never connect identity across cut or unknown.
Do not create a new shot simply because one entity becomes hidden or changes apparent size.

entities has at most 72 entries and at most 8 observed characters in each continuous segment.
Each entry has exactly entityId, description, classification, observations, parts.
entityId is a unique local alphanumeric/underscore/hyphen ID of at most 128 characters.
description is a neutral visible description, not an inferred story.
classification has exactly kind,status,basis,evidenceIds,reason.
kind is actor, object or unknown; status is observed or uncertain.
Actor basis is character_structure or independent_agency. Character_structure must cite visible
character evidence, distinguishing articulated/acting character structure from an object design.
Independent_agency requires at least two different frames showing independently acting character
behavior, not movement explained solely by being carried, camera motion or an effect.
Object basis is carried_object or rigid_object. Describe its visible connection or object structure.
Unknown has status=uncertain, basis=insufficient_evidence, no parts; evidenceIds may be empty.
For all other classification claims cite nonempty supporting visible/partially visible frames.
If an apparent creature may be a held object, retain uncertainty; do not label it observed actor.

observations contains exactly {evidenceId,visibility,location} for each frame in this entity's
contiguous span, at most 9 entries, in source order, including intermediate occluded frames.
visibility is visible, partially_occluded, occluded or unknown; location describes its screen region.
Keep an occluded character's identity only within an established continuous segment, without
inventing its appearance behind an object. Classification and attributes may cite only visible
or partially_occluded observations, never fully occluded/unknown frames as positive evidence.
Split entities across cut/unknown boundaries; do not reuse entityId to imply identity continuity.

parts has at most 16 entries, with at most 16 attributes total per entity.
Each part is exactly {partId,partGroup,attributes}; keep one item's shape and color in one part.
Actor partGroup is hair, clothing, action or effect. Held objects are separate object entities.
Object partGroup is held_item only; objects never acquire hair, clothing, actions or effects.
Each attribute is exactly {kind,value,status,evidenceIds}; status=observed or uncertain.
Each actor's own plus supported owned-object attributes must also total at most 16;
do not emit excess attributes that would require truncation or silently lose requirements.
hair permits hair_color; clothing permits clothing_color/clothing_shape; action permits action;
effect permits effect; held_item permits held_shape/held_class. No actor part contains environment.
hair_color/clothing_color: white, black, red, blue, brown, orange, gray, green, yellow, purple, light, dark.
clothing_shape: upper_garment, coat, scarf, shorts, trousers, armor, gloves.
held_shape: flat_object, blue_flat_object, long_rod, curved_object.
held_class: weapon, staff, tool. Shape/color or query vocabulary cannot establish weapon class.
action: look_up, move, run, jump, raise_item, shoot; cite two different frames showing change.
effect: light_arc, light_ring, projectile. Omit unsupported vocabulary instead of inventing a class.
An observed attribute on an uncertain actor/object classification cannot become a confirmed fact.

owners has at most 72 entries, exactly {objectId,actorId,status,evidenceIds,reason}.
Report only actor/object entities in the same continuous segment; status=observed or uncertain.
Observed ownership needs specific visible holding/contact evidence with both entities visible or
partially visible in the cited frames. Proximity, matching color and off-screen assumptions are
insufficient. Preserve uncertain ownership; do not lend an object's attributes to a nearby actor.

environment has at most 16 entries, exactly {partId,kind,value,status,evidenceIds}, kind=environment.
values: water, stone_platform, sandy_ground, indoors, outdoors. Each entry is within one continuous
segment. Every evidenceIds array uses only supplied IDs, without duplicates and in source order.
Do not extrapolate attributes or ownership over unsupported frames. notes has at most 16 nonempty
strings. Every description, reason, location and note is at most 500 characters; use Chinese.
When unsure retain unknown entities/boundaries and explain the gap; do not force all frames into
one segment or call an unresolved entity an absent character. This output is model evidence,
not human verification. Do not optimize the observations to satisfy a search query.
"""


def provider_temporal_identity() -> RefinementIdentity:
    return RefinementIdentity(
        PROMPT_VERSION,
        hashlib.sha256(PROMPT.encode()).hexdigest(),
        REFINEMENT_TEMPORAL_SCHEMA_VERSION,
        "deepseek",
        "deepseek-flash",
    )


def temporal_refinement_settings() -> RefinementSettings:
    """Explicit new profile settings; historical profiles retain their original default."""
    return RefinementSettings(max_output_tokens=4096)


def parse_temporal_detail(content: str, request: DetailRefinementRequest) -> CandidateDetail:
    if request.identity != provider_temporal_identity() or request.base_prompt_hash is None:
        raise ValueError("Unsupported temporal refinement identity.")
    if type(content) is not str or len(content.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError("Invalid or oversized temporal response.")
    scene = scene_from_model(_json(content), request.evidence)
    projection = project_temporal_scene(scene)
    return CandidateDetail(
        request.run_id,
        request.event_id.split(":")[1],
        request.event_id,
        request.candidate_id,
        request.event_fingerprint,
        request.media_sha256,
        request.configuration_hash,
        request.pipeline_version,
        request.base_prompt_version,
        request.base_prompt_hash,
        request.identity.prompt_hash,
        request.source_range,
        request.evidence,
        projection.shots,
        projection.notes,
        schema_version=DETAIL_TEMPORAL_SCHEMA_VERSION,
        temporal_scene=scene,
    )


class DeepSeekDetailTemporalProvider(DeepSeekDetailRefinementProvider):
    """Preserve one HTTP attempt and usage on failure; augment only the new profile input."""

    _prompt = PROMPT
    _identity = staticmethod(provider_temporal_identity)
    _parse = staticmethod(parse_temporal_detail)

    def _payload(self, request: DetailRefinementRequest) -> dict[str, object]:
        if request.base_prompt_hash is None:
            raise ValueError("Temporal evidence requires its base prompt identity.")
        payload = super()._payload(request)
        messages = cast(list[dict[str, object]], payload["messages"])
        blocks = cast(list[dict[str, object]], messages[1]["content"])
        previous = None
        for index, item in enumerate(request.evidence):
            source_us = item.source_time.time_us
            blocks[2 * index]["text"] = json.dumps(
                {
                    "frameIndex": index,
                    "evidenceId": item.evidence_id,
                    "sourceUs": source_us,
                    "deltaFromPreviousUs": None if previous is None else source_us - previous,
                },
                sort_keys=True,
            )
            previous = source_us
        blocks.insert(
            0,
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "sequenceVersion": "registered-frame-sequence-v1",
                        "frameCount": len(request.evidence),
                        "candidateInterval": {
                            "startUs": request.source_range.start_us,
                            "endUs": request.source_range.end_us,
                            "durationUs": request.source_range.duration_us,
                        },
                    },
                    sort_keys=True,
                ),
            },
        )
        return payload
