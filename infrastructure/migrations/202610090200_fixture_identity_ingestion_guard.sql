-- +goose Up

CREATE TABLE football.fixture_identity_ingestion_conflicts (
    conflict_sha256 football.sha256_hex PRIMARY KEY,
    provider_code text NOT NULL CHECK (provider_code <> ''),
    provider_match_id text NOT NULL CHECK (provider_match_id <> ''),
    source_snapshot_id uuid NOT NULL REFERENCES football.source_snapshots (id),
    existing_fixture_ids uuid[] NOT NULL CHECK (cardinality(existing_fixture_ids) > 0),
    conflict_reason text NOT NULL CHECK (conflict_reason <> ''),
    incoming_facts jsonb NOT NULL CHECK (jsonb_typeof(incoming_facts) = 'object'),
    created_at timestamptz NOT NULL
);

-- +goose StatementBegin
CREATE FUNCTION football.guard_product_history_fixture_identity() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM football.product_team_match_history existing
         WHERE existing.fixture_id <> NEW.fixture_id
           AND existing.kickoff_at = NEW.kickoff_at
           AND (
                existing.home_team_id IN (NEW.home_team_id, NEW.away_team_id)
                OR existing.away_team_id IN (NEW.home_team_id, NEW.away_team_id)
           )
    ) THEN
        RAISE EXCEPTION 'unresolved canonical fixture identity conflict at team/timestamp';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

CREATE TRIGGER product_history_fixture_identity_guard
BEFORE INSERT ON football.product_team_match_history
FOR EACH ROW EXECUTE FUNCTION football.guard_product_history_fixture_identity();

-- +goose Down

DROP TRIGGER product_history_fixture_identity_guard
    ON football.product_team_match_history;
DROP FUNCTION football.guard_product_history_fixture_identity();
DROP TABLE football.fixture_identity_ingestion_conflicts;
