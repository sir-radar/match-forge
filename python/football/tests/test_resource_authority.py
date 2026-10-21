from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from football.canonical_resources.resolution import CanonicalBinding, CanonicalResolutionError
from football.providers.resource_authority import (
    AuthorityError,
    ResourceAuthority,
    prepare_authority,
)
from football.providers.resource_capabilities import ResourceScope

NOW = datetime(2026, 10, 18, tzinfo=UTC)
SCOPE = ResourceScope(
    provider="fotmob", resource_type="results", competition="47", season="2025/2026"
)


def authority() -> ResourceAuthority:
    return ResourceAuthority(
        authority_id=UUID(int=100),
        scope=SCOPE,
        effective_from=NOW,
        effective_to=None,
        authority_tier="reviewed-result-source",
        qualification_state="QUALIFIED",
    )


def test_authority_decision_preserves_exact_scope_interval_and_qualification(
    tmp_path: Path,
) -> None:
    item = authority()
    publication = prepare_authority(
        tmp_path,
        item,
        decided_at=NOW - timedelta(days=1),
        reason="Reviewed retained results",
        evidence_refs=("qualification-report",),
    )
    assert publication.decision.effective_at == NOW
    assert publication.decision.decided_at < publication.decision.effective_at
    assert publication.decision.disposition == "QUALIFIED"
    evidence = publication.decision.evidence["authority"]
    assert isinstance(evidence, Mapping)
    scope = evidence["scope"]
    assert isinstance(scope, Mapping)
    assert scope["competition"] == "47"
    assert (
        publication.decision.from_bytes(publication.artifact.path.read_bytes())
        == publication.decision
    )


@pytest.mark.parametrize(
    "change",
    [
        {"effective_from": NOW.replace(tzinfo=None)},
        {"effective_from": None},
        {"effective_to": NOW.replace(tzinfo=None)},
        {"effective_to": NOW},
        {"effective_to": NOW - timedelta(seconds=1)},
        {"authority_tier": " "},
        {"qualification_state": ""},
    ],
)
def test_invalid_authority_intervals_and_labels_are_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(AuthorityError):
        replace(authority(), **change)


def test_authority_never_substitutes_for_identity_evidence(tmp_path: Path) -> None:
    item = authority()
    publication = prepare_authority(
        tmp_path,
        item,
        decided_at=NOW,
        reason="Resource authority only",
        evidence_refs=("qualification-report",),
    )
    with pytest.raises(CanonicalResolutionError, match="identity"):
        CanonicalBinding("/fixture", item.authority_id, publication.decision)


def test_tiers_and_qualification_states_are_owner_labels_without_a_global_ranking(
    tmp_path: Path,
) -> None:
    item = replace(
        authority(), authority_tier="fixture-review-only", qualification_state="REVIEW_REQUIRED"
    )
    publication = prepare_authority(
        tmp_path,
        item,
        decided_at=NOW,
        reason="Qualification still under review",
        evidence_refs=("pending-report",),
    )
    assert publication.decision.disposition == "REVIEW_REQUIRED"
    evidence = publication.decision.evidence["authority"]
    assert isinstance(evidence, Mapping)
    assert evidence["authority_tier"] == "fixture-review-only"
