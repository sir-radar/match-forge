-- +goose Up

-- Resolve each possible target's participants once per history statement.
-- A competition admission can append hundreds of decisions for the same targets.
-- Keep qualification and durable invalidation in the caller's transaction.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.enqueue_product_context_for_history()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    target_fixture uuid;
BEGIN
    FOR target_fixture IN
        WITH targets AS MATERIALIZED (
            SELECT target.fixture_id, target.kickoff_at,
                   football.product_fixture_team_at(
                       target.fixture_id, target.home_team_id,
                       LEAST(target.kickoff_at, statement_timestamp())
                   ) AS home_team_id,
                   football.product_fixture_team_at(
                       target.fixture_id, target.away_team_id,
                       LEAST(target.kickoff_at, statement_timestamp())
                   ) AS away_team_id
            FROM football.product_fixtures target
            WHERE target.kickoff_at >= (
                SELECT min(GREATEST(history.source_known_at, history.decided_at))
                FROM new_history_decisions history
            )
        )
        SELECT target.fixture_id
        FROM targets target
        WHERE EXISTS (
            SELECT 1 FROM new_history_decisions history
            WHERE target.fixture_id <> history.fixture_id
              AND target.kickoff_at >= GREATEST(history.source_known_at, history.decided_at)
              AND ((history.source_kickoff_precision = 'EXACT'
                    AND target.kickoff_at > history.kickoff_at)
                OR (history.source_kickoff_precision = 'DATE_ONLY'
                    AND target.kickoff_at::date > history.kickoff_at::date))
              AND (target.home_team_id IN (history.home_team_id, history.away_team_id)
                OR target.away_team_id IN (history.home_team_id, history.away_team_id))
        )
        ORDER BY target.fixture_id
    LOOP
        PERFORM football.enqueue_product_context_report_refresh(target_fixture);
    END LOOP;
    RETURN NULL;
END;
$$;
-- +goose StatementEnd

DROP TRIGGER enqueue_product_context_for_history ON football.product_match_history_decisions;
CREATE TRIGGER enqueue_product_context_for_history
    AFTER INSERT ON football.product_match_history_decisions
    REFERENCING NEW TABLE AS new_history_decisions
    FOR EACH STATEMENT EXECUTE FUNCTION football.enqueue_product_context_for_history();

-- +goose Down
-- Existing append-only decisions and queue generations must remain inspectable.
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'batched history context refresh is a forward-only migration'; END $$;
-- +goose StatementEnd
