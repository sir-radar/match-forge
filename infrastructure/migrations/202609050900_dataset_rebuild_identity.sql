-- +goose Up

ALTER TABLE football.dataset_versions
    ADD COLUMN build_spec_sha256 football.sha256_hex;

CREATE INDEX dataset_versions_build_spec_sha256_idx
    ON football.dataset_versions (build_spec_sha256)
    WHERE build_spec_sha256 IS NOT NULL;

-- Existing rows predate DatasetBuildSpecV1. Their immutable IDs and checksums
-- remain unchanged; only new explicit rebuilds record this checksum.

