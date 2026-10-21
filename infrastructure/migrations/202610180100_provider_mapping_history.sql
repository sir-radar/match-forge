-- +goose Up

-- The original mapping tables remain the identity owners. Capture their states
-- for historical reads; initial rows are known at capture, never backdated.
LOCK TABLE football.competition_provider_mappings, football.season_provider_mappings,
    football.team_provider_mappings, football.player_provider_mappings,
    football.match_provider_mappings IN SHARE ROW EXCLUSIVE MODE;

CREATE TABLE football.provider_mapping_history (
    history_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subject_type text NOT NULL CHECK (subject_type IN (
        'competition', 'season', 'team', 'player', 'match')),
    mapping_id uuid NOT NULL,
    canonical_id uuid NOT NULL,
    provider_id uuid NOT NULL REFERENCES football.providers(id),
    provider_entity_id text NOT NULL CHECK (provider_entity_id <> ''),
    provider_competition_id text,
    valid_from timestamptz,
    valid_to timestamptz,
    first_seen_at timestamptz NOT NULL,
    mapping_created_at timestamptz NOT NULL,
    mapping_method text NOT NULL CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual')),
    mapping_confidence double precision NOT NULL CHECK (
        mapping_confidence >= 0 AND mapping_confidence <= 1),
    source_snapshot_id uuid NOT NULL,
    operation text NOT NULL CHECK (operation IN ('BASELINE', 'INSERT', 'UPDATE', 'DELETE')),
    recorded_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    CHECK ((subject_type = 'season') = (provider_competition_id IS NOT NULL)),
    CHECK (provider_competition_id IS NULL OR provider_competition_id <> ''),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CHECK (known_at >= recorded_at AND known_at >= first_seen_at
           AND known_at >= mapping_created_at),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots(id, provider_id)
);

CREATE INDEX provider_mapping_history_native_idx ON football.provider_mapping_history
    (subject_type, provider_id, provider_entity_id, provider_competition_id, mapping_id);
CREATE INDEX provider_mapping_history_version_idx ON football.provider_mapping_history
    (subject_type, mapping_id, known_at DESC, history_id DESC);

-- +goose StatementBegin
CREATE FUNCTION football.capture_provider_mapping_state(
    subject text, action text, state jsonb, canonical_field text, native_field text
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    captured_at timestamptz := clock_timestamp();
    knowledge_time timestamptz;
BEGIN
    SELECT greatest(captured_at, snapshot.acquired_at,
                    (state->>'first_seen_at')::timestamptz,
                    (state->>'created_at')::timestamptz,
                    (SELECT max(h.known_at) FROM football.provider_mapping_history h
                     WHERE h.subject_type = subject AND h.mapping_id = (state->>'id')::uuid))
    INTO knowledge_time FROM football.source_snapshots snapshot
    WHERE snapshot.id = (state->>'source_snapshot_id')::uuid
      AND snapshot.provider_id = (state->>'provider_id')::uuid;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'mapping history requires its registered source snapshot';
    END IF;
    INSERT INTO football.provider_mapping_history (
        subject_type, mapping_id, canonical_id, provider_id, provider_entity_id,
        provider_competition_id, valid_from, valid_to, first_seen_at, mapping_created_at,
        mapping_method, mapping_confidence, source_snapshot_id, operation, recorded_at, known_at
    ) VALUES (
        subject, (state->>'id')::uuid, (state->>canonical_field)::uuid,
        (state->>'provider_id')::uuid, state->>native_field,
        CASE WHEN subject = 'season' THEN state->>'provider_competition_id' END,
        (state->>'valid_from')::timestamptz, (state->>'valid_to')::timestamptz,
        (state->>'first_seen_at')::timestamptz, (state->>'created_at')::timestamptz,
        state->>'mapping_method', (state->>'mapping_confidence')::double precision,
        (state->>'source_snapshot_id')::uuid, action, captured_at, knowledge_time
    );
END;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.record_provider_mapping_history() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.id IS DISTINCT FROM OLD.id THEN
        RAISE EXCEPTION 'provider mapping identifiers are immutable';
    END IF;
    IF TG_OP = 'UPDATE' AND
       (to_jsonb(NEW) - 'last_seen_at') IS NOT DISTINCT FROM (to_jsonb(OLD) - 'last_seen_at') THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        PERFORM football.capture_provider_mapping_state(
            TG_ARGV[0], TG_OP, to_jsonb(OLD), TG_ARGV[1], TG_ARGV[2]);
        RETURN OLD;
    END IF;
    PERFORM football.capture_provider_mapping_state(
        TG_ARGV[0], TG_OP, to_jsonb(NEW), TG_ARGV[1], TG_ARGV[2]);
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

SELECT football.capture_provider_mapping_state(
    'competition', 'BASELINE', to_jsonb(m), 'competition_id', 'provider_competition_id'
) FROM football.competition_provider_mappings m;
SELECT football.capture_provider_mapping_state(
    'season', 'BASELINE', to_jsonb(m), 'season_id', 'provider_season_id'
) FROM football.season_provider_mappings m;
SELECT football.capture_provider_mapping_state(
    'team', 'BASELINE', to_jsonb(m), 'team_id', 'provider_team_id'
) FROM football.team_provider_mappings m;
SELECT football.capture_provider_mapping_state(
    'player', 'BASELINE', to_jsonb(m), 'player_id', 'provider_player_id'
) FROM football.player_provider_mappings m;
SELECT football.capture_provider_mapping_state(
    'match', 'BASELINE', to_jsonb(m), 'match_id', 'provider_match_id'
) FROM football.match_provider_mappings m;

CREATE TRIGGER competition_mapping_history AFTER INSERT OR UPDATE OR DELETE
    ON football.competition_provider_mappings FOR EACH ROW EXECUTE FUNCTION
    football.record_provider_mapping_history('competition', 'competition_id', 'provider_competition_id');
CREATE TRIGGER season_mapping_history AFTER INSERT OR UPDATE OR DELETE
    ON football.season_provider_mappings FOR EACH ROW EXECUTE FUNCTION
    football.record_provider_mapping_history('season', 'season_id', 'provider_season_id');
CREATE TRIGGER team_mapping_history AFTER INSERT OR UPDATE OR DELETE
    ON football.team_provider_mappings FOR EACH ROW EXECUTE FUNCTION
    football.record_provider_mapping_history('team', 'team_id', 'provider_team_id');
CREATE TRIGGER player_mapping_history AFTER INSERT OR UPDATE OR DELETE
    ON football.player_provider_mappings FOR EACH ROW EXECUTE FUNCTION
    football.record_provider_mapping_history('player', 'player_id', 'provider_player_id');
CREATE TRIGGER match_mapping_history AFTER INSERT OR UPDATE OR DELETE
    ON football.match_provider_mappings FOR EACH ROW EXECUTE FUNCTION
    football.record_provider_mapping_history('match', 'match_id', 'provider_match_id');

-- +goose StatementBegin
CREATE FUNCTION football.reject_provider_mapping_history_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'provider mapping history is immutable';
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER provider_mapping_history_immutable BEFORE UPDATE OR DELETE
    ON football.provider_mapping_history FOR EACH ROW
    EXECUTE FUNCTION football.reject_provider_mapping_history_mutation();
CREATE TRIGGER provider_mapping_history_no_truncate BEFORE TRUNCATE
    ON football.provider_mapping_history FOR EACH STATEMENT
    EXECUTE FUNCTION football.reject_provider_mapping_history_mutation();

-- +goose StatementBegin
CREATE FUNCTION football.reject_provider_mapping_truncate() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'provider mappings require recorded row changes';
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER competition_mapping_no_truncate BEFORE TRUNCATE
    ON football.competition_provider_mappings FOR EACH STATEMENT
    EXECUTE FUNCTION football.reject_provider_mapping_truncate();
CREATE TRIGGER season_mapping_no_truncate BEFORE TRUNCATE
    ON football.season_provider_mappings FOR EACH STATEMENT
    EXECUTE FUNCTION football.reject_provider_mapping_truncate();
CREATE TRIGGER team_mapping_no_truncate BEFORE TRUNCATE
    ON football.team_provider_mappings FOR EACH STATEMENT
    EXECUTE FUNCTION football.reject_provider_mapping_truncate();
CREATE TRIGGER player_mapping_no_truncate BEFORE TRUNCATE
    ON football.player_provider_mappings FOR EACH STATEMENT
    EXECUTE FUNCTION football.reject_provider_mapping_truncate();
CREATE TRIGGER match_mapping_no_truncate BEFORE TRUNCATE
    ON football.match_provider_mappings FOR EACH STATEMENT
    EXECUTE FUNCTION football.reject_provider_mapping_truncate();

REVOKE EXECUTE ON FUNCTION football.capture_provider_mapping_state(text,text,jsonb,text,text)
    FROM PUBLIC;

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'provider identity history must be preserved; roll forward';
END $$;
-- +goose StatementEnd
