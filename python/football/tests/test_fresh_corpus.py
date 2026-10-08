from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pytest
from football.forecasting.fresh_corpus import (
    ConfidenceClass,
    DuplicateFixtureError,
    FixtureIdentity,
    HistoryMembership,
    IdentityStatus,
    ProviderMapping,
    ProviderTeam,
    SourceFixture,
    apply_firewall,
    chronological_split,
    classify_targets,
    direct_provider_crosswalk,
    promotion_state,
    reconcile_by_fixture_participation,
    reconcile_source_fixtures,
    reject_real_fixture_duplicates,
    semantic_sha256,
    target_manifest_row,
)

KICKOFF = datetime(2024, 8, 10, 14, tzinfo=UTC)


def _retained(
    *,
    fixture_id: str = "canonical-fixture",
    kickoff: datetime = KICKOFF,
    home_id: str = "canonical-home",
    away_id: str = "canonical-away",
    home_name: str = "Home FC",
    away_name: str = "Away FC",
    country: str = "DE",
    competition: str = "Bundesliga",
    season: str = "2024/2025",
    provider: str = "football_data_uk",
    division: int | None = None,
) -> FixtureIdentity:
    return FixtureIdentity(
        fixture_id=fixture_id,
        kickoff_at=kickoff,
        competition_id="competition",
        competition_name=competition,
        country_code=country,
        season=season,
        home_team_id=home_id,
        away_team_id=away_id,
        home_team_name=home_name,
        away_team_name=away_name,
        source_provider=provider,
        source_fixture_id=f"source-{fixture_id}",
        source_snapshot_id="snapshot",
        division=division,
    )


def _source(
    *,
    kickoff: datetime = KICKOFF,
    home_id: str = "provider-home",
    away_id: str = "provider-away",
    home_name: str = "Home",
    away_name: str = "Away",
) -> SourceFixture:
    return SourceFixture(
        provider_fixture_id="provider-fixture",
        canonical_provider_fixture_id="provider-canonical-fixture",
        kickoff_at=kickoff,
        competition_name="Bundesliga",
        country_code="DE",
        season="2024/2025",
        home_provider_team_id=home_id,
        away_provider_team_id=away_id,
        home_team_name=home_name,
        away_team_name=away_name,
        source_snapshot_ref="snapshot-ref",
    )


def _teams() -> tuple[ProviderTeam, ProviderTeam]:
    return (
        ProviderTeam("provider-home", "Home", "DE", "Bundesliga", "2024/2025"),
        ProviderTeam("provider-away", "Away", "DE", "Bundesliga", "2024/2025"),
    )


def test_exact_provider_id_mapping_reuses_existing_mapping() -> None:
    row = direct_provider_crosswalk(
        ProviderMapping(
            mapping_id="mapping",
            provider_code="football_data_uk",
            provider_team_id="Home",
            provider_team_name="Home",
            canonical_team_id="canonical-home",
            canonical_team_name="Home FC",
            country_code="DE",
            source_snapshot_id="snapshot",
            first_seen_at=KICKOFF,
            last_seen_at=KICKOFF,
        )
    )
    assert row.status == IdentityStatus.VERIFIED
    assert row.confidence_class == ConfidenceClass.EXACT_PROVIDER_ID


def test_provider_lineage_and_strong_fixture_participation_mapping() -> None:
    rows = reconcile_by_fixture_participation(
        _teams(), (_source(),), (_retained(),), verified_at=KICKOFF.isoformat()
    )
    assert {row.source_team_id: row.canonical_team_id for row in rows} == {
        "provider-home": "canonical-home",
        "provider-away": "canonical-away",
    }
    assert all(row.confidence_class == ConfidenceClass.STRONG_MULTI_ATTRIBUTE for row in rows)
    fixtures = reconcile_source_fixtures((_source(),), (_retained(),), rows)
    assert fixtures == {"provider-canonical-fixture": "canonical-fixture"}


def test_name_only_candidate_is_rejected_without_fixture_lineage() -> None:
    rows = reconcile_by_fixture_participation(
        (ProviderTeam("provider-home", "Home FC", "DE", "Bundesliga", "2024/2025"),),
        (),
        (_retained(),),
        verified_at=KICKOFF.isoformat(),
    )
    assert rows[0].status == IdentityStatus.UNRESOLVED


def test_ambiguous_fixture_signature_is_not_auto_mapped() -> None:
    retained = (
        _retained(),
        _retained(
            fixture_id="other",
            home_id="other-home",
            away_id="other-away",
            home_name="Home FC",
            away_name="Away FC",
        ),
    )
    rows = reconcile_by_fixture_participation(
        _teams(), (_source(),), retained, verified_at=KICKOFF.isoformat()
    )
    assert all(row.status == IdentityStatus.AMBIGUOUS for row in rows)


@pytest.mark.parametrize(
    ("country", "competition"),
    (("FR", "Bundesliga"), ("DE", "2. Bundesliga")),
)
def test_wrong_country_or_competition_history_is_rejected(country: str, competition: str) -> None:
    rows = reconcile_by_fixture_participation(
        _teams(),
        (_source(),),
        (_retained(country=country, competition=competition),),
        verified_at=KICKOFF.isoformat(),
    )
    assert all(row.status == IdentityStatus.UNRESOLVED for row in rows)


def test_same_name_distinct_clubs_are_separated_by_fixture_history() -> None:
    later = KICKOFF + timedelta(days=7)
    retained = (
        _retained(),
        _retained(
            fixture_id="reserve-fixture",
            kickoff=later,
            home_id="reserve-home",
            away_id="reserve-away",
            home_name="Home FC",
            away_name="Away FC",
        ),
    )
    rows = reconcile_by_fixture_participation(
        _teams(), (_source(),), retained, verified_at=KICKOFF.isoformat()
    )
    assert {row.source_team_id: row.canonical_team_id for row in rows}[
        "provider-home"
    ] == "canonical-home"


def test_mapping_revision_is_immutable_and_changes_identity() -> None:
    original = direct_provider_crosswalk(
        ProviderMapping(
            "mapping",
            "provider",
            "team",
            "Team",
            "canonical-a",
            "Team",
            "DE",
            "snapshot",
            KICKOFF,
            KICKOFF,
        )
    )
    with pytest.raises(FrozenInstanceError):
        original.canonical_team_id = "canonical-b"  # type: ignore[misc]
    revised = direct_provider_crosswalk(
        ProviderMapping(
            "mapping",
            "provider",
            "team",
            "Team",
            "canonical-b",
            "Team",
            "DE",
            "snapshot",
            KICKOFF,
            KICKOFF,
        )
    )
    assert revised.crosswalk_id != original.crosswalk_id


def test_spent_and_protected_targets_are_rejected() -> None:
    fixtures = (_retained(fixture_id="spent"), _retained(fixture_id="fresh"))
    assert [row.fixture_id for row in apply_firewall(fixtures, frozenset({"spent"}))] == ["fresh"]


def test_duplicate_fixture_is_rejected() -> None:
    duplicate = replace(_retained(), fixture_id="second-id")
    with pytest.raises(DuplicateFixtureError):
        reject_real_fixture_duplicates((_retained(), duplicate))


def test_same_fixture_from_two_providers_is_not_counted_twice() -> None:
    duplicate = replace(_retained(), source_provider="other-provider")
    assert len(reject_real_fixture_duplicates((_retained(), duplicate))) == 1


def test_future_and_same_kickoff_history_are_excluded() -> None:
    fixture = _retained()
    history = {
        "canonical-home": (
            HistoryMembership("canonical-home", "competition", "2024/2025", 1, KICKOFF),
            HistoryMembership(
                "canonical-home",
                "competition",
                "2024/2025",
                1,
                KICKOFF + timedelta(days=1),
            ),
        )
    }
    target = classify_targets((fixture,), frozenset(), history, {})[0]
    assert target.home_history_state == "ZERO_HISTORY"


@pytest.mark.parametrize(
    ("fitted", "category"),
    (
        (frozenset({"canonical-home", "canonical-away"}), "NATIVE_FITTED"),
        (frozenset({"canonical-home"}), "COLD_START_AWAY"),
        (frozenset({"canonical-away"}), "COLD_START_HOME"),
        (frozenset(), "COLD_START_BOTH"),
    ),
)
def test_native_fitted_requires_both_artifact_ids(fitted: frozenset[str], category: str) -> None:
    target = classify_targets((_retained(),), fitted, {}, {})[0]
    assert target.target_category == category


def test_cold_start_history_state_is_classified() -> None:
    history = {
        "canonical-home": (
            HistoryMembership(
                "canonical-home", "other", "2023/2024", 2, KICKOFF - timedelta(days=1)
            ),
        )
    }
    target = classify_targets((_retained(),), frozenset(), history, {})[0]
    assert target.home_history_state == "TRANSFER_HISTORY"
    assert target.away_history_state == "ZERO_HISTORY"


def test_promotion_requires_qualified_previous_season_membership() -> None:
    history = (
        HistoryMembership("canonical-home", "lower", "2023/2024", 2, KICKOFF - timedelta(days=1)),
    )
    assert promotion_state("canonical-home", "2024/2025", 1, history) == "PROMOTED_TEAM"
    assert promotion_state("unknown", "2024/2025", 1, history) == "PROMOTION_STATUS_UNKNOWN"
    target = classify_targets(
        (_retained(division=1),), frozenset(), {"canonical-home": history}, {}
    )[0]
    assert target.home_promotion_state == "PROMOTED_TEAM"
    assert target.away_promotion_state == "PROMOTION_STATUS_UNKNOWN"


def test_chronological_split_is_stable_and_keeps_kickoff_batches() -> None:
    fixtures = tuple(
        _retained(
            fixture_id=f"fixture-{index}",
            kickoff=KICKOFF + timedelta(days=index // 2),
        )
        for index in range(20)
    )
    targets = classify_targets(fixtures, frozenset(), {}, {})
    first = chronological_split(targets)
    second = chronological_split(tuple(reversed(targets)))
    first_rows = [target_manifest_row(row) for row in first]
    second_rows = [target_manifest_row(row) for row in second]
    assert first_rows == second_rows
    by_kickoff: dict[str, set[str]] = {}
    for row in first_rows:
        by_kickoff.setdefault(str(row["kickoff_at"]), set()).add(str(row["split"]))
    assert all(len(splits) == 1 for splits in by_kickoff.values())
    assert semantic_sha256(first_rows) == semantic_sha256(second_rows)
