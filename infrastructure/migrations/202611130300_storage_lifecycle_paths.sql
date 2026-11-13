-- +goose Up
-- Extends the five-hour lifecycle to policy-declared build outputs, dependency
-- caches and temporary directories inside the repository. A path is tracked by
-- device and inode, so a directory recreated after deletion is a new resource.
-- Completion means no consumer process is running and no process holds the
-- directory open or works inside it.

ALTER TABLE football.storage_lifecycle_resources
 DROP CONSTRAINT storage_lifecycle_resources_resource_class_check,
 ADD CONSTRAINT storage_lifecycle_resources_resource_class_check
  CHECK (resource_class IN ('TEST_DATABASE','WORKTREE','DISPOSABLE_PATH')),
 DROP CONSTRAINT storage_lifecycle_resources_backend_check,
 ADD CONSTRAINT storage_lifecycle_resources_backend_check CHECK (backend IN ('postgres','git','filesystem')),
 DROP CONSTRAINT storage_lifecycle_resources_owner_kind_check,
 ADD CONSTRAINT storage_lifecycle_resources_owner_kind_check
  CHECK (owner_kind IN ('INTEGRATION_HARNESS','HARNESS_CHILD','WORKTREE_DISCOVERY','POLICY_PATH')),
 DROP CONSTRAINT storage_lifecycle_resources_completion_check,
 ADD CONSTRAINT storage_lifecycle_resources_completion_check
  CHECK (completion IN ('OWNER_EXITED','PR_MERGED','CONSUMERS_IDLE'));

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'storage lifecycle history requires a forward migration'; END $$;
-- +goose StatementEnd
