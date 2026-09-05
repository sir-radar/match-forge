-- +goose Up

CREATE TABLE football.dependency_edges (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    upstream_kind text NOT NULL CHECK (upstream_kind IN (
        'SOURCE_RESOURCE', 'CANONICAL_OBSERVATION', 'DATASET',
        'MODEL_ARTIFACT', 'FORECAST', 'EVALUATION'
    )),
    upstream_id uuid NOT NULL,
    relationship text NOT NULL CHECK (relationship IN (
        'INPUT_TO', 'DERIVED_FROM', 'BUILT_FROM', 'FITTED_FROM',
        'FORECAST_WITH', 'EVALUATED_WITH'
    )),
    downstream_kind text NOT NULL CHECK (downstream_kind IN (
        'SOURCE_RESOURCE', 'CANONICAL_OBSERVATION', 'DATASET',
        'MODEL_ARTIFACT', 'FORECAST', 'EVALUATION'
    )),
    downstream_id uuid NOT NULL,
    contract_version text NOT NULL DEFAULT 'dependency-edge-v1' CHECK (contract_version <> ''),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (upstream_kind <> downstream_kind OR upstream_id <> downstream_id),
    UNIQUE (
        upstream_kind,
        upstream_id,
        relationship,
        downstream_kind,
        downstream_id,
        contract_version
    )
);

CREATE INDEX dependency_edges_upstream_idx
    ON football.dependency_edges (upstream_kind, upstream_id);

CREATE INDEX dependency_edges_downstream_idx
    ON football.dependency_edges (downstream_kind, downstream_id);

CREATE TABLE football.derived_state_events (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    object_kind text NOT NULL CHECK (object_kind IN (
        'DATASET', 'MODEL_ARTIFACT', 'FORECAST', 'EVALUATION'
    )),
    object_id uuid NOT NULL,
    state text NOT NULL CHECK (state IN (
        'REBUILD_REQUIRED', 'AFFECTED_BY_SOURCE_CORRECTION', 'SUPERSEDED'
    )),
    reason text NOT NULL CHECK (reason <> ''),
    cause_change_set_id uuid NOT NULL REFERENCES football.canonical_change_sets (id),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (object_kind, object_id, state, cause_change_set_id)
);

CREATE INDEX derived_state_events_object_recorded_idx
    ON football.derived_state_events (object_kind, object_id, recorded_at DESC, id DESC);

-- +goose StatementBegin
CREATE FUNCTION football.reject_dependency_lineage_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'dependency lineage is append-only';
END;
$$ LANGUAGE plpgsql;
-- +goose StatementEnd

CREATE TRIGGER dependency_edges_append_only
BEFORE UPDATE OR DELETE ON football.dependency_edges
FOR EACH ROW EXECUTE FUNCTION football.reject_dependency_lineage_mutation();

CREATE TRIGGER derived_state_events_append_only
BEFORE UPDATE OR DELETE ON football.derived_state_events
FOR EACH ROW EXECUTE FUNCTION football.reject_dependency_lineage_mutation();

-- +goose StatementBegin
CREATE FUNCTION football.require_trusted_derived_state_cause() RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM football.canonical_change_sets AS change_set
        WHERE change_set.id = NEW.cause_change_set_id
          AND change_set.status IN ('published', 'verified_existing')
          AND change_set.publication_scope = 'REAL_PROVIDER'
    ) THEN
        RAISE EXCEPTION 'derived state events require a trusted real-provider change set';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
-- +goose StatementEnd

CREATE TRIGGER derived_state_events_require_trusted_cause
BEFORE INSERT ON football.derived_state_events
FOR EACH ROW EXECUTE FUNCTION football.require_trusted_derived_state_cause();

-- +goose StatementBegin
CREATE FUNCTION football.require_dependency_replacement() RETURNS trigger AS $$
BEGIN
    IF NEW.state = 'SUPERSEDED' AND NOT EXISTS (
        SELECT 1
        FROM football.dependency_edges AS edge
        WHERE edge.upstream_kind = NEW.object_kind
          AND edge.upstream_id = NEW.object_id
          AND edge.relationship = 'DERIVED_FROM'
          AND edge.downstream_kind = NEW.object_kind
    ) THEN
        RAISE EXCEPTION 'superseded state requires a registered replacement edge';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
-- +goose StatementEnd

CREATE TRIGGER derived_state_events_require_replacement
BEFORE INSERT ON football.derived_state_events
FOR EACH ROW EXECUTE FUNCTION football.require_dependency_replacement();

INSERT INTO football.dependency_edges
    (upstream_kind, upstream_id, relationship, downstream_kind, downstream_id)
SELECT 'SOURCE_RESOURCE', input.source_resource_id, 'INPUT_TO', 'DATASET', input.dataset_version_id
FROM football.dataset_inputs AS input
JOIN football.source_resources AS resource ON resource.id = input.source_resource_id
JOIN football.source_snapshots AS snapshot ON snapshot.id = resource.source_snapshot_id
WHERE snapshot.source_kind = 'REAL_PROVIDER'
ON CONFLICT DO NOTHING;

INSERT INTO football.dependency_edges
    (upstream_kind, upstream_id, relationship, downstream_kind, downstream_id)
SELECT 'DATASET', input.dataset_version_id, 'FITTED_FROM', 'MODEL_ARTIFACT', input.model_artifact_id
FROM football.model_artifact_inputs AS input
ON CONFLICT DO NOTHING;

INSERT INTO football.dependency_edges
    (upstream_kind, upstream_id, relationship, downstream_kind, downstream_id)
SELECT 'MODEL_ARTIFACT', artifact.model_artifact_id, 'FORECAST_WITH', 'FORECAST', artifact.forecast_id
FROM football.forecast_artifacts AS artifact
ON CONFLICT DO NOTHING;

INSERT INTO football.dependency_edges
    (upstream_kind, upstream_id, relationship, downstream_kind, downstream_id)
SELECT 'DATASET', evaluation.dataset_version_id, 'EVALUATED_WITH', 'EVALUATION', evaluation.id
FROM football.sprint2_evaluation_runs AS evaluation
ON CONFLICT DO NOTHING;
