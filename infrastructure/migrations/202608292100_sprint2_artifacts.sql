-- +goose Up

CREATE TABLE football.model_fit_runs (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    model_family text NOT NULL CHECK (model_family IN (
        'TEAM_ELO',
        'DIXON_COLES_GOALS',
        'CORNER_POISSON',
        'CORNER_NEGATIVE_BINOMIAL',
        'CALIBRATION_PLATT',
        'CALIBRATION_ISOTONIC',
        'CALIBRATION_MULTICLASS'
    )),
    fit_spec_sha256 football.sha256_hex NOT NULL,
    status text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'reused')),
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((status = 'running') = (completed_at IS NULL)),
    CHECK ((status = 'failed') OR error_code IS NULL)
);

CREATE INDEX model_fit_runs_spec_idx
    ON football.model_fit_runs (fit_spec_sha256, started_at DESC);

CREATE TABLE football.model_artifacts (
    id uuid PRIMARY KEY,
    model_family text NOT NULL CHECK (model_family IN (
        'TEAM_ELO',
        'DIXON_COLES_GOALS',
        'CORNER_POISSON',
        'CORNER_NEGATIVE_BINOMIAL',
        'CALIBRATION_PLATT',
        'CALIBRATION_ISOTONIC',
        'CALIBRATION_MULTICLASS'
    )),
    fit_spec_sha256 football.sha256_hex NOT NULL UNIQUE,
    logical_model_state_sha256 football.sha256_hex NOT NULL,
    schema_version text NOT NULL CHECK (schema_version ~ '^[a-z0-9][a-z0-9._-]*$'),
    algorithm_version text NOT NULL CHECK (algorithm_version ~ '^[a-z0-9][a-z0-9._-]*$'),
    serializer_version text NOT NULL CHECK (serializer_version ~ '^[a-z0-9][a-z0-9._-]*$'),
    manifest_path text NOT NULL CHECK (
        manifest_path <> ''
        AND manifest_path !~ '(^/|(^|/)\.\.(/|$))'
    ),
    manifest_sha256 football.sha256_hex NOT NULL,
    status text NOT NULL CHECK (status IN ('published', 'rejected', 'retired')),
    published_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (id, model_family)
);

CREATE TABLE football.model_artifact_files (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    model_artifact_id uuid NOT NULL REFERENCES football.model_artifacts (id),
    relative_path text NOT NULL CHECK (
        relative_path <> ''
        AND relative_path !~ '(^/|(^|/)\.\.(/|$))'
    ),
    media_type text NOT NULL CHECK (media_type <> ''),
    physical_sha256 football.sha256_hex NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (model_artifact_id, relative_path)
);

CREATE TABLE football.model_artifact_inputs (
    model_artifact_id uuid NOT NULL REFERENCES football.model_artifacts (id),
    dataset_version_id uuid NOT NULL,
    source_snapshot_id uuid NOT NULL,
    feature_set_version text NOT NULL CHECK (
        feature_set_version ~ '^[a-z0-9][a-z0-9._-]*$'
    ),
    football_cutoff timestamptz NOT NULL,
    knowledge_cutoff timestamptz NOT NULL,
    quality_policy_sha256 football.sha256_hex NOT NULL,
    target_set_sha256 football.sha256_hex NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (model_artifact_id, dataset_version_id),
    FOREIGN KEY (dataset_version_id, source_snapshot_id)
        REFERENCES football.dataset_versions (id, source_snapshot_id)
);

CREATE TABLE football.baseline_forecasts (
    id uuid PRIMARY KEY,
    semantic_sha256 football.sha256_hex NOT NULL UNIQUE,
    match_id uuid NOT NULL REFERENCES football.matches (id),
    prediction_cutoff timestamptz NOT NULL,
    dataset_version_id uuid NOT NULL,
    source_snapshot_id uuid NOT NULL,
    feature_set_version text NOT NULL CHECK (
        feature_set_version ~ '^[a-z0-9][a-z0-9._-]*$'
    ),
    probability_variant text NOT NULL CHECK (
        probability_variant IN ('MODEL_RAW', 'MODEL_CALIBRATED')
    ),
    payload_path text NOT NULL CHECK (
        payload_path <> ''
        AND payload_path !~ '(^/|(^|/)\.\.(/|$))'
    ),
    payload_sha256 football.sha256_hex NOT NULL,
    target_set_sha256 football.sha256_hex NOT NULL,
    status text NOT NULL CHECK (status = 'published'),
    published_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (dataset_version_id, source_snapshot_id)
        REFERENCES football.dataset_versions (id, source_snapshot_id)
);

CREATE INDEX baseline_forecasts_match_cutoff_idx
    ON football.baseline_forecasts (match_id, prediction_cutoff DESC);

CREATE TABLE football.forecast_artifacts (
    forecast_id uuid NOT NULL REFERENCES football.baseline_forecasts (id),
    model_artifact_id uuid NOT NULL REFERENCES football.model_artifacts (id),
    artifact_role text NOT NULL CHECK (artifact_role IN ('PRIMARY', 'CALIBRATOR')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (forecast_id, model_artifact_id),
    UNIQUE (forecast_id, artifact_role)
);

CREATE TABLE football.sprint2_evaluation_runs (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    policy_version text NOT NULL CHECK (policy_version ~ '^[a-z0-9][a-z0-9._-]*$'),
    dataset_version_id uuid NOT NULL,
    source_snapshot_id uuid NOT NULL,
    target_set_sha256 football.sha256_hex NOT NULL,
    report_path text NOT NULL CHECK (
        report_path <> ''
        AND report_path !~ '(^/|(^|/)\.\.(/|$))'
    ),
    report_sha256 football.sha256_hex NOT NULL,
    status text NOT NULL CHECK (status IN ('PASS', 'PASS_WITH_WARNINGS', 'FAIL')),
    completed_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (dataset_version_id, source_snapshot_id)
        REFERENCES football.dataset_versions (id, source_snapshot_id),
    UNIQUE (policy_version, dataset_version_id, target_set_sha256, report_sha256)
);

CREATE TABLE football.model_promotion_events (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    model_artifact_id uuid NOT NULL REFERENCES football.model_artifacts (id),
    evaluation_run_id uuid NOT NULL REFERENCES football.sprint2_evaluation_runs (id),
    role text NOT NULL CHECK (role ~ '^[a-z][a-z0-9_/-]*$'),
    designation text NOT NULL CHECK (
        designation IN ('BASELINE_APPROVED', 'CALIBRATION_APPROVED', 'RETIRED')
    ),
    recorded_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (role, recorded_at, id)
);

CREATE INDEX model_promotion_events_role_idx
    ON football.model_promotion_events (role, recorded_at DESC, id DESC);
