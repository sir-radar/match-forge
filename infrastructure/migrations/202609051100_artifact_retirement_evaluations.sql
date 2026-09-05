-- +goose Up

ALTER TABLE football.artifact_retirement_events
    DROP CONSTRAINT artifact_retirement_events_object_id_fkey,
    DROP CONSTRAINT artifact_retirement_events_object_kind_check;

ALTER TABLE football.artifact_retirement_events
    ADD CONSTRAINT artifact_retirement_events_object_kind_check
    CHECK (object_kind IN ('FORECAST', 'EVALUATION'));

-- +goose StatementBegin
CREATE FUNCTION football.validate_artifact_retirement_event_target()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.object_kind NOT IN ('FORECAST', 'EVALUATION') THEN
        RETURN NEW;
    END IF;

    IF NEW.object_kind = 'FORECAST' AND EXISTS (
        SELECT 1 FROM football.baseline_forecasts WHERE id = NEW.object_id
    ) THEN
        RETURN NEW;
    END IF;

    IF NEW.object_kind = 'EVALUATION' AND EXISTS (
        SELECT 1 FROM football.sprint2_evaluation_runs WHERE id = NEW.object_id
    ) THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'artifact retirement target is not registered'
        USING ERRCODE = 'foreign_key_violation';
END;
$$;
-- +goose StatementEnd

CREATE TRIGGER artifact_retirement_events_target_exists
BEFORE INSERT ON football.artifact_retirement_events
FOR EACH ROW EXECUTE FUNCTION football.validate_artifact_retirement_event_target();
