"""Lossless, bounded invocation records for refinement attempts; no I/O."""

from dataclasses import asdict
from decimal import Decimal

from gamingcreator.application.detail_refinement import DetailRefinementRequest
from gamingcreator.application.providers import CostStatus, InvocationMetadata, ProviderUsage

ATTEMPT_SCHEMA_VERSION = "actor-detail-refinement-attempt-v2"


def metadata_payload(metadata: InvocationMetadata) -> dict[str, object]:
    value = asdict(metadata)
    usage = asdict(metadata.usage)
    for name in ("original_cost", "cost_cny"):
        amount = usage[name]
        usage[name] = None if amount is None else format(amount, "f")
    usage["cost_status"] = metadata.usage.cost_status.value
    value["usage"] = usage
    return value


def metadata_from_payload(value: object) -> InvocationMetadata:
    if type(value) is not dict or set(value) != set(InvocationMetadata.__dataclass_fields__):
        raise ValueError("Invalid invocation metadata fields.")
    raw = value["usage"]
    if type(raw) is not dict or set(raw) != set(ProviderUsage.__dataclass_fields__):
        raise ValueError("Invalid usage fields.")
    usage = dict(raw)
    for name in ("original_cost", "cost_cny"):
        amount = usage[name]
        if amount is not None and type(amount) is not str:
            raise ValueError("Cost must be a decimal string or unknown.")
        usage[name] = None if amount is None else Decimal(amount)
    usage["cost_status"] = CostStatus(usage["cost_status"])
    return InvocationMetadata(**{**value, "usage": ProviderUsage(**usage)})


def validate_metadata(metadata: InvocationMetadata, request: DetailRefinementRequest) -> None:
    identity = request.identity
    if (
        type(metadata) is not InvocationMetadata
        or metadata.provider != identity.provider
        or metadata.requested_model != identity.requested_model
        or metadata.prompt_version != identity.prompt_version
        or metadata.schema_version != identity.schema_version
        or type(metadata.attempt) is not int
        or metadata.attempt not in (0, 1)
        or type(metadata.usage) is not ProviderUsage
        or (
            metadata.elapsed_ms is not None
            and (type(metadata.elapsed_ms) is not int or metadata.elapsed_ms < 0)
        )
    ):
        raise ValueError("Invocation does not match the single-send refinement contract.")
    for name in (
        "provider",
        "requested_model",
        "actual_model",
        "model_revision",
        "prompt_version",
        "schema_version",
        "price_version",
        "request_id",
        "execution_details",
    ):
        value = getattr(metadata, name)
        maximum = 16_384 if name == "execution_details" else 256
        if value is not None and (type(value) is not str or not value or len(value) > maximum):
            raise ValueError("Invocation strings must be bounded identifiers or unknown.")
