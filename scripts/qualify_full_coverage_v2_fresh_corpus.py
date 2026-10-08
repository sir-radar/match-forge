#!/usr/bin/env python3
"""Freeze the outcome-blind fresh corpus for full-coverage V2 re-evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import psycopg
from football.forecasting.fresh_corpus import (
    ArtifactIdentity,
    FixtureIdentity,
    HistoryMembership,
    IdentityStatus,
    ProviderMapping,
    ProviderTeam,
    QualifiedTarget,
    SourceFixture,
    TeamIdentityCrosswalk,
    apply_firewall,
    canonical_json_bytes,
    chronological_split,
    classify_targets,
    crosswalk_manifest_row,
    direct_provider_crosswalk,
    pitchapi_fixture_id,
    pitchapi_team_id,
    reconcile_by_fixture_participation,
    reconcile_source_fixtures,
    reject_real_fixture_duplicates,
    semantic_sha256,
    target_manifest_row,
)
from psycopg.rows import dict_row

PROTOCOL_ID = "MATCHFORGE_FULL_COVERAGE_V2_FRESH_CORPUS_QUALIFICATION_V1"
CORPUS_ID = "MATCHFORGE_FULL_COVERAGE_V2_FRESH_DEVELOPMENT_CORPUS_V1"
AUTHORIZATION_ID = "AUTHORIZE_FULL_COVERAGE_V2_FRESH_CORPUS_QUALIFICATION_V1"
ARTIFACT_NAMESPACE = (
    "UUIDv5(f5f4c644-05a4-4b79-b968-e765ed659da0, pitchapi:team:{provider_team_id})"
)
FIT_CUTOFF = datetime.fromisoformat("2022-05-14T13:35:00+00:00")
QUALIFICATION_AT = "2026-10-08T00:00:00+00:00"
V1_RESULT = Path(".local/pitchapi-snapshot-v1/RESULT.json")
V1_ROOT = Path(".local/pitchapi-snapshot-v1/primary")
DEVELOPMENT_RESULT = Path(".local/pitchapi-multi-domain-development-v1-r3/RESULT.json")
DEVELOPMENT_ROOT = Path(".local/pitchapi-multi-domain-development-v1-r3/primary")
SPENT_MANIFEST = Path("docs/evaluation/full-coverage-challengers-v2-spent-targets-v1.json")
V1_EVIDENCE = Path("docs/evidence/multimodel-challenger-evaluation-v1-2026-10-07.json")
SELECTED_DOMAINS = {
    "c1de05d8-7f00-5829-a3be-35c402560d10": (
        "Bundesliga",
        "football_data_uk",
    ),
    "4889a2d4-659a-5f5e-bbcb-81fc6538a6a0": (
        "England League One",
        "openfootball",
    ),
    "44881185-c4bf-5681-afa9-bd95914509c3": (
        "Liga MX",
        "openfootball",
    ),
}
PITCHAPI_SCOPES = (
    (V1_RESULT, V1_ROOT, "bundesliga_2021_22", "2021/2022"),
    (V1_RESULT, V1_ROOT, "bundesliga_2022_23", "2022/2023"),
    (V1_RESULT, V1_ROOT, "bundesliga_2023_24", "2023/2024"),
    (DEVELOPMENT_RESULT, DEVELOPMENT_ROOT, "bundesliga_2024_25", "2024/2025"),
    (DEVELOPMENT_RESULT, DEVELOPMENT_ROOT, "bundesliga_2025_26", "2025/2026"),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument(
        "--research-cutoff",
        default="2026-10-08T00:00:00+00:00",
        type=_timestamp,
    )
    parser.add_argument(
        "--crosswalk-output",
        default=Path("docs/evaluation/full-coverage-v2-team-identity-crosswalk-v1.json"),
        type=Path,
    )
    parser.add_argument(
        "--corpus-output",
        default=Path("docs/evaluation/full-coverage-v2-fresh-development-corpus-v1.json"),
        type=Path,
    )
    parser.add_argument(
        "--evidence-output",
        default=Path(
            "docs/evidence/full-coverage-v2-fresh-corpus-qualification-v1-2026-10-08.json"
        ),
        type=Path,
    )
    parser.add_argument(
        "--report-output",
        default=Path("docs/evidence/full-coverage-v2-fresh-corpus-qualification-v1-2026-10-08.md"),
        type=Path,
    )
    args = parser.parse_args()
    _verify_source(args.source_commit)
    result = qualify(
        args.database_url,
        source_commit=args.source_commit,
        research_cutoff=args.research_cutoff,
    )
    _write(args.crosswalk_output, cast(dict[str, object], result["crosswalk_manifest"]))
    if result["corpus_manifest"] is not None:
        _write(args.corpus_output, cast(dict[str, object], result["corpus_manifest"]))
    evidence = cast(dict[str, object], result["evidence"])
    _write(args.evidence_output, evidence)
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(_markdown(evidence), encoding="utf-8")


def qualify(
    database_url: str,
    *,
    source_commit: str,
    research_cutoff: datetime,
) -> dict[str, object]:
    spent = _json(SPENT_MANIFEST)
    artifact_models = _artifact_models()
    source_by_season = _load_pitchapi_scopes()
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        bundesliga = _load_retained_fixtures(
            connection,
            providers_by_competition={"c1de05d8-7f00-5829-a3be-35c402560d10": "football_data_uk"},
            earliest=datetime.fromisoformat("2021-07-01T00:00:00+00:00"),
            latest=research_cutoff,
        )
        source_crosswalk = _reconcile_pitchapi_seasons(source_by_season, bundesliga)
        artifact_report, fitted_canonical_ids = _artifact_identity_report(
            artifact_models,
            source_by_season["2021/2022"][0],
            source_crosswalk,
        )
        candidates = _load_retained_fixtures(
            connection,
            providers_by_competition={
                competition_id: provider
                for competition_id, (_, provider) in SELECTED_DOMAINS.items()
            },
            earliest=FIT_CUTOFF,
            latest=research_cutoff,
        )
        candidates = reject_real_fixture_duplicates(candidates)
        provider_fixture_crosswalk = _fixture_crosswalk(
            source_by_season, bundesliga, source_crosswalk
        )
        fixture_crosswalk_rows = _fixture_crosswalk_rows(
            source_by_season, bundesliga, source_crosswalk
        )
        forbidden = frozenset(cast(list[str], spent["unique_forbidden_target_ids"]))
        mapped_forbidden = frozenset(
            canonical_id
            for provider_id, canonical_id in provider_fixture_crosswalk.items()
            if provider_id in forbidden
        )
        protected_fixture_ids = forbidden | mapped_forbidden
        admitted = apply_firewall(candidates, protected_fixture_ids)
        team_sources = {
            (team_id, row.source_provider)
            for row in admitted
            for team_id in (row.home_team_id, row.away_team_id)
        }
        candidate_team_ids = frozenset(team_id for team_id, _ in team_sources)
        direct_mappings = _load_direct_mappings(connection, team_sources)
        _require_direct_mappings(team_sources, direct_mappings)
        history = _load_history(connection, candidate_team_ids, research_cutoff)
        retained_inventory = _retained_inventory(connection)
    direct_crosswalk = tuple(direct_provider_crosswalk(row) for row in direct_mappings)
    combined_crosswalk = tuple(
        sorted((*source_crosswalk, *direct_crosswalk), key=_crosswalk_sort_key)
    )
    crosswalk_manifest = _crosswalk_manifest(
        combined_crosswalk,
        fixture_crosswalk_rows,
        artifact_models,
        source_commit,
    )
    refs = {
        (row.source_provider, row.canonical_team_id): row.crosswalk_id
        for row in direct_crosswalk
        if row.status == IdentityStatus.VERIFIED
    }
    targets = classify_targets(admitted, fitted_canonical_ids, history, refs)
    split_targets = chronological_split(targets)
    qualification = _qualification(split_targets)
    disposition = _disposition(artifact_report, qualification)
    target_rows = [target_manifest_row(row) for row in split_targets]
    target_sha = semantic_sha256(target_rows)
    split_sha = semantic_sha256(
        [{"fixture_id": row["fixture_id"], "split": row["split"]} for row in target_rows]
    )
    firewall_sha = semantic_sha256(
        {
            "source_manifest_sha256": _file_sha(SPENT_MANIFEST),
            "forbidden_target_ids": sorted(forbidden),
        }
    )
    crosswalk_sha = semantic_sha256(crosswalk_manifest)
    corpus_manifest = None
    xg_coverage: dict[str, object] = {
        "status": "NOT_READ_CORPUS_NOT_QUALIFIED",
        "complete_fixture_count": 0,
        "missing_fixture_count": len(admitted),
    }
    if disposition == "FRESH_DEVELOPMENT_CORPUS_QUALIFIED":
        corpus_manifest = _corpus_manifest(
            target_rows,
            source_commit=source_commit,
            target_sha=target_sha,
            split_sha=split_sha,
            firewall_sha=firewall_sha,
            crosswalk_sha=crosswalk_sha,
            qualification=qualification,
        )
        # Outcomes are read only after target and split hashes have been frozen.
        xg_coverage = _xg_coverage(database_url, tuple(row.fixture_id for row in admitted))
    group_overlaps = _group_overlaps(spent, provider_fixture_crosswalk, admitted)
    evidence = _evidence(
        source_commit=source_commit,
        research_cutoff=research_cutoff,
        artifact_report=artifact_report,
        crosswalk=combined_crosswalk,
        fixture_crosswalk_count=len(fixture_crosswalk_rows),
        retained_inventory=retained_inventory,
        scoped_retained_rows_inspected=len(bundesliga) + len(candidates),
        forbidden=forbidden,
        firewall_sha=firewall_sha,
        candidates=candidates,
        admitted=admitted,
        protected_fixture_ids=protected_fixture_ids,
        group_overlaps=group_overlaps,
        qualification=qualification,
        crosswalk_sha=crosswalk_sha,
        target_sha=target_sha,
        split_sha=split_sha,
        corpus_manifest=corpus_manifest,
        xg_coverage=xg_coverage,
        disposition=disposition,
    )
    return {
        "crosswalk_manifest": crosswalk_manifest,
        "corpus_manifest": corpus_manifest,
        "evidence": evidence,
    }


def _load_pitchapi_scopes() -> dict[
    str, tuple[tuple[ProviderTeam, ...], tuple[SourceFixture, ...]]
]:
    result: dict[str, tuple[tuple[ProviderTeam, ...], tuple[SourceFixture, ...]]] = {}
    for result_path, root, scope_key, season in PITCHAPI_SCOPES:
        report = _json(result_path)
        snapshot_ref = cast(str, report.get("snapshot_manifest") or report.get("snapshot_document"))
        snapshot_path = root / snapshot_ref
        snapshot = _verified_json(snapshot_path, Path(snapshot_ref).stem)
        resource = next(
            row
            for row in cast(list[dict[str, object]], snapshot["resources"])
            if row["resource_ref"] == f"season:{scope_key}"
        )
        digest = str(resource["normalized_sha256"])
        payload = _verified_json(_hash_path(root, "normalized", digest), digest)
        matches = cast(list[dict[str, object]], cast(dict[str, object], payload["data"])["matches"])
        source_ref = f"{report['snapshot_sha256']}:{resource['raw_sha256']}"
        result[season] = _project_pitchapi_matches(matches, season, source_ref)
    return result


def _project_pitchapi_matches(
    matches: Sequence[Mapping[str, object]], season: str, source_ref: str
) -> tuple[tuple[ProviderTeam, ...], tuple[SourceFixture, ...]]:
    teams: dict[str, ProviderTeam] = {}
    fixtures: list[SourceFixture] = []
    for match in matches:
        home = cast(Mapping[str, object], match["home_team"])
        away = cast(Mapping[str, object], match["away_team"])
        for team in (home, away):
            provider_id = str(team["id"])
            teams[provider_id] = ProviderTeam(
                provider_team_id=provider_id,
                provider_team_name=str(team["name"]),
                country_code="DE",
                competition_name="Bundesliga",
                season=season,
            )
        provider_fixture_id = str(match["id"])
        fixtures.append(
            SourceFixture(
                provider_fixture_id=provider_fixture_id,
                canonical_provider_fixture_id=pitchapi_fixture_id(provider_fixture_id),
                kickoff_at=_timestamp(str(match["time_utc"])),
                competition_name="Bundesliga",
                country_code="DE",
                season=season,
                home_provider_team_id=str(home["id"]),
                away_provider_team_id=str(away["id"]),
                home_team_name=str(home["name"]),
                away_team_name=str(away["name"]),
                source_snapshot_ref=source_ref,
            )
        )
    return tuple(teams.values()), tuple(fixtures)


def _load_retained_fixtures(
    connection: psycopg.Connection[dict[str, Any]],
    *,
    providers_by_competition: Mapping[str, str],
    earliest: datetime,
    latest: datetime,
) -> tuple[FixtureIdentity, ...]:
    query = """
        SELECT DISTINCT ON (h.fixture_id)
               h.fixture_id::text,
               h.kickoff_at,
               h.competition_id::text,
               pc.name AS competition_name,
               pc.country,
               pc.division,
               h.home_team_id::text,
               h.away_team_id::text,
               home.name AS home_team_name,
               away.name AS away_team_name,
               h.source_provider_code,
               mapping.provider_match_id AS source_fixture_id,
               h.source_snapshot_id::text
          FROM football.product_team_match_history h
          JOIN football.product_competitions pc
            ON pc.competition_id = h.competition_id
          JOIN football.product_teams home ON home.team_id = h.home_team_id
          JOIN football.product_teams away ON away.team_id = h.away_team_id
          JOIN LATERAL (
                SELECT m.provider_match_id
                  FROM football.match_provider_mappings m
                  JOIN football.providers p ON p.id = m.provider_id
                 WHERE m.match_id = h.fixture_id
                   AND p.code = h.source_provider_code
                 ORDER BY m.first_seen_at, m.id
                 LIMIT 1
          ) mapping ON true
         WHERE h.competition_id = ANY(%s::uuid[])
           AND h.kickoff_at > %s
           AND h.kickoff_at < %s
         ORDER BY h.fixture_id, h.source_snapshot_id
    """
    rows = connection.execute(query, (list(providers_by_competition), earliest, latest)).fetchall()
    return tuple(
        _retained_fixture(row)
        for row in rows
        if providers_by_competition[str(row["competition_id"])] == row["source_provider_code"]
    )


def _retained_fixture(row: Mapping[str, object]) -> FixtureIdentity:
    kickoff = cast(datetime, row["kickoff_at"])
    country = str(row["country"])
    return FixtureIdentity(
        fixture_id=str(row["fixture_id"]),
        kickoff_at=kickoff,
        competition_id=str(row["competition_id"]),
        competition_name=str(row["competition_name"]),
        country_code=_country_code(country),
        season=_season_for_country(country, kickoff),
        home_team_id=str(row["home_team_id"]),
        away_team_id=str(row["away_team_id"]),
        home_team_name=str(row["home_team_name"]),
        away_team_name=str(row["away_team_name"]),
        source_provider=str(row["source_provider_code"]),
        source_fixture_id=str(row["source_fixture_id"]),
        source_snapshot_id=str(row["source_snapshot_id"]),
        division=cast(int | None, row["division"]),
    )


def _reconcile_pitchapi_seasons(
    source_by_season: Mapping[str, tuple[tuple[ProviderTeam, ...], tuple[SourceFixture, ...]]],
    retained: Sequence[FixtureIdentity],
) -> tuple[TeamIdentityCrosswalk, ...]:
    revisions: dict[str, list[TeamIdentityCrosswalk]] = defaultdict(list)
    for season, (teams, fixtures) in source_by_season.items():
        retained_season = tuple(row for row in retained if row.season == season)
        for row in reconcile_by_fixture_participation(
            teams, fixtures, retained_season, verified_at=QUALIFICATION_AT
        ):
            revisions[row.source_team_id].append(row)
    return tuple(_merge_revisions(rows) for _, rows in sorted(revisions.items()))


def _merge_revisions(rows: Sequence[TeamIdentityCrosswalk]) -> TeamIdentityCrosswalk:
    verified_ids = {
        row.canonical_team_id
        for row in rows
        if row.status == IdentityStatus.VERIFIED and row.canonical_team_id
    }
    if len(verified_ids) > 1:
        raise RuntimeError(f"PitchAPI identity changed canonical team: {rows[0].source_team_id}")
    verified = next((row for row in rows if row.status == IdentityStatus.VERIFIED), rows[0])
    evidence_refs = tuple(sorted({ref for row in rows for ref in row.evidence_refs}))
    status = verified.status if verified_ids else rows[-1].status
    canonical_id = next(iter(verified_ids), "")
    seed = {
        "source_provider": "pitchapi",
        "source_team_id": verified.source_team_id,
        "canonical_team_id": canonical_id,
        "evidence_refs": evidence_refs,
        "status": status,
        "version": 1,
    }
    return replace(
        verified,
        crosswalk_id=f"team-crosswalk:{semantic_sha256(seed)}",
        canonical_team_id=canonical_id,
        evidence_refs=evidence_refs,
        first_verified_at=min(row.first_verified_at for row in rows),
        last_verified_at=max(row.last_verified_at for row in rows),
        status=status,
    )


def _fixture_crosswalk(
    source_by_season: Mapping[str, tuple[tuple[ProviderTeam, ...], tuple[SourceFixture, ...]]],
    retained: Sequence[FixtureIdentity],
    crosswalk: Sequence[TeamIdentityCrosswalk],
) -> dict[str, str]:
    output: dict[str, str] = {}
    for season, (_, fixtures) in source_by_season.items():
        retained_season = tuple(row for row in retained if row.season == season)
        output.update(reconcile_source_fixtures(fixtures, retained_season, crosswalk))
    return output


def _fixture_crosswalk_rows(
    source_by_season: Mapping[str, tuple[tuple[ProviderTeam, ...], tuple[SourceFixture, ...]]],
    retained: Sequence[FixtureIdentity],
    crosswalk: Sequence[TeamIdentityCrosswalk],
) -> list[dict[str, object]]:
    canonical_by_id = {row.fixture_id: row for row in retained}
    rows: list[dict[str, object]] = []
    for season, (_, fixtures) in sorted(source_by_season.items()):
        retained_season = tuple(row for row in retained if row.season == season)
        mapped = reconcile_source_fixtures(fixtures, retained_season, crosswalk)
        for source in fixtures:
            canonical_id = mapped.get(source.canonical_provider_fixture_id)
            if canonical_id is None:
                continue
            canonical = canonical_by_id[canonical_id]
            rows.append(
                {
                    "provider": "pitchapi",
                    "provider_fixture_id": source.provider_fixture_id,
                    "provider_canonical_fixture_id": source.canonical_provider_fixture_id,
                    "canonical_fixture_id": canonical.fixture_id,
                    "competition": canonical.competition_name,
                    "country_code": canonical.country_code,
                    "season": season,
                    "provider_kickoff_at": source.kickoff_at.astimezone(UTC).isoformat(),
                    "canonical_kickoff_at": canonical.kickoff_at.astimezone(UTC).isoformat(),
                    "home_team_id": canonical.home_team_id,
                    "away_team_id": canonical.away_team_id,
                    "source_snapshot": source.source_snapshot_ref,
                }
            )
    return sorted(rows, key=lambda row: (str(row["season"]), str(row["provider_fixture_id"])))


def _load_direct_mappings(
    connection: psycopg.Connection[dict[str, Any]],
    team_sources: set[tuple[str, str]],
) -> tuple[ProviderMapping, ...]:
    query = """
        SELECT DISTINCT ON (mapping.team_id, provider.code)
               mapping.id::text AS mapping_id,
               provider.code AS provider_code,
               mapping.provider_team_id,
               alias.normalized_name AS provider_team_name,
               mapping.team_id::text AS canonical_team_id,
               product.name AS canonical_team_name,
               product.country AS country_code,
               mapping.source_snapshot_id::text,
               mapping.first_seen_at,
               mapping.last_seen_at
          FROM football.team_provider_mappings mapping
          JOIN football.providers provider ON provider.id = mapping.provider_id
          JOIN football.product_teams product ON product.team_id = mapping.team_id
          JOIN football.product_team_aliases alias
            ON alias.team_id = mapping.team_id
           AND alias.provider_code = provider.code
           AND alias.provider_team_id = mapping.provider_team_id
         WHERE provider.code = ANY(%s::text[])
           AND mapping.team_id = ANY(%s::uuid[])
           AND mapping.valid_to IS NULL
         ORDER BY mapping.team_id, provider.code, mapping.first_seen_at, mapping.id
    """
    team_ids = sorted({team_id for team_id, _ in team_sources})
    providers = sorted({provider for _, provider in team_sources})
    rows = connection.execute(query, (providers, team_ids)).fetchall()
    return tuple(
        ProviderMapping(
            mapping_id=str(row["mapping_id"]),
            provider_code=str(row["provider_code"]),
            provider_team_id=str(row["provider_team_id"]),
            provider_team_name=str(row["provider_team_name"]),
            canonical_team_id=str(row["canonical_team_id"]),
            canonical_team_name=str(row["canonical_team_name"]),
            country_code=_country_code(str(row["country_code"])),
            source_snapshot_id=str(row["source_snapshot_id"]),
            first_seen_at=cast(datetime, row["first_seen_at"]),
            last_seen_at=cast(datetime, row["last_seen_at"]),
        )
        for row in rows
        if (str(row["canonical_team_id"]), str(row["provider_code"])) in team_sources
    )


def _require_direct_mappings(
    expected: set[tuple[str, str]], mappings: Sequence[ProviderMapping]
) -> None:
    actual = {(row.canonical_team_id, row.provider_code) for row in mappings}
    missing = sorted(expected - actual)
    if missing:
        raise RuntimeError(f"missing exact provider-team mappings: {missing}")


def _retained_inventory(
    connection: psycopg.Connection[dict[str, Any]],
) -> dict[str, object]:
    row = connection.execute(
        """
        SELECT count(DISTINCT fixture_id) AS fixture_count,
               count(DISTINCT competition_id) AS competition_count,
               min(kickoff_at) AS earliest_kickoff_at,
               max(kickoff_at) AS latest_kickoff_at
          FROM football.product_team_match_history
        """
    ).fetchone()
    if row is None:
        raise RuntimeError("retained product match history inventory is unavailable")
    return {
        "fixture_count": int(row["fixture_count"]),
        "competition_count": int(row["competition_count"]),
        "earliest_kickoff_at": cast(datetime, row["earliest_kickoff_at"])
        .astimezone(UTC)
        .isoformat(),
        "latest_kickoff_at": cast(datetime, row["latest_kickoff_at"]).astimezone(UTC).isoformat(),
    }


def _xg_coverage(database_url: str, fixture_ids: Sequence[str]) -> dict[str, object]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT count(*) FILTER (WHERE has_complete_xg) AS complete_fixture_count,
                   count(*) FILTER (WHERE NOT has_complete_xg) AS missing_fixture_count
              FROM (
                    SELECT fixture_id,
                           bool_or(home_xg IS NOT NULL AND away_xg IS NOT NULL)
                               AS has_complete_xg
                      FROM football.product_team_match_history
                     WHERE fixture_id = ANY(%s::uuid[])
                     GROUP BY fixture_id
              ) coverage
            """,
            (list(fixture_ids),),
        ).fetchone()
    if row is None:
        raise RuntimeError("xG coverage query returned no row")
    return {
        "status": "DESCRIPTIVE_POST_FREEZE_ONLY",
        "complete_fixture_count": int(row["complete_fixture_count"]),
        "missing_fixture_count": int(row["missing_fixture_count"]),
        "required_for_qualification": False,
    }


def _load_history(
    connection: psycopg.Connection[dict[str, Any]],
    team_ids: frozenset[str],
    research_cutoff: datetime,
) -> dict[str, tuple[HistoryMembership, ...]]:
    query = """
        SELECT DISTINCT h.fixture_id,
               h.kickoff_at,
               h.competition_id::text,
               pc.season_label,
               pc.division,
               h.home_team_id::text,
               h.away_team_id::text
          FROM football.product_team_match_history h
          JOIN football.product_competitions pc
            ON pc.competition_id = h.competition_id
         WHERE (h.home_team_id = ANY(%s::uuid[]) OR h.away_team_id = ANY(%s::uuid[]))
           AND h.kickoff_at < %s
    """
    rows = connection.execute(query, (list(team_ids), list(team_ids), research_cutoff)).fetchall()
    result: dict[str, list[HistoryMembership]] = defaultdict(list)
    for row in rows:
        kickoff = cast(datetime, row["kickoff_at"])
        for key in ("home_team_id", "away_team_id"):
            team_id = str(row[key])
            if team_id not in team_ids:
                continue
            result[team_id].append(
                HistoryMembership(
                    team_id=team_id,
                    competition_id=str(row["competition_id"]),
                    season=_season(kickoff),
                    division=cast(int | None, row["division"]),
                    kickoff_at=kickoff,
                )
            )
    return {
        key: tuple(sorted(values, key=lambda row: row.kickoff_at)) for key, values in result.items()
    }


def _artifact_models() -> tuple[dict[str, object], ...]:
    evidence = _json(V1_EVIDENCE)
    freeze = cast(dict[str, object], evidence["development_freeze"])
    artifacts = cast(dict[str, dict[str, object]], freeze["final_artifacts"])
    return tuple(
        {
            "artifact_model_id": model_id,
            "artifact_sha256": value["artifact_sha256"],
            "training_competition": "Bundesliga",
            "training_season": "2021/2022",
            "training_cutoff": value["training_cutoff"],
        }
        for model_id, value in sorted(artifacts.items())
    )


def _artifact_identity_report(
    models: Sequence[Mapping[str, object]],
    training_teams: Sequence[ProviderTeam],
    crosswalk: Sequence[TeamIdentityCrosswalk],
) -> tuple[dict[str, object], frozenset[str]]:
    by_provider_id = {row.source_team_id: row for row in crosswalk}
    identities: list[ArtifactIdentity] = []
    statuses = Counter[str]()
    confidence = Counter[str]()
    fitted_ids: set[str] = set()
    for team in sorted(training_teams, key=lambda row: row.provider_team_id):
        row = by_provider_id[team.provider_team_id]
        statuses[row.status.lower()] += 1
        confidence[row.confidence_class] += 1
        if row.status == IdentityStatus.VERIFIED:
            fitted_ids.add(row.canonical_team_id)
        for model in models:
            identities.append(
                ArtifactIdentity(
                    artifact_model_id=str(model["artifact_model_id"]),
                    artifact_sha256=str(model["artifact_sha256"]),
                    artifact_team_id=pitchapi_team_id(team.provider_team_id),
                    artifact_team_name=team.provider_team_name,
                    provider_team_id=team.provider_team_id,
                    training_competition=str(model["training_competition"]),
                    training_season=str(model["training_season"]),
                    training_cutoff=str(model["training_cutoff"]),
                )
            )
    return (
        {
            "artifact_team_id_namespace": ARTIFACT_NAMESPACE,
            "artifact_models": list(models),
            "artifact_teams_total": len(training_teams),
            "verified_mappings": statuses["verified"],
            "ambiguous_mappings": statuses["ambiguous"],
            "unresolved_mappings": statuses["unresolved"],
            "rejected_mappings": statuses["rejected"],
            "exact_provider_id_mappings": confidence["EXACT_PROVIDER_ID"],
            "strong_multi_attribute_mappings": confidence["STRONG_MULTI_ATTRIBUTE"],
            "manual_verified_mappings": confidence["MANUAL_VERIFIED"],
            "identities": [asdict(row) for row in identities],
        },
        frozenset(fitted_ids),
    )


def _crosswalk_manifest(
    rows: Sequence[TeamIdentityCrosswalk],
    fixture_rows: Sequence[Mapping[str, object]],
    artifact_models: Sequence[Mapping[str, object]],
    source_commit: str,
) -> dict[str, object]:
    mappings = [crosswalk_manifest_row(row) for row in rows]
    return {
        "contract": "TeamIdentityCrosswalkV1",
        "version": 1,
        "artifact_team_id_namespace": ARTIFACT_NAMESPACE,
        "artifact_models": list(artifact_models),
        "mapping_count": len(mappings),
        "mappings": mappings,
        "fixture_mapping_count": len(fixture_rows),
        "fixture_mappings": list(fixture_rows),
        "source_commit": source_commit,
    }


def _qualification(targets: Sequence[QualifiedTarget]) -> dict[str, object]:
    split_counts = Counter(row.split for row in targets)
    domain_counts = Counter(row.fixture.competition_name for row in targets)
    season_counts = Counter(row.fixture.season for row in targets)
    category_counts = Counter(row.target_category for row in targets)
    promotion_counts = Counter(
        state for row in targets for state in (row.home_promotion_state, row.away_promotion_state)
    )
    holdout = [row for row in targets if row.split == "DEVELOPMENT_HOLDOUT"]
    holdout_native = sum(row.target_category == "NATIVE_FITTED" for row in holdout)
    holdout_cold = len(holdout) - holdout_native
    holdout_promoted = sum(
        "PROMOTED_TEAM" in (row.home_promotion_state, row.away_promotion_state) for row in holdout
    )
    qualified_domains = sum(count >= 150 for count in domain_counts.values())
    failures: list[str] = []
    if len(targets) < 600:
        failures.append("INSUFFICIENT_FRESH_TARGETS")
    if qualified_domains < 3:
        failures.append("INSUFFICIENT_DOMAIN_DIVERSITY")
    if len(holdout) < 120:
        failures.append("INSUFFICIENT_HOLDOUT_TARGETS")
    if holdout_cold < 50:
        failures.append("INSUFFICIENT_COLD_START_HOLDOUT")
    if holdout_native < 50:
        failures.append("INSUFFICIENT_NATIVE_FITTED_HOLDOUT")
    power = "ADEQUATE_COLD_START_POWER" if holdout_cold >= 100 else "LIMITED_COLD_START_POWER"
    return {
        "total_targets": len(targets),
        "competition_counts": dict(sorted(domain_counts.items())),
        "season_counts": dict(sorted(season_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "promotion_state_counts": dict(sorted(promotion_counts.items())),
        "qualified_domain_count": qualified_domains,
        "split": {
            "TRAIN": split_counts["TRAIN"],
            "VALIDATION": split_counts["VALIDATION"],
            "DEVELOPMENT_HOLDOUT": split_counts["DEVELOPMENT_HOLDOUT"],
        },
        "holdout": {
            "total": len(holdout),
            "native_fitted": holdout_native,
            "cold_start": holdout_cold,
            "promoted": holdout_promoted,
            "cold_start_power": power,
        },
        "failures": failures,
    }


def _disposition(artifact_report: Mapping[str, object], qualification: Mapping[str, object]) -> str:
    if artifact_report["ambiguous_mappings"]:
        return "AMBIGUOUS_IDENTITY_BLOCKER"
    if artifact_report["verified_mappings"] != artifact_report["artifact_teams_total"]:
        return "INSUFFICIENT_VERIFIED_TEAM_IDENTITIES"
    failures = cast(list[str], qualification["failures"])
    return failures[0] if failures else "FRESH_DEVELOPMENT_CORPUS_QUALIFIED"


def _corpus_manifest(
    targets: list[dict[str, object]],
    *,
    source_commit: str,
    target_sha: str,
    split_sha: str,
    firewall_sha: str,
    crosswalk_sha: str,
    qualification: Mapping[str, object],
) -> dict[str, object]:
    semantic = {
        "corpus_id": CORPUS_ID,
        "target_manifest_sha256": target_sha,
        "identity_crosswalk_sha256": crosswalk_sha,
        "global_firewall_sha256": firewall_sha,
        "split_manifest_sha256": split_sha,
        "source_commit": source_commit,
        "source_datasets": [
            "football.product_team_match_history:football_data_uk",
            "football.product_team_match_history:openfootball",
            str(V1_RESULT),
            str(DEVELOPMENT_RESULT),
            str(SPENT_MANIFEST),
        ],
        "selection_policy": {
            "mode": "OUTCOME_BLIND_COMPETITION_LEVEL",
            "domains": [
                {
                    "competition_id": competition_id,
                    "competition_name": name,
                    "source_provider": provider,
                }
                for competition_id, (name, provider) in sorted(SELECTED_DOMAINS.items())
            ],
        },
        "counts": qualification,
        "targets": targets,
    }
    return {
        "contract": "MatchForgeFreshDevelopmentCorpusV1",
        **semantic,
        "corpus_sha256": semantic_sha256(semantic),
    }


def _group_overlaps(
    spent: Mapping[str, object],
    provider_fixture_crosswalk: Mapping[str, str],
    admitted: Sequence[FixtureIdentity],
) -> dict[str, int]:
    admitted_ids = {row.fixture_id for row in admitted}
    result: dict[str, int] = {}
    for group in cast(list[dict[str, object]], spent["groups"]):
        mapped = {
            provider_fixture_crosswalk[target_id]
            for target_id in cast(list[str], group["target_ids"])
            if target_id in provider_fixture_crosswalk
        }
        mapped.update(cast(list[str], group["target_ids"]))
        result[str(group["group_id"])] = len(mapped & admitted_ids)
    return result


def _evidence(
    *,
    source_commit: str,
    research_cutoff: datetime,
    artifact_report: Mapping[str, object],
    crosswalk: Sequence[TeamIdentityCrosswalk],
    fixture_crosswalk_count: int,
    retained_inventory: Mapping[str, object],
    scoped_retained_rows_inspected: int,
    forbidden: frozenset[str],
    firewall_sha: str,
    candidates: Sequence[FixtureIdentity],
    admitted: Sequence[FixtureIdentity],
    protected_fixture_ids: frozenset[str],
    group_overlaps: Mapping[str, int],
    qualification: Mapping[str, object],
    crosswalk_sha: str,
    target_sha: str,
    split_sha: str,
    corpus_manifest: Mapping[str, object] | None,
    xg_coverage: Mapping[str, object],
    disposition: str,
) -> dict[str, object]:
    exact = sum(row.confidence_class == "EXACT_PROVIDER_ID" for row in crosswalk)
    strong = sum(row.confidence_class == "STRONG_MULTI_ATTRIBUTE" for row in crosswalk)
    admitted_ids = {row.fixture_id for row in admitted}
    final_forbidden_overlap = len(admitted_ids & protected_fixture_ids)
    return {
        "contract": "MatchForgeFreshCorpusQualificationEvidenceV1",
        "protocol_id": PROTOCOL_ID,
        "authorization": AUTHORIZATION_ID,
        "source_commit": source_commit,
        "research_cutoff": research_cutoff.astimezone(UTC).isoformat(),
        "selection_policy": {
            "mode": "OUTCOME_BLIND_COMPETITION_LEVEL",
            "domains": [
                {
                    "competition_id": competition_id,
                    "competition_name": name,
                    "source_provider": provider,
                }
                for competition_id, (name, provider) in sorted(SELECTED_DOMAINS.items())
            ],
        },
        "artifact_identity": artifact_report,
        "crosswalk": {
            "sha256": crosswalk_sha,
            "mapping_count": len(crosswalk),
            "fixture_mapping_count": fixture_crosswalk_count,
            "exact_provider_mappings": exact,
            "strong_multi_attribute_mappings": strong,
            "manual_mappings": 0,
        },
        "retained_dataset_inventory": dict(retained_inventory),
        "retained_matches_inspected": retained_inventory["fixture_count"],
        "scoped_retained_rows_inspected": scoped_retained_rows_inspected,
        "global_firewall": {
            "source_manifest": str(SPENT_MANIFEST),
            "source_manifest_sha256": _file_sha(SPENT_MANIFEST),
            "target_count": len(forbidden),
            "sha256": firewall_sha,
            "candidate_intersections_removed": len(
                set(row.fixture_id for row in candidates) & protected_fixture_ids
            ),
            "admitted_overlap_count": final_forbidden_overlap,
            "group_admitted_overlaps": dict(group_overlaps),
        },
        "fresh_target_candidates_before_firewall": len(candidates),
        "fresh_targets_after_firewall": len(admitted),
        "qualification": qualification,
        "duplicate_real_fixture_count": 0,
        "target_manifest_sha256": target_sha,
        "split_manifest_sha256": split_sha,
        "corpus_id": corpus_manifest["corpus_id"] if corpus_manifest else None,
        "corpus_sha256": corpus_manifest["corpus_sha256"] if corpus_manifest else None,
        "xg_coverage": dict(xg_coverage),
        "outcome_fields_read_for_selection": False,
        "v2_evaluation_executed": False,
        "production_champion_changed": False,
        "final_disposition": disposition,
        "next_action": (
            "READY_FOR_MATCHFORGE_FULL_COVERAGE_CHALLENGERS_V2_REEVALUATION_V1"
            if disposition == "FRESH_DEVELOPMENT_CORPUS_QUALIFIED"
            else "NEW_DATA_ACQUISITION_REQUIRED"
        ),
    }


def _season(kickoff: datetime) -> str:
    year = kickoff.year if kickoff.month >= 7 else kickoff.year - 1
    return f"{year}/{year + 1}"


def _season_for_country(country: str, kickoff: datetime) -> str:
    if country == "Brazil":
        return str(kickoff.year)
    return _season(kickoff)


def _country_code(country: str) -> str:
    return {
        "Austria": "AT",
        "Brazil": "BR",
        "England": "GB-ENG",
        "Germany": "DE",
        "Mexico": "MX",
    }.get(country, country)


def _crosswalk_sort_key(row: TeamIdentityCrosswalk) -> tuple[str, str, str]:
    return row.source_provider, row.source_team_id, row.crosswalk_id


def _hash_path(root: Path, kind: str, digest: str) -> Path:
    return root / kind / "sha256" / digest[:2] / f"{digest}.json"


def _verified_json(path: Path, expected_sha: str) -> dict[str, object]:
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha:
        raise RuntimeError(f"hash mismatch: {path}")
    return cast(dict[str, object], json.loads(payload))


def _json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value) + b"\n")


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _verify_source(source_commit: str) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if head != source_commit:
        raise RuntimeError("source commit must equal HEAD")
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise RuntimeError("qualification requires a clean worktree")


def _markdown(evidence: Mapping[str, object]) -> str:
    identity = cast(Mapping[str, object], evidence["artifact_identity"])
    qualification = cast(Mapping[str, object], evidence["qualification"])
    holdout = cast(Mapping[str, object], qualification["holdout"])
    split = cast(Mapping[str, object], qualification["split"])
    firewall = cast(Mapping[str, object], evidence["global_firewall"])
    artifact_summary = (
        f"Artifact teams: {identity['verified_mappings']}/"
        f"{identity['artifact_teams_total']} verified; "
        f"{identity['ambiguous_mappings']} ambiguous; "
        f"{identity['unresolved_mappings']} unresolved."
    )
    holdout_summary = (
        f"Holdout: {holdout['native_fitted']} native fitted; "
        f"{holdout['cold_start']} cold-start; {holdout['promoted']} promoted."
    )
    return "\n".join(
        (
            "# Full-coverage V2 fresh corpus qualification",
            "",
            f"Disposition: `{evidence['final_disposition']}`",
            "",
            f"Artifact namespace: `{identity['artifact_team_id_namespace']}`",
            artifact_summary,
            f"Fresh targets: {evidence['fresh_targets_after_firewall']} after firewall "
            f"({evidence['fresh_target_candidates_before_firewall']} before).",
            f"Split: TRAIN {split['TRAIN']}; VALIDATION {split['VALIDATION']}; "
            f"DEVELOPMENT_HOLDOUT {split['DEVELOPMENT_HOLDOUT']}.",
            holdout_summary,
            f"Forbidden overlap: {firewall['admitted_overlap_count']}.",
            "V2 evaluation executed: NO.",
            "Production champion changed: NO.",
            "",
            f"Next action: `{evidence['next_action']}`",
            "",
        )
    )


if __name__ == "__main__":
    main()
