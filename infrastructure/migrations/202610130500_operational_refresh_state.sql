-- +goose Up
-- Scheduling metadata; source observations and their acquisition times remain immutable.
CREATE TABLE football.product_provider_refresh_state (
    provider_code text NOT NULL,
    resource_name text NOT NULL,
    last_attempt_at timestamptz NOT NULL,
    last_success_at timestamptz,
    next_attempt_at timestamptz NOT NULL,
    failed_requests integer NOT NULL DEFAULT 0 CHECK (failed_requests >= 0),
    last_error text,
    PRIMARY KEY (provider_code, resource_name)
);

CREATE TRIGGER check_worker_publication
    BEFORE INSERT OR UPDATE OR DELETE ON football.product_provider_refresh_state
    FOR EACH STATEMENT EXECUTE FUNCTION football.check_worker_publication();

CREATE INDEX product_unresolved_lifecycle_idx ON football.product_fixtures(kickoff_at,fixture_id)
    WHERE status IN ('SCHEDULED','LIVE','HALF_TIME','SUSPENDED','INTERRUPTED','POSTPONED');

-- Current operational eligibility uses the same dated mapping decisions as ingestion.
-- This view is not a historical forecast input.
CREATE VIEW football.product_recoverable_fixtures AS
SELECT f.fixture_id,f.competition_id,f.kickoff_at,p.code AS provider_code,m.provider_match_id
FROM football.product_fixtures f
JOIN football.product_competitions competition ON competition.competition_id=f.competition_id
    AND competition.metadata_status='VERIFIED'
JOIN football.match_provider_mappings m ON m.match_id=f.fixture_id
JOIN football.providers p ON p.id=m.provider_id
WHERE p.code IN ('fotmob','pitchapi') AND f.identity_status='VERIFIED'
  AND NOT EXISTS (SELECT 1 FROM football.fixture_identity_resolutions resolution
                  WHERE resolution.member_fixture_id=f.fixture_id AND resolution.active)
  AND f.status IN ('SCHEDULED','LIVE','HALF_TIME','SUSPENDED','INTERRUPTED','POSTPONED')
  AND m.valid_to IS NULL AND m.mapping_confidence=1
  AND m.mapping_method IN ('explicit_crosswalk','manual','deterministic')
  AND EXISTS (SELECT 1 FROM football.competition_provider_mappings cm
              WHERE cm.provider_id=p.id AND cm.competition_id=f.competition_id
                AND cm.valid_to IS NULL AND cm.mapping_confidence=1
                AND football.product_mapping_trusted('competition',cm.id,cm.competition_id))
  AND EXISTS (SELECT 1 FROM football.team_provider_mappings tm
              WHERE tm.provider_id=p.id AND tm.team_id=f.home_team_id
                AND tm.valid_to IS NULL AND tm.mapping_confidence=1
                AND football.product_mapping_trusted('team',tm.id,tm.team_id))
  AND EXISTS (SELECT 1 FROM football.team_provider_mappings tm
              WHERE tm.provider_id=p.id AND tm.team_id=f.away_team_id
                AND tm.valid_to IS NULL AND tm.mapping_confidence=1
                AND football.product_mapping_trusted('team',tm.id,tm.team_id));

-- +goose Down
DROP VIEW football.product_recoverable_fixtures;
DROP INDEX football.product_unresolved_lifecycle_idx;
DROP TABLE football.product_provider_refresh_state;
