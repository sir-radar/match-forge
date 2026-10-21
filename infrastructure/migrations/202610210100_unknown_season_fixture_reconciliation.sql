-- +goose Up

-- A live provider observation has no season label. Retain it as source evidence,
-- but use a verified native fixture ID and exact fixture context to merge an
-- already-created provisional Unknown-season row with its known representative.
-- Ambiguous and conflicting rows remain untouched for review.
-- +goose StatementBegin
CREATE FUNCTION football.reconcile_unknown_season_fixtures() RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
    repaired_count integer;
BEGIN
    PERFORM football.acquire_transaction_lock(20, 'product-identity-admission', false, true);

    WITH eligible_observations AS (
        SELECT member.fixture_id AS member_fixture_id,
               target.fixture_id AS target_fixture_id,
               target.competition_id AS selected_competition_id,
               member_competition.season_label AS member_season_label,
               target_competition.season_label AS target_season_label,
               member_observation.provider_code,
               member_observation.provider_match_id,
               member_observation.observation_id AS member_observation_id,
               member_observation.source_snapshot_id AS member_snapshot_id,
               target_observation.observation_id AS target_observation_id,
               target_observation.source_snapshot_id AS target_snapshot_id
          FROM football.product_provider_fixture_observations member_observation
          JOIN football.product_fixtures member
            ON member.fixture_id = member_observation.canonical_fixture_id
          JOIN football.product_competitions member_competition
            ON member_competition.competition_id = member.competition_id
          JOIN football.product_provider_fixture_observations target_observation
            ON target_observation.provider_code = member_observation.provider_code
           AND target_observation.provider_match_id = member_observation.provider_match_id
           AND target_observation.canonical_fixture_id IS NOT NULL
           AND target_observation.canonical_fixture_id <> member.fixture_id
          JOIN football.product_fixtures target
            ON target.fixture_id = target_observation.canonical_fixture_id
          JOIN football.product_competitions target_competition
            ON target_competition.competition_id = target.competition_id
         WHERE member_observation.canonical_fixture_id IS NOT NULL
           AND member.identity_status = 'PROVISIONAL'
           AND member_competition.metadata_status = 'PROVISIONAL'
           AND COALESCE(NULLIF(lower(btrim(member_competition.season_label)), ''), 'unknown') = 'unknown'
           AND target.identity_status = 'VERIFIED'
           AND target_competition.metadata_status = 'VERIFIED'
           AND NULLIF(lower(btrim(target_competition.season_label)), '') <> 'unknown'
           AND member.home_team_id = target.home_team_id
           AND member.away_team_id = target.away_team_id
           AND member.kickoff_at = target.kickoff_at
           AND (member.home_score IS NULL OR target.home_score IS NULL
                OR (member.home_score = target.home_score
                    AND member.away_score = target.away_score))
           AND NOT EXISTS (
                SELECT 1
                  FROM football.fixture_identity_resolutions existing_target_resolution
                 WHERE existing_target_resolution.member_fixture_id = target.fixture_id
                   AND existing_target_resolution.active
                   AND (existing_target_resolution.resolution_status NOT IN (
                            'UNIQUE', 'DUPLICATE_RESOLVED')
                        OR existing_target_resolution.representative_fixture_id <> target.fixture_id)
           )
           AND NOT EXISTS (
                SELECT 1
                  FROM football.product_provider_fixture_observations conflicting_observation
                  JOIN football.product_fixtures conflicting_fixture
                    ON conflicting_fixture.fixture_id = conflicting_observation.canonical_fixture_id
                  JOIN football.product_competitions conflicting_competition
                    ON conflicting_competition.competition_id = conflicting_fixture.competition_id
                 WHERE conflicting_observation.provider_code = member_observation.provider_code
                   AND conflicting_observation.provider_match_id = member_observation.provider_match_id
                   AND conflicting_fixture.fixture_id NOT IN (member.fixture_id, target.fixture_id)
                   AND conflicting_fixture.identity_status = 'VERIFIED'
                   AND conflicting_competition.metadata_status = 'VERIFIED'
                   AND NULLIF(lower(btrim(conflicting_competition.season_label)), '') <> 'unknown'
                   AND (conflicting_fixture.home_team_id <> member.home_team_id
                        OR conflicting_fixture.away_team_id <> member.away_team_id
                        OR conflicting_fixture.kickoff_at <> member.kickoff_at
                        OR (member.home_score IS NOT NULL
                            AND conflicting_fixture.home_score IS NOT NULL
                            AND (member.home_score <> conflicting_fixture.home_score
                                 OR member.away_score <> conflicting_fixture.away_score)))
           )
    ), candidate_pairs AS (
        SELECT member_fixture_id,
               target_fixture_id,
               selected_competition_id,
               member_season_label,
               target_season_label,
               jsonb_agg(
                   jsonb_build_object(
                       'provider_code', provider_code,
                       'provider_match_id', provider_match_id,
                       'member_observation_id', member_observation_id,
                       'member_snapshot_id', member_snapshot_id,
                       'target_observation_id', target_observation_id,
                       'target_snapshot_id', target_snapshot_id
                   ) ORDER BY provider_code, provider_match_id,
                       member_observation_id, target_observation_id
               ) AS provider_evidence
          FROM eligible_observations
         GROUP BY member_fixture_id, target_fixture_id, selected_competition_id,
                  member_season_label, target_season_label
    ), unique_candidates AS (
        SELECT candidate_pairs.*,
               count(*) OVER (PARTITION BY member_fixture_id) AS candidate_count
          FROM candidate_pairs
    ), repairable AS (
        SELECT member_fixture_id,
               target_fixture_id,
               selected_competition_id,
               jsonb_build_object(
                   'rule', 'same_provider_match_id_exact_context_unique_known_season_v1',
                   'member_fixture_id', member_fixture_id,
                   'representative_fixture_id', target_fixture_id,
                   'selected_competition_id', selected_competition_id,
                   'member_season_label', member_season_label,
                   'representative_season_label', target_season_label,
                   'provider_evidence', provider_evidence
               ) AS evidence
          FROM unique_candidates
         WHERE candidate_count = 1
           AND NOT EXISTS (
                SELECT 1 FROM football.fixture_identity_resolutions existing_member_resolution
                 WHERE existing_member_resolution.member_fixture_id = unique_candidates.member_fixture_id
                   AND existing_member_resolution.active
           )
    )
    INSERT INTO football.fixture_identity_resolutions (
        canonical_real_fixture_id, member_fixture_id, representative_fixture_id,
        resolution_status, selected_competition_id, resolution_reason,
        evidence_json, evidence_sha256, resolution_version, active, created_at
    )
    SELECT target_fixture_id,
           member_fixture_id,
           target_fixture_id,
           'DUPLICATE_RESOLVED',
           selected_competition_id,
           'Exact provider fixture identity and context establish the known-season representative',
           evidence,
           encode(sha256(convert_to(evidence::text, 'UTF8')), 'hex')::football.sha256_hex,
           'UnknownSeasonProviderFixtureV1',
           true,
           clock_timestamp()
      FROM repairable
    ON CONFLICT DO NOTHING;

    GET DIAGNOSTICS repaired_count = ROW_COUNT;
    RETURN repaired_count;
END;
$$;
-- +goose StatementEnd

-- Repair rows that have a unique provider-ID-backed, context-matching target.
-- The operational sync calls the same function after future provider updates.
SELECT football.reconcile_unknown_season_fixtures();

-- +goose Down
DROP FUNCTION football.reconcile_unknown_season_fixtures();
