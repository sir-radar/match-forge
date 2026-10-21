-- +goose Up

CREATE TABLE football.provider_resource_authority (
    decision_id uuid PRIMARY KEY,
    publication_sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    authority_id uuid NOT NULL,
    scope_sha256 football.sha256_hex NOT NULL,
    provider_id uuid NOT NULL REFERENCES football.providers(id),
    resource_type text NOT NULL CHECK (btrim(resource_type)<>''),
    competition_key text CHECK (competition_key IS NULL OR btrim(competition_key)<>''),
    season_key text CHECK (season_key IS NULL OR btrim(season_key)<>''),
    effective_from timestamptz NOT NULL,
    effective_to timestamptz,
    authority_tier text NOT NULL CHECK (btrim(authority_tier)<>''),
    qualification_state text NOT NULL CHECK (btrim(qualification_state)<>''),
    predecessor_decision_id uuid UNIQUE,
    decided_at timestamptz NOT NULL,
    registered_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    decision_contract_version text NOT NULL CHECK (decision_contract_version='1'),
    schema_sha256 football.sha256_hex NOT NULL,
    artifact_path text NOT NULL CHECK (
        artifact_path<>'' AND artifact_path !~ '(^/|(^|/)\.\.(/|$))'),
    artifact_sha256 football.sha256_hex NOT NULL,
    CHECK (competition_key IS NOT NULL OR season_key IS NULL),
    CHECK (effective_to IS NULL OR effective_from<effective_to),
    CHECK (known_at>=registered_at AND known_at>=decided_at),
    UNIQUE (decision_id,authority_id,scope_sha256),
    FOREIGN KEY (predecessor_decision_id,authority_id,scope_sha256)
        REFERENCES football.provider_resource_authority(decision_id,authority_id,scope_sha256)
);
CREATE UNIQUE INDEX provider_resource_authority_root_idx
    ON football.provider_resource_authority(authority_id) WHERE predecessor_decision_id IS NULL;
CREATE INDEX provider_resource_authority_knowledge_idx
    ON football.provider_resource_authority(provider_id,resource_type,competition_key,season_key,
        authority_id,known_at DESC,publication_sequence DESC);

-- +goose StatementBegin
CREATE FUNCTION football.stamp_provider_resource_authority() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    stamp timestamptz := clock_timestamp();
    parent football.provider_resource_authority;
BEGIN
    NEW.registered_at := stamp;
    NEW.known_at := stamp;
    IF NEW.decided_at>stamp THEN
        RAISE EXCEPTION 'authority cannot be published before its decision time';
    END IF;
    IF NEW.predecessor_decision_id IS NOT NULL THEN
        SELECT * INTO parent FROM football.provider_resource_authority
        WHERE decision_id=NEW.predecessor_decision_id;
        IF NEW.decision_id=NEW.predecessor_decision_id OR NEW.decided_at<parent.decided_at
           OR ROW(NEW.provider_id,NEW.resource_type,NEW.competition_key,NEW.season_key)
              IS DISTINCT FROM ROW(parent.provider_id,parent.resource_type,parent.competition_key,parent.season_key)
        THEN
            RAISE EXCEPTION 'authority revision requires the same scope and nondecreasing clock';
        END IF;
        NEW.known_at := greatest(stamp,parent.known_at);
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER provider_resource_authority_clock BEFORE INSERT
    ON football.provider_resource_authority FOR EACH ROW
    EXECUTE FUNCTION football.stamp_provider_resource_authority();

-- +goose StatementBegin
CREATE FUNCTION football.reject_provider_resource_authority_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'provider resource authority history is immutable';
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER provider_resource_authority_immutable BEFORE UPDATE OR DELETE
    ON football.provider_resource_authority FOR EACH ROW
    EXECUTE FUNCTION football.reject_provider_resource_authority_mutation();
CREATE TRIGGER provider_resource_authority_no_truncate BEFORE TRUNCATE
    ON football.provider_resource_authority FOR EACH STATEMENT
    EXECUTE FUNCTION football.reject_provider_resource_authority_mutation();
CREATE TRIGGER check_worker_publication BEFORE INSERT
    ON football.provider_resource_authority FOR EACH STATEMENT
    EXECUTE FUNCTION football.check_worker_publication();

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'provider resource authority history must be preserved; roll forward';
END $$;
-- +goose StatementEnd
