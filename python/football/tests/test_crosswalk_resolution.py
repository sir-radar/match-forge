from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from football.product.crosswalk_resolution import (
    CompetitionMetadata,
    Confidence,
    Decision,
    MappingRecord,
    ProviderEvidence,
    apply_high_confidence_resolutions,
    classify_competition,
    classify_team,
)

NOW = datetime(2026, 10, 3, tzinfo=UTC)
ENTITY_ID = UUID("10000000-0000-4000-8000-000000000001")
SNAPSHOT_ID = UUID("20000000-0000-4000-8000-000000000001")


def mapping(
    provider: str,
    provider_id: str,
    *,
    alias: str | None = None,
    country: str | None = "England",
    method: str = "deterministic",
) -> MappingRecord:
    suffix = len(provider) + len(provider_id)
    return MappingRecord(
        UUID(f"30000000-0000-4000-8000-{suffix:012d}"),
        ENTITY_ID,
        UUID(f"40000000-0000-4000-8000-{suffix:012d}"),
        provider,
        provider_id,
        method,
        SNAPSHOT_ID,
        NOW,
        NOW,
        alias,
        country,
    )


def provider_evidence(*fixtures: str) -> ProviderEvidence:
    return ProviderEvidence(
        frozenset({"competition-1"}),
        frozenset({"competition-1:2026"}),
        frozenset(fixtures),
    )


def test_competition_crosswalk_is_high_confidence() -> None:
    mappings = [mapping("api_football", "39"), mapping("openfootball", "en.1")]

    result = classify_competition(
        mappings,
        CompetitionMetadata("Premier League", "England", 1, "LEAGUE", "2026", 20, 380),
    )

    assert result.decision is Decision.SAME_ENTITY
    assert result.confidence is Confidence.HIGH
    assert "openfootball:en.1->api_football:39" in result.evidence_ref


def test_team_exact_alias_country_and_competition_is_high_confidence() -> None:
    mappings = [
        mapping("api_football", "33", alias="manchester united"),
        mapping("football_data_uk", "Man United", alias="manchester united"),
    ]
    evidence = {
        (ENTITY_ID, "api_football"): provider_evidence("fixture-a"),
        (ENTITY_ID, "football_data_uk"): provider_evidence("fixture-b"),
    }

    result = classify_team(mappings, evidence, {"competition-1"})

    assert result.decision is Decision.SAME_ENTITY
    assert result.confidence is Confidence.HIGH


def test_team_fixture_overlap_confirms_different_aliases() -> None:
    mappings = [
        mapping("api_football", "33", alias="man united"),
        mapping("football_data_uk", "Man Utd", alias="manchester united"),
    ]
    evidence = {
        (ENTITY_ID, "api_football"): provider_evidence("fixture-a", "fixture-b"),
        (ENTITY_ID, "football_data_uk"): provider_evidence("fixture-a", "fixture-b"),
    }

    result = classify_team(mappings, evidence, {"competition-1"})

    assert result.decision is Decision.SAME_ENTITY
    assert result.confidence is Confidence.HIGH


def test_team_likely_alias_without_fixture_overlap_requires_review() -> None:
    mappings = [
        mapping("api_football", "33", alias="manchester united"),
        mapping("football_data_uk", "Man U", alias="manchester united club"),
    ]
    evidence = {
        (ENTITY_ID, "api_football"): provider_evidence("fixture-a"),
        (ENTITY_ID, "football_data_uk"): provider_evidence("fixture-b"),
    }

    result = classify_team(mappings, evidence, {"competition-1"})

    assert result.decision is Decision.SAME_ENTITY
    assert result.confidence is Confidence.MEDIUM


def test_team_conflicting_country_name_and_membership_is_different() -> None:
    mappings = [
        mapping("api_football", "1", alias="united", country="England"),
        mapping("openfootball", "United", alias="city", country="Scotland"),
    ]
    evidence = {
        (ENTITY_ID, "api_football"): ProviderEvidence(
            frozenset({"competition-1"}), frozenset(), frozenset({"fixture-a"})
        ),
        (ENTITY_ID, "openfootball"): ProviderEvidence(
            frozenset({"competition-2"}), frozenset(), frozenset({"fixture-b"})
        ),
    }

    result = classify_team(mappings, evidence, {"competition-1", "competition-2"})

    assert result.decision is Decision.DIFFERENT_ENTITIES
    assert result.confidence is Confidence.HIGH


def test_apply_rejects_high_confidence_split_before_mutation() -> None:
    resolution = classify_team(
        [
            mapping("api_football", "1", alias="united", country="England"),
            mapping("openfootball", "United", alias="city", country="Scotland"),
        ],
        {
            (ENTITY_ID, "api_football"): ProviderEvidence(
                frozenset({"competition-1"}), frozenset(), frozenset({"fixture-a"})
            ),
            (ENTITY_ID, "openfootball"): ProviderEvidence(
                frozenset({"competition-2"}), frozenset(), frozenset({"fixture-b"})
            ),
        },
        {"competition-1", "competition-2"},
    )

    with pytest.raises(ValueError, match="dependency-specific correction"):
        apply_high_confidence_resolutions(None, [resolution], NOW)  # type: ignore[arg-type]
