-- +goose Up

-- Renew only the same correction after a mapping-change revocation, with a new
-- admitted support mapping. Earlier admissions and revocations remain immutable.
-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.validate_product_identity_correction() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.corrects_decision_id IS NULL THEN
        IF EXISTS (SELECT 1 FROM football.product_identity_admissions a
                   WHERE a.entity_type = NEW.entity_type AND a.mapping_id = NEW.mapping_id
                     AND a.corrects_decision_id IS NOT NULL) THEN
            RAISE EXCEPTION 'linked correction requires a linked continuation';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.disposition = 'REVOKED' THEN RETURN NEW; END IF;
    IF NEW.evidence->>'contract' IS DISTINCT FROM 'ProductTeamIdentityCorrectionV1'
       OR jsonb_typeof(NEW.evidence->'context_resources') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'identity correction requires typed context evidence';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM football.product_provider_mapping_decisions d
        JOIN football.match_provider_mappings fixture
          ON fixture.id = (NEW.evidence->>'fixture_registration_id')::uuid
         AND fixture.match_id = d.candidate_fixture_id
        JOIN football.product_fixtures f ON f.fixture_id = fixture.match_id
        JOIN football.product_competitions c ON c.competition_id = f.competition_id
        JOIN football.matches match ON match.id = f.fixture_id
        JOIN football.seasons season ON season.id = match.season_id
        JOIN football.team_provider_mappings source ON source.id = NEW.mapping_id
         AND source.provider_id = fixture.provider_id
        JOIN football.providers sp ON sp.id = source.provider_id
        JOIN football.team_provider_mappings target ON target.id = NEW.target_mapping_id
        JOIN football.providers tp ON tp.id = target.provider_id
        WHERE d.decision_id = NEW.corrects_decision_id AND d.disposition = 'CONTRADICTORY'
          AND NEW.evidence->'original_decision' = to_jsonb(d)
          AND sp.code = NEW.provider_code AND source.provider_team_id = NEW.provider_entity_id
          AND source.source_snapshot_id = NEW.source_snapshot_id AND source.valid_to IS NULL
          AND source.mapping_confidence = 1 AND target.mapping_confidence = 1
          AND target.valid_to IS NULL AND target.team_id = NEW.canonical_id
          AND tp.code = NEW.evidence->'target_evidence'->>'provider'
          AND target.source_snapshot_id = (NEW.evidence->'target_evidence'->>'source_snapshot_id')::uuid
          AND target.provider_team_id = NEW.evidence->'target_evidence'->>'provider_entity_id'
          AND NEW.evidence->>'reason' = 'INCORRECT_PRIOR_MAPPING'
          AND NEW.evidence->>'orientation' IN ('HOME', 'AWAY')
          AND source.team_id = CASE NEW.evidence->>'orientation'
              WHEN 'HOME' THEN f.home_team_id ELSE f.away_team_id END
          AND (NEW.evidence->'context'->>'kickoff')::timestamptz = f.kickoff_at
          AND NEW.evidence->'context'->>'country' = c.country
          AND (NEW.evidence->'context'->>'season_start')::date = season.start_date
          AND (NEW.evidence->'context'->>'season_end')::date = season.end_date
    ) THEN RAISE EXCEPTION 'identity correction requires exact contradiction, source and target linkage'; END IF;
    IF EXISTS (SELECT 1 FROM football.product_identity_admissions a
               WHERE a.mapping_id = NEW.mapping_id AND a.corrects_decision_id IS NOT NULL)
       AND NOT EXISTS (
           SELECT 1 FROM (SELECT * FROM football.product_identity_admissions a
               WHERE a.mapping_id = NEW.mapping_id AND a.entity_type = 'team'
               ORDER BY a.decided_at DESC, a.decision_id DESC LIMIT 1) previous
           WHERE previous.disposition = 'REVOKED'
             AND previous.reason = 'MAPPING_CHANGED_REVALIDATION_REQUIRED'
             AND previous.corrects_decision_id = NEW.corrects_decision_id
             AND previous.target_mapping_id = NEW.target_mapping_id
             AND previous.canonical_id = NEW.canonical_id
             AND previous.provider_code = NEW.provider_code
             AND previous.provider_entity_id = NEW.provider_entity_id
             AND previous.evidence->'fixture_registration_id' =
                 NEW.evidence->'fixture_registration_id'
             AND previous.evidence->'orientation' = NEW.evidence->'orientation'
             AND previous.evidence_sha256 <> NEW.evidence_sha256
             AND EXISTS (
                 SELECT 1 FROM jsonb_array_elements(NEW.evidence->'context_resources') item
                 JOIN football.team_provider_mappings support
                   ON support.id = (item->>'mapping_id')::uuid
                 JOIN football.providers provider ON provider.id = support.provider_id
                 WHERE support.valid_to IS NULL AND support.team_id = NEW.canonical_id
                   AND provider.code = 'fotmob' AND provider.code = item->>'provider'
                   AND support.source_snapshot_id = (item->>'source_snapshot_id')::uuid
                   AND football.product_mapping_trusted('team',support.id,support.team_id)
                   AND NOT EXISTS (
                       SELECT 1 FROM jsonb_array_elements(previous.evidence->'context_resources') prior_item
                       WHERE prior_item->>'mapping_id' = item->>'mapping_id'))
       ) THEN
        RAISE EXCEPTION 'existing linked correction must be retried or explicitly revoked';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_array_elements(NEW.evidence->'context_resources') item
        WHERE NOT EXISTS (
            SELECT 1 FROM football.source_resources r
            JOIN football.source_snapshots s ON s.id = r.source_snapshot_id
            JOIN football.providers p ON p.id = s.provider_id
            WHERE r.id = (item->>'source_resource_id')::uuid
              AND s.id = (item->>'source_snapshot_id')::uuid
              AND p.code = item->>'provider' AND r.sha256 = item->>'sha256'
              AND s.status = 'validated' AND r.parse_status = 'parsed'
              AND r.validation_status IN ('valid', 'warnings')
              AND r.acquired_at <= NEW.decided_at
        )
    ) OR jsonb_array_length(NEW.evidence->'context_resources') < 3 THEN
        RAISE EXCEPTION 'identity correction requires registered retained context resources';
    END IF;
    RETURN NEW;
END;
$$;
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'reviewed correction revalidation is a forward-only migration'; END $$;
-- +goose StatementEnd
