from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from football.ingestion.fixture_persistence import F3FixtureSourceV1
from football.providers.football_data_uk_f3 import (
    FootballDataUkF3ResolutionContextV1,
    process_football_data_uk_f3_fixture,
)
from football.providers.football_data_uk_match_resolution import (
    FootballDataUkCanonicalMatchCandidateV1,
)
from football.providers.football_data_uk_resolution import (
    FootballDataUkTeamCrosswalkRegistryV1,
    FootballDataUkTeamCrosswalkV1,
)

_FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "tests/fixtures/football_data_uk/phase1b"
_HOME_TEAM_ID = "00000000-0000-0000-0000-000000000101"
_AWAY_TEAM_ID = "00000000-0000-0000-0000-000000000102"
_MATCH_ID = "00000000-0000-0000-0000-000000000103"


def test_f3_quarantines_then_reprocesses_the_same_valid_fixture() -> None:
    source, payload = _source()
    initial = process_football_data_uk_f3_fixture(
        source=source,
        payload=payload,
        context=_context(home_candidates=()),
        crosswalks=_crosswalks(include_home=False),
        processed_at=_time(),
    )
    reviewed = process_football_data_uk_f3_fixture(
        source=source,
        payload=payload,
        context=_context(home_candidates=(_HOME_TEAM_ID,)),
        crosswalks=_crosswalks(include_home=True),
        processed_at=_time(),
    )

    assert initial.status == "quarantined"
    assert initial.quarantine_reason == "IDENTITY_UNRESOLVED"
    assert initial.home_team_resolution.decision is None
    assert reviewed.status == "ready_to_publish"
    assert reviewed.source is source
    assert reviewed.normalized_match.source_resource_identity == source.resource_identity
    assert reviewed.home_team_resolution.decision is not None
    assert reviewed.home_team_resolution.decision.provider_entity_id.startswith("fixture://")
    assert reviewed.match_resolution is not None
    assert reviewed.match_resolution.selected_canonical_match_id == _MATCH_ID


def _source() -> tuple[F3FixtureSourceV1, bytes]:
    payload = (_FIXTURE_ROOT / "f3_ambiguous_identity_v1.csv").read_bytes()
    manifest_payload = (_FIXTURE_ROOT / "f3_ambiguous_identity_v1.json").read_bytes()
    return (
        F3FixtureSourceV1.from_payload(
            payload=payload,
            acquired_at=_time(),
            manifest_path="fixtures/football_data_uk/phase1b/f3_ambiguous_identity_v1.json",
            manifest_payload=manifest_payload,
        ),
        payload,
    )


def _context(home_candidates: tuple[str, ...]) -> FootballDataUkF3ResolutionContextV1:
    return FootballDataUkF3ResolutionContextV1(
        canonical_competition_id="00000000-0000-0000-0000-000000000104",
        canonical_season_id="00000000-0000-0000-0000-000000000105",
        home_team_candidates=home_candidates,
        away_team_candidates=(_AWAY_TEAM_ID,),
        match_candidates=(
            FootballDataUkCanonicalMatchCandidateV1(
                canonical_match_id=_MATCH_ID,
                provider_match_date=date(2015, 8, 8),
            ),
        ),
    )


def _crosswalks(include_home: bool) -> FootballDataUkTeamCrosswalkRegistryV1:
    entries = [
        FootballDataUkTeamCrosswalkV1(
            provider_team_label="Arsenal",
            canonical_team_id=_AWAY_TEAM_ID,
            evidence_refs=("fixture-test-away",),
            version="FootballDataUkStatsBombTeamCrosswalkV1",
        )
    ]
    if include_home:
        entries.append(
            FootballDataUkTeamCrosswalkV1(
                provider_team_label="F3 Ambiguous Team",
                canonical_team_id=_HOME_TEAM_ID,
                evidence_refs=("fixture-review-home",),
                version="FootballDataUkStatsBombTeamCrosswalkV1",
            )
        )
    return FootballDataUkTeamCrosswalkRegistryV1(tuple(entries))


def _time() -> datetime:
    return datetime(2026, 9, 5, 12, tzinfo=UTC)
