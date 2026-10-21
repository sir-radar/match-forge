from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from football.forecasting.contracts import GoalForecastPayloadV1, forecast_payload_sha256
from football.forecasting.publication import ForecastPublicationError, ImmutableForecastStore
from test_forecast_publication import PUBLISHED_AT, _forecast


def test_goal_payload_seals_caller_owned_score_sequences() -> None:
    labels = ["0", "1", "2+"]
    matrix = [[0.12, 0.10, 0.08], [0.11, 0.14, 0.10], [0.09, 0.12, 0.14]]
    goal = GoalForecastPayloadV1(
        lambda_home=1.4,
        lambda_away=1.0,
        score_labels=cast(Any, labels),
        score_probabilities=cast(Any, matrix),
        over_0_5=0.9,
        over_1_5=0.7,
        over_2_5=0.5,
        over_3_5=0.3,
        over_4_5=0.1,
        btts_yes=0.55,
        home_clean_sheet=0.35,
        away_clean_sheet=0.25,
    )
    base = _forecast()
    sealed = replace(
        base, goal=goal, payload_sha256=forecast_payload_sha256(base.match_result, goal=goal)
    )
    before = sealed.to_bytes()
    labels[-1] = "3+"
    matrix[0][0] = 0.99
    matrix.append([0.0, 0.0, 0.0])
    assert sealed.to_bytes() == before
    assert goal.score_labels == ("0", "1", "2+")
    assert isinstance(goal.score_probabilities, tuple)
    assert all(isinstance(row, tuple) for row in goal.score_probabilities)


def test_forecast_seals_caller_owned_artifact_references() -> None:
    base = _forecast()
    artifacts = list(base.model_artifact_ids)
    sealed = replace(base, model_artifact_ids=cast(Any, artifacts))
    before = sealed.to_bytes()
    artifacts.clear()
    assert sealed.to_bytes() == before
    assert sealed.model_artifact_ids == base.model_artifact_ids


@pytest.mark.parametrize("unexpected_payload", [b"{}", b'{"forecast_effect":true}'])
def test_mismatched_sealed_payload_never_creates_an_immutable_file(
    unexpected_payload: bytes, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import football.forecasting.publication as publication

    forecast = _forecast()
    store = ImmutableForecastStore(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(
            publication, "forecast_payload_bytes", lambda *args, **kwargs: unexpected_payload
        )
        with pytest.raises(ForecastPublicationError, match="checksum"):
            store.publish(forecast, PUBLISHED_AT)
    assert not list(tmp_path.rglob("*.json"))
    published = store.publish(forecast, PUBLISHED_AT)
    assert published.physical_sha256 == forecast.payload_sha256
    assert store.publish(forecast, PUBLISHED_AT).status == "verified_existing"


def test_forecast_seals_competition_rule_provenance() -> None:
    base = _forecast()
    source_refs = list(base.competition_rules.source_refs)
    rules = replace(base.competition_rules, source_refs=cast(Any, source_refs))
    sealed = replace(base, competition_rules=rules)
    before = sealed.to_bytes()
    source_refs.clear()
    assert sealed.to_bytes() == before
    assert sealed.competition_rules.source_refs == base.competition_rules.source_refs
