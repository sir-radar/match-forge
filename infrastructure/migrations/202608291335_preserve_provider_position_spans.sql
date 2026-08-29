-- +goose Up

-- StatsBomb position spans are provider observations, not normalized intervals.
-- Real source rows can move backwards across provider periods and clocks. Preserve
-- those facts verbatim; the paired-null and non-negative clock checks remain.
ALTER TABLE football.player_position_stints
    DROP CONSTRAINT player_position_stints_check1;
