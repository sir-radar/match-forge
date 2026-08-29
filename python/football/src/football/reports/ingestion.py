from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid5

from football.contracts.source import canonical_json_bytes
from football.datasets import EventDatasetPublicationResult
from football.ingestion import AcquisitionResult, CanonicalIngestionResult
from football.storage.raw import ImmutableFileConflict, ImmutableFileStore
from football.validation import DatasetValidationResult

_REPORT_NAMESPACE = UUID("bac252a5-e1c3-4ab0-b18b-8ce21a4759ac")


class IngestionReportError(RuntimeError):
    """An immutable ingestion report cannot be safely published."""


@dataclass(frozen=True)
class ReportSource:
    role: str
    acquisition: AcquisitionResult
    source_snapshot_id: UUID


@dataclass(frozen=True)
class IngestionReportPublication:
    report_id: UUID
    json_path: Path
    markdown_path: Path
    json_sha256: str
    markdown_sha256: str
    status: str


def publish_competition_ingestion_report(
    data_root: Path,
    source: ReportSource,
    canonical: CanonicalIngestionResult,
) -> IngestionReportPublication:
    document = _base_document(
        operation="ingest_competitions",
        data_root=data_root,
        sources=(source,),
        scope={"competition_id": None, "season_id": None},
        canonical=_canonical_counts(catalog=canonical),
        dataset=None,
        validation=None,
    )
    return _publish(data_root, document)


def publish_season_ingestion_report(
    data_root: Path,
    *,
    competition_id: int,
    season_id: int,
    sources: tuple[ReportSource, ...],
    catalog: CanonicalIngestionResult,
    matches: CanonicalIngestionResult,
    details: CanonicalIngestionResult | None,
    dataset: EventDatasetPublicationResult | None,
    validation: DatasetValidationResult | None,
) -> IngestionReportPublication:
    document = _base_document(
        operation="ingest_season",
        data_root=data_root,
        sources=sources,
        scope={"competition_id": competition_id, "season_id": season_id},
        canonical=_canonical_counts(catalog=catalog, matches=matches, details=details),
        dataset=_dataset(data_root, dataset),
        validation=_validation(validation),
    )
    return _publish(data_root, document)


def _base_document(
    *,
    operation: str,
    data_root: Path,
    sources: tuple[ReportSource, ...],
    scope: dict[str, int | None],
    canonical: dict[str, int],
    dataset: dict[str, object] | None,
    validation: dict[str, object] | None,
) -> dict[str, object]:
    if not sources:
        raise ValueError("ingestion report requires at least one source")
    revisions = {source.acquisition.manifest.snapshot.source_git_sha for source in sources}
    providers = {source.acquisition.manifest.snapshot.provider for source in sources}
    if len(revisions) != 1 or len(providers) != 1:
        raise ValueError("ingestion report sources must share one provider revision")
    source_documents = tuple(_source(data_root, source) for source in sources)
    generated_at = max(source.acquisition.manifest.acquired_at for source in sources)
    identity = {
        "operation": operation,
        "source_manifest_sha256": [source.acquisition.manifest_sha256 for source in sources],
        "scope": scope,
        "dataset_version_id": dataset.get("dataset_version_id") if dataset else None,
        "validation_run_id": validation.get("validation_run_id") if validation else None,
    }
    report_id = uuid5(
        _REPORT_NAMESPACE,
        hashlib.sha256(canonical_json_bytes(identity)).hexdigest(),
    )
    return {
        "contract": "IngestionReportV1",
        "report_id": str(report_id),
        "operation": operation,
        "generated_at": _timestamp(generated_at),
        "provider": providers.pop(),
        "source_git_sha": revisions.pop(),
        "sources": list(source_documents),
        "scope": scope,
        "canonical": canonical,
        "dataset": dataset,
        "validation": validation,
    }


def _source(data_root: Path, source: ReportSource) -> dict[str, object]:
    acquisition = source.acquisition
    return {
        "role": source.role,
        "source_snapshot_id": str(source.source_snapshot_id),
        "acquired_at": _timestamp(acquisition.manifest.acquired_at),
        "manifest_path": acquisition.manifest_path.relative_to(data_root.resolve()).as_posix(),
        "manifest_sha256": acquisition.manifest_sha256,
        "resource_count": len(acquisition.manifest.resources),
        "size_bytes": sum(resource.size_bytes for resource in acquisition.manifest.resources),
    }


def _canonical_counts(
    *,
    catalog: CanonicalIngestionResult,
    matches: CanonicalIngestionResult | None = None,
    details: CanonicalIngestionResult | None = None,
) -> dict[str, int]:
    return {
        "competitions": catalog.competitions_seen,
        "seasons": catalog.seasons_seen,
        "teams": matches.teams_seen if matches else 0,
        "players": details.players_seen if details else 0,
        "matches": matches.matches_seen if matches else 0,
        "lineup_players": details.lineup_players_seen if details else 0,
        "position_stints": details.position_stints_seen if details else 0,
        "cards": details.cards_seen if details else 0,
        "events": details.events_seen if details else 0,
    }


def _dataset(
    data_root: Path, dataset: EventDatasetPublicationResult | None
) -> dict[str, object] | None:
    if dataset is None:
        return None
    return {
        "dataset_version_id": str(dataset.dataset_version_id),
        "manifest_path": dataset.manifest_path.relative_to(data_root.resolve()).as_posix(),
        "manifest_sha256": dataset.manifest_sha256,
        "file_count": len(dataset.files),
        "row_count": sum(file.row_count for file in dataset.files),
        "size_bytes": sum(file.size_bytes for file in dataset.files),
    }


def _validation(validation: DatasetValidationResult | None) -> dict[str, object] | None:
    if validation is None:
        return None
    return {
        "validation_run_id": str(validation.validation_run_id),
        "status": validation.status,
        "finding_count": len(validation.findings),
        "findings_by_severity": _counts(finding.severity for finding in validation.findings),
        "findings_by_rule": _counts(finding.rule_code for finding in validation.findings),
        "findings_by_action": _counts(finding.action for finding in validation.findings),
    }


def _counts(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _publish(data_root: Path, document: dict[str, object]) -> IngestionReportPublication:
    report_id = UUID(str(document["report_id"]))
    base = f"reports/ingestion/report={report_id}/ingestion-report-v1"
    json_payload = canonical_json_bytes(document) + b"\n"
    markdown_payload = _markdown(document).encode("utf-8")
    store = ImmutableFileStore(data_root)
    try:
        json_write = store.publish(f"{base}.json", json_payload)
        markdown_write = store.publish(f"{base}.md", markdown_payload)
    except ImmutableFileConflict as error:
        raise IngestionReportError(f"immutable ingestion report conflict: {report_id}") from error
    status = (
        "verified_published"
        if json_write.status == markdown_write.status == "verified_existing"
        else "published"
    )
    return IngestionReportPublication(
        report_id=report_id,
        json_path=json_write.path,
        markdown_path=markdown_write.path,
        json_sha256=json_write.sha256,
        markdown_sha256=markdown_write.sha256,
        status=status,
    )


def _markdown(document: dict[str, object]) -> str:
    scope = document["scope"]
    canonical = document["canonical"]
    sources = document["sources"]
    dataset = document["dataset"]
    validation = document["validation"]
    assert isinstance(scope, dict)
    assert isinstance(canonical, dict)
    assert isinstance(sources, list)
    lines = [
        "# Ingestion report",
        "",
        f"- Report: `{document['report_id']}`",
        f"- Operation: `{document['operation']}`",
        f"- Generated at: `{document['generated_at']}`",
        f"- Provider: `{document['provider']}`",
        f"- Source revision: `{document['source_git_sha']}`",
        f"- Competition ID: `{scope['competition_id']}`",
        f"- Season ID: `{scope['season_id']}`",
        "",
        "## Canonical counts",
        "",
        "| Entity | Count |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {name} | {count} |" for name, count in canonical.items())
    lines.extend(("", "## Sources", ""))
    for source in sources:
        assert isinstance(source, dict)
        lines.append(
            f"- `{source['role']}`: snapshot `{source['source_snapshot_id']}`, "
            f"{source['resource_count']} resources, {source['size_bytes']} bytes"
        )
    lines.extend(("", "## Dataset", ""))
    if isinstance(dataset, dict):
        lines.extend(
            (
                f"- Dataset version: `{dataset['dataset_version_id']}`",
                f"- Files: {dataset['file_count']}",
                f"- Rows: {dataset['row_count']}",
                f"- Bytes: {dataset['size_bytes']}",
                f"- Manifest: `{dataset['manifest_path']}`",
            )
        )
    else:
        lines.append("No event dataset published.")
    lines.extend(("", "## Validation", ""))
    if isinstance(validation, dict):
        lines.extend(
            (
                f"- Run: `{validation['validation_run_id']}`",
                f"- Status: **{validation['status']}**",
                f"- Findings: {validation['finding_count']}",
            )
        )
        rules = validation["findings_by_rule"]
        assert isinstance(rules, dict)
        lines.extend(f"- `{rule}`: {count}" for rule, count in rules.items())
    else:
        lines.append("Not applicable; no event dataset published.")
    return "\n".join(lines) + "\n"


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
