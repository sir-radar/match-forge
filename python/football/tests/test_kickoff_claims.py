from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest
from football.forecasting.kickoff import KickoffClaimError, resolve_local_kickoff


def test_resolves_london_local_kickoff_with_pinned_summer_and_winter_rules() -> None:
    summer = resolve_local_kickoff(date(2015, 8, 8), time(15, 0))
    winter = resolve_local_kickoff(date(2015, 12, 26), time(15, 0))

    assert summer == datetime(2015, 8, 8, 14, 0, tzinfo=UTC)
    assert winter == datetime(2015, 12, 26, 15, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("match_date", "kick_off"),
    (
        (date(2016, 3, 27), time(1, 30)),
        (date(2015, 10, 25), time(1, 30)),
    ),
)
def test_rejects_nonexistent_or_ambiguous_london_local_kickoff(
    match_date: date, kick_off: time
) -> None:
    with pytest.raises(KickoffClaimError, match="not one unambiguous local instant"):
        resolve_local_kickoff(match_date, kick_off)
