-- +goose Up
-- Resource-specific storage management: protection registry, consolidation evidence,
-- owner dispositions and durable operations. Protection is bound to immutable
-- identities (PostgreSQL system identifier + database OID, filesystem device + inode
-- + canonical path, Git common directory + worktree path), never to a name alone.
-- Nothing in this migration deletes, renames or rewrites an existing resource.

CREATE TABLE football.storage_protections (
 protection_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 backend text NOT NULL CHECK (backend IN ('postgres','filesystem','git')),
 identity_key text NOT NULL CHECK (length(identity_key) BETWEEN 3 AND 4096),
 identity jsonb NOT NULL CHECK (jsonb_typeof(identity)='object'),
 role text NOT NULL CHECK (role IN ('AUTHORITATIVE_OPERATING_DATABASE','REQUIRED_DATABASE',
   'REQUIRED_RECOVERY','REQUIRED_EVIDENCE','ACTIVE_OPERATING_FILES','OWNER_PROTECTED')),
 reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 2000),
 recorded_by text NOT NULL CHECK (length(recorded_by)>0),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE (identity_key, role)
);
-- At most one authoritative operating database per cluster. Supersession needs a
-- separately governed forward migration; the Admin workflow cannot change it.
CREATE UNIQUE INDEX storage_one_authoritative_database
 ON football.storage_protections ((identity->>'system_identifier'))
 WHERE role='AUTHORITATIVE_OPERATING_DATABASE';

CREATE TABLE football.storage_database_evidence (
 evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 identity_key text NOT NULL,
 system_identifier text NOT NULL,
 database_oid bigint NOT NULL CHECK (database_oid>0),
 database_name text NOT NULL,
 database_created_at timestamptz,
 size_bytes bigint NOT NULL CHECK (size_bytes>=0),
 authoritative_identity_key text NOT NULL,
 finding text NOT NULL CHECK (finding IN ('NO_UNIQUE_CANONICAL_IDENTITIES',
   'UNIQUE_CANONICAL_IDENTITIES_PRESENT','UNRESOLVED_SCHEMA_DIFFERENCE','UNRESOLVED_INVENTORY_ERROR')),
 unique_identity_rows bigint CHECK (unique_identity_rows>=0),
 tables jsonb NOT NULL CHECK (jsonb_typeof(tables)='object'),
 evidence_sha256 text NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
 source text NOT NULL CHECK (source IN ('ADMIN_COMPARE','INVENTORY_IMPORT')),
 observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK (identity_key<>authoritative_identity_key)
);
CREATE INDEX storage_database_evidence_latest ON football.storage_database_evidence(identity_key, observed_at DESC);

-- An owner disposition is bound to one exact evidence digest. New evidence for the
-- same database invalidates it automatically because the digest no longer matches.
CREATE TABLE football.storage_dispositions (
 disposition_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 identity_key text NOT NULL,
 evidence_sha256 text NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
 disposition text NOT NULL CHECK (disposition IN ('UNIQUE_DATA_NOT_REQUIRED','PRESERVE')),
 rationale text NOT NULL CHECK (length(rationale) BETWEEN 20 AND 4000),
 recorded_by text NOT NULL CHECK (length(recorded_by)>0),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX storage_dispositions_identity ON football.storage_dispositions(identity_key, recorded_at DESC);

CREATE TABLE football.storage_operations (
 operation_id uuid PRIMARY KEY,
 batch_id uuid NOT NULL,
 action text NOT NULL CHECK (action IN ('DELETE','QUARANTINE','RESTORE','PURGE')),
 resource_id text NOT NULL CHECK (resource_id ~ '^[0-9a-f]{64}$'),
 backend text NOT NULL CHECK (backend IN ('postgres','filesystem','git')),
 location text NOT NULL,
 identity_key text NOT NULL,
 identity jsonb NOT NULL CHECK (jsonb_typeof(identity)='object'),
 plan_sha256 text NOT NULL CHECK (plan_sha256 ~ '^[0-9a-f]{64}$'),
 approved_by text NOT NULL CHECK (length(approved_by)>0),
 confirmation text NOT NULL,
 state text NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','RUNNING','SUCCEEDED','FAILED','BLOCKED','CANCELLED')),
 expected_bytes bigint CHECK (expected_bytes>=0),
 reclaimed_bytes bigint CHECK (reclaimed_bytes>=0),
 measurement jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(measurement)='object'),
 quarantine_location text,
 restored_from uuid REFERENCES football.storage_operations(operation_id),
 error text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 started_at timestamptz,
 finished_at timestamptz,
 UNIQUE (batch_id, resource_id)
);
CREATE INDEX storage_operations_recent ON football.storage_operations(created_at DESC);
CREATE INDEX storage_operations_open ON football.storage_operations(state) WHERE state IN ('PENDING','RUNNING');
-- One open operation per resource identity prevents concurrent conflicting actions.
CREATE UNIQUE INDEX storage_operations_one_open_per_identity
 ON football.storage_operations(identity_key) WHERE state IN ('PENDING','RUNNING');

-- +goose StatementBegin
CREATE TRIGGER storage_protections_immutable BEFORE UPDATE OR DELETE ON football.storage_protections
 FOR EACH ROW EXECUTE FUNCTION football.storage_append_only();
CREATE TRIGGER storage_database_evidence_immutable BEFORE UPDATE OR DELETE ON football.storage_database_evidence
 FOR EACH ROW EXECUTE FUNCTION football.storage_append_only();
CREATE TRIGGER storage_dispositions_immutable BEFORE UPDATE OR DELETE ON football.storage_dispositions
 FOR EACH ROW EXECUTE FUNCTION football.storage_append_only();

-- Database-level last line of defence: no storage operation may ever target a
-- protected identity, whatever the API, worker or frontend believed.
CREATE FUNCTION football.storage_operation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
  RAISE EXCEPTION 'storage operation history is append-only' USING ERRCODE='55000';
 END IF;
 -- Only admission and progress are checked; a blocked or failed outcome must still be recordable.
 IF NEW.action<>'RESTORE' AND (TG_OP='INSERT' OR NEW.state IN ('RUNNING','SUCCEEDED')) AND EXISTS (
     SELECT 1 FROM football.storage_protections p WHERE p.identity_key=NEW.identity_key) THEN
  RAISE EXCEPTION 'resource % is protected; storage operations are rejected', NEW.identity_key
   USING ERRCODE='55000';
 END IF;
 IF NEW.backend='postgres' AND NEW.action<>'RESTORE' AND (TG_OP='INSERT' OR NEW.state IN ('RUNNING','SUCCEEDED'))
    AND EXISTS (SELECT 1 FROM football.storage_protections p
     WHERE p.backend='postgres' AND p.identity->>'system_identifier'=NEW.identity->>'system_identifier'
       AND p.identity->>'oid'=NEW.identity->>'oid') THEN
  RAISE EXCEPTION 'database OID % is protected', NEW.identity->>'oid' USING ERRCODE='55000';
 END IF;
 IF TG_OP='UPDATE' THEN
  IF OLD.state IN ('SUCCEEDED','FAILED','BLOCKED','CANCELLED') THEN
   RAISE EXCEPTION 'storage operation % is terminal', OLD.operation_id USING ERRCODE='55000';
  END IF;
  IF (NEW.operation_id,NEW.batch_id,NEW.action,NEW.resource_id,NEW.backend,NEW.location,NEW.identity_key,
      NEW.identity,NEW.plan_sha256,NEW.approved_by,NEW.confirmation,NEW.created_at)
     IS DISTINCT FROM (OLD.operation_id,OLD.batch_id,OLD.action,OLD.resource_id,OLD.backend,OLD.location,
      OLD.identity_key,OLD.identity,OLD.plan_sha256,OLD.approved_by,OLD.confirmation,OLD.created_at) THEN
   RAISE EXCEPTION 'storage operation identity is immutable' USING ERRCODE='55000';
  END IF;
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER storage_operations_guard BEFORE INSERT OR UPDATE OR DELETE ON football.storage_operations
 FOR EACH ROW EXECUTE FUNCTION football.storage_operation_guard();

-- Protection cannot be bypassed by recording a protection after an operation was
-- approved: the executor re-reads protections inside its fenced transaction, and
-- this trigger refuses to add a protection while a destructive operation for the
-- same identity is RUNNING, so the two can never interleave silently.
CREATE FUNCTION football.storage_protection_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM 1 FROM football.storage_operations o
  WHERE o.identity_key=NEW.identity_key AND o.state='RUNNING' FOR UPDATE;
 IF FOUND THEN
  RAISE EXCEPTION 'resource % has a running storage operation; retry after it finishes', NEW.identity_key
   USING ERRCODE='55P03';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER storage_protections_running_guard BEFORE INSERT ON football.storage_protections
 FOR EACH ROW EXECUTE FUNCTION football.storage_protection_guard();
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'storage management history requires a forward migration'; END $$;
-- +goose StatementEnd
