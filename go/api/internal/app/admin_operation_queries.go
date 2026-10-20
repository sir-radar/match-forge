package app

// Constant queries expose existing owners. Request values never become SQL names.
var operationQueries = map[string]struct{ source, query string }{
	"providers": {"REGISTERED_PROVIDER_METADATA", `SELECT to_jsonb(item) FROM (
        SELECT p.code AS provider,p.source_type,
            (SELECT max(s.acquired_at) FROM football.source_snapshots s WHERE s.provider_id=p.id
             AND s.source_kind='REAL_PROVIDER' AND s.status='validated'
             AND s.acquired_at<=transaction_timestamp()) AS last_validated_acquisition_at,
            (SELECT count(*) FROM football.provider_resource_capabilities c WHERE c.provider_id=p.id
             AND c.known_at<=transaction_timestamp()) AS capability_decisions
        FROM football.providers p) item ORDER BY item.provider`},
	"work-orchestrator": {"SHARED_WORK_REGISTRY", `SELECT to_jsonb(item) FROM (
        SELECT state,count(*) AS work_count,min(requested_at) AS oldest_requested_at,
               min(available_at) AS earliest_available_at
        FROM football.work_items GROUP BY state) item ORDER BY item.state`},
	"ingestion": {"REGISTERED_SOURCE_SNAPSHOTS", `SELECT to_jsonb(item) FROM (
        SELECT s.id AS source_snapshot_id,p.code AS provider,s.source_kind,s.status,s.acquired_at,
               (SELECT count(*) FROM football.source_resources r WHERE r.source_snapshot_id=s.id) AS resource_count
        FROM football.source_snapshots s JOIN football.providers p ON p.id=s.provider_id
        WHERE s.acquired_at<=transaction_timestamp()) item
        ORDER BY item.acquired_at DESC,item.source_snapshot_id`},
	"identity": {"CURRENT_IDENTITY_RECORDS", `SELECT to_jsonb(item) FROM (
        SELECT 'fixture' AS entity_type,identity_status AS status,count(*) AS entity_count
        FROM football.product_serving_fixtures GROUP BY identity_status
        UNION ALL SELECT 'duplicate_member',resolution_status,count(*)
        FROM football.fixture_identity_resolutions WHERE active AND created_at<=transaction_timestamp()
        GROUP BY resolution_status
        UNION ALL SELECT 'team_decision',disposition,count(*) FROM (
            SELECT DISTINCT ON(mapping_id) mapping_id,disposition
            FROM football.product_identity_admissions WHERE entity_type='team'
            ORDER BY mapping_id,decided_at DESC,decision_id DESC) latest GROUP BY disposition
        UNION ALL SELECT 'team','UNRESOLVED',count(*) FROM football.product_teams t
        WHERE NOT EXISTS (SELECT 1 FROM football.team_provider_mappings m
            WHERE m.team_id=t.team_id
              AND (m.valid_from IS NULL OR m.valid_from<=transaction_timestamp())
              AND (m.valid_to IS NULL OR m.valid_to>transaction_timestamp())
              AND football.product_mapping_trusted('team',m.id,m.team_id))
        ) item ORDER BY item.entity_type,item.status`},
	"coverage": {"REGISTERED_COVERAGE_REPORTS", `SELECT item.record FROM (
        SELECT known_at,report_id,jsonb_build_object('kind','provider','report_id',report_id,
            'provider',provider,'resource_type',resource_type,'competition_key',competition_key,
            'season_key',season_key,'expected',expected,'qualified',qualified,'coverage_ratio',coverage_ratio,
            'status',status,'knowledge_cutoff',knowledge_cutoff,'known_at',known_at) AS record FROM (
            SELECT DISTINCT ON(p.code,r.resource_type,r.competition_key,r.season_key) p.code AS provider,r.*
            FROM football.provider_resource_coverage r JOIN football.providers p ON p.id=r.provider_id
            WHERE r.known_at<=transaction_timestamp() AND r.knowledge_cutoff<=transaction_timestamp()
            ORDER BY p.code,r.resource_type,r.competition_key,r.season_key,
                r.knowledge_cutoff DESC,r.known_at DESC,r.publication_sequence DESC) latest
        UNION ALL SELECT known_at,report_id,jsonb_build_object('kind','canonical','report_id',report_id,
            'competition_id',competition_id,'season_id',season_id,'resource_type',resource_type,
            'expected',expected_canonical_units,'qualified',qualified_canonical_units,
            'coverage_ratio',coverage_ratio,'status',status,'knowledge_cutoff',knowledge_cutoff,
            'known_at',known_at) FROM (
            SELECT DISTINCT ON(competition_id,season_id,resource_type) *
            FROM football.canonical_resource_coverage WHERE known_at<=transaction_timestamp()
                AND knowledge_cutoff<=transaction_timestamp()
            ORDER BY competition_id,season_id,resource_type,knowledge_cutoff DESC,
                known_at DESC,publication_sequence DESC) latest
        ) item ORDER BY item.known_at DESC,item.report_id`},
	"data-quality": {"REGISTERED_VALIDATION_FINDINGS", `SELECT to_jsonb(item) FROM (
        SELECT id AS finding_id,validation_run_id,dataset_version_id,source_snapshot_id,
               rule_code,severity,action,scope_type
        FROM football.validation_findings) item ORDER BY item.finding_id`},
	"forecasting": {"PUBLISHED_FORECASTS", `SELECT to_jsonb(item) FROM (
        SELECT forecast_id,fixture_id,model_label,model_algorithm_version,model_artifact_sha256,
               football_cutoff,knowledge_cutoff,knowledge_mode,created_at,forecast_horizon
        FROM football.product_forecasts WHERE created_at<=transaction_timestamp()
        ) item ORDER BY item.created_at DESC,item.forecast_id`},
	"models": {"RUNTIME_MODEL_REGISTRY", `SELECT jsonb_build_object('registration',convert_from(record_bytes,'UTF8')::jsonb,
        'registration_sha256',registration_sha256,'registered_at',registered_at)
        FROM football.runtime_model_registrations WHERE registered_at<=transaction_timestamp()
        ORDER BY registered_at DESC,registration_sha256`},
	"experiments": {"EXPERIMENT_EXECUTION_WORK", `SELECT to_jsonb(item) FROM (
        SELECT work_id,input_hash,state,result_hash,requested_at,started_at,finished_at,
               attempt_count,parent_work_id,last_error_code
        FROM football.work_items WHERE work_type='EXPERIMENT_EXECUTION'
        ) item ORDER BY item.requested_at DESC,item.work_id`},
}

// Lease tokens grant publication rights and must never be returned to an operator client.
const operationWorkSelect = `SELECT jsonb_build_object(
    'work_id',w.work_id,'work_type',w.work_type,'state',w.state,'input_hash',w.input_hash,
    'priority',w.priority,'requested_at',w.requested_at,'available_at',w.available_at,
    'started_at',w.started_at,'finished_at',w.finished_at,
    'age_seconds',extract(epoch FROM transaction_timestamp()-w.requested_at),
    'generation',w.generation,'lease_owner',w.lease_owner,'lease_until',w.lease_until,
    'heartbeat_at',w.heartbeat_at,'attempt_count',w.attempt_count,'max_attempts',w.max_attempts,
    'parent_work_id',w.parent_work_id,
    'parent_sync_run_id',coalesce(
        (SELECT run_id FROM football.product_sync_runs WHERE run_id IN(w.work_id,w.parent_work_id)
         ORDER BY CASE WHEN run_id=w.work_id THEN 0 ELSE 1 END LIMIT 1),
        (SELECT q.sync_run_id FROM football.product_history_work h
         JOIN football.product_history_sync_queue q ON q.job_id=h.job_id AND q.queued_at=h.queued_at
         WHERE h.work_id=w.work_id ORDER BY q.queued_at DESC LIMIT 1)),
    'dependencies',ARRAY(SELECT dependency_work_id FROM football.work_dependencies d
        WHERE d.work_id=w.work_id ORDER BY dependency_work_id LIMIT 100),
    'dependency_count',(SELECT count(*) FROM football.work_dependencies d WHERE d.work_id=w.work_id),
    'last_error_code',w.last_error_code,'last_error_message',w.last_error_message
) FROM football.work_items w `
