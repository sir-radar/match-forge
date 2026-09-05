from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
from football.contracts import ArtifactRetirementContractError, ArtifactRetirementEventV1


def test_artifact_retirement_event_is_machine_readable() -> None:
    event = _event()

    assert event.to_dict()["contract"] == "ArtifactRetirementEventV1"
    assert len(event.sha256) == 64


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("object_kind", "DATASET", "object kind"),
        ("retirement_scope", "OTHER", "scope"),
        ("reason", "OTHER", "reason"),
    ),
)
def test_artifact_retirement_event_rejects_unknown_values(
    field: str, value: str, message: str
) -> None:
    with pytest.raises(ArtifactRetirementContractError, match=message):
        replace(_event(), **{field: value})  # type: ignore[arg-type]


def _event() -> ArtifactRetirementEventV1:
    return ArtifactRetirementEventV1(
        retirement_event_id=UUID("10000000-0000-4000-8000-000000000001"),
        object_kind="FORECAST",
        object_id=UUID("20000000-0000-4000-8000-000000000001"),
        retirement_scope="TEST_ONLY_HARD_GATE_EXCLUSION",
        reason="SYNTHETIC_TEST_LINEAGE",
        evidence_reference="decision:APPROVE_APPEND_ONLY_TEST_LINEAGE_RETIREMENT",
        recorded_at=datetime(2026, 9, 5, 17, 0, tzinfo=UTC),
        code_commit_sha="a" * 40,
    )
