"""Bounded Prometheus measurements; no provider I/O, feature building or model execution."""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from psycopg import Connection
from psycopg.rows import tuple_row

from football.contracts.source import canonical_json_bytes, sha256_bytes
from football.forecasting.features import FEATURE_CONTRACT_VERSION
from football.forecasting.postmatch_storage import monitor_postmatch
from football.providers.normalization.pipeline import NORMALIZERS

PROVIDERS = tuple(sorted({provider for provider, _ in NORMALIZERS}))
_RESOURCES = tuple(sorted({resource for _, resource in NORMALIZERS} | {"OTHER"}))
_FEATURES = (
    "travel",
    "manager_context",
    "lineup_context",
    "availability_context",
    "league_strength",
    "home_advantage",
    "tactical_context",
    "corners_context",
    "cards_context",
    "player_context",
    "quality",
)
_PACKAGED_SCHEMA = Path(__file__).with_name("fixture-feature-snapshot-v1.schema.json")
_SCHEMA_PATH = (
    _PACKAGED_SCHEMA
    if _PACKAGED_SCHEMA.is_file()
    else Path(__file__).resolve().parents[5]
    / "schemas/contracts/fixture-feature-snapshot-v1.schema.json"
)
_FEATURE_VALIDATOR = Draft202012Validator(
    json.loads(_SCHEMA_PATH.read_bytes()), format_checker=FormatChecker()
)
_LABEL = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


def sample(name: str, value: float | int | None, **labels: str) -> str:
    if any(not _LABEL.fullmatch(item) for item in (name, *labels, *labels.values())):
        raise ValueError("metric names and bounded labels must be identifiers")
    if value is not None and (type(value) not in (float, int) or not math.isfinite(value)):
        raise ValueError("metric values must be finite or explicitly unknown")
    label = (
        "{" + ",".join(f'{key}="{value}"' for key, value in sorted(labels.items())) + "}"
        if labels
        else ""
    )
    return f"{name}{label} {'NaN' if value is None else format(value, '.17g')}\n"


def _gauge(name: str, description: str) -> str:
    return f"# HELP {name} {description}\n# TYPE {name} gauge\n"


def feature_metrics(
    features: tuple[tuple[str, dict[str, Any]], ...],
    *,
    competitions: tuple[UUID, ...],
    window_start: datetime,
    window_end: datetime,
    observed_at: datetime,
) -> str:
    """Count nullable resource families in supplied checksum-bound feature exports."""
    unique = {}
    for digest, payload in features:
        if sha256_bytes(canonical_json_bytes(payload)) != digest:
            raise ValueError("feature snapshot checksum mismatch")
        try:
            _FEATURE_VALIDATOR.validate(payload)
            clocks = [
                datetime.fromisoformat(payload[name])
                for name in ("football_cutoff", "knowledge_cutoff")
            ]
            fixture = payload["fixture"]
            kickoff = datetime.fromisoformat(fixture["kickoff_at"])
            valid = (
                payload["contract"] == "FixtureFeatureSnapshotV1"
                and payload["feature_contract_version"] == FEATURE_CONTRACT_VERSION
                and UUID(fixture["competition_id"]) in competitions
                and window_start <= kickoff < window_end
                and all(clock.utcoffset() is not None and clock <= observed_at for clock in clocks)
                and clocks[0] <= kickoff
                and all(name in payload for name in _FEATURES)
            )
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise ValueError("invalid feature snapshot metadata") from error
        if not valid:
            raise ValueError("feature snapshot is unsupported, incomplete, future or outside scope")
        unique[digest] = payload
    output = _gauge(
        "feature_snapshot_samples", "Distinct supplied feature exports; not a population estimate."
    )
    output += sample("feature_snapshot_samples", len(unique))
    output += _gauge(
        "feature_missingness",
        "Fraction of supplied exports with a null resource family; NaN without samples.",
    )
    for family in _FEATURES:
        missing = sum(payload[family] is None for payload in unique.values())
        output += sample(
            "feature_missingness", missing / len(unique) if unique else None, family=family
        )
    return output


def _providers(connection: Connection[Any], providers: tuple[str, ...]) -> str:
    descriptions = {
        "provider_request_reservations": "Retained request-budget reservations.",
        "provider_acquisition_failures": "Current failed lifecycle acquisition jobs.",
        "provider_freshness_seconds": (
            "Latest validated REAL_PROVIDER acquisition age in seconds; NaN if absent."
        ),
    }
    output = "".join(_gauge(name, help_text) for name, help_text in descriptions.items())
    with connection.cursor(row_factory=tuple_row) as cursor:
        rows = cursor.execute(
            """SELECT p.code,
            (SELECT sum(b.requests_used) FROM football.provider_request_budgets b
             WHERE b.provider_code=p.code AND b.updated_at<=transaction_timestamp()),
            (SELECT count(*) FROM football.acquisition_jobs j WHERE j.provider_id=p.id
             AND j.status='failed' AND j.updated_at<=transaction_timestamp()),
            (SELECT extract(epoch FROM transaction_timestamp()-max(s.acquired_at))
             FROM football.source_snapshots s WHERE s.provider_id=p.id
             AND s.source_kind='REAL_PROVIDER' AND s.status='validated'
             AND s.acquired_at<=transaction_timestamp())
            FROM football.providers p WHERE p.code=ANY(%s) ORDER BY p.code""",
            (list(providers),),
        ).fetchall()
    known = {row[0]: row[1:] for row in rows}
    for provider in providers:
        values = known.get(provider, (None, None, None))
        for name, value in zip(descriptions, values, strict=True):
            output += sample(name, float(value) if value is not None else None, provider=provider)
    return output


def _coverage(
    connection: Connection[Any], providers: tuple[str, ...], competitions: tuple[UUID, ...]
) -> str:
    with connection.cursor(row_factory=tuple_row) as cursor:
        provider_rows = cursor.execute(
            """SELECT provider,resource_type,coverage_ratio FROM (
            SELECT DISTINCT ON (p.code,r.resource_type,r.competition_key,r.season_key)
                   p.code AS provider,r.* FROM football.provider_resource_coverage r
            JOIN football.providers p ON p.id=r.provider_id
            WHERE p.code=ANY(%s) AND r.known_at<=transaction_timestamp()
              AND r.knowledge_cutoff<=transaction_timestamp()
            ORDER BY p.code,r.resource_type,r.competition_key,r.season_key,
                     r.knowledge_cutoff DESC,r.known_at DESC,r.publication_sequence DESC
            ) latest""",
            (list(providers),),
        ).fetchall()
        canonical_rows = cursor.execute(
            """SELECT resource_type,coverage_ratio FROM (
            SELECT DISTINCT ON (competition_id,season_id,resource_type) *
            FROM football.canonical_resource_coverage
            WHERE competition_id=ANY(%s::uuid[]) AND known_at<=transaction_timestamp()
              AND knowledge_cutoff<=transaction_timestamp()
            ORDER BY competition_id,season_id,resource_type,knowledge_cutoff DESC,
                     known_at DESC,publication_sequence DESC) latest""",
            (list(competitions),),
        ).fetchall()
    groups: dict[tuple[str, str], list[float | None]] = defaultdict(list)
    for provider, resource, ratio in provider_rows:
        groups[provider, resource if resource in _RESOURCES else "OTHER"].append(ratio)
    for resource, ratio in canonical_rows:
        groups["", resource if resource in _RESOURCES else "OTHER"].append(ratio)
    output = ""
    for kind, selections in (("provider", providers), ("canonical", ("",))):
        for suffix, description in (
            (
                "ratio",
                "Minimum known ratio among latest scope reports; NaN without known denominators.",
            ),
            ("scopes", "Latest reported scopes, including unknown denominators."),
            ("known_scopes", "Latest reported scopes with positive known denominators."),
        ):
            output += _gauge(f"{kind}_coverage_{suffix}", description)
        for provider in selections:
            for resource in _RESOURCES:
                values = groups[provider, resource]
                measured = [float(value) for value in values if value is not None]
                labels = {"resource": resource, **({"provider": provider} if provider else {})}
                for suffix, value in (
                    ("ratio", min(measured) if measured else None),
                    ("scopes", len(values)),
                    ("known_scopes", len(measured)),
                ):
                    output += sample(f"{kind}_coverage_{suffix}", value, **labels)
    return output


def _identities(
    connection: Connection[Any], competitions: tuple[UUID, ...], start: datetime, end: datetime
) -> str:
    with connection.cursor(row_factory=tuple_row) as cursor:
        team_row = cursor.execute("""SELECT count(*) FROM football.product_teams t
            WHERE NOT EXISTS (
            SELECT 1 FROM football.team_provider_mappings m WHERE m.team_id=t.team_id
              AND (m.valid_from IS NULL OR m.valid_from<=transaction_timestamp())
              AND (m.valid_to IS NULL OR m.valid_to>transaction_timestamp())
              AND football.product_mapping_trusted('team',m.id,m.team_id))""").fetchone()
        fixture_row = cursor.execute(
            """SELECT
            count(*) FILTER(WHERE identity_status<>'VERIFIED'),
            count(*) FILTER(WHERE identity_status='VERIFIED' AND status='SCHEDULED'
                           AND kickoff_at>transaction_timestamp()
                           AND forecast_availability='FORECAST_AVAILABLE')
            FROM football.product_serving_fixtures WHERE competition_id=ANY(%s::uuid[])
              AND kickoff_at>=%s AND kickoff_at<%s""",
            (list(competitions), start, end),
        ).fetchone()
        duplicate_row = cursor.execute(
            """SELECT count(*) FROM football.fixture_identity_resolutions r
            JOIN football.product_fixtures f ON f.fixture_id=r.member_fixture_id
            WHERE r.active AND r.resolution_status='DUPLICATE_RESOLVED'
              AND r.member_fixture_id<>r.representative_fixture_id
              AND r.created_at<=transaction_timestamp() AND f.competition_id=ANY(%s::uuid[])
              AND f.kickoff_at>=%s AND f.kickoff_at<%s""",
            (list(competitions), start, end),
        ).fetchone()
    assert team_row is not None and fixture_row is not None and duplicate_row is not None
    teams, (unresolved, available), duplicates = team_row[0], fixture_row, duplicate_row[0]
    output = ""
    for name, value, description in (
        (
            "unresolved_team_identities",
            teams,
            "Current product teams without any trusted active provider mapping.",
        ),
        (
            "unresolved_fixture_identities",
            unresolved,
            "Current serving fixtures without verified identity in the selected window.",
        ),
        (
            "canonical_fixture_duplicates",
            duplicates,
            "Active resolved nonrepresentative duplicate members in the selected window.",
        ),
        (
            "forecastable_fixtures",
            available,
            "Future scheduled verified serving fixtures flagged FORECAST_AVAILABLE in the window.",
        ),
    ):
        output += _gauge(name, description) + sample(name, value)
    return output


def render_domain_metrics(
    connection: Connection[Any],
    *,
    competitions: tuple[UUID, ...],
    window_start: datetime,
    window_end: datetime,
    providers: tuple[str, ...] = PROVIDERS,
    horizon: str = "LATEST",
    features: tuple[tuple[str, dict[str, Any]], ...] = (),
) -> str:
    """Join the caller's consistent read-only transaction; never infer missing observations."""
    if (
        not providers
        or len(set(providers)) != len(providers)
        or not set(providers) <= set(PROVIDERS)
    ):
        raise ValueError("metrics require unique registered adapter provider codes")
    providers = tuple(sorted(providers))
    with connection.cursor(row_factory=tuple_row) as cursor:
        clock_row = cursor.execute("SELECT transaction_timestamp()").fetchone()
    assert clock_row is not None
    observed_at = clock_row[0]
    report = monitor_postmatch(
        connection,
        competitions=competitions,
        window_start=window_start,
        window_end=window_end,
        knowledge_cutoff=observed_at,
        horizon=horizon,
        review_limits={},
    )["overall"]
    output = _providers(connection, providers) + _coverage(connection, providers, competitions)
    output += _identities(connection, competitions, window_start, window_end)
    output += feature_metrics(
        features,
        competitions=competitions,
        window_start=window_start,
        window_end=window_end,
        observed_at=observed_at,
    )
    values = {
        **report["metrics"],
        "coverage": report["coverage"]["ratio"],
        "samples": report["coverage"]["selected"],
        "scored": report["coverage"]["scored"],
        "review_required": int(report["status"] == "REVIEW_REQUIRED"),
    }
    for name, value in values.items():
        metric = "postmatch_" + name
        output += _gauge(
            metric,
            "Selected published pre-match forecasts in the window; NaN without observations.",
        ) + sample(metric, value)
    return output
