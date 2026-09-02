from __future__ import annotations

import pytest
from football.ingestion import (
    EventStreamReconciliationError,
    EventStreamReconciliationV1,
    ProviderEventStreamV1,
)


def test_event_streams_preserve_provider_order_and_authoritative_selection() -> None:
    statsbomb = _stream("statsbomb_open_data", ("sb-1", "sb-2"))
    streams = EventStreamReconciliationV1("match-1", (statsbomb,))

    assert streams.authoritative_events("statsbomb_open_data") == ("sb-1", "sb-2")
    assert streams.fused_events() == ("sb-1", "sb-2")


def test_event_streams_reject_implicit_cross_provider_fusion() -> None:
    streams = EventStreamReconciliationV1(
        "match-1",
        (_stream("statsbomb_open_data", ("sb-1",)), _stream("other_provider", ("op-1",))),
    )

    with pytest.raises(EventStreamReconciliationError, match="alignment contract"):
        streams.fused_events()


def test_event_streams_validate_order_and_duplicate_providers() -> None:
    with pytest.raises(EventStreamReconciliationError, match="source order"):
        ProviderEventStreamV1("provider", "resource:1", ("e1", "e2"), (2, 1))
    with pytest.raises(EventStreamReconciliationError, match="one stream per provider"):
        EventStreamReconciliationV1(
            "match-1", (_stream("provider", ("e1",)), _stream("provider", ("e2",)))
        )


def _stream(provider_id: str, events: tuple[str, ...]) -> ProviderEventStreamV1:
    return ProviderEventStreamV1(
        provider_id, f"resource:{provider_id}", events, tuple(range(len(events)))
    )
