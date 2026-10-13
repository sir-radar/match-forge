import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from football.product.operational_provider_sync import OperationalProviderSync
from football.providers.pitchapi import PitchApiResponse


@pytest.mark.parametrize("corrupt", [False, True])
def test_legacy_identity_replay_checks_source_and_selects_only_missing_matches(
    tmp_path: Path, corrupt: bool
) -> None:
    raw = json.dumps(
        {
            "data": {
                "matches": [
                    {
                        "id": "m_Legacy",
                        "league": {"id": "l_Legacy", "name": "League"},
                        "home_team": {"id": "t_Home01", "name": "Home"},
                        "away_team": {"id": "t_Away01", "name": "Away"},
                        "time_utc": "2026-10-09T12:00:00Z",
                        "status": "finished",
                        "score_home": 1,
                        "score_away": 0,
                    }
                ]
            }
        }
    ).encode()
    (tmp_path / "snapshot.json").write_bytes(raw)
    snapshot = uuid4()
    connection = MagicMock()
    connection.execute.return_value.fetchall.return_value = [
        (
            snapshot,
            "snapshot.json",
            "0" * 64 if corrupt else hashlib.sha256(raw).hexdigest(),
            datetime(2026, 10, 10, tzinfo=UTC),
            ["m_Legacy"],
        )
    ]
    sync = OperationalProviderSync(connection, tmp_path, provider_code="pitchapi")
    sync._store_observation = MagicMock()  # type: ignore[method-assign]
    if corrupt:
        with pytest.raises(ValueError, match="checksum mismatch"):
            sync._restore_legacy_pitchapi_identity()
        sync._store_observation.assert_not_called()
    else:
        sync._restore_legacy_pitchapi_identity()
        row, stored_snapshot, canonical = sync._store_observation.call_args.args
        assert row.home_team_name == "Home"
        assert row.away_team_name == "Away"
        assert row.observed_at == datetime(2026, 10, 10, tzinfo=UTC)
        assert stored_snapshot == snapshot
        assert canonical is None


def test_live_date_sync_does_not_replay_bulk_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sync = OperationalProviderSync(MagicMock(), tmp_path, provider_code="pitchapi")
    replay = MagicMock(side_effect=AssertionError("live polling must not replay bulk history"))
    monkeypatch.setattr(sync, "reconcile_stored_observations", replay)
    monkeypatch.setattr(sync, "_record_response", MagicMock(return_value=uuid4()))
    diagnostics = MagicMock(return_value={})
    monkeypatch.setattr(sync, "_sync_diagnostics", diagnostics)
    monkeypatch.setattr(
        "football.product.operational_provider_sync.settle_external_predictions",
        lambda _connection, _now: 0,
    )
    response = PitchApiResponse(
        "/v1/date/2026-10-12",
        datetime(2026, 10, 12, tzinfo=UTC),
        "0" * 64,
        b"{}",
        {"matches": []},
    )
    result = sync.sync_pitchapi(
        MagicMock(matches_by_date=MagicMock(return_value=response)),
        date(2026, 10, 12),
        date(2026, 10, 12),
        details_limit=0,
        live_details_limit=0,
    )
    assert result["status"] == "COMPLETED"
    assert result["stored_observations_reconciled"] == 0
    assert diagnostics.call_args.args[1] == date(2026, 10, 12)
    replay.assert_not_called()
