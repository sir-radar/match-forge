-- +goose Up

-- Candidate decisions bound the search; dated eligibility still decides refreshes.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.enqueue_product_context_for_team_name()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    target_fixture uuid;
BEGIN
    IF OLD.name IS NOT DISTINCT FROM NEW.name THEN
        RETURN NEW;
    END IF;
    FOR target_fixture IN
        WITH changed_history AS MATERIALIZED (
            SELECT history.fixture_id, history.home_team_id, history.away_team_id,
                   history.kickoff_at, history.source_kickoff_precision,
                   min(GREATEST(history.source_known_at, history.decided_at)) AS known_at
            FROM football.product_match_history_decisions history
            WHERE NEW.team_id IN (history.home_team_id, history.away_team_id)
            GROUP BY history.fixture_id, history.home_team_id, history.away_team_id,
                     history.kickoff_at, history.source_kickoff_precision
        ), targets AS MATERIALIZED (
            SELECT target.fixture_id, target.kickoff_at,
                   LEAST(target.kickoff_at, statement_timestamp()) AS knowledge_cutoff,
                   football.product_fixture_team_at(
                       target.fixture_id, target.home_team_id,
                       LEAST(target.kickoff_at, statement_timestamp())
                   ) AS home_team_id,
                   football.product_fixture_team_at(
                       target.fixture_id, target.away_team_id,
                       LEAST(target.kickoff_at, statement_timestamp())
                   ) AS away_team_id
            FROM football.product_fixtures target
            WHERE target.kickoff_at >= (SELECT min(history.known_at) FROM changed_history history)
        ), relevant_targets AS MATERIALIZED (
            SELECT target.* FROM targets target
            WHERE EXISTS (
                SELECT 1 FROM changed_history history
                WHERE history.fixture_id <> target.fixture_id
                  AND history.known_at <= target.knowledge_cutoff
                  AND ((history.source_kickoff_precision = 'EXACT'
                        AND history.kickoff_at < target.kickoff_at)
                    OR (history.source_kickoff_precision = 'DATE_ONLY'
                        AND history.kickoff_at::date < target.kickoff_at::date))
                  AND (target.home_team_id IN (history.home_team_id, history.away_team_id)
                    OR target.away_team_id IN (history.home_team_id, history.away_team_id))
            )
        )
        SELECT target.fixture_id
        FROM relevant_targets target
        WHERE EXISTS (
            SELECT 1 FROM football.product_eligible_team_history_at(
                target.knowledge_cutoff, ARRAY[target.home_team_id, target.away_team_id]
            ) history
            WHERE history.fixture_id <> target.fixture_id
              AND NEW.team_id IN (history.home_team_id, history.away_team_id)
              AND history.known_at <= target.knowledge_cutoff
              AND ((history.source_kickoff_precision = 'EXACT'
                    AND history.kickoff_at < target.kickoff_at)
                OR (history.source_kickoff_precision = 'DATE_ONLY'
                    AND history.kickoff_at::date < target.kickoff_at::date))
        )
        ORDER BY target.fixture_id
    LOOP
        PERFORM football.enqueue_product_context_report_refresh(target_fixture);
    END LOOP;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

-- +goose Down

-- Restore only the prior trigger function; keep all rows and generations.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.enqueue_product_context_for_team_name()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    target_fixture uuid;
BEGIN
    IF OLD.name IS NOT DISTINCT FROM NEW.name THEN
        RETURN NEW;
    END IF;
    FOR target_fixture IN
        SELECT DISTINCT target.fixture_id
        FROM football.product_fixtures target
        CROSS JOIN LATERAL (
            SELECT football.product_fixture_team_at(
                target.fixture_id, target.home_team_id,
                LEAST(target.kickoff_at, statement_timestamp())
            ) AS home_team_id,
            football.product_fixture_team_at(
                target.fixture_id, target.away_team_id,
                LEAST(target.kickoff_at, statement_timestamp())
            ) AS away_team_id
        ) teams
        CROSS JOIN LATERAL football.product_eligible_team_history_at(
            LEAST(target.kickoff_at, statement_timestamp()),
            ARRAY[teams.home_team_id, teams.away_team_id]
        ) history
        WHERE history.fixture_id <> target.fixture_id
          AND NEW.team_id IN (history.home_team_id, history.away_team_id)
          AND history.known_at <= LEAST(target.kickoff_at, statement_timestamp())
          AND ((history.source_kickoff_precision = 'EXACT'
                AND history.kickoff_at < target.kickoff_at)
            OR (history.source_kickoff_precision = 'DATE_ONLY'
                AND history.kickoff_at::date < target.kickoff_at::date))
    LOOP
        PERFORM football.enqueue_product_context_report_refresh(target_fixture);
    END LOOP;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
