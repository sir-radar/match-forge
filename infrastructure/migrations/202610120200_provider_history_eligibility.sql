-- +goose Up

ALTER TABLE football.product_fixtures ADD COLUMN identity_status text NOT NULL
    DEFAULT 'VERIFIED' CHECK (identity_status IN ('VERIFIED', 'PROVISIONAL', 'QUARANTINED'));
ALTER TABLE football.product_competitions ADD COLUMN metadata_status text NOT NULL
    DEFAULT 'VERIFIED' CHECK (metadata_status IN ('VERIFIED', 'PROVISIONAL'));
ALTER TABLE football.product_competitions DROP CONSTRAINT product_competitions_competition_type_check;
ALTER TABLE football.product_competitions ADD CONSTRAINT product_competitions_competition_type_check
    CHECK (competition_type IN ('LEAGUE', 'CUP', 'UNKNOWN'));

UPDATE football.product_fixtures fixture SET identity_status = 'PROVISIONAL'
WHERE EXISTS (
    SELECT 1 FROM football.product_provider_mapping_decisions decision
    WHERE decision.candidate_fixture_id = fixture.fixture_id
      AND decision.evidence->>'identity_scope' = 'provider'
);
UPDATE football.product_competitions competition
SET metadata_status = 'PROVISIONAL', country = 'Unknown', continent = 'Unknown',
    competition_type = 'UNKNOWN', season_label = 'Unknown'
WHERE competition.country = 'World' AND competition.availability_status = 'SOURCE_DATA_INCOMPLETE'
  AND EXISTS (SELECT 1 FROM football.product_fixtures fixture
              WHERE fixture.competition_id = competition.competition_id
                AND fixture.identity_status = 'PROVISIONAL');

-- Raw history is retained. Consumers must also apply their own knowledge cutoff.
CREATE VIEW football.product_eligible_match_history AS
SELECT history.*, snapshot.acquired_at AS known_at
FROM football.product_team_match_history history
JOIN football.source_snapshots snapshot ON snapshot.id = history.source_snapshot_id
LEFT JOIN football.product_fixtures fixture ON fixture.fixture_id = history.fixture_id
WHERE COALESCE(fixture.identity_status, 'VERIFIED') = 'VERIFIED'
  AND NOT EXISTS (
      SELECT 1 FROM football.fixture_identity_resolutions resolution
      WHERE resolution.member_fixture_id = history.fixture_id AND resolution.active
        AND (resolution.resolution_status NOT IN ('UNIQUE', 'DUPLICATE_RESOLVED')
             OR resolution.representative_fixture_id <> history.fixture_id)
  );

-- +goose Down

DROP VIEW football.product_eligible_match_history;
ALTER TABLE football.product_competitions DROP CONSTRAINT product_competitions_competition_type_check;
UPDATE football.product_competitions SET competition_type = 'LEAGUE' WHERE competition_type = 'UNKNOWN';
ALTER TABLE football.product_competitions ADD CONSTRAINT product_competitions_competition_type_check
    CHECK (competition_type IN ('LEAGUE', 'CUP'));
ALTER TABLE football.product_competitions DROP COLUMN metadata_status;
ALTER TABLE football.product_fixtures DROP COLUMN identity_status;
