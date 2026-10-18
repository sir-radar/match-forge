"""Immutable coverage evidence; existing R3 provider history remains an independent owner."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from psycopg import Connection, sql

from football.coverage.resources import (
    CanonicalCoverage,
    CanonicalCoverageScope,
    CoverageError,
    CoverageMetrics,
    ProviderCoverage,
)
from football.providers.resource_capabilities import ResourceScope
from football.storage.raw import ImmutableFileStore, ImmutableWrite

type CoverageReport = ProviderCoverage | CanonicalCoverage


@dataclass(frozen=True, slots=True)
class PreparedCoverage:
    report: CoverageReport
    artifact: ImmutableWrite


@dataclass(frozen=True, slots=True)
class CoverageRecord:
    report_id: UUID
    scope: ResourceScope | CanonicalCoverageScope
    knowledge_cutoff: datetime
    known_at: datetime
    metrics: CoverageMetrics
    observed: int | None
    supporting_providers: tuple[str, ...]
    artifact_path: str
    artifact_sha256: str


def _path(report: CoverageReport) -> str:
    kind = "provider" if isinstance(report, ProviderCoverage) else "canonical"
    return f"coverage/{kind}/v1/{report.sha256}.json"


def prepare_coverage(root: Path, report: CoverageReport) -> PreparedCoverage:
    checked = replace(report)
    artifact = ImmutableFileStore(root).publish(_path(checked), checked.to_bytes())
    return PreparedCoverage(checked, artifact)


class CoverageRegistry:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def register(self, prepared: PreparedCoverage) -> UUID:
        report, artifact = replace(prepared.report), prepared.artifact
        if (artifact.relative_path, artifact.sha256, artifact.size_bytes) != (
            _path(report),
            report.sha256,
            len(report.to_bytes()),
        ):
            raise CoverageError("prepared coverage metadata differs from the measured inputs")
        try:
            if artifact.path.is_symlink() or artifact.path.read_bytes() != report.to_bytes():
                raise CoverageError("coverage artifact bytes differ")
        except OSError as error:
            raise CoverageError("coverage artifact bytes are unavailable") from error
        with self._connection.transaction():
            self._register(report, artifact)
        return report.report_id

    def _register(self, report: CoverageReport, artifact: ImmutableWrite) -> None:
        metrics = report.metrics
        scope_columns: tuple[str, ...]
        scope_values: tuple[object, ...]
        if isinstance(report, ProviderCoverage):
            provider = self._connection.execute(
                "SELECT id FROM football.providers WHERE code=%s", (report.scope.provider,)
            ).fetchone()
            if provider is None:
                raise CoverageError("coverage provider is not registered")
            table = "provider_resource_coverage"
            scope_columns = (
                "provider_id",
                "resource_type",
                "competition_key",
                "season_key",
                "observed",
            )
            scope_values = (
                provider[0],
                report.scope.resource_type,
                report.scope.competition,
                report.scope.season,
                report.observed,
            )
        else:
            providers = self._connection.execute(
                "SELECT code FROM football.providers WHERE code=ANY(%s)",
                (list(report.supporting_providers),),
            ).fetchall()
            if {row[0] for row in providers} != set(report.supporting_providers):
                raise CoverageError("canonical supporting providers are not registered")
            table = "canonical_resource_coverage"
            scope_columns = ("competition_id", "season_id", "resource_type", "supporting_providers")
            scope_values = (
                report.scope.competition_id,
                report.scope.season_id,
                report.scope.resource_type,
                list(report.supporting_providers),
            )
        count_columns = (
            ("expected", "qualified")
            if isinstance(report, ProviderCoverage)
            else ("expected_canonical_units", "qualified_canonical_units")
        )
        columns = (
            "report_id",
            *scope_columns,
            "knowledge_cutoff",
            *count_columns,
            "contract_version",
            "artifact_path",
            "artifact_sha256",
        )
        values = (
            report.report_id,
            *scope_values,
            report.knowledge_cutoff,
            metrics.expected,
            metrics.qualified,
            "1",
            artifact.relative_path,
            artifact.sha256,
        )
        names = sql.SQL(",").join(map(sql.Identifier, columns))
        self._connection.execute(
            sql.SQL(
                "INSERT INTO football.{}({}) VALUES ({}) ON CONFLICT (report_id) DO NOTHING"
            ).format(
                sql.Identifier(table), names, sql.SQL(",").join(sql.Placeholder() for _ in values)
            ),
            values,
        )
        actual = self._connection.execute(
            sql.SQL("SELECT {} FROM football.{} WHERE report_id=%s").format(
                names, sql.Identifier(table)
            ),
            (report.report_id,),
        ).fetchone()
        if actual != values:
            raise CoverageError("registered coverage conflicts with its immutable input evidence")

    def provider_at(
        self, scope: ResourceScope, knowledge_cutoff: datetime
    ) -> CoverageRecord | None:
        _aware(knowledge_cutoff)
        row = self._connection.execute(
            """
            SELECT r.report_id,r.knowledge_cutoff,r.known_at,r.expected,r.qualified,r.observed,
                ARRAY[]::text[],r.artifact_path,r.artifact_sha256
            FROM football.provider_resource_coverage r
            JOIN football.providers p ON p.id=r.provider_id
            WHERE p.code=%s AND r.resource_type=%s
              AND r.competition_key IS NOT DISTINCT FROM %s AND r.season_key IS NOT DISTINCT FROM %s
              AND r.knowledge_cutoff<=%s AND r.known_at<=%s
            ORDER BY r.knowledge_cutoff DESC,r.known_at DESC,r.publication_sequence DESC LIMIT 1
            """,
            (
                scope.provider,
                scope.resource_type,
                scope.competition,
                scope.season,
                knowledge_cutoff,
                knowledge_cutoff,
            ),
        ).fetchone()
        return _record(scope, row) if row else None

    def canonical_at(
        self, scope: CanonicalCoverageScope, knowledge_cutoff: datetime
    ) -> CoverageRecord | None:
        _aware(knowledge_cutoff)
        row = self._connection.execute(
            """
            SELECT report_id,knowledge_cutoff,known_at,expected_canonical_units,
                qualified_canonical_units,NULL::bigint,
                supporting_providers,artifact_path,artifact_sha256
            FROM football.canonical_resource_coverage
            WHERE competition_id=%s AND season_id=%s AND resource_type=%s
              AND knowledge_cutoff<=%s AND known_at<=%s
            ORDER BY knowledge_cutoff DESC,known_at DESC,publication_sequence DESC LIMIT 1
            """,
            (
                scope.competition_id,
                scope.season_id,
                scope.resource_type,
                knowledge_cutoff,
                knowledge_cutoff,
            ),
        ).fetchone()
        return _record(scope, row) if row else None


def _aware(value: datetime) -> None:
    if value.utcoffset() is None:
        raise CoverageError("coverage knowledge cutoff requires a timezone")


def _record(scope: ResourceScope | CanonicalCoverageScope, row: tuple[Any, ...]) -> CoverageRecord:
    return CoverageRecord(
        row[0],
        scope,
        row[1],
        row[2],
        CoverageMetrics(row[3], row[4]),
        row[5],
        tuple(row[6]),
        row[7],
        row[8],
    )


def load_coverage(root: Path, record: CoverageRecord) -> dict[str, object]:
    path = ImmutableFileStore(root).path_for(record.artifact_path)
    if path.is_symlink():
        raise CoverageError("coverage artifact must not be a symlink")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise CoverageError("coverage artifact bytes are unavailable") from error
    if hashlib.sha256(payload).hexdigest() != record.artifact_sha256:
        raise CoverageError("coverage artifact checksum mismatch")
    report = json.loads(payload)
    kind = "ProviderCoverage" if isinstance(record.scope, ResourceScope) else "CanonicalCoverage"
    expected_id = uuid5(NAMESPACE_URL, f"matchforge:coverage:{kind}:" + record.artifact_sha256)
    metrics = record.metrics.to_dict()
    if isinstance(record.scope, ResourceScope):
        metrics["observed"] = record.observed
    else:
        metrics["expected_canonical_units"] = metrics.pop("expected")
        metrics["qualified_canonical_units"] = metrics.pop("qualified")
        metrics["supporting_providers"] = list(record.supporting_providers)
    if (
        not isinstance(report, dict)
        or report.get("contract") != kind
        or report.get("contract_version") != "1"
        or expected_id != record.report_id
        or report.get("scope") != record.scope.to_dict()
        or report.get("metrics") != metrics
        or report.get("knowledge_cutoff") != record.knowledge_cutoff.astimezone(UTC).isoformat()
    ):
        raise CoverageError("coverage artifact differs from its registered measurement")
    return report
