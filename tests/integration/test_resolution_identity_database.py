"""Identity review uses existing admissions on a pre-Resolution-Center schema."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from football.product.domain import normalize_team_name
from football.product.identity_correction import correct_team_identity, revoke_team_correction
from football.product.resolution_identity import mapping_detail

from tests.integration.test_team_identity_correction import (
    identity,
    isolated_database,
    retained,
    seed,
)


def test_read_only_review_reuses_exact_crosswalk_and_retained_proof(tmp_path: Path) -> None:
    with isolated_database("202610310300") as url, psycopg.connect(url) as connection:
        home, _ = seed(connection, tmp_path)
        connection.commit()
        connection.execute("SET TRANSACTION READ ONLY")
        assert connection.execute(
            "SELECT to_regclass('football.resolution_review_events')"
        ).fetchone() == (None,)
        before = retained(connection)
        original = mapping_detail(connection, tmp_path, "team", home.source_mapping_id)
        target = mapping_detail(connection, tmp_path, "team", home.target_mapping_id)
        repeated = mapping_detail(connection, tmp_path, "team", home.source_mapping_id)
        assert original["evidence_version"] == repeated["evidence_version"]
        assert target["status"] == "VERIFIED"
        candidate = next(
            item
            for item in original["candidates"]
            if item["mapping_id"] == str(home.target_mapping_id)
        )
        assert candidate["reason"] == "EXISTING_EXPLICIT_CROSSWALK"
        assert candidate["admission_permission"] is False
        assert original["correction_options"][0]["original_decision_id"] == str(
            home.original_decision_id
        )
        assert original["affected_fixtures"]
        assert retained(connection) == before


def test_prospective_correction_and_revocation_keep_prior_identity(tmp_path: Path) -> None:
    with isolated_database("202610310300") as url, psycopg.connect(url) as connection:
        home, _ = seed(connection, tmp_path)
        before = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        prior = identity(connection, home, before)
        correction = correct_team_identity(connection, tmp_path, home)
        admitted_at = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        reviewed = mapping_detail(connection, tmp_path, "team", home.source_mapping_id)
        assert reviewed["status"] == "VERIFIED"
        assert reviewed["decision"]["canonical_id"] == str(identity(connection, home, admitted_at))
        revoke_team_correction(connection, UUID(correction["decision_id"]), "OPERATOR_REVOKED")
        revoked = mapping_detail(connection, tmp_path, "team", home.source_mapping_id)
        assert revoked["status"] == "BLOCKED"
        assert revoked["decision"]["disposition"] == "REVOKED"
        assert identity(connection, home, before) == prior
        assert identity(connection, home, admitted_at) is not None


def test_alias_only_candidates_never_change_an_admission(tmp_path: Path) -> None:
    with isolated_database("202610310300") as url, psycopg.connect(url) as connection:
        home, away = seed(connection, tmp_path)
        connection.execute(
            """UPDATE football.product_teams SET country='England' WHERE team_id=(
               SELECT team_id FROM football.team_provider_mappings WHERE id=%s)""",
            (home.source_mapping_id,),
        )
        connection.execute(
            """INSERT INTO football.product_team_aliases
               (provider_code,provider_team_id,normalized_name,country,team_id)
               SELECT 'api_football',provider_team_id,'brentford','England',team_id
               FROM football.team_provider_mappings WHERE id=%s""",
            (away.target_mapping_id,),
        )
        before = connection.execute(
            "SELECT to_jsonb(a) FROM football.product_identity_admissions a ORDER BY decision_id"
        ).fetchall()
        detail = mapping_detail(connection, tmp_path, "team", home.source_mapping_id)
        assert detail["status"] == "CONTRADICTORY"
        candidate = next(
            item
            for item in detail["candidates"]
            if item["mapping_id"] == str(away.target_mapping_id)
        )
        assert candidate["reason"] == "ALIAS_DISCOVERY_ONLY_CATEGORY_AND_FIXTURE_EVIDENCE_REQUIRED"
        assert candidate["admission_permission"] is False
        assert (
            connection.execute(
                "SELECT to_jsonb(a) FROM football.product_identity_admissions a "
                "ORDER BY decision_id"
            ).fetchall()
            == before
        )
        connection.execute(
            "UPDATE football.product_team_aliases SET normalized_name=%s "
            "WHERE provider_code='api_football'",
            (normalize_team_name("Brentford Women"),),
        )
        without_women = mapping_detail(connection, tmp_path, "team", home.source_mapping_id)
        assert not any(
            item["mapping_id"] == str(away.target_mapping_id)
            for item in without_women["candidates"]
        )


def test_missing_source_stays_protected(tmp_path: Path) -> None:
    with isolated_database("202610310300") as url, psycopg.connect(url) as connection:
        home, _ = seed(connection, tmp_path)
        target = mapping_detail(connection, tmp_path, "team", home.target_mapping_id)
        (tmp_path / "raw/api_football.json").unlink()
        missing = mapping_detail(connection, tmp_path, "team", home.target_mapping_id)
        assert target["status"] == "VERIFIED"
        assert missing["status"] == "BLOCKED"
        assert missing["decision"]["reason"] == "RETAINED_SOURCE_EVIDENCE_REQUIRED"
        assert missing["evidence_version"] != target["evidence_version"]


def test_missing_mapping_is_reported_without_creating_an_identity(tmp_path: Path) -> None:
    with (
        isolated_database("202610310300") as url,
        psycopg.connect(url) as connection,
        pytest.raises(ValueError, match="current mapping not found"),
    ):
        mapping_detail(connection, tmp_path, "team", uuid4())
