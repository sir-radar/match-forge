from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from football.forecasting.elo import EloConfig, EloMatch, TeamEloModel
from football.history.fixture_identity import (
    CanonicalHistoryRow,
    ProviderFixtureEvidence,
    ResolutionStatus,
    ResolvedHistoricalMatchV1,
    audit_canonical_history,
)

KICKOFF = datetime(2025, 8, 1, 15, tzinfo=UTC)
HOME = UUID(int=1)
AWAY = UUID(int=2)
THIRD = UUID(int=3)
COMPETITION = UUID(int=10)
OTHER_COMPETITION = UUID(int=11)
SNAPSHOT = UUID(int=20)


def _row(index: int = 1, **changes: object) -> CanonicalHistoryRow:
    provider = str(changes.pop("source_provider_code", "provider_a"))
    fixture_id = cast(UUID, changes.pop("fixture_id", UUID(int=100 + index)))
    competition_id = changes.get("competition_id", COMPETITION)
    evidence = ProviderFixtureEvidence(
        provider,
        str(changes.pop("provider_match_id", f"resource.csv#{index}")),
        SNAPSHOT,
        "source",
        "revision",
        str(changes.pop("provider_path", "resource.csv")),
        "a" * 64,
        "league.1" if competition_id == COMPETITION else "league.2",
    )
    base = CanonicalHistoryRow(
        fixture_id=fixture_id,
        kickoff_at=KICKOFF,
        competition_id=COMPETITION,
        competition_name="League",
        country="Country",
        division=1,
        season_label="2025/2026",
        home_team_id=HOME,
        away_team_id=AWAY,
        home_team_name="Home",
        away_team_name="Away",
        home_goals=2,
        away_goals=1,
        home_xg=None,
        away_xg=None,
        source_provider_code=provider,
        source_snapshot_id=SNAPSHOT,
        source_kickoff_precision="EXACT",
        provider_evidence=(evidence,),
    )
    return replace(base, **cast(Any, changes))


def test_same_fixture_id_database_duplicate_is_one_row_by_contract() -> None:
    audit = audit_canonical_history((_row(),))
    assert len(audit.resolved_history) == 1
    assert audit.identities[0].resolution_status is ResolutionStatus.UNIQUE


def test_exact_duplicate_from_independent_providers_contributes_once() -> None:
    first = _row()
    second = _row(
        2,
        source_provider_code="provider_b",
        provider_path="other.csv",
        fixture_id=UUID(int=102),
    )
    audit = audit_canonical_history((first, second))
    assert len(audit.resolved_history) == 1
    assert audit.identities[0].resolution_status is ResolutionStatus.DUPLICATE_RESOLVED
    assert len(audit.resolved_history[0].member_fixture_ids) == 2


def test_same_provider_match_id_for_two_fixture_ids_resolves_once() -> None:
    first = _row(provider_match_id="immutable-1")
    second = _row(2, fixture_id=UUID(int=102), provider_match_id="immutable-1")
    audit = audit_canonical_history((first, second))
    assert len(audit.resolved_history) == 1
    assert audit.identities[0].resolution_status is ResolutionStatus.DUPLICATE_RESOLVED


def test_competition_disagreement_is_quarantined_without_unique_support() -> None:
    audit = audit_canonical_history(
        (_row(), _row(2, fixture_id=UUID(int=102), competition_id=OTHER_COMPETITION))
    )
    assert not audit.resolved_history
    assert audit.identities[0].resolution_status is ResolutionStatus.AMBIGUOUS_QUARANTINED
    assert audit.counts["competition_identity_conflicts"] == 1


def test_conflicting_scores_are_quarantined() -> None:
    audit = audit_canonical_history((_row(), _row(2, fixture_id=UUID(int=102), home_goals=3)))
    assert not audit.resolved_history
    assert audit.identities[0].resolution_reason == "CONFLICTING_SCORE_FACTS"


def test_same_team_different_opponent_at_same_kickoff_is_quarantined() -> None:
    audit = audit_canonical_history(
        (_row(), _row(2, fixture_id=UUID(int=102), away_team_id=THIRD, away_team_name="Third"))
    )
    assert not audit.resolved_history
    assert {item.resolution_status for item in audit.identities} == {
        ResolutionStatus.IMPOSSIBLE_TEAM_SCHEDULE_QUARANTINED
    }


def test_reversed_home_away_at_same_kickoff_is_quarantined() -> None:
    audit = audit_canonical_history(
        (
            _row(),
            _row(
                2,
                fixture_id=UUID(int=102),
                home_team_id=AWAY,
                away_team_id=HOME,
                home_team_name="Away",
                away_team_name="Home",
            ),
        )
    )
    assert not audit.resolved_history
    assert audit.counts["team_double_booking_clusters"] == 2


def test_legitimate_sequential_matches_remain_admitted() -> None:
    audit = audit_canonical_history(
        (_row(), _row(2, fixture_id=UUID(int=102), kickoff_at=KICKOFF + timedelta(days=1)))
    )
    assert len(audit.resolved_history) == 2
    assert audit.unresolved_failures == 0


def test_openfootball_competition_conflict_never_reaches_elo_twice() -> None:
    first = _row(source_provider_code="openfootball", provider_path="2019-20/ru.1.json")
    second = _row(
        2,
        fixture_id=UUID(int=102),
        competition_id=OTHER_COMPETITION,
        source_provider_code="openfootball",
        provider_path="2019-20/ru.2.json",
    )
    audit = audit_canonical_history((first, second))
    assert len(audit.resolved_history) == 0
    assert audit.identities[0].resolution_status is ResolutionStatus.AMBIGUOUS_QUARANTINED


def test_resolved_duplicate_contributes_one_elo_update() -> None:
    audit = audit_canonical_history(
        (_row(), _row(2, source_provider_code="provider_b", fixture_id=UUID(int=102)))
    )
    run = TeamEloModel(EloConfig(model_version="resolved-history-test-v1")).rate(
        tuple(_elo(row) for row in audit.resolved_history)
    )
    assert len(run.matches) == 1


def test_ambiguous_duplicate_contributes_zero_elo_updates() -> None:
    audit = audit_canonical_history(
        (_row(), _row(2, fixture_id=UUID(int=102), competition_id=OTHER_COMPETITION))
    )
    run = TeamEloModel(EloConfig(model_version="resolved-history-test-v1")).rate(
        tuple(_elo(row) for row in audit.resolved_history)
    )
    assert run.matches == ()


def test_legitimate_sequential_resolved_matches_produce_two_elo_updates() -> None:
    audit = audit_canonical_history(
        (_row(), _row(2, fixture_id=UUID(int=102), kickoff_at=KICKOFF + timedelta(days=1)))
    )
    run = TeamEloModel(EloConfig(model_version="resolved-history-test-v1")).rate(
        tuple(_elo(row) for row in audit.resolved_history)
    )
    assert len(run.matches) == 2


def _elo(resolved: ResolvedHistoricalMatchV1) -> EloMatch:
    return EloMatch(
        match_id=resolved.real_fixture_id,
        competition_id=resolved.competition_id,
        kickoff_at=resolved.kickoff_at,
        home_team_id=resolved.home_team_id,
        away_team_id=resolved.away_team_id,
        home_score=resolved.home_goals,
        away_score=resolved.away_goals,
    )
