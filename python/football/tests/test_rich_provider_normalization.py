from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from football.contracts.observations import ObservationProvenance, ObservationTime
from football.contracts.observations_v3 import ObservationVersionsV3
from football.providers.normalization.common import NormalizationContext, NormalizationResult
from football.providers.normalization.pipeline import normalize_resource


def normalize_csv(
    row: str, header: str = "HTHG,HTAG,HTR,FTHG,FTAG,FTR,Referee"
) -> NormalizationResult:
    raw = f"Div,HomeTeam,AwayTeam,{header}\nE0,Home,Away,{row}\n".encode()
    source = UUID("794637be-a42e-4f7b-a06c-869bf010a4bf")
    now = datetime(2026, 10, 16, 12, tzinfo=UTC)
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "football_data_uk", None, source, source, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=now, acquired_at=now, known_at=now),
        resource_key="sample.csv",
    )
    result = normalize_resource(context, "statistics", raw)
    assert result == normalize_resource(context, "statistics", raw)
    return result


def test_csv_retains_zero_half_time_scores_and_referee_without_name_identity() -> None:
    result = normalize_csv("0,0,D,1,0,H,A Referee")
    assert not result.findings
    score, referee = (json.loads(item.to_bytes()) for item in result.observations)
    assert score["period"] == "FIRST_HALF"
    assert score["score_basis"] == "REGULATION_90"
    assert score["period_complete"] is True
    assert score["home_goals"] == score["away_goals"] == 0
    assert referee["name"] == "A Referee"
    assert referee["referee"]["provider_native_id"] is None
    assert referee["referee"]["canonical_id"] is None
    for item in result.observations:
        assert isinstance(item.versions, ObservationVersionsV3)
        assert item.versions.observation_contract_version == "3"
        assert item.versions.normalizer_version == "football_data_uk-statistics-v2"
        assert item.versions.semantic_version is None
        assert item.provenance.source_record_key


def test_csv_missing_values_do_not_become_zero_or_final_period() -> None:
    assert not normalize_csv(",,,,,,").observations
    result = normalize_csv("1,0,H,,,,")
    assert not result.findings
    assert len(result.observations) == 1
    assert result.observations[0].to_dict()["period_complete"] is None


@pytest.mark.parametrize(
    "row",
    ["0,,D,1,0,H,", "0,0,H,1,0,H,", "2,0,H,1,0,H,", "0,0,D,1,,H,", "-1,0,A,1,0,H,"],
)
def test_csv_invalid_half_time_scores_are_reported_without_fabricated_periods(row: str) -> None:
    result = normalize_csv(row)
    assert not result.observations
    assert any(item.rule_code == "MF_NORM_SOURCE_RECORD_INVALID" for item in result.findings)


def test_csv_bad_half_time_does_not_remove_valid_team_statistics_or_referee() -> None:
    result = normalize_csv(
        "2,0,H,1,0,H,A Referee,4,0",
        "HTHG,HTAG,HTR,FTHG,FTAG,FTR,Referee,HS,AS",
    )
    assert [item.CONTRACT for item in result.observations] == [
        "TeamStatisticObservationV2",
        "TeamStatisticObservationV2",
        "RefereeObservationV3",
    ]
    assert result.observations[1].to_dict()["total_shots"] == 0
