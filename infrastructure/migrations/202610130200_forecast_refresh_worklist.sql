-- +goose Up
CREATE TABLE football.product_forecast_refresh_work (
    fixture_id uuid PRIMARY KEY REFERENCES football.product_fixtures (fixture_id),
    requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    generation bigint NOT NULL DEFAULT 1 CHECK (generation > 0),
    completed_generation bigint NOT NULL DEFAULT 0
        CHECK (completed_generation >= 0 AND completed_generation <= generation),
    completed_at timestamptz
);
CREATE INDEX product_forecast_refresh_pending_idx
    ON football.product_forecast_refresh_work (requested_at, fixture_id)
    WHERE generation > completed_generation;
CREATE TRIGGER check_worker_publication
    BEFORE INSERT OR UPDATE OR DELETE ON football.product_forecast_refresh_work
    FOR EACH STATEMENT EXECUTE FUNCTION football.check_worker_publication();

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_forecast_refresh(fixture_key uuid)
RETURNS void LANGUAGE sql AS $$
    INSERT INTO football.product_forecast_refresh_work (fixture_id)
    VALUES (fixture_key)
    ON CONFLICT (fixture_id) DO UPDATE
    SET generation = football.product_forecast_refresh_work.generation + 1,
        requested_at = CASE WHEN football.product_forecast_refresh_work.generation >
                                 football.product_forecast_refresh_work.completed_generation
                            THEN football.product_forecast_refresh_work.requested_at
                            ELSE clock_timestamp() END,
        completed_at = NULL;
$$;
-- +goose StatementEnd

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_forecast_for_fixture()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND
       (OLD.home_team_id, OLD.away_team_id, OLD.kickoff_at, OLD.status, OLD.identity_status)
       IS NOT DISTINCT FROM
       (NEW.home_team_id, NEW.away_team_id, NEW.kickoff_at, NEW.status, NEW.identity_status) THEN
        RETURN NEW;
    END IF;
    IF NEW.status = 'SCHEDULED' AND NEW.identity_status = 'VERIFIED'
       AND NEW.kickoff_at > clock_timestamp() THEN
        PERFORM football.enqueue_product_forecast_refresh(NEW.fixture_id);
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_product_forecast_for_fixture
    AFTER INSERT OR UPDATE OF home_team_id, away_team_id, kickoff_at, status, identity_status
    ON football.product_fixtures FOR EACH ROW
    EXECUTE FUNCTION football.enqueue_product_forecast_for_fixture();

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_forecast_for_history()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    WITH previous AS (
        SELECT home_team_id, away_team_id, kickoff_at, source_kickoff_precision, eligible
        FROM football.product_match_history_decisions
        WHERE fixture_id = NEW.fixture_id AND decision_id <> NEW.decision_id
        ORDER BY decided_at DESC, decision_id DESC LIMIT 1
    ), changed AS (
        SELECT NEW.home_team_id, NEW.away_team_id, NEW.kickoff_at,
               NEW.source_kickoff_precision, NEW.eligible
        UNION ALL SELECT * FROM previous
    )
    INSERT INTO football.product_forecast_refresh_work (fixture_id)
    SELECT target.fixture_id
    FROM football.product_fixtures target
    WHERE target.status = 'SCHEDULED' AND target.identity_status = 'VERIFIED'
      AND target.kickoff_at > clock_timestamp()
      AND EXISTS (
          SELECT 1 FROM changed WHERE changed.eligible
            AND (target.home_team_id IN (changed.home_team_id, changed.away_team_id)
                 OR target.away_team_id IN (changed.home_team_id, changed.away_team_id))
            AND ((changed.source_kickoff_precision = 'EXACT'
                  AND changed.kickoff_at < target.kickoff_at)
                 OR (changed.source_kickoff_precision = 'DATE_ONLY'
                     AND changed.kickoff_at::date < target.kickoff_at::date))
      )
    ORDER BY target.fixture_id
    ON CONFLICT (fixture_id) DO UPDATE
    SET generation = football.product_forecast_refresh_work.generation + 1,
        requested_at = CASE WHEN football.product_forecast_refresh_work.generation >
                                 football.product_forecast_refresh_work.completed_generation
                            THEN football.product_forecast_refresh_work.requested_at
                            ELSE clock_timestamp() END,
        completed_at = NULL;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_product_forecast_for_history
    AFTER INSERT ON football.product_match_history_decisions FOR EACH ROW
    EXECUTE FUNCTION football.enqueue_product_forecast_for_history();

INSERT INTO football.product_forecast_refresh_work (fixture_id)
SELECT fixture_id FROM football.product_fixtures
WHERE status = 'SCHEDULED' AND identity_status = 'VERIFIED'
  AND kickoff_at > clock_timestamp()
ON CONFLICT (fixture_id) DO NOTHING;

-- +goose Down
-- The worklist is operational state. Remove triggers and functions before its table.
DROP TRIGGER enqueue_product_forecast_for_history ON football.product_match_history_decisions;
DROP FUNCTION football.enqueue_product_forecast_for_history();
DROP TRIGGER enqueue_product_forecast_for_fixture ON football.product_fixtures;
DROP FUNCTION football.enqueue_product_forecast_for_fixture();
DROP FUNCTION football.enqueue_product_forecast_refresh(uuid);
DROP TRIGGER check_worker_publication ON football.product_forecast_refresh_work;
DROP TABLE football.product_forecast_refresh_work;
