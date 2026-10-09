-- +goose Up

CREATE TABLE football.fixture_identity_resolutions (
    canonical_real_fixture_id uuid NOT NULL,
    member_fixture_id uuid NOT NULL REFERENCES football.matches (id),
    representative_fixture_id uuid NOT NULL REFERENCES football.matches (id),
    resolution_status text NOT NULL CHECK (resolution_status IN (
        'UNIQUE', 'DUPLICATE_RESOLVED', 'AMBIGUOUS_QUARANTINED',
        'IMPOSSIBLE_TEAM_SCHEDULE_QUARANTINED'
    )),
    selected_competition_id uuid REFERENCES football.competitions (id),
    resolution_reason text NOT NULL CHECK (resolution_reason <> ''),
    evidence_json jsonb NOT NULL CHECK (jsonb_typeof(evidence_json) = 'object'),
    evidence_sha256 football.sha256_hex NOT NULL,
    resolution_version text NOT NULL CHECK (resolution_version <> ''),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (canonical_real_fixture_id, member_fixture_id, resolution_version)
);

CREATE UNIQUE INDEX fixture_identity_active_member_idx
    ON football.fixture_identity_resolutions (member_fixture_id)
    WHERE active;

CREATE INDEX fixture_identity_active_real_fixture_idx
    ON football.fixture_identity_resolutions (
        canonical_real_fixture_id, resolution_status, selected_competition_id
    )
    WHERE active;

-- +goose Down

DROP TABLE football.fixture_identity_resolutions;
