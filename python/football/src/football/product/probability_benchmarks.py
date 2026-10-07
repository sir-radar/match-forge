from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from psycopg import Connection

from football.product.api_football import ApiResponse
from football.product.domain import sha256_json, stable_id

SPORTMONKS_BASE_URL = "https://api.sportmonks.com/v3/football"
Transport = Callable[[str, Mapping[str, str]], bytes]


class BenchmarkStatus(StrEnum):
    SUCCESS = "SUCCESS"
    DISABLED_NOT_CONFIGURED = "DISABLED_NOT_CONFIGURED"
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    PLAN_RESTRICTION = "PLAN_RESTRICTION"
    FIXTURE_NOT_PREDICTABLE = "FIXTURE_NOT_PREDICTABLE"
    MAPPING_FAILURE = "MAPPING_FAILURE"
    MISSING_PROBABILITIES = "MISSING_PROBABILITIES"
    PROVIDER_OUTAGE = "PROVIDER_OUTAGE"


@dataclass(frozen=True, slots=True)
class ProbabilityBenchmark:
    provider_code: str
    provider_fixture_id: str
    captured_at: datetime
    status: BenchmarkStatus
    home_probability: float | None = None
    draw_probability: float | None = None
    away_probability: float | None = None
    predicted_winner: str | None = None
    predicted_home_goals: str | None = None
    predicted_away_goals: str | None = None
    under_over: str | None = None
    comparison: Mapping[str, object] | None = None
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class PersistedBenchmark:
    benchmark_id: UUID
    mapping_status: str
    collection_status: BenchmarkStatus
    inserted: bool


def persist_probability_benchmark(
    connection: Connection[Any],
    benchmark: ProbabilityBenchmark,
    *,
    provider_payload: Mapping[str, object] | None = None,
    source_snapshot_id: UUID | None = None,
) -> PersistedBenchmark:
    """Persist one benchmark using only exact provider fixture mappings."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT fixture.fixture_id
            FROM football.match_provider_mappings mapping
            JOIN football.providers provider ON provider.id = mapping.provider_id
            JOIN football.product_fixtures fixture ON fixture.fixture_id = mapping.match_id
            WHERE provider.code = %s AND mapping.provider_match_id = %s
            ORDER BY fixture.fixture_id
            """,
            (benchmark.provider_code, benchmark.provider_fixture_id),
        )
        fixture_ids = [row[0] for row in cursor.fetchall()]
    mapping_status = (
        "MATCHED" if len(fixture_ids) == 1 else "AMBIGUOUS" if fixture_ids else "UNMATCHED"
    )
    fixture_id = fixture_ids[0] if mapping_status == "MATCHED" else None
    status = benchmark.status
    failure_reason = benchmark.failure_reason
    if status is BenchmarkStatus.SUCCESS and mapping_status != "MATCHED":
        status = BenchmarkStatus.MAPPING_FAILURE
        failure_reason = f"exact provider fixture mapping is {mapping_status.lower()}"
    revision_sha = sha256_json(
        {
            "provider_code": benchmark.provider_code,
            "provider_fixture_id": benchmark.provider_fixture_id,
            "fixture_id": str(fixture_id) if fixture_id else None,
            "mapping_status": mapping_status,
            "collection_status": status,
            "captured_at": benchmark.captured_at.isoformat(),
            "home_probability": benchmark.home_probability,
            "draw_probability": benchmark.draw_probability,
            "away_probability": benchmark.away_probability,
            "provider_payload": provider_payload,
            "source_snapshot_id": str(source_snapshot_id) if source_snapshot_id else None,
        }
    )
    benchmark_id = stable_id("external-probability-benchmark", revision_sha)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO football.external_probability_benchmarks (
                benchmark_id, revision_sha256, provider_code, provider_fixture_id,
                fixture_id, mapping_status, collection_status, benchmark_role,
                captured_at, home_probability, draw_probability, away_probability,
                provider_payload, source_snapshot_id, failure_reason
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'BENCHMARK_ONLY', %s, %s, %s,
                %s, %s::jsonb, %s, %s)
            ON CONFLICT (revision_sha256) DO NOTHING
            """,
            (
                benchmark_id,
                revision_sha,
                benchmark.provider_code,
                benchmark.provider_fixture_id,
                fixture_id,
                mapping_status,
                status.value,
                benchmark.captured_at,
                benchmark.home_probability,
                benchmark.draw_probability,
                benchmark.away_probability,
                json.dumps(provider_payload) if provider_payload is not None else None,
                source_snapshot_id,
                failure_reason,
            ),
        )
        inserted = cursor.rowcount == 1
    return PersistedBenchmark(benchmark_id, mapping_status, status, inserted)


def parse_api_football_prediction(
    response: ApiResponse, provider_fixture_id: str
) -> ProbabilityBenchmark:
    if not response.rows:
        return _failure(
            "api_football",
            provider_fixture_id,
            response.fetched_at,
            BenchmarkStatus.FIXTURE_NOT_PREDICTABLE,
            "empty prediction response",
        )
    prediction = _mapping(response.rows[0], "predictions")
    percent = _mapping(prediction, "percent")
    probabilities = _probabilities(percent.get("home"), percent.get("draw"), percent.get("away"))
    if probabilities is None:
        return _failure(
            "api_football",
            provider_fixture_id,
            response.fetched_at,
            BenchmarkStatus.MISSING_PROBABILITIES,
            "missing or invalid 1X2 percentages",
        )
    winner = prediction.get("winner")
    goals = prediction.get("goals")
    return ProbabilityBenchmark(
        provider_code="api_football",
        provider_fixture_id=provider_fixture_id,
        captured_at=response.fetched_at,
        status=BenchmarkStatus.SUCCESS,
        home_probability=probabilities[0],
        draw_probability=probabilities[1],
        away_probability=probabilities[2],
        predicted_winner=(
            str(winner.get("name")) if isinstance(winner, Mapping) and winner.get("name") else None
        ),
        predicted_home_goals=(
            str(goals.get("home"))
            if isinstance(goals, Mapping) and goals.get("home") is not None
            else None
        ),
        predicted_away_goals=(
            str(goals.get("away"))
            if isinstance(goals, Mapping) and goals.get("away") is not None
            else None
        ),
        under_over=(str(prediction["under_over"]) if prediction.get("under_over") else None),
        comparison=(
            cast(Mapping[str, object], response.rows[0].get("comparison"))
            if isinstance(response.rows[0].get("comparison"), Mapping)
            else None
        ),
    )


class SportmonksPredictionClient:
    def __init__(self, api_token: str | None, *, transport: Transport | None = None) -> None:
        self.api_token = api_token
        self.transport = transport or _http_get

    def fixture_probability(self, provider_fixture_id: str) -> ProbabilityBenchmark:
        captured_at = datetime.now(UTC)
        if not self.api_token:
            return _failure(
                "sportmonks",
                provider_fixture_id,
                captured_at,
                BenchmarkStatus.DISABLED_NOT_CONFIGURED,
                "SPORTMONKS_API_TOKEN is not configured",
            )
        query = urllib.parse.urlencode({"api_token": self.api_token, "include": "type"})
        path = f"/predictions/probabilities/fixtures/{provider_fixture_id}"
        url = f"{SPORTMONKS_BASE_URL}{path}?{query}"
        try:
            raw = self.transport(url, {})
        except TimeoutError:
            return _failure(
                "sportmonks",
                provider_fixture_id,
                captured_at,
                BenchmarkStatus.TIMEOUT,
                "provider request timed out",
            )
        except (OSError, urllib.error.URLError):
            return _failure(
                "sportmonks",
                provider_fixture_id,
                captured_at,
                BenchmarkStatus.PROVIDER_OUTAGE,
                "provider request failed",
            )
        try:
            payload = cast(Mapping[str, Any], json.loads(raw))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _failure(
                "sportmonks",
                provider_fixture_id,
                captured_at,
                BenchmarkStatus.PROVIDER_OUTAGE,
                "provider returned invalid JSON",
            )
        rows = payload.get("data")
        if not isinstance(rows, Sequence):
            return _failure(
                "sportmonks",
                provider_fixture_id,
                captured_at,
                BenchmarkStatus.PLAN_RESTRICTION,
                "prediction data unavailable for subscription",
            )
        return parse_sportmonks_probability(rows, provider_fixture_id, captured_at)


def parse_sportmonks_probability(
    rows: Sequence[object], provider_fixture_id: str, captured_at: datetime
) -> ProbabilityBenchmark:
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        values = raw.get("predictions")
        if not isinstance(values, Mapping) or not {"home", "draw", "away"}.issubset(values):
            continue
        probabilities = _probabilities(values.get("home"), values.get("draw"), values.get("away"))
        if probabilities is None:
            break
        return ProbabilityBenchmark(
            provider_code="sportmonks",
            provider_fixture_id=provider_fixture_id,
            captured_at=captured_at,
            status=BenchmarkStatus.SUCCESS,
            home_probability=probabilities[0],
            draw_probability=probabilities[1],
            away_probability=probabilities[2],
        )
    return _failure(
        "sportmonks",
        provider_fixture_id,
        captured_at,
        BenchmarkStatus.MISSING_PROBABILITIES,
        "full-time result probabilities are absent or invalid",
    )


def _probabilities(home: object, draw: object, away: object) -> tuple[float, float, float] | None:
    try:
        values = tuple(_percentage(value) for value in (home, draw, away))
    except (TypeError, ValueError):
        return None
    if any(not math.isfinite(value) or value < 0 for value in values):
        return None
    total = sum(values)
    if total <= 0:
        return None
    return cast(tuple[float, float, float], tuple(value / total for value in values))


def _percentage(value: object) -> float:
    if isinstance(value, str):
        return float(value.strip().removesuffix("%")) / 100.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("probability percentage is not numeric")
    return float(value) / 100.0 if value > 1 else float(value)


def _mapping(value: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    nested = value.get(name)
    return cast(Mapping[str, Any], nested) if isinstance(nested, Mapping) else {}


def _failure(
    provider: str, fixture: str, captured_at: datetime, status: BenchmarkStatus, reason: str
) -> ProbabilityBenchmark:
    return ProbabilityBenchmark(provider, fixture, captured_at, status, failure_reason=reason)


def _http_get(url: str, headers: Mapping[str, str]) -> bytes:
    request = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return cast(bytes, response.read())
