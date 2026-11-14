from datetime import UTC, datetime, timedelta

import pytest
from football.product.external_prediction_recovery import _evaluate, _evaluation

KICKOFF = datetime(2026, 10, 17, 14, tzinfo=UTC)


def row(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "kickoff_at": KICKOFF,
        "collected_at": KICKOFF - timedelta(hours=6),
        "date_status": "VERIFIED",
    }
    values.update(changes)
    return values


@pytest.mark.parametrize(
    ("changes", "reviewed", "decided_at", "expected"),
    [
        ({}, False, KICKOFF + timedelta(days=3), "PROSPECTIVE"),
        ({}, True, KICKOFF - timedelta(hours=1), "PROSPECTIVE"),
        ({}, True, KICKOFF + timedelta(hours=1), "RETROSPECTIVE"),
        ({"collected_at": KICKOFF + timedelta(minutes=1)}, False, None, "RETROSPECTIVE"),
        ({"date_status": "UNKNOWN"}, False, None, "RETROSPECTIVE"),
    ],
)
def test_prospective_only_for_pre_kickoff_captures_and_blind_associations(
    changes: dict[str, object], reviewed: bool, decided_at: datetime | None, expected: str
) -> None:
    assert _evaluation(row(**changes), "CONTEXTUAL_POLICY", reviewed, decided_at) == expected


def settlement_row(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "identity_conflict": False,
        "effective_match_status": "CONTEXTUAL",
        "identity_status": "VERIFIED",
        "native_fixture": False,
        "native_provider": None,
        "date_status": "NOT_APPLICABLE",
        "result_conflict": False,
        "market": "RESULT_1X2",
        "selection": "HOME_WIN",
        "fixture_status": "FINISHED",
        "home_score": 2,
        "away_score": 1,
        "score_basis": "REGULATION_90",
    }
    values.update(changes)
    return values


def test_contextual_match_settles_and_provisional_fixture_waits() -> None:
    assert _evaluate(settlement_row()) == ("WON", None)
    assert _evaluate(settlement_row(identity_status="PROVISIONAL")) == (
        "PENDING",
        "CONTEXTUAL_FIXTURE_PROVISIONAL",
    )
    assert _evaluate(settlement_row(identity_conflict=True)) == ("PENDING", "IDENTITY_CONFLICT")
    assert _evaluate(settlement_row(result_conflict=True)) == ("PENDING", "RESULT_CONFLICT")
    assert _evaluate(settlement_row(score_basis="UNKNOWN")) == (
        "PENDING",
        "QUALIFIED_SCORE_UNAVAILABLE",
    )
