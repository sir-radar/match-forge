from __future__ import annotations

from datetime import UTC, datetime

from football.providers.football_data_uk_resolution import (
    FootballDataUkTeamCrosswalkRegistryV1,
    FootballDataUkTeamCrosswalkV1,
    resolve_football_data_uk_team,
)


def test_reviewed_team_crosswalk_creates_append_only_approved_resolution() -> None:
    registry = FootballDataUkTeamCrosswalkRegistryV1(
        (
            FootballDataUkTeamCrosswalkV1(
                provider_team_label="Man United",
                canonical_team_id="canonical-team-1",
                evidence_refs=("review/team-crosswalk/man-united",),
                version="FootballDataUkStatsBombTeamCrosswalkV1",
            ),
        )
    )

    result = resolve_football_data_uk_team(
        provider_team_label="Man United",
        candidate_canonical_ids=("canonical-team-1",),
        registry=registry,
        source_evidence_ref="football_data_uk/mmz4281/1516/E0.csv/sha256/abc",
        decision_id="team-resolution-1",
        created_at=datetime(2026, 9, 4, 14, 15, tzinfo=UTC),
    )

    assert result.status == "RESOLVED"
    assert result.selected_canonical_team_id == "canonical-team-1"
    assert result.decision is not None
    assert result.decision.status == "MANUALLY_APPROVED"
    assert result.decision.provider_id == "football_data_uk"


def test_unreviewed_ambiguous_team_never_auto_merges() -> None:
    result = resolve_football_data_uk_team(
        provider_team_label="United",
        candidate_canonical_ids=("canonical-team-1", "canonical-team-2"),
        registry=FootballDataUkTeamCrosswalkRegistryV1(()),
        source_evidence_ref="football_data_uk/mmz4281/1516/E0.csv/sha256/abc",
        decision_id="team-resolution-ambiguous",
        created_at=datetime(2026, 9, 4, 14, 15, tzinfo=UTC),
    )

    assert result.status == "REVIEW_REQUIRED"
    assert result.selected_canonical_team_id is None
    assert result.decision is not None
    assert result.decision.status == "REVIEW_REQUIRED"
