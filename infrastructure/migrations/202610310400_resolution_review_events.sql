-- +goose Up
-- Review workflow only. Existing identity, source, fixture and work tables remain authoritative.
CREATE TABLE football.resolution_review_events (
    event_id uuid PRIMARY KEY DEFAULT uuidv7(),
    request_id uuid NOT NULL UNIQUE,
    case_key text NOT NULL CHECK (length(case_key) BETWEEN 1 AND 256),
    action text NOT NULL CHECK (action IN (
        'APPROVE', 'REJECT', 'CORRECT', 'QUARANTINE', 'REQUEST_EVIDENCE', 'BLOCK',
        'REVALIDATE', 'RESOLVE_DUPLICATE', 'DEFER'
    )),
    actor text NOT NULL CHECK (length(actor) BETWEEN 1 AND 128),
    reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 2000),
    evidence_version football.sha256_hex NOT NULL,
    request_sha256 football.sha256_hex NOT NULL,
    detail jsonb NOT NULL CHECK (jsonb_typeof(detail) = 'object'),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX resolution_review_case_history ON football.resolution_review_events
    (case_key, recorded_at DESC, event_id DESC);
CREATE TRIGGER resolution_review_events_append_only BEFORE UPDATE OR DELETE
    ON football.resolution_review_events FOR EACH ROW
    EXECUTE FUNCTION football.reject_dependency_lineage_mutation();

-- +goose StatementBegin
CREATE FUNCTION football.stamp_resolution_review_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.recorded_at := clock_timestamp();
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER stamp_resolution_review_event BEFORE INSERT ON football.resolution_review_events
    FOR EACH ROW EXECUTE FUNCTION football.stamp_resolution_review_event();

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'resolution review events are append-only; use a forward migration';
END $$;
-- +goose StatementEnd
