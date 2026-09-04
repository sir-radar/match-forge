-- +goose Up

ALTER TABLE football.source_snapshots
    ADD COLUMN source_kind text NOT NULL DEFAULT 'REAL_PROVIDER' CHECK (
        source_kind IN ('REAL_PROVIDER', 'CONTRACT_FIXTURE')
    ),
    ADD COLUMN fixture_id text,
    ADD CONSTRAINT source_snapshots_fixture_identity_check CHECK (
        (source_kind = 'REAL_PROVIDER' AND fixture_id IS NULL)
        OR (source_kind = 'CONTRACT_FIXTURE' AND fixture_id IS NOT NULL AND fixture_id <> '')
    );

CREATE TABLE football.fixture_sources (
    source_snapshot_id uuid PRIMARY KEY REFERENCES football.source_snapshots (id),
    fixture_id text NOT NULL UNIQUE CHECK (fixture_id <> '')
);

-- +goose StatementBegin
CREATE FUNCTION football.require_contract_fixture_source() RETURNS trigger AS $$
DECLARE
    snapshot_fixture_id text;
BEGIN
    SELECT fixture_id INTO snapshot_fixture_id
    FROM football.source_snapshots
    WHERE id = NEW.source_snapshot_id AND source_kind = 'CONTRACT_FIXTURE';

    IF snapshot_fixture_id IS NULL OR snapshot_fixture_id <> NEW.fixture_id THEN
        RAISE EXCEPTION 'fixture source registry requires a matching contract fixture snapshot';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
-- +goose StatementEnd

CREATE TRIGGER fixture_sources_require_contract_fixture
BEFORE INSERT OR UPDATE ON football.fixture_sources
FOR EACH ROW EXECUTE FUNCTION football.require_contract_fixture_source();

CREATE TABLE football.fixture_processing_attempts (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    attempt_key football.sha256_hex NOT NULL UNIQUE,
    source_snapshot_id uuid NOT NULL,
    source_resource_id uuid NOT NULL,
    raw_sha256 football.sha256_hex NOT NULL,
    reprocess_request_id uuid REFERENCES football.quarantine_reprocess_requests (id),
    resolution_decision_id uuid REFERENCES football.resolution_decisions (id),
    processing_status text NOT NULL CHECK (processing_status IN ('quarantined', 'succeeded')),
    failure_reason text,
    publication_status text NOT NULL CHECK (publication_status IN ('not_published', 'published')),
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL,
    FOREIGN KEY (source_snapshot_id) REFERENCES football.fixture_sources (source_snapshot_id),
    FOREIGN KEY (source_resource_id, source_snapshot_id)
        REFERENCES football.source_resources (id, source_snapshot_id),
    CHECK (completed_at >= started_at),
    CHECK ((processing_status = 'quarantined') = (failure_reason IS NOT NULL)),
    CHECK ((processing_status = 'quarantined') = (publication_status = 'not_published'))
);

-- +goose StatementBegin
CREATE FUNCTION football.require_fixture_attempt_lineage() RETURNS trigger AS $$
DECLARE
    resource_sha256 football.sha256_hex;
    request_resource_id uuid;
BEGIN
    SELECT sha256 INTO resource_sha256
    FROM football.source_resources
    WHERE id = NEW.source_resource_id AND source_snapshot_id = NEW.source_snapshot_id;

    IF resource_sha256 IS NULL OR resource_sha256 <> NEW.raw_sha256 THEN
        RAISE EXCEPTION 'fixture attempt SHA must match its registered source resource';
    END IF;

    IF NEW.reprocess_request_id IS NOT NULL THEN
        SELECT quarantine.source_resource_id INTO request_resource_id
        FROM football.quarantine_reprocess_requests AS request
        JOIN football.quarantine_records AS quarantine
            ON quarantine.id = request.source_quarantine_record_id
        WHERE request.id = NEW.reprocess_request_id;

        IF request_resource_id IS NULL OR request_resource_id <> NEW.source_resource_id THEN
            RAISE EXCEPTION 'fixture attempt reprocess request must use the same source resource';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
-- +goose StatementEnd

CREATE TRIGGER fixture_attempts_require_lineage
BEFORE INSERT OR UPDATE ON football.fixture_processing_attempts
FOR EACH ROW EXECUTE FUNCTION football.require_fixture_attempt_lineage();

CREATE TABLE football.quarantine_resolution_outcomes (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    outcome_key football.sha256_hex NOT NULL UNIQUE,
    quarantine_record_id uuid NOT NULL REFERENCES football.quarantine_records (id),
    reprocess_request_id uuid NOT NULL REFERENCES football.quarantine_reprocess_requests (id),
    processing_attempt_id uuid NOT NULL REFERENCES football.fixture_processing_attempts (id),
    resolution_decision_id uuid NOT NULL REFERENCES football.resolution_decisions (id),
    outcome text NOT NULL CHECK (outcome IN ('resolved', 'still_quarantined')),
    recorded_at timestamptz NOT NULL
);

-- +goose StatementBegin
CREATE FUNCTION football.require_fixture_quarantine_outcome_lineage() RETURNS trigger AS $$
DECLARE
    quarantine_resource_id uuid;
    request_quarantine_id uuid;
    attempt_resource_id uuid;
    attempt_request_id uuid;
    attempt_decision_id uuid;
BEGIN
    SELECT source_resource_id INTO quarantine_resource_id
    FROM football.quarantine_records
    WHERE id = NEW.quarantine_record_id;

    SELECT source_quarantine_record_id INTO request_quarantine_id
    FROM football.quarantine_reprocess_requests
    WHERE id = NEW.reprocess_request_id;

    SELECT source_resource_id, reprocess_request_id, resolution_decision_id
    INTO attempt_resource_id, attempt_request_id, attempt_decision_id
    FROM football.fixture_processing_attempts
    WHERE id = NEW.processing_attempt_id;

    IF quarantine_resource_id IS NULL
       OR request_quarantine_id <> NEW.quarantine_record_id
       OR attempt_resource_id <> quarantine_resource_id
       OR attempt_request_id <> NEW.reprocess_request_id
       OR attempt_decision_id <> NEW.resolution_decision_id THEN
        RAISE EXCEPTION 'fixture quarantine outcome must retain one quarantine reprocess chain';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
-- +goose StatementEnd

CREATE TRIGGER fixture_quarantine_outcomes_require_lineage
BEFORE INSERT OR UPDATE ON football.quarantine_resolution_outcomes
FOR EACH ROW EXECUTE FUNCTION football.require_fixture_quarantine_outcome_lineage();

ALTER TABLE football.canonical_change_sets
    ADD COLUMN publication_scope text NOT NULL DEFAULT 'REAL_PROVIDER' CHECK (
        publication_scope IN ('REAL_PROVIDER', 'CONTRACT_FIXTURE')
    );

-- +goose StatementBegin
CREATE FUNCTION football.reject_fixture_dataset_version() RETURNS trigger AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM football.source_snapshots
        WHERE id = NEW.source_snapshot_id AND source_kind = 'CONTRACT_FIXTURE'
    ) THEN
        RAISE EXCEPTION 'contract fixture sources cannot create analytical datasets';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
-- +goose StatementEnd

CREATE TRIGGER dataset_versions_reject_fixture_source
BEFORE INSERT ON football.dataset_versions
FOR EACH ROW EXECUTE FUNCTION football.reject_fixture_dataset_version();
