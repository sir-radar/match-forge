from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

import pytest
from football.contracts.observations import ObservationProvenance, ObservationTime
from football.providers.normalization.common import NormalizationContext, NormalizationResult
from football.providers.normalization.pipeline import normalize_resource


def normalize(rows: str) -> NormalizationResult:
    raw = ("Rank,Club,Country,Level,Elo,From,To\n" + rows).encode()
    now = datetime(2026, 11, 2, tzinfo=UTC)
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "clubelo", None, UUID(int=1), UUID(int=2), hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=now, acquired_at=now, known_at=now),
        resource_key="https://raw.githubusercontent.com/archive/sha/clubelo.csv",
    )
    return normalize_resource(context, "ratings_archive", raw)


def test_real_archive_shape_keeps_dates_names_and_acquisition_separate() -> None:
    result = normalize("1,Bayern,GER,1,2000.5,2026-08-31,2026-12-31\n")
    assert not result.findings
    ratings = [o for o in result.observations if o.CONTRACT == "TeamRatingObservationV3"]
    assert len(ratings) == 1
    row = ratings[0].to_dict()
    assert row["rating_date"] == "2026-08-31"
    assert row["rating"] == 2000.5
    team = row["team"]
    assert isinstance(team, dict)
    assert team["provider_native_id"] is None
    assert team["canonical_id"] is None
    assert ratings[0].time.event_time is None
    assert ratings[0].time.known_at == datetime(2026, 11, 2, tzinfo=UTC)
    assert result.observations[0].to_dict()["name"] == "Bayern"


@pytest.mark.parametrize("value", ["NaN", "inf", "", "invalid"])
def test_invalid_ratings_are_quarantined(value: str) -> None:
    result = normalize(f"1,Bayern,GER,1,{value},2026-08-31,2026-12-31\n")
    assert not result.observations
    assert result.findings


@pytest.mark.parametrize("start,end", [("2026-02-30", "2026-12-31"), ("2026-12-31", "2026-08-31")])
def test_invalid_dates_never_become_rating_observations(start: str, end: str) -> None:
    result = normalize(f"1,Bayern,GER,1,2000,{start},{end}\n")
    assert not result.observations
    assert result.findings


@pytest.mark.parametrize("row", ['1,"unterminated', "1,Bayern,GER,1,2000,2026-01-01\n"])
def test_malformed_csv_is_reported_without_observations(row: str) -> None:
    result = normalize(row)
    assert not result.observations
    assert result.findings
