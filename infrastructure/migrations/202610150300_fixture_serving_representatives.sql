-- +goose Up
-- Current product lists only. Historical context and immutable detail references
-- continue to use their existing dated contracts and original fixture IDs.
CREATE VIEW football.product_serving_fixtures AS
SELECT f.fixture_id,
       COALESCE(competition.competition_id, f.competition_id) AS competition_id,
       f.home_team_id, f.away_team_id, f.kickoff_at, f.status,
       f.home_score, f.away_score, f.venue, f.round_name,
       f.forecast_availability, f.updated_at, f.result_score_basis, f.identity_status
FROM football.product_effective_fixtures f
LEFT JOIN LATERAL (
    SELECT min(cm.competition_id::text)::uuid AS competition_id
    FROM football.match_provider_mappings mm
    JOIN football.providers p ON p.id = mm.provider_id
    JOIN football.product_provider_fixture_observations o
      ON o.provider_code = p.code AND o.provider_match_id = mm.provider_match_id
     AND o.canonical_fixture_id = f.fixture_id
    JOIN football.competition_provider_mappings cm
      ON cm.provider_id = p.id AND cm.provider_competition_id = o.provider_competition_id
     AND cm.valid_to IS NULL AND cm.mapping_confidence = 1
     AND football.product_mapping_trusted('competition', cm.id, cm.competition_id)
    WHERE f.identity_status = 'PROVISIONAL'
      AND mm.match_id = f.fixture_id AND mm.valid_to IS NULL
      AND mm.mapping_confidence = 1
    HAVING count(DISTINCT cm.competition_id) = 1
) competition ON true
WHERE (f.identity_status <> 'PROVISIONAL' OR EXISTS (
    SELECT 1 FROM football.match_provider_mappings mapping
    WHERE mapping.match_id = f.fixture_id AND mapping.valid_to IS NULL
))
AND NOT EXISTS (
    SELECT 1 FROM football.fixture_identity_resolutions resolution
    WHERE resolution.member_fixture_id = f.fixture_id AND resolution.active
      AND resolution.resolution_status = 'DUPLICATE_RESOLVED'
      AND resolution.member_fixture_id <> resolution.representative_fixture_id
      AND resolution.created_at <= statement_timestamp()
);

-- +goose Down
DROP VIEW football.product_serving_fixtures;
