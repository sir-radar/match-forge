-- +goose Up

ALTER TABLE football.product_sync_runs
    DROP CONSTRAINT product_sync_runs_sync_type_check;
ALTER TABLE football.product_sync_runs
    ADD CONSTRAINT product_sync_runs_sync_type_check CHECK (
        sync_type IN (
            'MVP_SYNC', 'OPENFOOTBALL', 'FOOTBALL_DATA_UK', 'HISTORY_BACKFILL',
            'FORECAST_REFRESH', 'CONTEXT_REPORTS', 'EXTERNAL_PREDICTIONS',
            'FOTMOB_SYNC', 'PITCHAPI_SYNC', 'ALL_DATA'
        )
    );

CREATE TABLE football.product_context_report_refresh_work (
    fixture_id uuid PRIMARY KEY REFERENCES football.product_fixtures (fixture_id) ON DELETE CASCADE,
    requested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    generation bigint NOT NULL DEFAULT 1 CHECK (generation > 0),
    completed_generation bigint NOT NULL DEFAULT 0
        CHECK (completed_generation >= 0 AND completed_generation <= generation),
    completed_at timestamptz
);
CREATE INDEX product_context_report_refresh_pending_idx
    ON football.product_context_report_refresh_work (requested_at, fixture_id)
    WHERE generation > completed_generation;

-- Existing serving fixtures need one context projection after deployment. Newer
-- fixtures and history decisions are queued by the triggers below.
INSERT INTO football.product_context_report_refresh_work (fixture_id)
SELECT fixture_id FROM football.product_serving_fixtures
ON CONFLICT (fixture_id) DO NOTHING;

CREATE TRIGGER check_worker_publication BEFORE INSERT OR UPDATE OR DELETE
    ON football.product_context_report_refresh_work FOR EACH STATEMENT
    EXECUTE FUNCTION football.check_worker_publication();

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_context_report_refresh(fixture_key uuid)
RETURNS void LANGUAGE sql AS $$
    INSERT INTO football.product_context_report_refresh_work (fixture_id)
    VALUES (fixture_key)
    ON CONFLICT (fixture_id) DO UPDATE
    SET generation = football.product_context_report_refresh_work.generation + 1,
        requested_at = CASE
            WHEN football.product_context_report_refresh_work.generation >
                 football.product_context_report_refresh_work.completed_generation
            THEN football.product_context_report_refresh_work.requested_at
            ELSE clock_timestamp()
        END,
        completed_at = NULL;
$$;
-- +goose StatementEnd

-- Fixture changes affect their own context and, for scheduled matches, the
-- upcoming-match/rest context of earlier fixtures involving either team.
-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_context_for_fixture()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    target_fixture uuid;
BEGIN
    IF TG_OP = 'UPDATE' AND
       (OLD.competition_id, OLD.home_team_id, OLD.away_team_id, OLD.kickoff_at, OLD.status,
        OLD.identity_status, OLD.updated_at)
       IS NOT DISTINCT FROM
       (NEW.competition_id, NEW.home_team_id, NEW.away_team_id, NEW.kickoff_at, NEW.status,
        NEW.identity_status, NEW.updated_at) THEN
        RETURN NEW;
    END IF;

    PERFORM football.enqueue_product_context_report_refresh(NEW.fixture_id);

    IF TG_OP = 'UPDATE' THEN
        FOR target_fixture IN
            SELECT DISTINCT target.fixture_id
            FROM football.product_fixtures target
            WHERE target.fixture_id <> NEW.fixture_id
              AND target.kickoff_at < OLD.kickoff_at
              AND target.kickoff_at >= OLD.updated_at
              AND (target.home_team_id IN (OLD.home_team_id, OLD.away_team_id)
                OR target.away_team_id IN (OLD.home_team_id, OLD.away_team_id))
        LOOP
            PERFORM football.enqueue_product_context_report_refresh(target_fixture);
        END LOOP;
    END IF;
    FOR target_fixture IN
        SELECT DISTINCT target.fixture_id
        FROM football.product_fixtures target
        WHERE target.fixture_id <> NEW.fixture_id
          AND target.kickoff_at < NEW.kickoff_at
          AND target.kickoff_at >= NEW.updated_at
          AND (target.home_team_id IN (NEW.home_team_id, NEW.away_team_id)
            OR target.away_team_id IN (NEW.home_team_id, NEW.away_team_id))
    LOOP
        PERFORM football.enqueue_product_context_report_refresh(target_fixture);
    END LOOP;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_product_context_for_fixture
    AFTER INSERT OR UPDATE OF competition_id, home_team_id, away_team_id, kickoff_at, status,
        identity_status, updated_at
    ON football.product_fixtures FOR EACH ROW
    EXECUTE FUNCTION football.enqueue_product_context_for_fixture();

-- An append-only history decision can add, correct, or remove a result from a
-- target's eligible history. Queue only later targets that could know it.
-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_context_for_history()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    target_fixture uuid;
    known_at timestamptz := GREATEST(NEW.source_known_at, NEW.decided_at);
BEGIN
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
        WHERE target.fixture_id <> NEW.fixture_id
          AND target.kickoff_at >= known_at
          AND ((NEW.source_kickoff_precision = 'EXACT' AND target.kickoff_at > NEW.kickoff_at)
            OR (NEW.source_kickoff_precision = 'DATE_ONLY'
                AND target.kickoff_at::date > NEW.kickoff_at::date))
          AND (teams.home_team_id IN (NEW.home_team_id, NEW.away_team_id)
            OR teams.away_team_id IN (NEW.home_team_id, NEW.away_team_id))
    LOOP
        PERFORM football.enqueue_product_context_report_refresh(target_fixture);
    END LOOP;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_product_context_for_history
    AFTER INSERT ON football.product_match_history_decisions FOR EACH ROW
    EXECUTE FUNCTION football.enqueue_product_context_for_history();

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_context_for_coach()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    target_fixture uuid;
BEGIN
    FOR target_fixture IN
        SELECT target.fixture_id
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
        WHERE target.kickoff_at > NEW.effective_at
          AND target.kickoff_at >= NEW.known_at
          AND NEW.team_id IN (teams.home_team_id, teams.away_team_id)
    LOOP
        PERFORM football.enqueue_product_context_report_refresh(target_fixture);
    END LOOP;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_product_context_for_coach
    AFTER INSERT ON football.product_coach_observations FOR EACH ROW
    EXECUTE FUNCTION football.enqueue_product_context_for_coach();

-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_context_for_lineup()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    target_fixture uuid;
BEGIN
    FOR target_fixture IN
        SELECT target.fixture_id
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
        WHERE target.kickoff_at > NEW.kickoff_at
          AND target.kickoff_at >= NEW.known_at
          AND NEW.team_id IN (teams.home_team_id, teams.away_team_id)
    LOOP
        PERFORM football.enqueue_product_context_report_refresh(target_fixture);
    END LOOP;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_product_context_for_lineup
    AFTER INSERT ON football.product_lineup_observations FOR EACH ROW
    EXECUTE FUNCTION football.enqueue_product_context_for_lineup();

-- Identity admissions can change the team IDs used by future fixture context,
-- including fixtures that have no history row of their own yet.
-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_context_for_identity_admission()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    target_fixture uuid;
BEGIN
    IF NEW.entity_type <> 'team' THEN
        RETURN NEW;
    END IF;
    FOR target_fixture IN
        SELECT DISTINCT fixture.fixture_id
        FROM football.product_fixtures fixture
        JOIN football.match_provider_mappings registered
          ON registered.match_id = fixture.fixture_id
        JOIN football.team_provider_mappings mapping
          ON mapping.id = NEW.mapping_id AND mapping.provider_id = registered.provider_id
        WHERE mapping.team_id IN (fixture.home_team_id, fixture.away_team_id)
          AND fixture.kickoff_at >= GREATEST(NEW.decided_at, NEW.source_observed_at)
    LOOP
        PERFORM football.enqueue_product_context_report_refresh(target_fixture);
    END LOOP;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd
CREATE TRIGGER enqueue_product_context_for_identity_admission
    AFTER INSERT ON football.product_identity_admissions FOR EACH ROW
    EXECUTE FUNCTION football.enqueue_product_context_for_identity_admission();

-- Historical opponent labels are part of the immutable context projection.
-- Refresh only target fixtures whose eligible history contains this team.
-- +goose StatementBegin
CREATE FUNCTION football.enqueue_product_context_for_team_name()
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
CREATE TRIGGER enqueue_product_context_for_team_name
    AFTER UPDATE OF name ON football.product_teams FOR EACH ROW
    EXECUTE FUNCTION football.enqueue_product_context_for_team_name();

-- +goose Down
-- Public context reports and their work references are retained; roll forward.
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'context report refresh work is durable; roll forward';
END $$;
-- +goose StatementEnd
