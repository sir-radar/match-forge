-- +goose Up

CREATE TABLE football.product_model_artifacts (
    artifact_sha256 football.sha256_hex PRIMARY KEY,
    model_id text NOT NULL CHECK (model_id <> ''),
    model_family text NOT NULL CHECK (model_family <> ''),
    model_version text NOT NULL CHECK (model_version <> ''),
    dependency_name text NOT NULL CHECK (dependency_name <> ''),
    dependency_version text NOT NULL CHECK (dependency_version <> ''),
    training_start timestamptz NOT NULL,
    training_cutoff timestamptz NOT NULL,
    dataset_sha256 football.sha256_hex NOT NULL,
    configuration_sha256 football.sha256_hex NOT NULL,
    feature_contract text NOT NULL CHECK (feature_contract <> ''),
    code_commit_sha text NOT NULL CHECK (code_commit_sha ~ '^[0-9a-f]{40}$'),
    random_seed bigint,
    manifest jsonb NOT NULL CHECK (jsonb_typeof(manifest) = 'object'),
    created_at timestamptz NOT NULL,
    CHECK (training_start <= training_cutoff),
    UNIQUE (model_id, dataset_sha256, configuration_sha256, code_commit_sha)
);

CREATE TABLE football.product_model_forecasts (
    model_forecast_id uuid PRIMARY KEY,
    semantic_sha256 football.sha256_hex NOT NULL UNIQUE,
    fixture_id uuid NOT NULL REFERENCES football.product_fixtures (fixture_id),
    model_id text NOT NULL CHECK (model_id <> ''),
    model_family text NOT NULL CHECK (model_family <> ''),
    model_version text NOT NULL CHECK (model_version <> ''),
    model_artifact_sha256 football.sha256_hex
        REFERENCES football.product_model_artifacts (artifact_sha256),
    forecast_role text NOT NULL CHECK (forecast_role IN ('RESEARCH', 'SHADOW', 'CHAMPION')),
    status text NOT NULL CHECK (status IN (
        'SUCCESS', 'INSUFFICIENT_DATA', 'UNSEEN_TEAM', 'MODEL_FIT_UNAVAILABLE',
        'MODEL_ERROR', 'INVALID_DISTRIBUTION'
    )),
    football_cutoff timestamptz NOT NULL,
    knowledge_cutoff timestamptz NOT NULL,
    knowledge_mode text NOT NULL CHECK (knowledge_mode <> ''),
    input_snapshot_sha256 football.sha256_hex NOT NULL,
    payload jsonb CHECK (payload IS NULL OR jsonb_typeof(payload) = 'object'),
    payload_sha256 football.sha256_hex,
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(warnings) = 'array'),
    failure_reason text,
    created_at timestamptz NOT NULL,
    CHECK ((status = 'SUCCESS') = (payload IS NOT NULL AND payload_sha256 IS NOT NULL)),
    CHECK (status = 'SUCCESS' OR failure_reason IS NOT NULL),
    UNIQUE (fixture_id, model_id, model_artifact_sha256, input_snapshot_sha256)
);

CREATE INDEX product_model_forecasts_fixture_model_idx
    ON football.product_model_forecasts (fixture_id, model_id, created_at DESC);
CREATE INDEX product_model_forecasts_research_idx
    ON football.product_model_forecasts (model_id, created_at DESC)
    WHERE forecast_role IN ('RESEARCH', 'SHADOW');
CREATE UNIQUE INDEX product_model_forecasts_champion_revision_idx
    ON football.product_model_forecasts (fixture_id, knowledge_cutoff)
    WHERE forecast_role = 'CHAMPION' AND status = 'SUCCESS';

CREATE TABLE football.product_model_evaluations (
    evaluation_id uuid PRIMARY KEY,
    evaluation_sha256 football.sha256_hex NOT NULL UNIQUE,
    model_id text NOT NULL CHECK (model_id <> ''),
    evaluation_policy_id text NOT NULL CHECK (evaluation_policy_id <> ''),
    dataset_role text NOT NULL CHECK (dataset_role IN ('DEVELOPMENT', 'EVALUATION')),
    target_count integer NOT NULL CHECK (target_count > 0),
    metrics jsonb NOT NULL CHECK (jsonb_typeof(metrics) = 'object'),
    report_uri text,
    created_at timestamptz NOT NULL
);

CREATE INDEX product_model_evaluations_model_idx
    ON football.product_model_evaluations (model_id, created_at DESC);

CREATE TABLE football.external_probability_benchmarks (
    benchmark_id uuid PRIMARY KEY,
    revision_sha256 football.sha256_hex NOT NULL UNIQUE,
    provider_code text NOT NULL CHECK (provider_code IN ('api_football', 'sportmonks')),
    provider_fixture_id text NOT NULL CHECK (provider_fixture_id <> ''),
    fixture_id uuid REFERENCES football.product_fixtures (fixture_id),
    mapping_status text NOT NULL CHECK (mapping_status IN ('MATCHED', 'UNMATCHED', 'AMBIGUOUS')),
    collection_status text NOT NULL CHECK (collection_status IN (
        'SUCCESS', 'DISABLED_NOT_CONFIGURED', 'TIMEOUT', 'RATE_LIMIT',
        'AUTHENTICATION_FAILURE', 'PLAN_RESTRICTION', 'FIXTURE_NOT_PREDICTABLE',
        'MAPPING_FAILURE', 'MISSING_PROBABILITIES', 'PROVIDER_OUTAGE'
    )),
    benchmark_role text NOT NULL CHECK (benchmark_role = 'BENCHMARK_ONLY'),
    captured_at timestamptz NOT NULL,
    home_probability double precision CHECK (home_probability BETWEEN 0 AND 1),
    draw_probability double precision CHECK (draw_probability BETWEEN 0 AND 1),
    away_probability double precision CHECK (away_probability BETWEEN 0 AND 1),
    provider_payload jsonb CHECK (
        provider_payload IS NULL OR jsonb_typeof(provider_payload) = 'object'
    ),
    source_snapshot_id uuid REFERENCES football.source_snapshots (id),
    failure_reason text,
    CHECK (
        collection_status <> 'SUCCESS'
        OR (
            mapping_status = 'MATCHED'
            AND home_probability IS NOT NULL
            AND draw_probability IS NOT NULL
            AND away_probability IS NOT NULL
            AND abs(home_probability + draw_probability + away_probability - 1.0) <= 1e-10
        )
    )
);

CREATE INDEX external_probability_benchmarks_fixture_idx
    ON football.external_probability_benchmarks (fixture_id, provider_code, captured_at DESC);

-- +goose StatementBegin
CREATE FUNCTION football.guard_multi_model_immutable() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'multi-model forecasting evidence is immutable';
END;
$$;
-- +goose StatementEnd

CREATE TRIGGER product_model_artifacts_immutable
BEFORE UPDATE OR DELETE ON football.product_model_artifacts
FOR EACH ROW EXECUTE FUNCTION football.guard_multi_model_immutable();

CREATE TRIGGER product_model_forecasts_immutable
BEFORE UPDATE OR DELETE ON football.product_model_forecasts
FOR EACH ROW EXECUTE FUNCTION football.guard_multi_model_immutable();

CREATE TRIGGER product_model_evaluations_immutable
BEFORE UPDATE OR DELETE ON football.product_model_evaluations
FOR EACH ROW EXECUTE FUNCTION football.guard_multi_model_immutable();

CREATE TRIGGER external_probability_benchmarks_immutable
BEFORE UPDATE OR DELETE ON football.external_probability_benchmarks
FOR EACH ROW EXECUTE FUNCTION football.guard_multi_model_immutable();

-- +goose Down

DROP TRIGGER external_probability_benchmarks_immutable ON football.external_probability_benchmarks;
DROP TRIGGER product_model_evaluations_immutable ON football.product_model_evaluations;
DROP TRIGGER product_model_forecasts_immutable ON football.product_model_forecasts;
DROP TRIGGER product_model_artifacts_immutable ON football.product_model_artifacts;
DROP FUNCTION football.guard_multi_model_immutable();
DROP TABLE football.external_probability_benchmarks;
DROP TABLE football.product_model_evaluations;
DROP TABLE football.product_model_forecasts;
DROP TABLE football.product_model_artifacts;
