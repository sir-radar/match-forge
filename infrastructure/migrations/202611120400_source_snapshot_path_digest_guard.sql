-- +goose Up
-- Reject new or re-pointed source snapshots whose manifest checksum is the SHA-256 of the
-- manifest path string. Existing legacy rows are untouched: status updates still succeed,
-- and the trigger fires only when a row is inserted or its manifest columns change.

-- +goose StatementBegin
CREATE FUNCTION football.reject_source_snapshot_path_digest()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.manifest_sha256 = encode(sha256(convert_to(NEW.manifest_path, 'UTF8')), 'hex') THEN
        RAISE EXCEPTION 'source snapshot manifest checksum is the digest of its path'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

CREATE TRIGGER source_snapshots_reject_path_digest
BEFORE INSERT OR UPDATE OF manifest_path, manifest_sha256 ON football.source_snapshots
FOR EACH ROW EXECUTE FUNCTION football.reject_source_snapshot_path_digest();

-- +goose Down
DROP TRIGGER source_snapshots_reject_path_digest ON football.source_snapshots;
DROP FUNCTION football.reject_source_snapshot_path_digest();
