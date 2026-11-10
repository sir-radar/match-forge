"""Explicit period counts and referee labels; no derived second-half scores."""

from __future__ import annotations

from football.contracts.observations_v3 import PeriodScoreObservationV3, RefereeObservationV3
from football.providers.native.flashscore import FlashscoreSummary, feed_cells
from football.providers.native.reader import native_record
from football.providers.normalization.common import ObservationCollector, count, required_text


def summary(output: ObservationCollector, payload: object) -> None:
    if not isinstance(payload, bytes):
        raise ValueError("Flashscore summary requires original feed bytes")
    row, referees = _source_summary(payload)
    if row["AC"] != "3":
        raise ValueError("Summary period scores require the verified finished status")
    _scores(output, row)
    if len(referees) > 1:
        raise ValueError("Conflicting referee labels have no qualified shared role")
    if referees:
        output.emit(
            RefereeObservationV3,
            "feed:summary/REF",
            fixture=output.context.fixture(),
            referee=output.context.reference(None, "feed:summary/REF"),
            name=next(iter(referees)),
        )


def _source_summary(payload: bytes) -> tuple[FlashscoreSummary, set[str]]:
    fields: dict[str, str] = {}
    referees: set[str] = set()
    for cells in feed_cells(payload.decode("utf-8")):
        info = None
        for key, value in cells:
            if key in FlashscoreSummary.__annotations__:
                if key in fields:
                    raise ValueError("Duplicate native period-summary field")
                fields[key] = value
            elif key == "MIT":
                info = value
            elif key == "MIV" and info == "REF":
                referees.add(required_text(value))
    return native_record(FlashscoreSummary, fields), referees


def _scores(output: ObservationCollector, row: FlashscoreSummary) -> None:
    for period, home, away in (
        ("FIRST_HALF", row.get("BA"), row.get("BB")),
        ("SECOND_HALF", row.get("BC"), row.get("BD")),
    ):
        if home is None and away is None:
            continue
        if home is None or away is None:
            raise ValueError("Incomplete source period score pair")
        output.emit(
            PeriodScoreObservationV3,
            "feed:summary/" + period,
            fixture=output.context.fixture(),
            period=period,
            score_basis="UNKNOWN",
            home_goals=count(home),
            away_goals=count(away),
            period_complete=None,
        )
