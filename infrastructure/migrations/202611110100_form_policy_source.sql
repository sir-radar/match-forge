-- +goose Up
-- Inputs for form-policy-v1. football.public_context_source stays unchanged for
-- N-1 readers and for the reports already published under its fingerprints.
-- Forecast inputs still come only from product_eligible_team_history_at.

-- A provider gives friendlies no type of their own, so the competition label is
-- the only available signal. Unclassified competitions stay visible as such.
-- +goose StatementBegin
CREATE FUNCTION football.product_competition_scope(competition_type text, competition_name text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN competition_name ~* '\mfriendl(y|ies)\M' THEN 'FRIENDLY'
        WHEN competition_type = 'LEAGUE' THEN 'LEAGUE'
        WHEN competition_type = 'CUP' THEN 'CUP'
        ELSE 'UNCLASSIFIED'
    END
$$;
-- +goose StatementEnd

-- Competition-recognized results for the given teams: finished matches on any
-- score basis and awarded matches with a recorded score. A row is usable only
-- when its current canonical state was already stored at knowledge_time, so a
-- later rewrite removes it from earlier cutoffs instead of leaking into them.
-- +goose StatementBegin
CREATE FUNCTION football.product_official_team_results_at(
    knowledge_time timestamptz, team_keys uuid[], before_kickoff timestamptz, per_team integer
) RETURNS TABLE (
    fixture_id uuid, competition_id uuid, home_team_id uuid, away_team_id uuid,
    kickoff_at timestamptz, status text, home_goals smallint, away_goals smallint,
    score_basis text, known_at timestamptz
) LANGUAGE sql STABLE AS $$
    SELECT DISTINCT ON (candidate.fixture_id)
           candidate.fixture_id, candidate.competition_id, candidate.home_team_id,
           candidate.away_team_id, candidate.kickoff_at, candidate.status,
           candidate.home_score, candidate.away_score, candidate.result_score_basis,
           candidate.updated_at
    FROM unnest(team_keys) AS team(team_id)
    CROSS JOIN LATERAL (
        SELECT side.* FROM (
            (SELECT pf.* FROM football.product_fixtures pf
             WHERE pf.home_team_id = team.team_id AND pf.kickoff_at < before_kickoff
               AND pf.status IN ('FINISHED', 'AWARDED') AND pf.home_score IS NOT NULL
               AND pf.identity_status = 'VERIFIED' AND pf.updated_at <= knowledge_time
             ORDER BY pf.kickoff_at DESC, pf.fixture_id LIMIT per_team)
            UNION ALL
            (SELECT pf.* FROM football.product_fixtures pf
             WHERE pf.away_team_id = team.team_id AND pf.kickoff_at < before_kickoff
               AND pf.status IN ('FINISHED', 'AWARDED') AND pf.home_score IS NOT NULL
               AND pf.identity_status = 'VERIFIED' AND pf.updated_at <= knowledge_time
             ORDER BY pf.kickoff_at DESC, pf.fixture_id LIMIT per_team)
        ) side
        ORDER BY side.kickoff_at DESC, side.fixture_id LIMIT per_team
    ) candidate
    WHERE per_team > 0
      AND NOT EXISTS (
        SELECT 1 FROM football.fixture_identity_resolutions resolution
        WHERE resolution.member_fixture_id = candidate.fixture_id AND resolution.active
          AND (resolution.resolution_status NOT IN ('UNIQUE', 'DUPLICATE_RESOLVED')
               OR resolution.representative_fixture_id <> candidate.fixture_id))
    ORDER BY candidate.fixture_id
$$;
-- +goose StatementEnd

-- The v1 manifest plus official results, earlier fixtures of either team that
-- still have no usable result, and the competition scope of every row.
-- +goose StatementBegin
CREATE FUNCTION football.public_context_source_v2(fixture_key uuid)
RETURNS jsonb LANGUAGE sql STABLE SET timezone = 'UTC' AS $$
    WITH target AS (
        SELECT fixture_id, competition_id, kickoff_at,
            LEAST(kickoff_at, statement_timestamp()) AS knowledge_cutoff,
            football.product_fixture_team_at(fixture_id, home_team_id,
                LEAST(kickoff_at, statement_timestamp())) AS home_team_id,
            football.product_fixture_team_at(fixture_id, away_team_id,
                LEAST(kickoff_at, statement_timestamp())) AS away_team_id
        FROM football.product_fixtures WHERE fixture_id = fixture_key
    ), base AS (
        SELECT football.public_context_source(fixture_key) AS value
    ), results AS (
        SELECT r.*, home.name AS home_team, away.name AS away_team
        FROM target t
        CROSS JOIN LATERAL football.product_official_team_results_at(
            t.knowledge_cutoff, ARRAY[t.home_team_id, t.away_team_id], t.kickoff_at, 30) r
        JOIN football.product_teams home ON home.team_id = r.home_team_id
        JOIN football.product_teams away ON away.team_id = r.away_team_id
        WHERE r.fixture_id <> t.fixture_id
    ), pending AS (
        SELECT team.team_id, p.fixture_id, p.kickoff_at, p.status
        FROM target t
        CROSS JOIN LATERAL unnest(ARRAY[t.home_team_id, t.away_team_id]) AS team(team_id)
        CROSS JOIN LATERAL (
            SELECT pf.fixture_id, pf.kickoff_at, pf.status FROM football.product_fixtures pf
            WHERE (pf.home_team_id = team.team_id OR pf.away_team_id = team.team_id)
              AND pf.fixture_id <> t.fixture_id AND pf.kickoff_at < t.kickoff_at
              AND pf.kickoff_at >= t.kickoff_at - interval '400 days'
              AND pf.identity_status = 'VERIFIED' AND pf.updated_at <= t.knowledge_cutoff
              AND (pf.status IN ('SCHEDULED', 'LIVE', 'HALF_TIME', 'SUSPENDED', 'INTERRUPTED')
                   OR (pf.status = 'AWARDED' AND pf.home_score IS NULL))
            ORDER BY pf.kickoff_at DESC, pf.fixture_id LIMIT 10
        ) p
    ), scopes AS (
        SELECT c.competition_id,
               football.product_competition_scope(c.competition_type, c.name) AS scope
        FROM football.product_competitions c
        WHERE c.competition_id IN (
            SELECT competition_id FROM target
            UNION SELECT competition_id FROM results
            UNION SELECT (item->>'competition_id')::uuid
                  FROM base, jsonb_array_elements(base.value->'history') item)
    )
    SELECT base.value || jsonb_build_object(
        'source_version', 'public-context-source-v2',
        'form_policy_version', 'form-policy-v1',
        'results', (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY r.kickoff_at DESC, r.fixture_id), '[]')
                    FROM results r),
        'pending_results', (SELECT coalesce(jsonb_agg(to_jsonb(p)
                    ORDER BY p.team_id, p.kickoff_at DESC, p.fixture_id), '[]') FROM pending p),
        'competition_scopes', (SELECT coalesce(jsonb_object_agg(s.competition_id, s.scope), '{}')
                    FROM scopes s)
    ) FROM base WHERE base.value IS NOT NULL
$$;
-- +goose StatementEnd

-- A result, or the lack of one, changes the form of the same teams' later
-- fixtures. Only fixtures that kick off after this row was stored can see it.
-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_context_for_result() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    target_fixture uuid;
    team_keys uuid[] := ARRAY[NEW.home_team_id, NEW.away_team_id];
    earliest timestamptz := NEW.kickoff_at;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF (OLD.status, OLD.home_score, OLD.away_score, OLD.result_score_basis,
            OLD.identity_status, OLD.kickoff_at, OLD.home_team_id, OLD.away_team_id)
           IS NOT DISTINCT FROM
           (NEW.status, NEW.home_score, NEW.away_score, NEW.result_score_basis,
            NEW.identity_status, NEW.kickoff_at, NEW.home_team_id, NEW.away_team_id) THEN
            RETURN NEW;
        END IF;
        team_keys := team_keys || ARRAY[OLD.home_team_id, OLD.away_team_id];
        earliest := LEAST(NEW.kickoff_at, OLD.kickoff_at);
    ELSIF NEW.status NOT IN ('FINISHED', 'AWARDED') THEN
        RETURN NEW;
    END IF;
    FOR target_fixture IN
        SELECT target.fixture_id FROM football.product_fixtures target
        WHERE target.fixture_id <> NEW.fixture_id
          AND target.kickoff_at > earliest AND target.kickoff_at >= NEW.updated_at
          AND (target.home_team_id = ANY(team_keys) OR target.away_team_id = ANY(team_keys))
        ORDER BY target.fixture_id
    LOOP
        PERFORM football.enqueue_product_context_report_refresh(target_fixture);
    END LOOP;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

CREATE TRIGGER enqueue_product_context_for_result
    AFTER INSERT OR UPDATE OF status, home_score, away_score, result_score_basis,
        identity_status, kickoff_at, home_team_id, away_team_id
    ON football.product_fixtures FOR EACH ROW
    EXECUTE FUNCTION football.enqueue_product_context_for_result();

-- +goose Down
DROP TRIGGER enqueue_product_context_for_result ON football.product_fixtures;
DROP FUNCTION football.enqueue_product_context_for_result();
DROP FUNCTION football.public_context_source_v2(uuid);
DROP FUNCTION football.product_official_team_results_at(timestamptz, uuid[], timestamptz, integer);
DROP FUNCTION football.product_competition_scope(text, text);
