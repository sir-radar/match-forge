-- +goose Up

CREATE TABLE football.provider_resource_coverage (
    report_id uuid PRIMARY KEY,
    publication_sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    provider_id uuid NOT NULL REFERENCES football.providers(id),
    resource_type text NOT NULL CHECK (btrim(resource_type)<>''),
    competition_key text CHECK (competition_key IS NULL OR btrim(competition_key)<>''),
    season_key text CHECK (season_key IS NULL OR btrim(season_key)<>''),
    knowledge_cutoff timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    expected bigint CHECK (expected>=0),
    observed bigint NOT NULL CHECK (observed>=0),
    qualified bigint NOT NULL CHECK (qualified>=0 AND qualified<=observed),
    coverage_ratio double precision GENERATED ALWAYS AS (
        CASE WHEN expected>0 THEN qualified::double precision/expected ELSE NULL END) STORED,
    status text GENERATED ALWAYS AS (
        CASE WHEN expected IS NULL OR expected=0 THEN 'UNKNOWN'
             WHEN qualified=expected THEN 'COMPLETE' ELSE 'PARTIAL' END) STORED,
    contract_version text NOT NULL CHECK (contract_version='1'),
    artifact_path text NOT NULL CHECK (
        artifact_path<>'' AND artifact_path !~ '(^/|(^|/)\.\.(/|$))'),
    artifact_sha256 football.sha256_hex NOT NULL,
    CHECK (expected IS NULL OR qualified<=expected),
    CHECK (competition_key IS NOT NULL OR season_key IS NULL),
    CHECK (known_at>=knowledge_cutoff)
);
CREATE INDEX provider_resource_coverage_at_idx ON football.provider_resource_coverage(
    provider_id,resource_type,competition_key,season_key,knowledge_cutoff DESC,known_at DESC);

CREATE TABLE football.canonical_resource_coverage (
    report_id uuid PRIMARY KEY,
    publication_sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    competition_id uuid NOT NULL,
    season_id uuid NOT NULL,
    resource_type text NOT NULL CHECK (btrim(resource_type)<>''),
    knowledge_cutoff timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    expected_canonical_units bigint CHECK (expected_canonical_units>=0),
    qualified_canonical_units bigint NOT NULL CHECK (qualified_canonical_units>=0),
    supporting_providers text[] NOT NULL,
    coverage_ratio double precision GENERATED ALWAYS AS (
        CASE WHEN expected_canonical_units>0 THEN qualified_canonical_units::double precision/expected_canonical_units ELSE NULL END) STORED,
    status text GENERATED ALWAYS AS (
        CASE WHEN expected_canonical_units IS NULL OR expected_canonical_units=0 THEN 'UNKNOWN'
             WHEN qualified_canonical_units=expected_canonical_units THEN 'COMPLETE' ELSE 'PARTIAL' END) STORED,
    contract_version text NOT NULL CHECK (contract_version='1'),
    artifact_path text NOT NULL CHECK (
        artifact_path<>'' AND artifact_path !~ '(^/|(^|/)\.\.(/|$))'),
    artifact_sha256 football.sha256_hex NOT NULL,
    CHECK (expected_canonical_units IS NULL OR qualified_canonical_units<=expected_canonical_units),
    CHECK ((qualified_canonical_units=0)=(cardinality(supporting_providers)=0)),
    CHECK (array_position(supporting_providers,NULL) IS NULL),
    CHECK (known_at>=knowledge_cutoff),
    FOREIGN KEY (season_id,competition_id) REFERENCES football.seasons(id,competition_id)
);
CREATE INDEX canonical_resource_coverage_at_idx ON football.canonical_resource_coverage(
    competition_id,season_id,resource_type,knowledge_cutoff DESC,known_at DESC);

-- +goose StatementBegin
CREATE FUNCTION football.stamp_resource_coverage() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.known_at := clock_timestamp();
    IF NEW.knowledge_cutoff>NEW.known_at THEN
        RAISE EXCEPTION 'coverage cannot use future knowledge';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
-- +goose StatementBegin
CREATE FUNCTION football.reject_resource_coverage_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'resource coverage snapshots are immutable';
END;
$$;
-- +goose StatementEnd
-- +goose StatementBegin
DO $$
DECLARE relation text;
BEGIN
    FOREACH relation IN ARRAY ARRAY['provider_resource_coverage','canonical_resource_coverage'] LOOP
        EXECUTE format('CREATE TRIGGER resource_coverage_clock BEFORE INSERT ON football.%I
            FOR EACH ROW EXECUTE FUNCTION football.stamp_resource_coverage()',relation);
        EXECUTE format('CREATE TRIGGER resource_coverage_immutable BEFORE UPDATE OR DELETE ON football.%I
            FOR EACH ROW EXECUTE FUNCTION football.reject_resource_coverage_mutation()',relation);
        EXECUTE format('CREATE TRIGGER resource_coverage_no_truncate BEFORE TRUNCATE ON football.%I
            FOR EACH STATEMENT EXECUTE FUNCTION football.reject_resource_coverage_mutation()',relation);
        EXECUTE format('CREATE TRIGGER check_worker_publication BEFORE INSERT ON football.%I
            FOR EACH STATEMENT EXECUTE FUNCTION football.check_worker_publication()',relation);
    END LOOP;
END $$;
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'coverage evidence must be preserved; roll forward';
END $$;
-- +goose StatementEnd
