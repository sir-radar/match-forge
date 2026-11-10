-- +goose Up

-- A linked reconstruction may use one proved, adjacent replacement of a closed
-- native mapping. Existing FDO corrections and all historical rows stay intact.
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
          AND source.source_snapshot_id = NEW.source_snapshot_id
          AND (
            (source.valid_to IS NULL AND NEW.evidence->>'reason'='INCORRECT_PRIOR_MAPPING')
            OR (
              source.valid_to IS NOT NULL AND sp.code='fotmob' AND target.provider_id=source.provider_id
              AND source.provider_team_id=target.provider_team_id
              AND source.team_id<>target.team_id AND source.mapping_method='deterministic'
              AND target.valid_from=source.valid_to AND source.valid_to<=NEW.decided_at
              AND NEW.reason='REPLACED_NATIVE_MAPPING_CORRECTED'
              AND NEW.evidence->>'reason'='REPLACED_NATIVE_MAPPING'
              AND d.provider_code='fotmob'
              AND d.reason='verified team_provider_mappings contradicts exact-name candidate'
              AND NEW.evidence->'context'->>lower(NEW.evidence->>'orientation')=source.provider_team_id
              AND (NEW.evidence->'replacement'->>'source_valid_to')::timestamptz=source.valid_to
              AND (NEW.evidence->'replacement'->>'target_valid_from')::timestamptz=target.valid_from
              AND NEW.evidence->'replacement'->'native_fixture_bridge'->'old_resource'->>'source_snapshot_id'=source.source_snapshot_id::text
              AND NEW.evidence->'replacement'->'native_fixture_bridge'->'old_resource'->>'sha256'=NEW.evidence->>'sha256'
              AND NEW.evidence->'replacement'->'native_fixture_bridge'->'current_resource'->>'source_snapshot_id'=fixture.source_snapshot_id::text
              AND football.product_mapping_trusted('team',target.id,target.team_id)
              AND EXISTS (
                SELECT 1 FROM (SELECT * FROM football.product_identity_admissions
                  WHERE entity_type='team' AND mapping_id=target.id
                  ORDER BY decided_at DESC,decision_id DESC LIMIT 1) admitted
                WHERE admitted.disposition='CROSSWALK' AND admitted.corrects_decision_id IS NULL
              )
              AND EXISTS (
                SELECT 1 FROM football.product_teams old_team,football.product_teams new_team
                WHERE old_team.team_id=source.team_id AND new_team.team_id=target.team_id
                  AND old_team.country=c.country AND new_team.country=c.country
                  AND new_team.name=NEW.evidence->'replacement'->>'target_label'
              )
              AND EXISTS (
                SELECT 1 FROM football.product_identity_admissions revoked
                WHERE revoked.decision_id=(NEW.evidence->'replacement'->>'prior_revocation_id')::uuid
                  AND revoked.entity_type='team' AND revoked.mapping_id=source.id
                  AND revoked.provider_code=sp.code AND revoked.provider_entity_id=source.provider_team_id
                  AND revoked.disposition='REVOKED' AND revoked.corrects_decision_id IS NULL
                  AND revoked.reason='MAPPING_CHANGED_REVALIDATION_REQUIRED'
                  AND NOT EXISTS(SELECT 1 FROM football.product_identity_admissions later
                    WHERE later.entity_type='team' AND later.mapping_id=source.id
                      AND (later.decided_at,later.decision_id)>(revoked.decided_at,revoked.decision_id))
              )
            )
          )
          AND source.mapping_confidence = 1 AND target.mapping_confidence = 1
          AND target.valid_to IS NULL AND target.team_id = NEW.canonical_id
          AND tp.code = NEW.evidence->'target_evidence'->>'provider'
          AND target.source_snapshot_id = (NEW.evidence->'target_evidence'->>'source_snapshot_id')::uuid
          AND target.provider_team_id = NEW.evidence->'target_evidence'->>'provider_entity_id'
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


-- +goose StatementBegin
CREATE OR REPLACE FUNCTION football.record_product_history_decisions(fixture_keys uuid[]) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM football.lock_history_qualification(fixture_keys);
    INSERT INTO football.product_match_history_decisions (
        fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
        home_goals, away_goals, home_xg, away_xg, source_provider_code,
        source_snapshot_id, source_kickoff_precision, eligible, reason, source_known_at)
    SELECT proposed.* FROM (
    SELECT h.fixture_id, h.competition_id, COALESCE(hm.identity, h.home_team_id) AS home_team_id,
           COALESCE(am.identity, h.away_team_id) AS away_team_id, h.kickoff_at,
           h.home_goals, h.away_goals, h.home_xg, h.away_xg, h.source_provider_code,
           h.source_snapshot_id, h.source_kickoff_precision,
           s.status = 'validated' AND COALESCE(f.identity_status, 'VERIFIED') = 'VERIFIED'
           AND COALESCE(f.status NOT IN ('AWARDED', 'ABANDONED', 'CANCELLED'), true)
           AND NOT EXISTS (SELECT 1 FROM football.fixture_identity_resolutions r
               WHERE r.member_fixture_id = h.fixture_id AND r.active
                 AND (r.resolution_status NOT IN ('UNIQUE', 'DUPLICATE_RESOLVED')
                      OR r.representative_fixture_id <> h.fixture_id))
           AND EXISTS (SELECT 1 FROM football.competition_provider_mappings m
               WHERE m.competition_id = h.competition_id AND m.provider_id = s.provider_id
                 AND m.valid_to IS NULL AND m.mapping_confidence = 1
                 AND football.product_mapping_trusted('competition', m.id, m.competition_id))
           AND COALESCE(hm.trusted, false)
           AND COALESCE(am.trusted, false) AS eligible,
           CASE WHEN f.status IN ('AWARDED', 'ABANDONED', 'CANCELLED')
                THEN 'non-played terminal status' ELSE 'ProductIdentityTrustV1' END AS reason, s.acquired_at AS source_known_at
    FROM football.product_team_match_history h
    JOIN football.source_snapshots s ON s.id = h.source_snapshot_id
    LEFT JOIN football.product_fixtures f ON f.fixture_id = h.fixture_id
    LEFT JOIN LATERAL (
        SELECT CASE WHEN count(DISTINCT effective.identity) = 1
                    THEN min(effective.identity::text)::uuid END AS identity,
               count(DISTINCT effective.identity) = 1 AND bool_and(
                   football.product_mapping_trusted('team', mapping.id, effective.identity)) AS trusted
        FROM football.team_provider_mappings mapping
        CROSS JOIN LATERAL (SELECT COALESCE(
            football.product_team_identity_at(mapping.id, clock_timestamp()),
            mapping.team_id) AS identity) effective
        WHERE mapping.team_id = h.home_team_id AND mapping.provider_id = s.provider_id
          AND (mapping.valid_to IS NULL OR EXISTS (
              SELECT 1 FROM football.product_identity_admissions admission
              WHERE admission.entity_type='team' AND admission.mapping_id=mapping.id
                AND admission.corrects_decision_id IS NOT NULL
                AND admission.disposition='CROSSWALK'
                AND admission.reason='REPLACED_NATIVE_MAPPING_CORRECTED'
                AND admission.canonical_id=effective.identity
                AND NOT EXISTS(SELECT 1 FROM football.product_identity_admissions later
                  WHERE later.entity_type='team' AND later.mapping_id=mapping.id
                    AND (later.decided_at,later.decision_id)>
                        (admission.decided_at,admission.decision_id))))
    ) hm ON true
    LEFT JOIN LATERAL (
        SELECT CASE WHEN count(DISTINCT effective.identity) = 1
                    THEN min(effective.identity::text)::uuid END AS identity,
               count(DISTINCT effective.identity) = 1 AND bool_and(
                   football.product_mapping_trusted('team', mapping.id, effective.identity)) AS trusted
        FROM football.team_provider_mappings mapping
        CROSS JOIN LATERAL (SELECT COALESCE(
            football.product_team_identity_at(mapping.id, clock_timestamp()),
            mapping.team_id) AS identity) effective
        WHERE mapping.team_id = h.away_team_id AND mapping.provider_id = s.provider_id
          AND (mapping.valid_to IS NULL OR EXISTS (
              SELECT 1 FROM football.product_identity_admissions admission
              WHERE admission.entity_type='team' AND admission.mapping_id=mapping.id
                AND admission.corrects_decision_id IS NOT NULL
                AND admission.disposition='CROSSWALK'
                AND admission.reason='REPLACED_NATIVE_MAPPING_CORRECTED'
                AND admission.canonical_id=effective.identity
                AND NOT EXISTS(SELECT 1 FROM football.product_identity_admissions later
                  WHERE later.entity_type='team' AND later.mapping_id=mapping.id
                    AND (later.decided_at,later.decision_id)>
                        (admission.decided_at,admission.decision_id))))
    ) am ON true
    WHERE h.fixture_id = ANY(fixture_keys)) proposed
    WHERE NOT EXISTS (
        SELECT 1 FROM (SELECT * FROM football.product_match_history_decisions
                      WHERE fixture_id = proposed.fixture_id
                      ORDER BY decided_at DESC, decision_id DESC LIMIT 1) previous
        WHERE (to_jsonb(previous) - 'decision_id' - 'decided_at') = to_jsonb(proposed)
    ) ORDER BY proposed.fixture_id;
END;
$$;
-- +goose StatementEnd

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'replaced native corrections are a forward-only migration'; END $$;
-- +goose StatementEnd
