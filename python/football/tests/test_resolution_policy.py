from __future__ import annotations

import pytest
from football.ingestion import DataResolutionPolicyV1, ResolutionPolicyError


def test_resolution_policy_is_field_scoped_and_canonical() -> None:
    policy = _policy()

    assert policy.to_dict()["field"] == "regulation_time_score"
    assert policy.source_precedence == ("statsbomb_open_data", "totalcorner_api")
    assert len(policy.sha256) == 64


def test_resolution_policy_rejects_global_or_ineligible_precedence() -> None:
    with pytest.raises(ResolutionPolicyError, match="ineligible"):
        _policy(source_precedence=("other_provider",))
    with pytest.raises(ResolutionPolicyError, match="must be unique"):
        _policy(eligible_providers=("statsbomb_open_data", "statsbomb_open_data"))


def test_resolution_policy_rejects_invalid_freshness_and_tolerance() -> None:
    with pytest.raises(ResolutionPolicyError, match="freshness"):
        _policy(freshness_window_seconds=0)
    with pytest.raises(ResolutionPolicyError, match="tolerance"):
        _policy(conflict_tolerance=-1.0)


def _policy(
    *,
    eligible_providers: tuple[str, ...] = ("statsbomb_open_data", "totalcorner_api"),
    source_precedence: tuple[str, ...] = ("statsbomb_open_data", "totalcorner_api"),
    freshness_window_seconds: int | None = 86_400,
    conflict_tolerance: float = 0.0,
) -> DataResolutionPolicyV1:
    return DataResolutionPolicyV1(
        policy_version="score-v1",
        domain="match",
        resource="match_observation",
        field="regulation_time_score",
        eligible_providers=eligible_providers,
        source_precedence=source_precedence,
        freshness_window_seconds=freshness_window_seconds,
        require_complete=True,
        required_validation_statuses=("passed", "warnings"),
        conflict_tolerance=conflict_tolerance,
        escalation="quarantine",
    )
