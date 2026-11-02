"""Source-side statistics remain unresolved until independently bound to teams."""

from __future__ import annotations

from typing import Any

from football.providers.native.flashscore import FlashscoreStatistic, feed_records
from football.providers.native.reader import native_record
from football.providers.normalization.common import ObservationCollector
from football.providers.normalization.measurements import (
    TEAM_METRICS,
    add_measurement,
    emit_team_statistics,
    measurement,
)

_METRICS = {
    **TEAM_METRICS,
    "cornerkicks": "corners",
    "ballpossession": "possession",
    "expectedgoalsxg": "expected_goals",
    "xgontargetxgot": "expected_goals_on_target",
    "goalkeepersaves": "saves",
    "throwins": "throw_ins",
    "goalkicks": "goal_kicks",
    "hitthewoodwork": "woodwork",
    "tackles": "tackles",
}
_PERIODS = {"Match": "FULL_MATCH", "1st Half": "FIRST_HALF", "2nd Half": "SECOND_HALF"}


def statistics(output: ObservationCollector, payload: object) -> None:
    if not isinstance(payload, bytes):
        raise ValueError("Flashscore statistics requires original feed bytes")
    rows = feed_records(payload.decode("utf-8"), {*FlashscoreStatistic.__annotations__, "SE", "SF"})
    if not any("SE" in row for row in rows) or not any("SD" in row for row in rows):
        raise ValueError("Flashscore statistics feed has no period or named measurement")
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    blocked: dict[tuple[str, str], set[str]] = {}
    period: str | None = None
    output.finding(
        "TEAM_ID_UNRESOLVED",
        "feed:statistics",
        "Feed has home/away values without native team IDs; source sides remain unresolved",
        severity="WARNING",
    )
    for index, row in enumerate(rows):
        path = f"feed:statistics/{index}"
        with output.record(path):
            if "SE" in row:
                period = _PERIODS.get(row["SE"])
                if period is None:
                    output.finding(
                        "PERIOD_UNKNOWN",
                        path,
                        "Unmapped Flashscore statistics tab",
                        evidence={"source_value": row["SE"]},
                    )
            elif "SD" in row:
                if period is None:
                    raise ValueError("Statistic requires a mapped source period")
                _statistic(
                    output, native_record(FlashscoreStatistic, row), period, path, grouped, blocked
                )
    for (period, side), values in grouped.items():
        emit_team_statistics(
            output,
            "feed:statistics/" + side + "/" + period,
            output.context.reference(None, "feed:statistics/" + side),
            period,
            values,
        )


def _statistic(
    output: ObservationCollector,
    row: FlashscoreStatistic,
    period: str,
    path: str,
    grouped: dict[tuple[str, str], dict[str, Any]],
    blocked: dict[tuple[str, str], set[str]],
) -> None:
    for side, raw in (("home", row.get("SH")), ("away", row.get("SI"))):
        key = (period, side)
        values = grouped.setdefault(key, {})
        denied = blocked.setdefault(key, set())
        field = path + "/" + side
        if raw is not None and "/" in raw:
            output.finding(
                "STATISTIC_VALUE_UNQUALIFIED",
                field,
                "Source fraction does not establish the named count definition",
                severity="WARNING",
                evidence={"source_key": row["SG"], "source_value": raw},
            )
            continue
        parsed = measurement(output, row["SG"], raw, field, _METRICS)
        add_measurement(output, values, denied, parsed, field)
