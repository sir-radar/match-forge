from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from football.ingestion import (
    ConflictRecordError,
    DataResolutionPolicyV1,
    EscalationActionV1,
    FieldObservationV1,
    reconcile_field_observations,
)


def test_reconciliation_marks_equal_statsbomb_and_football_data_scores_corrobated() -> None:
    result = reconcile_field_observations(
        _score_policy(),
        (
            FieldObservationV1(
                observation_ref="observation:statsbomb:score",
                provider_id="statsbomb_open_data",
                value=(2, 1),
                validation_status="passed",
            ),
            FieldObservationV1(
                observation_ref="observation:football-data:score",
                provider_id="football_data_uk",
                value=(2, 1),
                validation_status="passed",
            ),
        ),
        conflict_id="score-conflict-1",
        created_at=datetime(2026, 9, 4, 15, 0, tzinfo=UTC),
    )

    assert result.status == "CORROBORATED"
    assert result.conflict is None
    assert result.observation_refs == (
        "observation:statsbomb:score",
        "observation:football-data:score",
    )


def test_reconciliation_quarantines_conflicting_scores_without_auto_selecting_statsbomb() -> None:
    result = reconcile_field_observations(
        _score_policy(),
        (
            FieldObservationV1(
                observation_ref="observation:statsbomb:score",
                provider_id="statsbomb_open_data",
                value=(2, 1),
                validation_status="passed",
            ),
            FieldObservationV1(
                observation_ref="observation:football-data:score",
                provider_id="football_data_uk",
                value=(2, 2),
                validation_status="passed",
            ),
        ),
        conflict_id="score-conflict-2",
        created_at=datetime(2026, 9, 4, 15, 0, tzinfo=UTC),
    )

    assert result.status == "QUARANTINED"
    assert result.conflict is not None
    assert result.conflict.disposition == "QUARANTINED"
    assert result.conflict.selected_observation_ref is None


def test_reconciliation_uses_review_escalation_without_selecting_a_conflict_winner() -> None:
    result = reconcile_field_observations(
        _score_policy(escalation="review"),
        (
            FieldObservationV1(
                observation_ref="observation:statsbomb:score",
                provider_id="statsbomb_open_data",
                value=(2, 1),
                validation_status="passed",
            ),
            FieldObservationV1(
                observation_ref="observation:football-data:score",
                provider_id="football_data_uk",
                value=(2, 2),
                validation_status="passed",
            ),
        ),
        conflict_id="score-conflict-3",
        created_at=datetime(2026, 9, 4, 15, 0, tzinfo=UTC),
    )

    assert result.status == "REVIEW_REQUIRED"
    assert result.conflict is not None
    assert result.conflict.disposition == "REVIEW_REQUIRED"
    assert result.conflict.selected_observation_ref is None


def test_reconciliation_rejects_ineligible_provider_before_comparison() -> None:
    with pytest.raises(ConflictRecordError, match="ineligible"):
        reconcile_field_observations(
            _score_policy(),
            (
                FieldObservationV1(
                    observation_ref="observation:statsbomb:score",
                    provider_id="statsbomb_open_data",
                    value=(2, 1),
                    validation_status="passed",
                ),
                FieldObservationV1(
                    observation_ref="observation:unapproved:score",
                    provider_id="unapproved_source",
                    value=(2, 1),
                    validation_status="passed",
                ),
            ),
            conflict_id="score-conflict-4",
            created_at=datetime(2026, 9, 4, 15, 0, tzinfo=UTC),
        )


def _score_policy(*, escalation: str = "quarantine") -> DataResolutionPolicyV1:
    return DataResolutionPolicyV1(
        policy_version="FootballDataUkPhase1BScoreReconciliationV1",
        domain="match",
        resource="match_result",
        field="regulation_time_score",
        eligible_providers=("statsbomb_open_data", "football_data_uk"),
        source_precedence=("statsbomb_open_data", "football_data_uk"),
        freshness_window_seconds=None,
        require_complete=True,
        required_validation_statuses=("passed",),
        conflict_tolerance=0.0,
        escalation=cast(EscalationActionV1, escalation),
    )
