-- +goose Up

ALTER TABLE football.product_sync_runs DROP CONSTRAINT product_sync_runs_sync_type_check;
ALTER TABLE football.product_sync_runs ADD CONSTRAINT product_sync_runs_sync_type_check CHECK (
    sync_type IN ('MVP_SYNC','OPENFOOTBALL','FOOTBALL_DATA_UK','HISTORY_BACKFILL',
        'FORECAST_REFRESH','CONTEXT_REPORTS','PUBLIC_REPORTS','EXTERNAL_PREDICTIONS',
        'FOTMOB_SYNC','PITCHAPI_SYNC','ALL_DATA')
);
DROP INDEX football.product_sync_runs_one_active_lane_idx;
CREATE UNIQUE INDEX product_sync_runs_one_active_lane_idx
    ON football.product_sync_runs ((CASE
        WHEN sync_type='FOTMOB_SYNC' THEN 'LIVE_FOTMOB'
        WHEN sync_type='PITCHAPI_SYNC' THEN 'LIVE_PITCHAPI'
        WHEN sync_type IN ('CONTEXT_REPORTS','PUBLIC_REPORTS') THEN 'PUBLIC_REPORTS'
        ELSE 'BULK' END)) WHERE status IN ('QUEUED','RUNNING');

ALTER TABLE football.product_context_report_refresh_work
    ADD COLUMN last_attempt_at timestamptz,
    ADD COLUMN retry_at timestamptz NOT NULL DEFAULT '-infinity',
    ADD COLUMN last_error text;
CREATE TABLE football.product_report_refresh_work (
    report_kind text NOT NULL CHECK (report_kind IN ('PERFORMANCE','COMPARISON')),
    scope_id uuid NOT NULL,
    horizon text NOT NULL CHECK (horizon IN ('LATEST','7D','3D','24H','6H','1H','15M')),
    requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    generation bigint NOT NULL DEFAULT 1 CHECK (generation>0),
    completed_generation bigint NOT NULL DEFAULT 0
        CHECK (completed_generation>=0 AND completed_generation<=generation),
    completed_at timestamptz,
    last_attempt_at timestamptz,
    retry_at timestamptz NOT NULL DEFAULT '-infinity',
    last_error text,
    PRIMARY KEY (report_kind,scope_id,horizon),
    CHECK (report_kind='PERFORMANCE' OR horizon='LATEST')
);
CREATE INDEX product_report_refresh_pending_idx
    ON football.product_report_refresh_work (report_kind,retry_at,last_attempt_at,requested_at,scope_id)
    WHERE generation>completed_generation;
CREATE TRIGGER check_worker_publication BEFORE INSERT OR UPDATE OR DELETE
    ON football.product_report_refresh_work FOR EACH STATEMENT
    EXECUTE FUNCTION football.check_worker_publication();

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_report(kind text,scope uuid,forecast_horizon text)
RETURNS void LANGUAGE sql AS $$
    INSERT INTO football.product_report_refresh_work(report_kind,scope_id,horizon)
    VALUES(kind,scope,forecast_horizon)
    ON CONFLICT (report_kind,scope_id,horizon) DO UPDATE
    SET generation=football.product_report_refresh_work.generation+1,
        requested_at=CASE WHEN football.product_report_refresh_work.generation>
            football.product_report_refresh_work.completed_generation
            THEN football.product_report_refresh_work.requested_at ELSE clock_timestamp() END,
        completed_at=NULL,
        retry_at=CASE WHEN football.product_report_refresh_work.generation=
            football.product_report_refresh_work.completed_generation THEN '-infinity'::timestamptz
            ELSE football.product_report_refresh_work.retry_at END;
$$;
-- +goose StatementEnd
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.enqueue_product_context_report_refresh(fixture_key uuid)
RETURNS void LANGUAGE sql AS $$
    INSERT INTO football.product_context_report_refresh_work(fixture_id) VALUES(fixture_key)
    ON CONFLICT (fixture_id) DO UPDATE
    SET generation=football.product_context_report_refresh_work.generation+1,
        requested_at=CASE WHEN football.product_context_report_refresh_work.generation>
            football.product_context_report_refresh_work.completed_generation
            THEN football.product_context_report_refresh_work.requested_at ELSE clock_timestamp() END,
        retry_at=CASE WHEN football.product_context_report_refresh_work.generation=
            football.product_context_report_refresh_work.completed_generation THEN '-infinity'::timestamptz
            ELSE football.product_context_report_refresh_work.retry_at END,
        completed_at=NULL;
$$;
-- +goose StatementEnd
-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_performance(competition uuid)
RETURNS void LANGUAGE sql AS $$
    SELECT football.enqueue_product_report('PERFORMANCE',competition,horizon)
    FROM unnest(ARRAY['LATEST','7D','3D','24H','6H','1H','15M']) horizon;
$$;
-- +goose StatementEnd
-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_reports_for_fixture()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prediction uuid;
BEGIN
    PERFORM football.enqueue_product_performance(NEW.competition_id);
    IF TG_OP='UPDATE' AND OLD.competition_id IS DISTINCT FROM NEW.competition_id THEN
        PERFORM football.enqueue_product_performance(OLD.competition_id);
    END IF;
    FOR prediction IN SELECT prediction_id FROM football.external_predictions
        WHERE fixture_id=NEW.fixture_id ORDER BY prediction_id
    LOOP
        PERFORM football.enqueue_product_report('COMPARISON',prediction,'LATEST');
    END LOOP;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_product_reports_for_fixture
    AFTER INSERT OR UPDATE OF competition_id,kickoff_at,status,home_score,away_score,
        result_score_basis,identity_status,updated_at ON football.product_fixtures
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_product_reports_for_fixture();

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_reports_for_forecast()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE competition uuid; prediction uuid;
BEGIN
    SELECT competition_id INTO competition FROM football.product_fixtures
        WHERE fixture_id=NEW.fixture_id;
    PERFORM football.enqueue_product_performance(competition);
    FOR prediction IN SELECT prediction_id FROM football.external_predictions
        WHERE fixture_id=NEW.fixture_id ORDER BY prediction_id
    LOOP
        PERFORM football.enqueue_product_report('COMPARISON',prediction,'LATEST');
    END LOOP;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_product_reports_for_forecast AFTER INSERT ON football.product_forecasts
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_product_reports_for_forecast();

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_reports_for_prediction()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM football.enqueue_product_report('COMPARISON',NEW.prediction_id,'LATEST');
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_product_reports_for_prediction AFTER INSERT ON football.external_predictions
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_product_reports_for_prediction();

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_reports_for_resolution()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE competition uuid;
BEGIN
    SELECT competition_id INTO competition FROM football.product_fixtures
        WHERE fixture_id=NEW.member_fixture_id;
    IF competition IS NOT NULL THEN
        PERFORM football.enqueue_product_performance(competition);
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_product_reports_for_resolution
    AFTER INSERT OR UPDATE ON football.fixture_identity_resolutions
    FOR EACH ROW EXECUTE FUNCTION football.enqueue_product_reports_for_resolution();

SELECT football.enqueue_product_performance(competition_id) FROM (
    SELECT DISTINCT fixture.competition_id FROM football.product_fixtures fixture
    JOIN football.product_forecasts forecast USING (fixture_id)
) competitions;
SELECT football.enqueue_product_report('COMPARISON',prediction_id,'LATEST')
    FROM football.external_predictions ORDER BY prediction_id;

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'report scheduling retains durable work; roll forward'; END $$;
-- +goose StatementEnd
