-- +goose Up

-- Candidate IDs are selected separately. Eligibility always uses the latest
-- dated decision, including revocation and corrected effective team identities.
-- +goose StatementBegin
CREATE FUNCTION football.product_eligible_fixture_history_at(
    knowledge_time timestamptz, fixture_keys uuid[]
) RETURNS TABLE (
    fixture_id uuid, competition_id uuid, home_team_id uuid, away_team_id uuid,
    kickoff_at timestamptz, home_goals smallint, away_goals smallint,
    home_xg double precision, away_xg double precision, source_provider_code text,
    source_snapshot_id uuid, source_kickoff_precision text, known_at timestamptz
) LANGUAGE sql STABLE AS $$
    SELECT latest.fixture_id,latest.competition_id,latest.home_team_id,latest.away_team_id,
           latest.kickoff_at,latest.home_goals,latest.away_goals,latest.home_xg,latest.away_xg,
           latest.source_provider_code,latest.source_snapshot_id,latest.source_kickoff_precision,
           GREATEST(latest.source_known_at,latest.decided_at)
    FROM (SELECT DISTINCT unnest(fixture_keys) AS fixture_id) candidate
    JOIN LATERAL (
        SELECT d.* FROM football.product_match_history_decisions d
        WHERE d.fixture_id=candidate.fixture_id AND d.decided_at<=knowledge_time
        ORDER BY d.decided_at DESC,d.decision_id DESC LIMIT 1
    ) latest ON true
    WHERE latest.eligible AND latest.source_known_at<=knowledge_time
$$;
-- +goose StatementEnd

-- +goose Down
DROP FUNCTION football.product_eligible_fixture_history_at(timestamptz,uuid[]);
