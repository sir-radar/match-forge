-- +goose Up
-- Serving is current-state only; retained rows and mapping history are unchanged.
CREATE VIEW football.product_uncontested_provider_resources AS
SELECT resource.* FROM football.product_provider_resource_observations resource
WHERE NOT EXISTS (
    SELECT 1 FROM football.match_provider_mappings mapping
    JOIN football.providers provider ON provider.id=mapping.provider_id
    LEFT JOIN football.fixture_identity_resolutions resolution
      ON resolution.member_fixture_id=mapping.match_id AND resolution.active
    WHERE provider.code=resource.provider_code
      AND mapping.provider_match_id=resource.provider_match_id
      AND mapping.valid_to IS NULL AND mapping.mapping_confidence=1
      AND mapping.mapping_method IN ('explicit_crosswalk','manual','deterministic')
      AND coalesce(resolution.representative_fixture_id,mapping.match_id)
          <> resource.canonical_fixture_id
);

-- +goose Down
DROP VIEW football.product_uncontested_provider_resources;
