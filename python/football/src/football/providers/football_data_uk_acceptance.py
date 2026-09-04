from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from football.contracts.source import canonical_json_bytes
from football.providers.football_data_uk import FootballDataUkSourceResourceV1
from football.providers.football_data_uk_csv import FootballDataUkCoverageReportV1
from football.providers.football_data_uk_overlap import FootballDataUkOverlapPrefixSelectionV1


class FootballDataUkAcceptanceCorpusError(ValueError):
    """The bounded Football-Data acceptance corpus lacks immutable evidence."""


@dataclass(frozen=True, slots=True)
class FootballDataUkAcceptanceCorpusManifestV1:
    """Immutable identity for the frozen Phase 1B Football-Data proof corpus."""

    corpus_id: str
    created_at: datetime
    notes_resource: FootballDataUkSourceResourceV1
    current_season_resource: FootballDataUkSourceResourceV1
    current_season_coverage: FootballDataUkCoverageReportV1
    overlap_season_resource: FootballDataUkSourceResourceV1
    overlap_season_coverage: FootballDataUkCoverageReportV1
    overlap_selection: FootballDataUkOverlapPrefixSelectionV1
    contract: str = "FootballDataUkAcceptanceCorpusManifestV1"

    def __post_init__(self) -> None:
        if self.contract != "FootballDataUkAcceptanceCorpusManifestV1":
            raise FootballDataUkAcceptanceCorpusError("unsupported acceptance corpus contract")
        if not self.corpus_id or self.created_at.tzinfo is None:
            raise FootballDataUkAcceptanceCorpusError(
                "corpus identity and timezone-aware creation time are required"
            )
        _require_resource(
            self.notes_resource,
            "schema_semantics_and_attribution",
            "notes.txt",
            "notes",
        )
        _require_resource(
            self.current_season_resource,
            "historical_league_csv",
            "mmz4281/2526/E0.csv",
            "current-season",
        )
        _require_resource(
            self.overlap_season_resource,
            "historical_league_csv",
            "mmz4281/1516/E0.csv",
            "overlap-season",
        )
        _require_coverage(
            self.current_season_coverage,
            self.current_season_resource,
            "current-season",
        )
        _require_coverage(
            self.overlap_season_coverage,
            self.overlap_season_resource,
            "overlap-season",
        )
        _require_selection(self.overlap_selection, self.overlap_season_resource)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        selection = self.overlap_selection
        return {
            "contract": self.contract,
            "corpus_id": self.corpus_id,
            "created_at": self.created_at.isoformat(),
            "source_resources": [
                _resource_ref(self.notes_resource),
                _resource_ref(self.current_season_resource),
                _resource_ref(self.overlap_season_resource),
            ],
            "coverage_reports": [
                _coverage_ref(self.current_season_coverage),
                _coverage_ref(self.overlap_season_coverage),
            ],
            "selection_rule_version": selection.selection_rule_version,
            "p1_record_indexes": [record.csv_record_index for record in selection.selected_records],
            "p1_trusted_record_indexes": sorted(selection.selected_trusted_record_indexes),
            "p1_provider_team_labels": sorted(selection.provider_team_labels),
        }


def _require_resource(
    resource: FootballDataUkSourceResourceV1,
    resource_type: str,
    source_path: str,
    label: str,
) -> None:
    if resource.resource_type != resource_type or resource.source_path != source_path:
        raise FootballDataUkAcceptanceCorpusError(f"{label} resource is outside the frozen corpus")


def _require_coverage(
    coverage: FootballDataUkCoverageReportV1,
    resource: FootballDataUkSourceResourceV1,
    label: str,
) -> None:
    if (
        coverage.resource_identity != resource.resource_identity
        or coverage.source_resource_sha256 != resource.raw_sha256
    ):
        raise FootballDataUkAcceptanceCorpusError(
            f"{label} coverage is not bound to its frozen resource"
        )


def _require_selection(
    selection: FootballDataUkOverlapPrefixSelectionV1,
    resource: FootballDataUkSourceResourceV1,
) -> None:
    if selection.selection_rule_version != "FootballDataUkOverlapPrefixSelectionV1":
        raise FootballDataUkAcceptanceCorpusError("unsupported overlap selection rule")
    if not selection.selected_records or not selection.selected_trusted_record_indexes:
        raise FootballDataUkAcceptanceCorpusError(
            "overlap selection lacks selected trusted records"
        )
    selected_indexes = {record.csv_record_index for record in selection.selected_records}
    if not selection.selected_trusted_record_indexes <= selected_indexes:
        raise FootballDataUkAcceptanceCorpusError("trusted records are outside the selected prefix")
    records = selection.ordered_records + selection.selected_records
    if any(record.source_resource_identity != resource.resource_identity for record in records):
        raise FootballDataUkAcceptanceCorpusError(
            "overlap records are not bound to the frozen resource"
        )
    selected_teams = frozenset(
        team
        for record in selection.selected_records
        for team in (record.provider_home_team_name, record.provider_away_team_name)
    )
    if selected_teams != selection.provider_team_labels:
        raise FootballDataUkAcceptanceCorpusError(
            "selected prefix does not cover the provider team set"
        )


def _resource_ref(resource: FootballDataUkSourceResourceV1) -> dict[str, str]:
    return {
        "resource_identity": resource.resource_identity,
        "source_path": resource.source_path,
        "raw_sha256": resource.raw_sha256,
    }


def _coverage_ref(coverage: FootballDataUkCoverageReportV1) -> dict[str, object]:
    return {
        "resource_identity": coverage.resource_identity,
        "source_resource_sha256": coverage.source_resource_sha256,
        "header_sha256": coverage.header_sha256,
        "row_count": coverage.row_count,
    }
