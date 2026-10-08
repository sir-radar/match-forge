"""Immutable semantic forecast revision contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID


class RevisionReason(StrEnum):
    INITIAL_FORECAST = "INITIAL_FORECAST"
    BASELINE_HISTORY_CHANGED = "BASELINE_HISTORY_CHANGED"
    MODEL_ARTIFACT_CHANGED = "MODEL_ARTIFACT_CHANGED"
    H2H_CONTEXT_CHANGED = "H2H_CONTEXT_CHANGED"
    INJURY_STATUS_CHANGED = "INJURY_STATUS_CHANGED"
    SUSPENSION_STATUS_CHANGED = "SUSPENSION_STATUS_CHANGED"
    PREDICTED_LINEUP_CHANGED = "PREDICTED_LINEUP_CHANGED"
    CONFIRMED_LINEUP_AVAILABLE = "CONFIRMED_LINEUP_AVAILABLE"
    MANAGER_CONTEXT_CHANGED = "MANAGER_CONTEXT_CHANGED"
    REST_CONTEXT_CHANGED = "REST_CONTEXT_CHANGED"
    FIXTURE_METADATA_CHANGED = "FIXTURE_METADATA_CHANGED"
    MANUAL_REFRESH = "MANUAL_REFRESH"


class ForecastHorizon(StrEnum):
    EARLY_GT_7D = "EARLY_GT_7D"
    SEVEN_DAYS = "7D"
    THREE_DAYS = "3D"
    TWENTY_FOUR_HOURS = "24H"
    SIX_HOURS = "6H"
    ONE_HOUR = "1H"
    FIFTEEN_MINUTES = "15M"
    CONFIRMED_LINEUP = "CONFIRMED_LINEUP"


@dataclass(frozen=True, slots=True)
class ForecastRevisionV1:
    forecast_id: UUID
    fixture_id: UUID
    issued_at: datetime
    football_cutoff: datetime
    knowledge_cutoff: datetime
    forecast_horizon: ForecastHorizon
    supersedes_forecast_id: UUID | None
    model_id: str
    artifact_sha256: str
    predictive_input_snapshot_sha256: str
    context_snapshot_sha256: str
    revision_reason_codes: tuple[RevisionReason, ...]
    new_information_ids: tuple[str, ...]
    probability_payload: dict[str, object]
    payload_sha256: str


def requires_forecast_revision(
    previous_predictive_sha256: str | None,
    predictive_sha256: str,
) -> bool:
    """Context hashes are deliberately absent: non-predictive updates do not revise forecasts."""
    return previous_predictive_sha256 != predictive_sha256


def classify_horizon(
    issued_at: datetime,
    kickoff_at: datetime,
    *,
    confirmed_lineup_consumed: bool = False,
) -> ForecastHorizon:
    if confirmed_lineup_consumed:
        return ForecastHorizon.CONFIRMED_LINEUP
    remaining = kickoff_at - issued_at
    if remaining > timedelta(days=7):
        return ForecastHorizon.EARLY_GT_7D
    if remaining > timedelta(days=3):
        return ForecastHorizon.SEVEN_DAYS
    if remaining > timedelta(hours=24):
        return ForecastHorizon.THREE_DAYS
    if remaining > timedelta(hours=6):
        return ForecastHorizon.TWENTY_FOUR_HOURS
    if remaining > timedelta(hours=1):
        return ForecastHorizon.SIX_HOURS
    if remaining > timedelta(minutes=15):
        return ForecastHorizon.ONE_HOUR
    return ForecastHorizon.FIFTEEN_MINUTES
