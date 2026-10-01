-- +goose Up

ALTER TABLE football.source_resources
    ADD COLUMN parser_version text;

UPDATE football.source_resources resource
SET parser_version = CASE provider.code
    WHEN 'openfootball' THEN 'openfootball-product-v1'
    WHEN 'football_data_uk' THEN 'football-data-uk-product-v1'
END
FROM football.source_snapshots snapshot
JOIN football.providers provider ON provider.id = snapshot.provider_id
WHERE resource.source_snapshot_id = snapshot.id
  AND provider.code IN ('openfootball', 'football_data_uk');

ALTER TABLE football.source_resources
    ADD CONSTRAINT source_resources_parser_version_nonempty
    CHECK (parser_version IS NULL OR parser_version <> '');

-- +goose Down

ALTER TABLE football.source_resources
    DROP CONSTRAINT source_resources_parser_version_nonempty;

ALTER TABLE football.source_resources
    DROP COLUMN parser_version;
