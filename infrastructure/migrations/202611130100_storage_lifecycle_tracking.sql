-- +goose Up
-- Durable lifecycle state for the five-hour cleanup policy. Only two resource
-- classes exist: disposable test databases registered by the integration harness
-- (or discovered as children of a registered run) and Git worktrees. A row
-- records creation, the owner, the last verified activity, completion and the
-- current eligibility. Eligibility is recomputed and revalidated before every
-- deletion; a row never grants permission on its own, and deletion still goes
-- through storage_operations and its protection guard.

CREATE TABLE football.storage_lifecycle_resources (
 identity_key text PRIMARY KEY CHECK (length(identity_key) BETWEEN 3 AND 4096),
 resource_class text NOT NULL CHECK (resource_class IN ('TEST_DATABASE','WORKTREE')),
 backend text NOT NULL CHECK (backend IN ('postgres','git')),
 identity jsonb NOT NULL CHECK (jsonb_typeof(identity)='object'),
 location text NOT NULL CHECK (length(location)>0),
 owner_kind text NOT NULL CHECK (owner_kind IN ('INTEGRATION_HARNESS','HARNESS_CHILD','WORKTREE_DISCOVERY')),
 owner_ref jsonb NOT NULL CHECK (jsonb_typeof(owner_ref)='object'),
 created_at timestamptz NOT NULL,
 registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 last_activity_at timestamptz NOT NULL,
 activity_fingerprint text NOT NULL DEFAULT '',
 completed_at timestamptz,
 completion text CHECK (completion IN ('OWNER_EXITED','PR_MERGED')),
 state text NOT NULL DEFAULT 'ACTIVE' CHECK (state IN ('ACTIVE','WAITING','ELIGIBLE','BLOCKED','DELETING','DELETED','ABSENT')),
 eligible_at timestamptz,
 blockers jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(blockers)='array'),
 checked_at timestamptz,
 claim_token uuid,
 claimed_until timestamptz,
 operation_id uuid REFERENCES football.storage_operations(operation_id),
 reclaimed_bytes bigint CHECK (reclaimed_bytes>=0),
 CHECK ((completion IS NULL) = (completed_at IS NULL)),
 CHECK (state<>'ELIGIBLE' OR (completed_at IS NOT NULL AND eligible_at IS NOT NULL))
);
CREATE INDEX storage_lifecycle_open ON football.storage_lifecycle_resources(state)
 WHERE state NOT IN ('DELETED','ABSENT');

-- Immutable audit trail of every lifecycle decision and result.
CREATE TABLE football.storage_lifecycle_events (
 event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 identity_key text NOT NULL,
 event text NOT NULL CHECK (event IN ('REGISTERED','ACTIVITY','COMPLETED','WAITING','ELIGIBLE','BLOCKED',
   'CLAIMED','SUBMITTED','DELETED','DELETE_FAILED','ABSENT','REJECTED')),
 detail jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(detail)='object'),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX storage_lifecycle_events_recent ON football.storage_lifecycle_events(recorded_at DESC);
CREATE INDEX storage_lifecycle_events_identity ON football.storage_lifecycle_events(identity_key, recorded_at DESC);

-- +goose StatementBegin
CREATE TRIGGER storage_lifecycle_events_immutable BEFORE UPDATE OR DELETE ON football.storage_lifecycle_events
 FOR EACH ROW EXECUTE FUNCTION football.storage_append_only();

-- A lifecycle row cannot change identity, and a protected identity can never be
-- registered, marked eligible or submitted for deletion, whatever the caller
-- believed. A protection recorded later leaves the row trackable as BLOCKED.
CREATE FUNCTION football.storage_lifecycle_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
  RAISE EXCEPTION 'storage lifecycle state is retained; mark it ABSENT or DELETED instead' USING ERRCODE='55000';
 END IF;
 IF TG_OP='UPDATE' AND (NEW.identity_key,NEW.resource_class,NEW.backend,NEW.identity,NEW.owner_kind,NEW.owner_ref,NEW.created_at)
    IS DISTINCT FROM (OLD.identity_key,OLD.resource_class,OLD.backend,OLD.identity,OLD.owner_kind,OLD.owner_ref,OLD.created_at) THEN
  RAISE EXCEPTION 'storage lifecycle identity is immutable' USING ERRCODE='55000';
 END IF;
 IF TG_OP='UPDATE' AND OLD.state IN ('DELETED','ABSENT') AND NEW.state<>OLD.state THEN
  RAISE EXCEPTION 'storage lifecycle resource % is terminal', OLD.identity_key USING ERRCODE='55000';
 END IF;
 IF (TG_OP='INSERT' OR NEW.state IN ('ELIGIBLE','DELETING')) AND EXISTS (
     SELECT 1 FROM football.storage_protections p
      WHERE p.identity_key=NEW.identity_key
         OR (NEW.backend='postgres' AND p.backend='postgres'
             AND p.identity->>'system_identifier'=NEW.identity->>'system_identifier'
             AND p.identity->>'oid'=NEW.identity->>'oid')) THEN
  RAISE EXCEPTION 'resource % is protected and cannot enter the cleanup lifecycle', NEW.identity_key
   USING ERRCODE='55000';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER storage_lifecycle_guard BEFORE INSERT OR UPDATE OR DELETE ON football.storage_lifecycle_resources
 FOR EACH ROW EXECUTE FUNCTION football.storage_lifecycle_guard();
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'storage lifecycle history requires a forward migration'; END $$;
-- +goose StatementEnd
