"""Retained ClubElo CSV ratings; archive lineage and anonymous clubs stay explicit."""

from __future__ import annotations

import csv
import io
from datetime import date

from football.contracts.observations_v2 import TeamObservationV2
from football.contracts.observations_v3 import TeamRatingObservationV3
from football.providers.normalization.common import ObservationCollector, number, required_text


def ratings_archive(output: ObservationCollector, payload: object) -> None:
    if not isinstance(payload, bytes):
        raise ValueError("ClubElo archive requires retained CSV bytes")
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")), strict=True)
    if reader.fieldnames != ["Rank", "Club", "Country", "Level", "Elo", "From", "To"]:
        raise ValueError("ClubElo archive header differs from the verified CSV schema")
    try:
        rows = list(reader)
    except csv.Error as error:
        raise ValueError("invalid ClubElo CSV") from error
    for index, row in enumerate(rows, 2):
        path = f"csv:row:{index}"
        with output.record(path):
            if None in row or any(value is None for value in row.values()):
                raise ValueError("ClubElo archive row differs from its header")
            start, end = date.fromisoformat(row["From"]), date.fromisoformat(row["To"])
            if end < start:
                raise ValueError("ClubElo source rating interval is reversed")
            value = number(row["Elo"])
            if value is None:
                raise ValueError("ClubElo rating is missing")
            name, country = required_text(row["Club"]), required_text(row["Country"])
            # Daily CSV labels can differ from URL slugs. A name is not a native
            # team ID or a MatchForge identity; retain the source-record reference.
            team = output.context.reference(None, path + "/Club")
            output.emit(TeamObservationV2, path + "/Club", team=team, name=name, country=country)
            output.emit(
                TeamRatingObservationV3,
                path,
                team=team,
                rating_date=start,
                rating=value,
                rating_system="ClubElo",
            )
