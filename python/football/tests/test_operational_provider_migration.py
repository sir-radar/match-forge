from pathlib import Path


def test_operational_provider_migration_preserves_observations_and_experiment_isolation() -> None:
    migration = Path(
        "infrastructure/migrations/202610090300_operational_provider_sync.sql"
    ).read_text(encoding="utf-8")

    assert "product_provider_fixture_observations" in migration
    assert "semantic_sha256 football.sha256_hex NOT NULL UNIQUE" in migration
    assert "source_updated_at timestamptz" in migration
    assert "development_only boolean NOT NULL DEFAULT true CHECK (development_only)" in migration
    assert "point_in_time_eligibility" in migration
    assert "external_prediction_result_revisions" in migration
    assert "'FOTMOB_SYNC'" in migration and "'PITCHAPI_SYNC'" in migration


def test_score_basis_migration_distinguishes_knockout_results() -> None:
    migration = Path(
        "infrastructure/migrations/202610090400_external_prediction_score_basis.sql"
    ).read_text(encoding="utf-8")

    assert "result_score_basis" in migration
    assert "'EXTRA_TIME', 'PENALTY_SHOOTOUT', 'UNKNOWN'" in migration


def test_reconciliation_migration_keeps_reviewable_decisions() -> None:
    migration = Path(
        "infrastructure/migrations/202610090500_operational_provider_reconciliation.sql"
    ).read_text(encoding="utf-8")

    assert "product_provider_mapping_decisions" in migration
    assert "'AUTO_ACCEPTED', 'MANUAL_ACCEPTED', 'REVIEW_REQUIRED', 'CONTRADICTORY'" in migration
    assert "provider_home_team_id" in migration and "provider_away_team_id" in migration
