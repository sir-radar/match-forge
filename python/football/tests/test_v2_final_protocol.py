from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from football.forecasting.replacement_holdout import (
    ChampionEligibility,
    ChampionEligibilityInput,
    CompetitionPriorPoissonV1,
    ReferenceStackV1,
    champion_eligibility,
)
from football.history.fixture_identity import (
    CanonicalHistoryRow,
    ProviderFixtureEvidence,
    audit_canonical_history,
)

from scripts.prepare_full_coverage_v2_final import (
    ROOT,
    _relevant_history_manifest,
    _verify_v1_2_spent,
)
from scripts.run_full_coverage_v2_final import (
    _competition_match,
    _historical,
    _history_counts,
    _prepare_before_reveal,
    _snapshot,
)
from scripts.run_full_coverage_v2_replacement_holdout import FrozenTarget

KICKOFF = datetime(2025, 8, 20, 15, tzinfo=UTC)
HOME = UUID(int=1)
AWAY = UUID(int=2)
THIRD = UUID(int=3)
COMPETITION = UUID(int=10)
SNAPSHOT = UUID(int=20)


def test_v1_2_spent_guard_matches_immutable_execution_state() -> None:
    _verify_v1_2_spent(ROOT)


def test_resolved_history_manifest_excludes_selected_real_fixtures() -> None:
    target = {
        "real_fixture_id": str(UUID(int=101)),
        "home_team": str(HOME),
        "away_team": str(AWAY),
        "competition_id": str(COMPETITION),
        "kickoff": KICKOFF.isoformat(),
    }
    metadata = (
        _metadata(UUID(int=101), KICKOFF - timedelta(days=1)),
        _metadata(UUID(int=102), KICKOFF - timedelta(days=2)),
    )
    manifest = _relevant_history_manifest(metadata, (target,))
    assert [row["real_fixture_id"] for row in manifest] == [str(UUID(int=102))]


def test_every_batch_forecast_is_sealed_before_outcome_access() -> None:
    events: list[str] = []
    batch = (_target(UUID(int=101)), _target(UUID(int=102)))

    def prepare(target: FrozenTarget) -> UUID:
        events.append(f"forecast:{target.fixture_id}")
        return target.fixture_id

    def reveal(targets: Sequence[FrozenTarget]) -> str:
        assert targets == batch
        events.append("outcomes")
        return "revealed"

    prepared, outcomes = _prepare_before_reveal(batch, prepare, reveal)
    assert prepared == (UUID(int=101), UUID(int=102))
    assert outcomes == "revealed"
    assert events == [
        "forecast:00000000-0000-0000-0000-000000000065",
        "forecast:00000000-0000-0000-0000-000000000066",
        "outcomes",
    ]


def test_resolved_history_drives_qualification_snapshot_elo_and_competition_prior() -> None:
    duplicate = _row(101, KICKOFF - timedelta(days=2), HOME, AWAY)
    alias = _row(102, KICKOFF - timedelta(days=2), HOME, AWAY, provider="provider_b")
    later = _row(103, KICKOFF - timedelta(days=1), HOME, THIRD)
    resolved = audit_canonical_history((duplicate, alias, later)).resolved_history
    target = _target(UUID(int=200), home=HOME, away=AWAY, home_count=2, away_count=1)
    source = {
        "real_fixture_id": str(UUID(int=200)),
        "source_evidence_sha256": "a" * 64,
    }

    first = _snapshot(target, tuple(_historical(row) for row in resolved), source)
    second = _snapshot(target, tuple(_historical(row) for row in resolved), source)
    qualification_counts = (
        sum(HOME in (row.home_team_id, row.away_team_id) for row in resolved),
        sum(AWAY in (row.home_team_id, row.away_team_id) for row in resolved),
    )
    eligibility = champion_eligibility(
        ChampionEligibilityInput(True, True, True, True, True, *qualification_counts)
    )
    reference = ReferenceStackV1().select(eligibility)
    prior_history = tuple(_competition_match(row) for row in resolved)
    prior_count = (
        CompetitionPriorPoissonV1(1.5, 1.1)
        .rates(
            competition_id=COMPETITION,
            kickoff_at=KICKOFF,
            history=prior_history,
        )
        .prior_match_count
    )

    assert len(resolved) == 2
    assert _history_counts(first, target) == qualification_counts == (2, 1)
    assert prior_count == sum(row.competition_id == COMPETITION for row in resolved) == 2
    assert eligibility.status is ChampionEligibility.INELIGIBLE
    assert reference.model_id == target.reference_model_id
    assert tuple(row.fixture_id for row in first.qualified_history) == tuple(
        row.real_fixture_id for row in resolved
    )
    assert first.sha256 == second.sha256


def _target(
    fixture_id: UUID,
    *,
    home: UUID = HOME,
    away: UUID = AWAY,
    home_count: int = 0,
    away_count: int = 0,
) -> FrozenTarget:
    eligibility = champion_eligibility(
        ChampionEligibilityInput(True, True, True, True, True, home_count, away_count)
    )
    reference = ReferenceStackV1().select(eligibility)
    return FrozenTarget(
        fixture_id=fixture_id,
        kickoff_at=KICKOFF,
        competition_id=COMPETITION,
        competition_name="League",
        season="2025/2026",
        home_team_id=home,
        away_team_id=away,
        home_prior_match_count=home_count,
        away_prior_match_count=away_count,
        champion_eligibility=eligibility.status.value,
        champion_ineligibility_reason=eligibility.reason.value if eligibility.reason else None,
        home_promoted=False,
        away_promoted=False,
        expected_route="COLD_START_BOTH",
        reference_model_id=reference.model_id,
        reference_mode=reference.mode.value,
    )


def _row(
    fixture: int,
    kickoff: datetime,
    home: UUID,
    away: UUID,
    *,
    provider: str = "provider_a",
) -> CanonicalHistoryRow:
    fixture_id = UUID(int=fixture)
    evidence = ProviderFixtureEvidence(
        provider,
        f"resource.csv#{fixture}",
        SNAPSHOT,
        "source",
        "revision",
        "resource.csv",
        "a" * 64,
        "league.1",
    )
    return CanonicalHistoryRow(
        fixture_id,
        kickoff,
        COMPETITION,
        "League",
        "Country",
        1,
        "2025/2026",
        home,
        away,
        "Home",
        "Away",
        2,
        1,
        None,
        None,
        provider,
        SNAPSHOT,
        "EXACT",
        (evidence,),
    )


def _metadata(real_fixture_id: UUID, kickoff: datetime) -> dict[str, object]:
    return {
        "real_fixture_id": str(real_fixture_id),
        "member_fixture_ids": [str(real_fixture_id)],
        "representative_fixture_id": str(real_fixture_id),
        "competition_id": str(COMPETITION),
        "kickoff_at": kickoff,
        "home_team_id": str(HOME),
        "away_team_id": str(AWAY),
        "resolution_status": "UNIQUE",
        "evidence_sha256": "a" * 64,
    }
