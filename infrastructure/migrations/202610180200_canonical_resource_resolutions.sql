-- +goose Up

-- Conclusions and lineage only. Resource values remain in typed immutable observations.
CREATE TABLE football.canonical_resource_resolutions (
    decision_id uuid PRIMARY KEY,
    publication_sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    resource_type text NOT NULL CHECK (resource_type <> ''),
    canonical_subject_id uuid NOT NULL,
    context_sha256 football.sha256_hex NOT NULL,
    disposition text NOT NULL CHECK (disposition IN ('RESOLVED','REVIEW_REQUIRED','QUARANTINED')),
    selected_observation_id uuid REFERENCES football.resource_observation_artifacts(observation_id),
    predecessor_decision_id uuid,
    knowledge_cutoff timestamptz NOT NULL,
    decided_at timestamptz NOT NULL,
    registered_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    decision_contract_version text NOT NULL CHECK (decision_contract_version = '1'),
    schema_sha256 football.sha256_hex NOT NULL,
    artifact_path text NOT NULL CHECK (
        artifact_path <> '' AND artifact_path !~ '(^/|(^|/)\.\.(/|$))'),
    artifact_sha256 football.sha256_hex NOT NULL,
    CHECK ((disposition = 'RESOLVED') = (selected_observation_id IS NOT NULL)),
    CHECK (decided_at >= knowledge_cutoff AND known_at >= decided_at AND known_at >= registered_at),
    UNIQUE (decision_id,resource_type,canonical_subject_id,context_sha256),
    UNIQUE (predecessor_decision_id),
    FOREIGN KEY (predecessor_decision_id,resource_type,canonical_subject_id,context_sha256)
        REFERENCES football.canonical_resource_resolutions(
            decision_id,resource_type,canonical_subject_id,context_sha256)
);

CREATE INDEX canonical_resource_resolution_knowledge_idx
    ON football.canonical_resource_resolutions(
        resource_type,canonical_subject_id,context_sha256,known_at DESC,publication_sequence DESC);

-- A scope has one root and each revision has at most one successor. These unique
-- constraints arbitrate concurrent publishers without an additional advisory lock.
CREATE UNIQUE INDEX canonical_resource_resolution_root_idx
    ON football.canonical_resource_resolutions(resource_type,canonical_subject_id,context_sha256)
    WHERE predecessor_decision_id IS NULL;

-- +goose StatementBegin
CREATE FUNCTION football.stamp_canonical_resolution() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    stamp timestamptz := clock_timestamp();
    parent football.canonical_resource_resolutions;
BEGIN
    NEW.registered_at := stamp;
    NEW.known_at := stamp;
    IF NEW.decided_at > stamp OR NEW.knowledge_cutoff > NEW.decided_at THEN
        RAISE EXCEPTION 'canonical decision requires available knowledge';
    END IF;
    IF NEW.predecessor_decision_id IS NOT NULL THEN
        SELECT * INTO parent FROM football.canonical_resource_resolutions
        WHERE decision_id = NEW.predecessor_decision_id;
        NEW.known_at := greatest(stamp, parent.known_at);
        IF NEW.predecessor_decision_id = NEW.decision_id
           OR NEW.decided_at < parent.decided_at
           OR NEW.knowledge_cutoff < parent.knowledge_cutoff THEN
            RAISE EXCEPTION 'canonical revision cannot precede its predecessor';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER canonical_resource_resolution_clock BEFORE INSERT
    ON football.canonical_resource_resolutions FOR EACH ROW
    EXECUTE FUNCTION football.stamp_canonical_resolution();

CREATE TABLE football.canonical_resolution_evidence (
    decision_id uuid NOT NULL REFERENCES football.canonical_resource_resolutions(decision_id),
    observation_id uuid NOT NULL REFERENCES football.resource_observation_artifacts(observation_id),
    role text NOT NULL CHECK (role IN ('SUPPORTING','CONFLICTING','UNRESOLVED')),
    observation_sha256 football.sha256_hex NOT NULL,
    canonical_value_sha256 football.sha256_hex NOT NULL,
    PRIMARY KEY (decision_id,observation_id)
);

ALTER TABLE football.canonical_resource_resolutions
    ADD CONSTRAINT canonical_selected_evidence_fk
    FOREIGN KEY (decision_id,selected_observation_id)
    REFERENCES football.canonical_resolution_evidence(decision_id,observation_id)
    DEFERRABLE INITIALLY DEFERRED;

-- +goose StatementBegin
CREATE FUNCTION football.reject_canonical_resolution_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'canonical resolution decisions and evidence are immutable';
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER canonical_resource_resolution_immutable BEFORE UPDATE OR DELETE
    ON football.canonical_resource_resolutions FOR EACH ROW
    EXECUTE FUNCTION football.reject_canonical_resolution_mutation();
CREATE TRIGGER canonical_resource_resolution_no_truncate BEFORE TRUNCATE
    ON football.canonical_resource_resolutions FOR EACH STATEMENT
    EXECUTE FUNCTION football.reject_canonical_resolution_mutation();
CREATE TRIGGER canonical_resolution_evidence_immutable BEFORE UPDATE OR DELETE
    ON football.canonical_resolution_evidence FOR EACH ROW
    EXECUTE FUNCTION football.reject_canonical_resolution_mutation();
CREATE TRIGGER canonical_resolution_evidence_no_truncate BEFORE TRUNCATE
    ON football.canonical_resolution_evidence FOR EACH STATEMENT
    EXECUTE FUNCTION football.reject_canonical_resolution_mutation();

CREATE TRIGGER check_worker_publication BEFORE INSERT
    ON football.canonical_resource_resolutions FOR EACH STATEMENT
    EXECUTE FUNCTION football.check_worker_publication();
CREATE TRIGGER check_worker_publication BEFORE INSERT
    ON football.canonical_resolution_evidence FOR EACH STATEMENT
    EXECUTE FUNCTION football.check_worker_publication();

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'canonical conclusions and their evidence must be preserved; roll forward';
END $$;
-- +goose StatementEnd
