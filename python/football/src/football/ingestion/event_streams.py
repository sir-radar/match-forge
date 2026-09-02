from __future__ import annotations

from dataclasses import dataclass


class EventStreamReconciliationError(ValueError):
    """Provider event streams cannot be fused under the current contract."""


@dataclass(frozen=True, slots=True)
class ProviderEventStreamV1:
    provider_id: str
    source_resource_ref: str
    event_refs: tuple[str, ...]
    source_order: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.provider_id or not self.source_resource_ref:
            raise EventStreamReconciliationError("event stream identity is required")
        if len(self.event_refs) != len(self.source_order):
            raise EventStreamReconciliationError("event references and source order must align")
        if len(self.event_refs) != len(set(self.event_refs)):
            raise EventStreamReconciliationError("event references must be unique")
        if any(
            left >= right
            for left, right in zip(self.source_order, self.source_order[1:], strict=False)
        ):
            raise EventStreamReconciliationError("provider event source order must be increasing")


@dataclass(frozen=True, slots=True)
class EventStreamReconciliationV1:
    canonical_match_id: str
    streams: tuple[ProviderEventStreamV1, ...]
    alignment_contract_version: str | None = None

    def __post_init__(self) -> None:
        if not self.canonical_match_id or not self.streams:
            raise EventStreamReconciliationError("match and event streams are required")
        providers = [stream.provider_id for stream in self.streams]
        if len(providers) != len(set(providers)):
            raise EventStreamReconciliationError("one stream per provider is required")
        if self.alignment_contract_version is not None and not self.alignment_contract_version:
            raise EventStreamReconciliationError("alignment contract version must not be empty")

    def authoritative_events(self, provider_id: str) -> tuple[str, ...]:
        for stream in self.streams:
            if stream.provider_id == provider_id:
                return stream.event_refs
        raise EventStreamReconciliationError(f"event stream provider is not present: {provider_id}")

    def fused_events(self) -> tuple[str, ...]:
        if len(self.streams) > 1 and self.alignment_contract_version is None:
            raise EventStreamReconciliationError(
                "cross-provider event fusion requires an approved alignment contract"
            )
        if len(self.streams) == 1:
            return self.streams[0].event_refs
        return tuple(event for stream in self.streams for event in stream.event_refs)
