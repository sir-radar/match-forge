from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from football.product.operational_provider_sync import OperationalProviderSync, SyncCounts
from football.providers.pitchapi import PitchApiFixture


@pytest.mark.parametrize("season_label", [None, "", "  ", "Unknown", " uNkNoWn "])
def test_provider_scoped_fixture_requires_a_known_season(
    tmp_path: Path, season_label: str | None
) -> None:
    connection = MagicMock()
    sync = OperationalProviderSync(connection, tmp_path, provider_code="pitchapi")
    sync._record_mapping_decision = MagicMock()  # type: ignore[method-assign]
    snapshot_id = uuid4()
    row = _fixture_observation()

    assert sync._create_provider_scoped_fixture(row, snapshot_id, season_label=season_label) is None

    connection.cursor.assert_not_called()
    sync._record_mapping_decision.assert_called_once()
    decision = sync._record_mapping_decision.call_args.args
    assert decision[2:5] == (None, "REVIEW_REQUIRED", "provider season label unavailable")
    assert decision[5]["reason_code"] == "PROVIDER_SEASON_UNAVAILABLE"
    assert decision[5]["season_label"] == season_label


def test_live_observation_without_season_is_retained_without_creating_fixture(
    tmp_path: Path,
) -> None:
    connection = MagicMock()
    sync = OperationalProviderSync(connection, tmp_path, provider_code="pitchapi")
    sync._load_geographic_scopes = MagicMock()  # type: ignore[method-assign]
    sync._resolve_fixture = MagicMock(return_value=None)  # type: ignore[method-assign]
    sync._record_mapping_decision = MagicMock()  # type: ignore[method-assign]
    sync._store_observation = MagicMock(return_value=True)  # type: ignore[method-assign]
    row = _fixture_observation()
    snapshot_id = uuid4()
    counts = SyncCounts()

    resolved = sync._ingest_observations([row], snapshot_id, counts)

    assert resolved == [(row, None)]
    sync._store_observation.assert_called_once_with(row, snapshot_id, None)
    assert counts.canonical_fixtures_created == 0
    assert counts.unmatched == 1
    assert counts.inserted == 1


def test_known_source_season_does_not_reuse_unknown_provisional_competition(
    tmp_path: Path,
) -> None:
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.side_effect = [
        None,
        ("Unknown", "PROVISIONAL", "Japan"),
    ]
    sync = OperationalProviderSync(connection, tmp_path, provider_code="pitchapi")
    sync._record_mapping_decision = MagicMock()  # type: ignore[method-assign]
    sync._load_geographic_scopes = MagicMock()  # type: ignore[method-assign]

    assert (
        sync._create_provider_scoped_fixture(_fixture_observation(), uuid4(), season_label="2026")
        is None
    )

    sync._load_geographic_scopes.assert_not_called()
    assert connection.cursor.return_value.__enter__.return_value.execute.call_count == 2
    decision = sync._record_mapping_decision.call_args.args
    assert decision[3:5] == (
        "REVIEW_REQUIRED",
        "provisional competition season conflicts with the source season",
    )
    assert decision[5]["reason_code"] == "PROVISIONAL_COMPETITION_SEASON_CONFLICT"


def _fixture_observation() -> PitchApiFixture:
    return PitchApiFixture(
        provider_match_id="m_ABC123",
        provider_competition_id="l_ABC123",
        provider_home_team_id="t_HOME01",
        provider_away_team_id="t_AWAY01",
        home_team_name="Home",
        away_team_name="Away",
        kickoff_at=datetime(2026, 10, 21, 12, tzinfo=UTC),
        status="SCHEDULED",
        provider_status="scheduled",
        home_score=None,
        away_score=None,
        minute=None,
        added_time=None,
        period=None,
        source_updated_at=None,
        observed_at=datetime(2026, 10, 21, 11, tzinfo=UTC),
        provider_competition_name="League",
    )
