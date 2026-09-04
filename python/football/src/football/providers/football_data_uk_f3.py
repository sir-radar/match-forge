from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from football.ingestion.fixture_persistence import F3FixtureSourceV1
from football.normalization import (
    FootballDataUkNormalizedMatchV1,
    normalize_football_data_uk_record,
)
from football.providers.football_data_uk_csv import parse_football_data_uk_csv
from football.providers.football_data_uk_match_resolution import (
    FootballDataUkCanonicalMatchCandidateV1,
    FootballDataUkMatchResolutionContextV1,
    FootballDataUkMatchResolutionV1,
    resolve_football_data_uk_match,
)
from football.providers.football_data_uk_resolution import (
    FootballDataUkTeamCrosswalkRegistryV1,
    FootballDataUkTeamResolutionV1,
    resolve_football_data_uk_team,
)

F3FixtureProcessingStatusV1 = Literal["quarantined", "ready_to_publish"]


class FootballDataUkF3Error(ValueError):
    """The frozen F3 acceptance fixture cannot follow its approved route."""


@dataclass(frozen=True, slots=True)
class FootballDataUkF3ResolutionContextV1:
    canonical_competition_id: str
    canonical_season_id: str
    home_team_candidates: tuple[str, ...]
    away_team_candidates: tuple[str, ...]
    match_candidates: tuple[FootballDataUkCanonicalMatchCandidateV1, ...]

    def __post_init__(self) -> None:
        if not self.canonical_competition_id or not self.canonical_season_id:
            raise FootballDataUkF3Error("fixture competition and season mappings are required")


@dataclass(frozen=True, slots=True)
class FootballDataUkF3ProcessingResultV1:
    status: F3FixtureProcessingStatusV1
    source: F3FixtureSourceV1
    normalized_match: FootballDataUkNormalizedMatchV1
    home_team_resolution: FootballDataUkTeamResolutionV1
    away_team_resolution: FootballDataUkTeamResolutionV1
    match_resolution: FootballDataUkMatchResolutionV1 | None
    quarantine_reason: str | None


def process_football_data_uk_f3_fixture(
    *,
    source: F3FixtureSourceV1,
    payload: bytes,
    context: FootballDataUkF3ResolutionContextV1,
    crosswalks: FootballDataUkTeamCrosswalkRegistryV1,
    processed_at: datetime,
) -> FootballDataUkF3ProcessingResultV1:
    """Run the frozen fixture through the normal parser and no-guess mappings."""

    if processed_at.tzinfo is None:
        raise FootballDataUkF3Error("fixture processing time must be timezone-aware")
    parsed = parse_football_data_uk_csv(source, payload)
    if parsed.schema.status == "quarantine" or len(parsed.records) != 1:
        raise FootballDataUkF3Error("F3 fixture must remain one schema-compatible CSV record")
    normalized = normalize_football_data_uk_record(source, parsed.records[0])
    home = _team_resolution(
        source,
        normalized.provider_home_team_name,
        context.home_team_candidates,
        crosswalks,
        processed_at,
    )
    away = _team_resolution(
        source,
        normalized.provider_away_team_name,
        context.away_team_candidates,
        crosswalks,
        processed_at,
    )
    if home.status != "RESOLVED" or away.status != "RESOLVED":
        return FootballDataUkF3ProcessingResultV1(
            status="quarantined",
            source=source,
            normalized_match=normalized,
            home_team_resolution=home,
            away_team_resolution=away,
            match_resolution=None,
            quarantine_reason="IDENTITY_UNRESOLVED",
        )
    match = resolve_football_data_uk_match(
        FootballDataUkMatchResolutionContextV1(
            provider_match_ref=normalized.provider_match_ref,
            canonical_competition_id=context.canonical_competition_id,
            canonical_season_id=context.canonical_season_id,
            canonical_home_team_id=home.selected_canonical_team_id or "",
            canonical_away_team_id=away.selected_canonical_team_id or "",
            provider_match_date=normalized.provider_match_date,
            evidence_refs=(source.resource_identity,),
        ),
        context.match_candidates,
        decision_id=f"{source.fixture_id}:match:review-v1",
        created_at=processed_at,
    )
    if match.status != "RESOLVED":
        return FootballDataUkF3ProcessingResultV1(
            status="quarantined",
            source=source,
            normalized_match=normalized,
            home_team_resolution=home,
            away_team_resolution=away,
            match_resolution=match,
            quarantine_reason="MATCH_UNRESOLVED",
        )
    return FootballDataUkF3ProcessingResultV1(
        status="ready_to_publish",
        source=source,
        normalized_match=normalized,
        home_team_resolution=home,
        away_team_resolution=away,
        match_resolution=match,
        quarantine_reason=None,
    )


def _team_resolution(
    source: F3FixtureSourceV1,
    label: str,
    candidates: tuple[str, ...],
    crosswalks: FootballDataUkTeamCrosswalkRegistryV1,
    processed_at: datetime,
) -> FootballDataUkTeamResolutionV1:
    resolution = resolve_football_data_uk_team(
        provider_team_label=label,
        candidate_canonical_ids=candidates,
        registry=crosswalks,
        source_evidence_ref=source.resource_identity,
        decision_id=f"{source.fixture_id}:team:{label}:review-v1",
        created_at=processed_at,
    )
    if resolution.decision is None:
        return resolution
    decision = replace(
        resolution.decision,
        provider_entity_id=f"{source.fixture_locator}#team={label}",
    )
    return replace(resolution, decision=decision)
