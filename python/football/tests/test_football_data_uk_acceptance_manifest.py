from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from football.normalization import normalize_football_data_uk_record
from football.providers import (
    FootballDataUkAcceptanceCorpusError,
    FootballDataUkAcceptanceCorpusManifestV1,
    FootballDataUkAcceptanceCorpusStoreV1,
    FootballDataUkSourceResourceV1,
    parse_football_data_uk_csv,
)
from football.providers.football_data_uk import FootballDataUkResourceTypeV1
from football.providers.football_data_uk_overlap import select_football_data_uk_overlap_prefix


def test_acceptance_manifest_binds_frozen_receipts_coverage_and_exact_p1_records() -> None:
    notes = _receipt("schema_semantics_and_attribution", "notes.txt", b"terms")
    current = _receipt("historical_league_csv", "mmz4281/2526/E0.csv", _csv("26"))
    overlap = _receipt("historical_league_csv", "mmz4281/1516/E0.csv", _csv("16"))
    current_validation = parse_football_data_uk_csv(current, _csv("26"))
    overlap_validation = parse_football_data_uk_csv(overlap, _csv("16"))
    selection = select_football_data_uk_overlap_prefix(
        tuple(
            normalize_football_data_uk_record(overlap, record)
            for record in overlap_validation.records
        ),
        corners_declared=True,
        trusted_record_indexes=frozenset((1,)),
    )

    manifest = FootballDataUkAcceptanceCorpusManifestV1(
        corpus_id="football-data-uk-phase1b-p1-v1",
        created_at=datetime(2026, 9, 4, 16, 0, tzinfo=UTC),
        notes_resource=notes,
        current_season_resource=current,
        current_season_coverage=current_validation.coverage,
        overlap_season_resource=overlap,
        overlap_season_coverage=overlap_validation.coverage,
        overlap_selection=selection,
    )

    manifest_data = manifest.to_dict()
    assert manifest_data["p1_record_indexes"] == [1]
    assert manifest_data["p1_trusted_record_indexes"] == [1]
    source_resources = manifest_data["source_resources"]
    assert isinstance(source_resources, list)
    overlap_resource = source_resources[2]
    assert isinstance(overlap_resource, dict)
    assert overlap_resource["raw_sha256"] == overlap.raw_sha256
    assert len(manifest.sha256) == 64


def test_acceptance_manifest_rejects_coverage_not_bound_to_its_frozen_resource() -> None:
    notes = _receipt("schema_semantics_and_attribution", "notes.txt", b"terms")
    current = _receipt("historical_league_csv", "mmz4281/2526/E0.csv", _csv("26"))
    overlap = _receipt("historical_league_csv", "mmz4281/1516/E0.csv", _csv("16"))
    overlap_validation = parse_football_data_uk_csv(overlap, _csv("16"))
    selection = select_football_data_uk_overlap_prefix(
        tuple(
            normalize_football_data_uk_record(overlap, record)
            for record in overlap_validation.records
        ),
        corners_declared=True,
        trusted_record_indexes=frozenset((1,)),
    )

    with pytest.raises(FootballDataUkAcceptanceCorpusError, match="current-season coverage"):
        FootballDataUkAcceptanceCorpusManifestV1(
            corpus_id="football-data-uk-phase1b-p1-v1",
            created_at=datetime(2026, 9, 4, 16, 0, tzinfo=UTC),
            notes_resource=notes,
            current_season_resource=current,
            current_season_coverage=overlap_validation.coverage,
            overlap_season_resource=overlap,
            overlap_season_coverage=overlap_validation.coverage,
            overlap_selection=selection,
        )


def test_acceptance_manifest_is_immutably_publishable(tmp_path: Path) -> None:
    manifest = _manifest()
    store = FootballDataUkAcceptanceCorpusStoreV1(tmp_path)

    write = store.publish(manifest)
    retry = store.publish(manifest)

    assert write.path.read_bytes() == manifest.to_bytes()
    assert retry.status == "verified_existing"


def _manifest() -> FootballDataUkAcceptanceCorpusManifestV1:
    notes = _receipt("schema_semantics_and_attribution", "notes.txt", b"terms")
    current = _receipt("historical_league_csv", "mmz4281/2526/E0.csv", _csv("26"))
    overlap = _receipt("historical_league_csv", "mmz4281/1516/E0.csv", _csv("16"))
    current_validation = parse_football_data_uk_csv(current, _csv("26"))
    overlap_validation = parse_football_data_uk_csv(overlap, _csv("16"))
    selection = select_football_data_uk_overlap_prefix(
        tuple(
            normalize_football_data_uk_record(overlap, record)
            for record in overlap_validation.records
        ),
        corners_declared=True,
        trusted_record_indexes=frozenset((1,)),
    )
    return FootballDataUkAcceptanceCorpusManifestV1(
        corpus_id="football-data-uk-phase1b-p1-v1",
        created_at=datetime(2026, 9, 4, 16, 0, tzinfo=UTC),
        notes_resource=notes,
        current_season_resource=current,
        current_season_coverage=current_validation.coverage,
        overlap_season_resource=overlap,
        overlap_season_coverage=overlap_validation.coverage,
        overlap_selection=selection,
    )


def _receipt(
    resource_type: str,
    source_path: str,
    payload: bytes,
) -> FootballDataUkSourceResourceV1:
    return FootballDataUkSourceResourceV1.from_payload(
        resource_type=cast(FootballDataUkResourceTypeV1, resource_type),
        source_path=source_path,
        payload=payload,
        observed_by_matchforge_at=datetime(2026, 9, 4, 15, 0, tzinfo=UTC),
        http_status=200,
        content_type="text/plain" if source_path == "notes.txt" else "text/csv",
    )


def _csv(season_suffix: str) -> bytes:
    return (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HC,AC\n"
        f"E0,01/01/{season_suffix},Alpha,Beta,1,0,H,0,0,D,5,4\n"
    ).encode()
