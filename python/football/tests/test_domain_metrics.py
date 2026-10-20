import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from football.contracts.source import canonical_json_bytes
from football.observability.domain_metrics import feature_metrics, sample

NOW = datetime(2026, 10, 20, tzinfo=UTC)
COMPETITION = UUID(int=1)


def exported_feature() -> dict[str, Any]:
    from football.forecasting.features import FixtureFeatureSnapshotV1
    from football.forecasting.model_contracts import CompetitionContext
    from football.forecasting.snapshot import build_forecast_snapshot

    return FixtureFeatureSnapshotV1(
        build_forecast_snapshot(
            fixture_id=UUID(int=2),
            competition_id=COMPETITION,
            competition_context=CompetitionContext.LEAGUE,
            season_label="2026",
            kickoff_at=NOW,
            home_team_id=UUID(int=3),
            away_team_id=UUID(int=4),
            football_cutoff=NOW,
            knowledge_cutoff=NOW,
            knowledge_mode="bitemporal",
            history=(),
        )
    ).to_dict()


def feature_args() -> dict[str, Any]:
    return dict(
        competitions=(COMPETITION,),
        window_start=NOW - timedelta(days=1),
        window_end=NOW + timedelta(days=1),
        observed_at=NOW,
    )


def sealed(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest(), payload


def test_feature_missingness_uses_unique_bound_snapshots_and_fixed_families() -> None:
    payload = exported_feature()
    payload["travel"] = {"distance_km": 2.0}
    bound = sealed(payload)
    output = feature_metrics((bound, bound), **feature_args())
    assert "feature_snapshot_samples 1\n" in output
    assert 'feature_missingness{family="travel"} 0\n' in output
    assert 'feature_missingness{family="cards_context"} 1\n' in output
    assert "fixture_id" not in output and str(COMPETITION) not in output
    assert 'feature_missingness{family="quality"} NaN\n' in feature_metrics((), **feature_args())


@pytest.mark.parametrize(
    "change",
    [
        {"contract": "unknown"},
        {"feature_contract_version": "unknown"},
        {"knowledge_cutoff": (NOW + timedelta(seconds=1)).isoformat()},
        {"football_cutoff": NOW.replace(tzinfo=None).isoformat()},
        {"fixture": {"competition_id": str(UUID(int=2)), "kickoff_at": NOW.isoformat()}},
    ],
)
def test_unbound_future_or_out_of_scope_feature_exports_are_rejected(
    change: dict[str, Any],
) -> None:
    payload = {**exported_feature(), **change}
    with pytest.raises(ValueError, match="feature"):
        feature_metrics((sealed(payload),), **feature_args())


def test_changed_feature_export_cannot_use_the_old_hash() -> None:
    digest, payload = sealed(exported_feature())
    payload["quality"] = []
    with pytest.raises(ValueError, match="checksum"):
        feature_metrics(((digest, payload),), **feature_args())


def test_metric_samples_encode_unknown_and_reject_nonfinite_values() -> None:
    assert sample("unknown", None) == "unknown NaN\n"
    assert sample("ratio", 0.25, family="travel") == 'ratio{family="travel"} 0.25\n'
    with pytest.raises(ValueError, match="finite"):
        sample("bad", float("inf"))
