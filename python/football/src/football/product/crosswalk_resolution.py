"""Evidence-based resolution of active cross-provider product identities."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from enum import StrEnum
from itertools import combinations
from pathlib import Path
from typing import Any, TextIO, cast
from uuid import UUID

import psycopg
from psycopg import Connection

from football.product.identity_audit import audit_report
from football.product.identity_crosswalks import COMPETITION_CROSSWALKS


class Decision(StrEnum):
    SAME_ENTITY = "SAME_ENTITY"
    DIFFERENT_ENTITIES = "DIFFERENT_ENTITIES"
    UNRESOLVED = "UNRESOLVED"


class Confidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True, slots=True)
class MappingRecord:
    mapping_id: UUID
    entity_id: UUID
    provider_id: UUID
    provider_code: str
    provider_entity_id: str
    mapping_method: str
    source_snapshot_id: UUID
    first_seen_at: datetime
    last_seen_at: datetime
    alias: str | None = None
    country: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderEvidence:
    competitions: frozenset[str]
    competition_seasons: frozenset[str]
    fixtures: frozenset[str]


@dataclass(frozen=True, slots=True)
class Resolution:
    entity_type: str
    entity_id: UUID
    decision: Decision
    confidence: Confidence
    target_group: str
    evidence_ref: str
    reason: str
    mappings: tuple[MappingRecord, ...]


@dataclass(frozen=True, slots=True)
class CompetitionMetadata:
    name: str
    country: str
    division: int | None
    competition_type: str
    season: str
    known_teams: int
    fixtures: int


def resolve_crosswalks(connection: Connection[Any]) -> list[Resolution]:
    competition_mappings, metadata = _competition_groups(connection)
    competition_resolutions = [
        classify_competition(mappings, metadata[entity_id])
        for entity_id, mappings in competition_mappings.items()
    ]
    confirmed_competitions = {
        str(item.entity_id)
        for item in competition_resolutions
        if item.decision is Decision.SAME_ENTITY and item.confidence is Confidence.HIGH
    }
    team_mappings = _team_groups(connection)
    team_evidence = _team_provider_evidence(connection)
    team_resolutions = [
        classify_team(mappings, team_evidence, confirmed_competitions)
        for mappings in team_mappings.values()
    ]
    return sorted(
        [*competition_resolutions, *team_resolutions],
        key=lambda item: (item.entity_type, str(item.entity_id)),
    )


def classify_competition(
    mappings: Sequence[MappingRecord], metadata: CompetitionMetadata
) -> Resolution:
    mapping_keys = {(item.provider_code, item.provider_entity_id) for item in mappings}
    links: list[str] = []
    missing: list[str] = []
    contradictions: list[str] = []
    for mapping in mappings:
        if mapping.provider_code == "api_football":
            continue
        target = COMPETITION_CROSSWALKS.get(mapping.provider_code, {}).get(
            mapping.provider_entity_id
        )
        source = f"{mapping.provider_code}:{mapping.provider_entity_id}"
        if target is None:
            missing.append(source)
        elif target not in mapping_keys:
            contradictions.append(f"{source}->{target[0]}:{target[1]}")
        else:
            links.append(f"{source}->{target[0]}:{target[1]}")

    common = (
        f"country={metadata.country};division={metadata.division};type={metadata.competition_type};"
        f"season={metadata.season};known_teams={metadata.known_teams};fixtures={metadata.fixtures}"
    )
    entity_id = mappings[0].entity_id
    if contradictions:
        return Resolution(
            "competition",
            entity_id,
            Decision.DIFFERENT_ENTITIES,
            Confidence.HIGH,
            "",
            ";".join(sorted(contradictions)),
            f"Explicit provider-ID crosswalk contradicts current canonical group; {common}.",
            tuple(mappings),
        )
    if not missing and links:
        return Resolution(
            "competition",
            entity_id,
            Decision.SAME_ENTITY,
            Confidence.HIGH,
            str(entity_id),
            ";".join(sorted(links)),
            f"Provider-ID crosswalks form one API-Football-anchored group; {common}.",
            tuple(mappings),
        )
    return Resolution(
        "competition",
        entity_id,
        Decision.UNRESOLVED,
        Confidence.LOW,
        "",
        ";".join(sorted(missing)) or "missing_provider_crosswalk",
        f"No complete provider-ID crosswalk; {common}.",
        tuple(mappings),
    )


def classify_team(
    mappings: Sequence[MappingRecord],
    evidence: Mapping[tuple[UUID, str], ProviderEvidence],
    confirmed_competitions: set[str],
) -> Resolution:
    entity_id = mappings[0].entity_id
    aliases = [item.alias for item in mappings if item.alias]
    countries = {item.country.casefold() for item in mappings if item.country}
    provider_evidence = {
        item.provider_code: evidence.get(
            (entity_id, item.provider_code), ProviderEvidence(frozenset(), frozenset(), frozenset())
        )
        for item in mappings
    }
    pair_metrics = [
        _pair_metrics(left, right, provider_evidence, confirmed_competitions)
        for left, right in combinations(sorted(provider_evidence), 2)
    ]
    exact_alias = len(aliases) == len(mappings) and len(set(aliases)) == 1
    minimum_similarity = _minimum_similarity(aliases)
    all_have_history = all(item.fixtures for item in provider_evidence.values())
    all_share_competition = bool(pair_metrics) and all(item[0] > 0 for item in pair_metrics)
    all_share_fixtures = bool(pair_metrics) and all(item[2] >= 2 for item in pair_metrics)
    shared_fixtures = sum(item[2] for item in pair_metrics)
    shared_season_pairs = sum(item[1] > 0 for item in pair_metrics)
    minimum_common_competitions = min((item[0] for item in pair_metrics), default=0)
    evidence_ref = (
        "db:product_team_aliases;db:match_provider_mappings;"
        f"providers={'+'.join(sorted(provider_evidence))}"
    )
    reason = (
        f"normalized_aliases={len(set(aliases))};nonempty_countries={len(countries)};"
        f"min_common_competitions={minimum_common_competitions};"
        f"shared_fixture_links={shared_fixtures};shared_season_pairs={shared_season_pairs};"
        f"providers_with_history={sum(bool(item.fixtures) for item in provider_evidence.values())}"
    )

    if len(countries) > 1 and not all_share_competition and minimum_similarity < 0.5:
        return Resolution(
            "team",
            entity_id,
            Decision.DIFFERENT_ENTITIES,
            Confidence.HIGH,
            "",
            evidence_ref,
            f"Conflicting countries, names, and competition membership; {reason}.",
            tuple(mappings),
        )
    if len(countries) <= 1 and all_have_history and all_share_competition:
        if exact_alias or all_share_fixtures:
            return Resolution(
                "team",
                entity_id,
                Decision.SAME_ENTITY,
                Confidence.HIGH,
                str(entity_id),
                evidence_ref,
                f"Compatible alias, country, competition, and provider history evidence; {reason}.",
                tuple(mappings),
            )
        if minimum_similarity >= 0.75:
            return Resolution(
                "team",
                entity_id,
                Decision.SAME_ENTITY,
                Confidence.MEDIUM,
                str(entity_id),
                evidence_ref,
                f"Likely alias match with compatible competition evidence; {reason}.",
                tuple(mappings),
            )
    return Resolution(
        "team",
        entity_id,
        Decision.UNRESOLVED,
        Confidence.LOW,
        "",
        evidence_ref,
        f"Evidence is incomplete or contradictory; {reason}.",
        tuple(mappings),
    )


def apply_high_confidence_resolutions(
    connection: Connection[Any], resolutions: Sequence[Resolution], resolved_at: datetime
) -> int:
    unsupported = [
        item
        for item in resolutions
        if item.confidence is Confidence.HIGH and item.decision is Decision.DIFFERENT_ENTITIES
    ]
    if unsupported:
        raise ValueError("high-confidence splits require dependency-specific correction")
    revised = 0
    for resolution in resolutions:
        if resolution.confidence is not Confidence.HIGH:
            continue
        if resolution.decision is not Decision.SAME_ENTITY:
            continue
        for mapping in resolution.mappings:
            if mapping.mapping_method in {"explicit_crosswalk", "manual"}:
                continue
            _revise_mapping(connection, resolution.entity_type, mapping, resolved_at)
            revised += 1
    return revised


def write_review_csv(path: Path, resolutions: Sequence[Resolution]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        _write_review_rows(handle, resolutions)


def _write_review_rows(handle: TextIO, resolutions: Sequence[Resolution]) -> None:
    fields = (
        "entity_type",
        "current_matchforge_id",
        "provider_code",
        "provider_entity_id",
        "decision",
        "confidence",
        "target_group",
        "evidence_ref",
        "reason",
    )
    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for resolution in resolutions:
        for mapping in sorted(
            resolution.mappings, key=lambda item: (item.provider_code, item.provider_entity_id)
        ):
            writer.writerow(
                {
                    "entity_type": resolution.entity_type,
                    "current_matchforge_id": resolution.entity_id,
                    "provider_code": mapping.provider_code,
                    "provider_entity_id": mapping.provider_entity_id,
                    "decision": resolution.decision,
                    "confidence": resolution.confidence,
                    "target_group": resolution.target_group,
                    "evidence_ref": resolution.evidence_ref,
                    "reason": resolution.reason,
                }
            )


def write_summary(
    path: Path,
    resolutions: Sequence[Resolution],
    revised_mappings: int,
    post_apply_audit: Mapping[str, object] | None,
) -> None:
    counts = _resolution_counts(resolutions)
    mapping_count = sum(len(item.mappings) for item in resolutions)
    review = [item for item in resolutions if item.confidence is not Confidence.HIGH]
    lines = [
        "# Entity Crosswalk Summary",
        "",
        f"- Competitions automatically confirmed: {counts['competition_confirmed']}",
        f"- Competitions split: {counts['competition_split']}",
        f"- Competitions unresolved: {counts['competition_unresolved']}",
        f"- Teams automatically confirmed: {counts['team_confirmed']}",
        f"- Teams split: {counts['team_split']}",
        f"- Teams unresolved: {counts['team_unresolved']}",
        f"- Total provider mappings: {mapping_count}",
        f"- Mapping rows revised: {revised_mappings}",
        "- Affected fixtures/history from splits: 0",
        "- Forecast rebuild required: NO",
        "- Post-apply identity audit: "
        f"{post_apply_audit['status'] if post_apply_audit else 'NOT_RUN'}",
        "",
        "## Owner review",
        "",
    ]
    if review:
        lines.append(
            f"Owner review required: {sum(len(item.mappings) for item in review)} mappings"
        )
        for item in review:
            lines.append(
                f"- {item.entity_type} `{item.entity_id}`: {item.decision} / "
                f"{item.confidence} — {item.reason}"
            )
    else:
        lines.append("Owner review required: 0 mappings")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _competition_groups(
    connection: Connection[Any],
) -> tuple[dict[UUID, list[MappingRecord]], dict[UUID, CompetitionMetadata]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH cross_provider AS (
                SELECT competition_id
                FROM football.competition_provider_mappings
                WHERE valid_to IS NULL
                GROUP BY competition_id
                HAVING count(DISTINCT provider_id) > 1
            ), participants AS (
                SELECT competition_id, fixture_id, home_team_id AS team_id
                FROM football.product_team_match_history
                UNION
                SELECT competition_id, fixture_id, away_team_id
                FROM football.product_team_match_history
                UNION
                SELECT competition_id, fixture_id, home_team_id FROM football.product_fixtures
                UNION
                SELECT competition_id, fixture_id, away_team_id FROM football.product_fixtures
            ), stats AS (
                SELECT competition_id, count(DISTINCT team_id) AS teams,
                       count(DISTINCT fixture_id) AS fixtures
                FROM participants GROUP BY competition_id
            )
            SELECT mapping.id, mapping.competition_id, mapping.provider_id, provider.code,
                   mapping.provider_competition_id, mapping.mapping_method,
                   mapping.source_snapshot_id, mapping.first_seen_at, mapping.last_seen_at,
                   product.name, product.country, product.division,
                   product.competition_type, product.season_label,
                   coalesce(stats.teams, 0), coalesce(stats.fixtures, 0)
            FROM cross_provider candidate
            JOIN football.competition_provider_mappings mapping
              ON mapping.competition_id = candidate.competition_id AND mapping.valid_to IS NULL
            JOIN football.providers provider ON provider.id = mapping.provider_id
            JOIN football.product_competitions product
              ON product.competition_id = candidate.competition_id
            LEFT JOIN stats ON stats.competition_id = candidate.competition_id
            ORDER BY mapping.competition_id, provider.code, mapping.provider_competition_id
            """
        )
        rows = cursor.fetchall()
    groups: dict[UUID, list[MappingRecord]] = defaultdict(list)
    metadata: dict[UUID, CompetitionMetadata] = {}
    for row in rows:
        entity_id = cast(UUID, row[1])
        groups[entity_id].append(_mapping_record(row[:9]))
        metadata[entity_id] = CompetitionMetadata(
            str(row[9]),
            str(row[10]),
            row[11],
            str(row[12]),
            str(row[13]),
            int(row[14]),
            int(row[15]),
        )
    return dict(groups), metadata


def _team_groups(connection: Connection[Any]) -> dict[UUID, list[MappingRecord]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH cross_provider AS (
                SELECT team_id
                FROM football.team_provider_mappings
                WHERE valid_to IS NULL
                GROUP BY team_id
                HAVING count(DISTINCT provider_id) > 1
            )
            SELECT mapping.id, mapping.team_id, mapping.provider_id, provider.code,
                   mapping.provider_team_id, mapping.mapping_method,
                   mapping.source_snapshot_id, mapping.first_seen_at, mapping.last_seen_at,
                   alias.normalized_name, alias.country
            FROM cross_provider candidate
            JOIN football.team_provider_mappings mapping
              ON mapping.team_id = candidate.team_id AND mapping.valid_to IS NULL
            JOIN football.providers provider ON provider.id = mapping.provider_id
            LEFT JOIN football.product_team_aliases alias
              ON alias.team_id = mapping.team_id AND alias.provider_code = provider.code
             AND alias.provider_team_id = mapping.provider_team_id
            ORDER BY mapping.team_id, provider.code, mapping.provider_team_id
            """
        )
        rows = cursor.fetchall()
    groups: dict[UUID, list[MappingRecord]] = defaultdict(list)
    for row in rows:
        record = _mapping_record(row)
        groups[record.entity_id].append(record)
    return dict(groups)


def _team_provider_evidence(
    connection: Connection[Any],
) -> dict[tuple[UUID, str], ProviderEvidence]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH cross_provider AS (
                SELECT team_id
                FROM football.team_provider_mappings
                WHERE valid_to IS NULL
                GROUP BY team_id
                HAVING count(DISTINCT provider_id) > 1
            ), participants AS (
                SELECT fixture_id, competition_id, kickoff_at, home_team_id AS team_id
                FROM football.product_team_match_history
                UNION
                SELECT fixture_id, competition_id, kickoff_at, away_team_id
                FROM football.product_team_match_history
                UNION
                SELECT fixture_id, competition_id, kickoff_at, home_team_id
                FROM football.product_fixtures
                UNION
                SELECT fixture_id, competition_id, kickoff_at, away_team_id
                FROM football.product_fixtures
            )
            SELECT participant.team_id, provider.code,
                   array_agg(DISTINCT participant.competition_id::text),
                   array_agg(DISTINCT participant.competition_id::text || ':' ||
                       extract(year FROM participant.kickoff_at)::integer::text),
                   array_agg(DISTINCT participant.fixture_id::text)
            FROM participants participant
            JOIN cross_provider candidate ON candidate.team_id = participant.team_id
            JOIN football.match_provider_mappings mapping
              ON mapping.match_id = participant.fixture_id AND mapping.valid_to IS NULL
            JOIN football.providers provider ON provider.id = mapping.provider_id
            GROUP BY participant.team_id, provider.code
            """
        )
        rows = cursor.fetchall()
    return {
        (cast(UUID, row[0]), str(row[1])): ProviderEvidence(
            frozenset(row[2]), frozenset(row[3]), frozenset(row[4])
        )
        for row in rows
    }


def _mapping_record(row: Sequence[object]) -> MappingRecord:
    return MappingRecord(
        cast(UUID, row[0]),
        cast(UUID, row[1]),
        cast(UUID, row[2]),
        str(row[3]),
        str(row[4]),
        str(row[5]),
        cast(UUID, row[6]),
        cast(datetime, row[7]),
        cast(datetime, row[8]),
        str(row[9]) if len(row) > 9 and row[9] is not None else None,
        str(row[10]) if len(row) > 10 and row[10] is not None else None,
    )


def _pair_metrics(
    left: str,
    right: str,
    evidence: Mapping[str, ProviderEvidence],
    confirmed_competitions: set[str],
) -> tuple[int, int, int]:
    left_evidence = evidence[left]
    right_evidence = evidence[right]
    common_competitions = (
        left_evidence.competitions & right_evidence.competitions & confirmed_competitions
    )
    common_seasons = {
        item
        for item in left_evidence.competition_seasons & right_evidence.competition_seasons
        if item.rsplit(":", 1)[0] in confirmed_competitions
    }
    return (
        len(common_competitions),
        len(common_seasons),
        len(left_evidence.fixtures & right_evidence.fixtures),
    )


def _minimum_similarity(aliases: Sequence[str]) -> float:
    if len(aliases) < 2:
        return 0.0
    return min(
        SequenceMatcher(None, left, right).ratio() for left, right in combinations(aliases, 2)
    )


def _revise_mapping(
    connection: Connection[Any],
    entity_type: str,
    mapping: MappingRecord,
    resolved_at: datetime,
) -> None:
    table, identity_column, provider_identity_column = {
        "competition": (
            "football.competition_provider_mappings",
            "competition_id",
            "provider_competition_id",
        ),
        "team": ("football.team_provider_mappings", "team_id", "provider_team_id"),
    }[entity_type]
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table} SET valid_to = %s WHERE id = %s AND valid_to IS NULL",
            (resolved_at, mapping.mapping_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"mapping changed during resolution: {mapping.mapping_id}")
        cursor.execute(
            f"""
            INSERT INTO {table} (
                {identity_column}, provider_id, {provider_identity_column}, valid_from,
                valid_to, first_seen_at, last_seen_at, mapping_method,
                mapping_confidence, source_snapshot_id
            ) VALUES (%s, %s, %s, %s, NULL, %s, %s, 'explicit_crosswalk', 1.0, %s)
            """,
            (
                mapping.entity_id,
                mapping.provider_id,
                mapping.provider_entity_id,
                resolved_at,
                mapping.first_seen_at,
                mapping.last_seen_at,
                mapping.source_snapshot_id,
            ),
        )


def _resolution_counts(resolutions: Sequence[Resolution]) -> dict[str, int]:
    result: dict[str, int] = {}
    for entity_type in ("competition", "team"):
        scoped = [item for item in resolutions if item.entity_type == entity_type]
        result[f"{entity_type}_confirmed"] = sum(
            item.decision is Decision.SAME_ENTITY and item.confidence is Confidence.HIGH
            for item in scoped
        )
        result[f"{entity_type}_split"] = sum(
            item.decision is Decision.DIFFERENT_ENTITIES and item.confidence is Confidence.HIGH
            for item in scoped
        )
        result[f"{entity_type}_unresolved"] = sum(
            item.confidence is not Confidence.HIGH or item.decision is Decision.UNRESOLVED
            for item in scoped
        )
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--review-csv", type=Path, default=Path("docs/entity-crosswalk-review.csv"))
    parser.add_argument("--summary-md", type=Path, default=Path("docs/entity-crosswalk-summary.md"))
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    revised = 0
    post_apply_audit: Mapping[str, object] | None = None
    try:
        with psycopg.connect(args.database_url) as connection:
            resolutions = resolve_crosswalks(connection)
            if args.apply:
                revised = apply_high_confidence_resolutions(
                    connection, resolutions, datetime.now(UTC)
                )
                post_apply_audit = audit_report(connection)
    except (psycopg.Error, OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"contract": "EntityCrosswalkResolutionV1", "error": str(error)}))
        return 2
    write_review_csv(args.review_csv, resolutions)
    write_summary(args.summary_md, resolutions, revised, post_apply_audit)
    review_count = sum(
        len(item.mappings) for item in resolutions if item.confidence is not Confidence.HIGH
    )
    report = {
        "contract": "EntityCrosswalkResolutionV1",
        "status": "PASS" if review_count == 0 else "REVIEW_REQUIRED",
        "apply": args.apply,
        "groups": len(resolutions),
        "provider_mappings": sum(len(item.mappings) for item in resolutions),
        "mapping_rows_revised": revised,
        "owner_review_mapping_count": review_count,
        "post_apply_identity_audit": post_apply_audit["status"] if post_apply_audit else None,
    }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if review_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
