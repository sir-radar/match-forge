package app

import (
	"bufio"
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

var (
	errSyncAlreadyRunning  = errors.New("a data synchronization is already running")
	errSyncRunNotFound     = errors.New("sync run not found")
	errSyncRunNotActive    = errors.New("sync run is not active")
	errSyncRunNotRetryable = errors.New("only failed or cancelled sync runs can be retried")
)

type syncConflictError struct {
	ActiveRun SyncRun
}

func (conflict syncConflictError) Error() string { return errSyncAlreadyRunning.Error() }
func (conflict syncConflictError) Unwrap() error { return errSyncAlreadyRunning }

type SyncType string

const (
	SyncMVP                 SyncType = "MVP_SYNC"
	SyncOpenFootball        SyncType = "OPENFOOTBALL"
	SyncFootballDataUK      SyncType = "FOOTBALL_DATA_UK"
	SyncHistoryBackfill     SyncType = "HISTORY_BACKFILL"
	SyncForecastRefresh     SyncType = "FORECAST_REFRESH"
	SyncExternalPredictions SyncType = "EXTERNAL_PREDICTIONS"
	SyncFotMob              SyncType = "FOTMOB_SYNC"
	SyncPitchAPI            SyncType = "PITCHAPI_SYNC"
	SyncAllData             SyncType = "ALL_DATA"
)

type SyncRequest struct {
	Type        SyncType `json:"sync_type"`
	Date        string   `json:"date,omitempty"`
	FromDate    string   `json:"from_date,omitempty"`
	Season      string   `json:"season,omitempty"`
	Competition string   `json:"competition,omitempty"`
	Country     string   `json:"country,omitempty"`
	RetryOf     string   `json:"-"`
}

type SyncRun struct {
	ID            string                 `json:"run_id"`
	Type          SyncType               `json:"sync_type"`
	Status        string                 `json:"status"`
	RequestedAt   time.Time              `json:"requested_at"`
	StartedAt     *time.Time             `json:"started_at"`
	FinishedAt    *time.Time             `json:"finished_at"`
	RequestedDate *string                `json:"requested_date"`
	Parameters    map[string]interface{} `json:"parameters"`
	Summary       map[string]interface{} `json:"summary"`
	ErrorMessage  *string                `json:"error_message"`
	LogPath       *string                `json:"log_path"`
	HistoryQueue  *HistoryQueueProgress  `json:"history_queue,omitempty"`
}

type HistoryQueueProgress struct {
	Total     int `json:"total"`
	Pending   int `json:"pending"`
	Running   int `json:"running"`
	Succeeded int `json:"succeeded"`
	Failed    int `json:"failed"`
}

type Coverage struct {
	EligibleHistory         int  `json:"eligible_history"`
	ExcludedHistory         int  `json:"excluded_history"`
	ProvisionalFixtures     int  `json:"provisional_fixtures"`
	VerifiedProviderMatches int  `json:"verified_provider_matches"`
	IdentityConflicts       int  `json:"identity_conflicts"`
	HistoricalMatches       int  `json:"historical_matches"`
	CompetitionsWithHistory int  `json:"competitions_with_history"`
	TeamsWithTenMatches     int  `json:"teams_with_10_matches"`
	TeamsBelowTenMatches    int  `json:"teams_below_10_matches"`
	ScheduledFixtures       int  `json:"scheduled_fixtures"`
	ForecastAvailable       int  `json:"forecast_available"`
	NotEnoughHistory        int  `json:"not_enough_history"`
	MappingFailures         int  `json:"mapping_failures"`
	SourceConflicts         int  `json:"source_conflicts"`
	MissingLiveScores       int  `json:"missing_live_scores"`
	FotMobMapped            int  `json:"fotmob_mapped"`
	FotMobUnmapped          int  `json:"fotmob_unmapped"`
	PitchAPIMapped          int  `json:"pitchapi_mapped"`
	PitchAPIUnmapped        int  `json:"pitchapi_unmapped"`
	FotMobHistory           int  `json:"fotmob_history"`
	PitchAPIHistory         int  `json:"pitchapi_history"`
	APIQuotaRequestsUsed    int  `json:"api_football_requests_used"`
	APIQuotaRemaining       int  `json:"api_football_remaining"`
	APIQuotaExhausted       bool `json:"api_football_exhausted"`
}

type SyncRunner interface {
	Start(context.Context, SyncRequest) (SyncRun, error)
	Stop(context.Context, string) (SyncRun, error)
	Retry(context.Context, string) (SyncRun, error)
	List(context.Context) ([]SyncRun, error)
	Get(context.Context, string) (SyncRun, error)
	Coverage(context.Context) (Coverage, error)
}

type syncRunnerShutdown interface {
	Shutdown(context.Context)
}

type unavailableSyncRunner struct{}

func (unavailableSyncRunner) Start(context.Context, SyncRequest) (SyncRun, error) {
	return SyncRun{}, errProductUnavailable
}
func (unavailableSyncRunner) Stop(context.Context, string) (SyncRun, error) {
	return SyncRun{}, errProductUnavailable
}
func (unavailableSyncRunner) Retry(context.Context, string) (SyncRun, error) {
	return SyncRun{}, errProductUnavailable
}
func (unavailableSyncRunner) List(context.Context) ([]SyncRun, error) {
	return nil, errProductUnavailable
}
func (unavailableSyncRunner) Get(context.Context, string) (SyncRun, error) {
	return SyncRun{}, errProductUnavailable
}
func (unavailableSyncRunner) Coverage(context.Context) (Coverage, error) {
	return Coverage{}, errProductUnavailable
}

type CommandSyncRunner struct {
	ctx      context.Context
	pool     *pgxpool.Pool
	repoRoot string
	logger   *slog.Logger
	mu       sync.Mutex
	active   map[string]*syncRunControl
}

type syncRunControl struct {
	cancel context.CancelFunc
	done   chan struct{}
}

const (
	syncRunHeartbeatInterval = 15 * time.Second
	syncRunLease             = 2 * time.Minute
)

func NewCommandSyncRunner(
	ctx context.Context,
	pool *pgxpool.Pool,
	repoRoot string,
	logger *slog.Logger,
) *CommandSyncRunner {
	return &CommandSyncRunner{
		ctx: ctx, pool: pool, repoRoot: repoRoot, logger: logger,
		active: make(map[string]*syncRunControl),
	}
}

func (runner *CommandSyncRunner) Start(ctx context.Context, request SyncRequest) (SyncRun, error) {
	args, err := syncCommandArgs(request)
	if err != nil {
		return SyncRun{}, err
	}
	encodedParameters, err := json.Marshal(syncParameters(request))
	if err != nil {
		return SyncRun{}, err
	}
	requestedDate, err := validateSyncDateRange(request.Date, request.FromDate)
	if err != nil {
		return SyncRun{}, err
	}
	runID, err := newUUID()
	if err != nil {
		return SyncRun{}, err
	}
	logPath := filepath.Join(".local", "sync-runs", runID+".log")
	if err = runner.enqueue(ctx, request, runID, logPath, requestedDate, encodedParameters); err != nil {
		var postgresError *pgconn.PgError
		if errors.As(err, &postgresError) && postgresError.Code == "23505" {
			return SyncRun{}, runner.activeRunConflict(ctx)
		}
		return SyncRun{}, err
	}
	run, err := runner.Get(ctx, runID)
	if err != nil {
		return SyncRun{}, err
	}
	runContext, cancel := context.WithCancel(runner.ctx)
	control := &syncRunControl{cancel: cancel, done: make(chan struct{})}
	runner.mu.Lock()
	runner.active[runID] = control
	runner.mu.Unlock()
	go runner.execute(runContext, runID, logPath, args, control)
	return run, nil
}

func (runner *CommandSyncRunner) enqueue(
	ctx context.Context,
	request SyncRequest,
	runID string,
	logPath string,
	requestedDate *time.Time,
	encodedParameters []byte,
) error {
	transaction, err := runner.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer func() { _ = transaction.Rollback(ctx) }()
	if _, err = transaction.Exec(ctx, `
		UPDATE football.product_sync_runs
		SET status = 'FAILED', finished_at = clock_timestamp(),
		    error_message = 'worker lease expired; safe to retry'
		WHERE status IN ('QUEUED', 'RUNNING')
		  AND (CASE
		      WHEN sync_type = 'FOTMOB_SYNC' THEN 'LIVE_FOTMOB'
		      WHEN sync_type = 'PITCHAPI_SYNC' THEN 'LIVE_PITCHAPI'
		      ELSE 'BULK'
		  END) = $1
		  AND COALESCE(heartbeat_at, requested_at) <
		      clock_timestamp() - $2 * interval '1 second'
	`, syncLane(request.Type), int64(syncRunLease/time.Second)); err != nil {
		return err
	}
	_, err = transaction.Exec(ctx, `
		INSERT INTO football.product_sync_runs (
			run_id, sync_type, status, requested_date, parameters, log_path,
			worker_id, heartbeat_at
		) VALUES ($1, $2, 'QUEUED', $3, $4::jsonb, $5, $6, clock_timestamp())
	`, runID, request.Type, requestedDate, encodedParameters, logPath, runID)
	if err != nil {
		return err
	}
	return transaction.Commit(ctx)
}

func syncLane(syncType SyncType) string {
	switch syncType {
	case SyncFotMob:
		return "LIVE_FOTMOB"
	case SyncPitchAPI:
		return "LIVE_PITCHAPI"
	default:
		return "BULK"
	}
}

func syncParameters(request SyncRequest) map[string]interface{} {
	parameters := map[string]interface{}{}
	for key, value := range map[string]string{
		"from_date": request.FromDate, "season": request.Season,
		"competition": request.Competition, "country": request.Country,
		"retry_of_run_id": request.RetryOf,
	} {
		if value != "" {
			parameters[key] = value
		}
	}
	return parameters
}

func parseSyncDate(value string) (*time.Time, error) {
	if value == "" {
		return nil, nil
	}
	parsed, err := time.Parse("2006-01-02", value)
	if err != nil {
		return nil, fmt.Errorf("date must use YYYY-MM-DD")
	}
	return &parsed, nil
}

func validateSyncDateRange(dateValue string, fromDateValue string) (*time.Time, error) {
	requestedDate, err := parseSyncDate(dateValue)
	if err != nil {
		return nil, err
	}
	fromDate, err := parseSyncDate(fromDateValue)
	if err != nil {
		return nil, fmt.Errorf("from_date %w", err)
	}
	if requestedDate != nil && fromDate != nil && fromDate.After(*requestedDate) {
		return nil, fmt.Errorf("from_date must not be after date")
	}
	return requestedDate, nil
}

func (runner *CommandSyncRunner) activeRunConflict(ctx context.Context) error {
	activeRun, err := scanSyncRun(runner.pool.QueryRow(
		ctx,
		syncRunSelect+" WHERE status IN ('QUEUED', 'RUNNING') ORDER BY requested_at DESC LIMIT 1",
	))
	if err != nil {
		return errSyncAlreadyRunning
	}
	return syncConflictError{ActiveRun: activeRun}
}

func (runner *CommandSyncRunner) execute(
	ctx context.Context, runID string, logPath string, args []string, control *syncRunControl,
) {
	defer func() {
		control.cancel()
		runner.mu.Lock()
		delete(runner.active, runID)
		close(control.done)
		runner.mu.Unlock()
	}()
	if !runner.markRunning(ctx, runID) {
		return
	}
	heartbeatContext, stopHeartbeat := context.WithCancel(ctx)
	defer stopHeartbeat()
	go runner.heartbeat(heartbeatContext, runID)
	absoluteLog := filepath.Join(runner.repoRoot, logPath)
	if err := os.MkdirAll(filepath.Dir(absoluteLog), 0o750); err != nil {
		runner.fail(runID, err)
		return
	}
	logFile, err := os.OpenFile(absoluteLog, os.O_CREATE|os.O_RDWR|os.O_EXCL, 0o600)
	if err != nil {
		runner.fail(runID, err)
		return
	}
	defer logFile.Close()
	summary, err := runner.runCommand(ctx, runID, args, logFile)
	if err != nil {
		if runner.cancelIfRequested(ctx, runID) {
			return
		}
		runner.fail(runID, err)
		return
	}
	if runner.cancelIfRequested(ctx, runID) {
		return
	}
	encoded, err := json.Marshal(summary)
	if err != nil {
		runner.fail(runID, err)
		return
	}
	status, errorMessage := syncCompletion(summary)
	if runner.cancelIfRequested(ctx, runID) {
		return
	}
	if _, err = runner.pool.Exec(
		runner.ctx,
		`UPDATE football.product_sync_runs
		 SET status = $2, finished_at = clock_timestamp(), summary = $3::jsonb,
		     error_message = $4
		 WHERE run_id = $1`,
		runID,
		status,
		encoded,
		errorMessage,
	); err != nil {
		runner.logger.Error("finish sync run", "run_id", runID, "error", err)
	}
}

func (runner *CommandSyncRunner) markRunning(ctx context.Context, runID string) bool {
	_, err := runner.pool.Exec(
		ctx,
		`UPDATE football.product_sync_runs
		 SET status = 'RUNNING', started_at = clock_timestamp(), heartbeat_at = clock_timestamp()
		 WHERE run_id = $1`,
		runID,
	)
	if err == nil {
		return true
	}
	if !runner.cancelIfRequested(ctx, runID) {
		runner.logger.Error("start sync run", "run_id", runID, "error", err)
	}
	return false
}

func (runner *CommandSyncRunner) heartbeat(ctx context.Context, runID string) {
	ticker := time.NewTicker(syncRunHeartbeatInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if _, err := runner.pool.Exec(
				ctx,
				`UPDATE football.product_sync_runs SET heartbeat_at = clock_timestamp()
				 WHERE run_id = $1 AND status IN ('QUEUED', 'RUNNING')`,
				runID,
			); err != nil && !errors.Is(err, context.Canceled) {
				runner.logger.Warn("heartbeat sync run", "run_id", runID, "error", err)
			}
		}
	}
}

func (runner *CommandSyncRunner) cancelIfRequested(ctx context.Context, runID string) bool {
	if !errors.Is(ctx.Err(), context.Canceled) {
		return false
	}
	runner.cancelled(runID)
	return true
}

func syncCompletion(summary map[string]interface{}) (string, *string) {
	if summary["status"] != "COMPLETED_WITH_ERRORS" {
		return "SUCCEEDED", nil
	}
	message := "one or more data synchronization operations failed; see summary.errors"
	return "FAILED", &message
}

func (runner *CommandSyncRunner) runCommand(
	ctx context.Context, runID string, args []string, logFile *os.File,
) (map[string]interface{}, error) {
	command := exec.CommandContext(ctx, args[0], args[1:]...)
	command.Dir = runner.repoRoot
	command.Env = append(os.Environ(), "MATCHFORGE_SYNC_RUN_ID="+runID)
	command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	command.Cancel = func() error {
		if command.Process == nil {
			return os.ErrProcessDone
		}
		return syscall.Kill(-command.Process.Pid, syscall.SIGKILL)
	}
	pipe, err := command.StdoutPipe()
	if err != nil {
		return nil, err
	}
	command.Stderr = logFile
	if err = command.Start(); err != nil {
		return nil, err
	}
	lastLine, scanErr := lastOutputLine(io.TeeReader(pipe, logFile))
	waitErr := command.Wait()
	if scanErr != nil {
		return nil, scanErr
	}
	summary := map[string]interface{}{}
	if waitErr != nil {
		if json.Unmarshal([]byte(lastLine), &summary) == nil &&
			summary["status"] == "COMPLETED_WITH_ERRORS" {
			return summary, nil
		}
		return nil, commandFailure(waitErr, logFile)
	}
	if err = json.Unmarshal([]byte(lastLine), &summary); err != nil {
		return nil, fmt.Errorf("sync command did not return structured JSON: %w", err)
	}
	return summary, nil
}

func (runner *CommandSyncRunner) cancelled(runID string) {
	message := "stopped by operator"
	if _, err := runner.pool.Exec(
		context.WithoutCancel(runner.ctx),
		`UPDATE football.product_sync_runs
		 SET status = 'CANCELLED', finished_at = clock_timestamp(), error_message = $2
		 WHERE run_id = $1 AND status IN ('QUEUED', 'RUNNING')`,
		runID,
		message,
	); err != nil {
		runner.logger.Error("cancel sync run", "run_id", runID, "error", err)
	}
}

func (runner *CommandSyncRunner) Stop(ctx context.Context, id string) (SyncRun, error) {
	run, err := runner.Get(ctx, id)
	if err != nil {
		return SyncRun{}, err
	}
	if run.Status != "QUEUED" && run.Status != "RUNNING" {
		return SyncRun{}, errSyncRunNotActive
	}
	runner.mu.Lock()
	control := runner.active[id]
	runner.mu.Unlock()
	if control == nil {
		runner.cancelled(id)
		return runner.Get(ctx, id)
	}
	control.cancel()
	select {
	case <-control.done:
		return runner.Get(ctx, id)
	case <-ctx.Done():
		return SyncRun{}, ctx.Err()
	}
}

func (runner *CommandSyncRunner) Shutdown(ctx context.Context) {
	runner.mu.Lock()
	controls := make([]*syncRunControl, 0, len(runner.active))
	for _, control := range runner.active {
		controls = append(controls, control)
		control.cancel()
	}
	runner.mu.Unlock()
	for _, control := range controls {
		select {
		case <-control.done:
		case <-ctx.Done():
			return
		}
	}
}

func (runner *CommandSyncRunner) Retry(ctx context.Context, id string) (SyncRun, error) {
	run, err := runner.Get(ctx, id)
	if err != nil {
		return SyncRun{}, err
	}
	if run.Status != "FAILED" && run.Status != "CANCELLED" {
		return SyncRun{}, errSyncRunNotRetryable
	}
	return runner.Start(ctx, syncRequestFromRun(run))
}

func syncRequestFromRun(run SyncRun) SyncRequest {
	request := SyncRequest{Type: run.Type, RetryOf: run.ID}
	if run.RequestedDate != nil {
		request.Date = *run.RequestedDate
	}
	request.FromDate = stringParameter(run.Parameters, "from_date")
	request.Season = stringParameter(run.Parameters, "season")
	request.Competition = stringParameter(run.Parameters, "competition")
	request.Country = stringParameter(run.Parameters, "country")
	return request
}

func stringParameter(parameters map[string]interface{}, key string) string {
	value, _ := parameters[key].(string)
	return value
}

func lastOutputLine(reader io.Reader) (string, error) {
	var lastLine string
	scanner := bufio.NewScanner(reader)
	scanner.Buffer(make([]byte, 64*1024), 4*1024*1024)
	for scanner.Scan() {
		if strings.TrimSpace(scanner.Text()) != "" {
			lastLine = scanner.Text()
		}
	}
	return lastLine, scanner.Err()
}

func commandFailure(cause error, logFile *os.File) error {
	if _, err := logFile.Seek(0, io.SeekStart); err != nil {
		return cause
	}
	lastLine, err := lastOutputLine(logFile)
	if err != nil || strings.TrimSpace(lastLine) == "" {
		return cause
	}
	return fmt.Errorf("%w: %s", cause, lastLine)
}

func (runner *CommandSyncRunner) fail(runID string, cause error) {
	message := cause.Error()
	if len(message) > 4000 {
		message = message[:4000]
	}
	if _, err := runner.pool.Exec(
		context.WithoutCancel(runner.ctx),
		`UPDATE football.product_sync_runs
		 SET status = 'FAILED', finished_at = clock_timestamp(), error_message = $2
		 WHERE run_id = $1`,
		runID,
		message,
	); err != nil {
		runner.logger.Error("fail sync run", "run_id", runID, "error", err)
	}
}

func (runner *CommandSyncRunner) List(ctx context.Context) ([]SyncRun, error) {
	rows, err := runner.pool.Query(ctx, syncRunSelect+" ORDER BY requested_at DESC LIMIT 50")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	runs := []SyncRun{}
	for rows.Next() {
		run, scanErr := scanSyncRun(rows)
		if scanErr != nil {
			return nil, scanErr
		}
		runs = append(runs, run)
	}
	return runs, rows.Err()
}

func (runner *CommandSyncRunner) Get(ctx context.Context, id string) (SyncRun, error) {
	if !regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`).MatchString(id) {
		return SyncRun{}, errSyncRunNotFound
	}
	run, err := scanSyncRun(runner.pool.QueryRow(ctx, syncRunSelect+" WHERE run_id = $1", id))
	if errors.Is(err, pgx.ErrNoRows) {
		return SyncRun{}, errSyncRunNotFound
	}
	return run, err
}

func newUUID() (string, error) {
	value := make([]byte, 16)
	if _, err := rand.Read(value); err != nil {
		return "", err
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	return fmt.Sprintf(
		"%08x-%04x-%04x-%04x-%012x",
		value[0:4], value[4:6], value[6:8], value[8:10], value[10:16],
	), nil
}

func (runner *CommandSyncRunner) Coverage(ctx context.Context) (Coverage, error) {
	var coverage Coverage
	err := runner.pool.QueryRow(ctx, `
		WITH eligible_history AS MATERIALIZED (
            SELECT * FROM football.product_eligible_match_history WHERE known_at <= now()
        ), team_counts AS (
			SELECT team_id, count(*) AS matches
			FROM (
				SELECT home_team_id AS team_id FROM eligible_history
				UNION ALL
				SELECT away_team_id AS team_id FROM eligible_history
			) appearances GROUP BY team_id
		)
		SELECT
			(SELECT count(*) FROM eligible_history),
            (SELECT count(*) FROM football.product_team_match_history) -
				(SELECT count(*) FROM eligible_history),
            (SELECT count(*) FROM football.product_fixtures WHERE identity_status = 'PROVISIONAL'),
            (SELECT count(DISTINCT (observation.provider_code, observation.provider_match_id))
             FROM football.product_provider_fixture_observations observation
             JOIN football.product_fixtures fixture ON fixture.fixture_id = observation.canonical_fixture_id
             WHERE fixture.identity_status = 'VERIFIED'),
            (SELECT count(*) FROM football.fixture_identity_resolutions
             WHERE active AND resolution_status IN
                 ('AMBIGUOUS_QUARANTINED', 'IMPOSSIBLE_TEAM_SCHEDULE_QUARANTINED')),
			(SELECT count(*) FROM football.product_team_match_history),
			(SELECT count(DISTINCT competition_id) FROM football.product_team_match_history),
			(SELECT count(*) FROM team_counts WHERE matches >= 10),
			(SELECT count(*) FROM team_counts WHERE matches < 10),
			(SELECT count(*) FROM football.product_fixtures WHERE status = 'SCHEDULED'),
			(SELECT count(*) FROM football.product_fixtures
			 WHERE status = 'SCHEDULED' AND forecast_availability = 'FORECAST_AVAILABLE'),
			(SELECT count(*) FROM football.product_fixtures
			 WHERE status = 'SCHEDULED' AND forecast_availability = 'NOT_ENOUGH_HISTORY'),
			(SELECT COALESCE(sum((latest.summary->>'mapping_failures')::integer), 0)
			 FROM (
				 SELECT DISTINCT ON (sync_type) summary
				 FROM football.product_sync_runs
				 WHERE status = 'SUCCEEDED' AND summary ? 'mapping_failures'
				 ORDER BY sync_type, finished_at DESC
			 ) latest),
			(SELECT count(*) FROM football.product_source_result_conflicts),
			(SELECT count(*) FROM football.product_fixtures
			 WHERE status IN ('LIVE', 'HALF_TIME', 'SUSPENDED', 'INTERRUPTED')
			   AND (home_score IS NULL OR away_score IS NULL)),
			(SELECT count(*) FROM football.product_provider_fixture_observations
			 WHERE provider_code = 'fotmob' AND canonical_fixture_id IS NOT NULL),
			(SELECT count(*) FROM football.product_provider_fixture_observations
			 WHERE provider_code = 'fotmob' AND canonical_fixture_id IS NULL),
			(SELECT count(*) FROM football.product_provider_fixture_observations
			 WHERE provider_code = 'pitchapi' AND canonical_fixture_id IS NOT NULL),
			(SELECT count(*) FROM football.product_provider_fixture_observations
			 WHERE provider_code = 'pitchapi' AND canonical_fixture_id IS NULL),
			(SELECT count(*) FROM football.product_team_match_history
			 WHERE source_provider_code = 'fotmob'),
			(SELECT count(*) FROM football.product_team_match_history
			 WHERE source_provider_code = 'pitchapi'),
			COALESCE((SELECT requests_used FROM football.provider_request_budgets
			 WHERE provider_code = 'api_football' AND window_date = CURRENT_DATE), 0),
			COALESCE((SELECT remaining_requests FROM football.provider_request_budgets
			 WHERE provider_code = 'api_football' AND window_date = CURRENT_DATE), -1),
			COALESCE((SELECT exhausted FROM football.provider_request_budgets
			 WHERE provider_code = 'api_football' AND window_date = CURRENT_DATE), false)
	`).Scan(
		&coverage.EligibleHistory,
		&coverage.ExcludedHistory,
		&coverage.ProvisionalFixtures,
		&coverage.VerifiedProviderMatches,
		&coverage.IdentityConflicts,
		&coverage.HistoricalMatches,
		&coverage.CompetitionsWithHistory,
		&coverage.TeamsWithTenMatches,
		&coverage.TeamsBelowTenMatches,
		&coverage.ScheduledFixtures,
		&coverage.ForecastAvailable,
		&coverage.NotEnoughHistory,
		&coverage.MappingFailures,
		&coverage.SourceConflicts,
		&coverage.MissingLiveScores,
		&coverage.FotMobMapped,
		&coverage.FotMobUnmapped,
		&coverage.PitchAPIMapped,
		&coverage.PitchAPIUnmapped,
		&coverage.FotMobHistory,
		&coverage.PitchAPIHistory,
		&coverage.APIQuotaRequestsUsed,
		&coverage.APIQuotaRemaining,
		&coverage.APIQuotaExhausted,
	)
	return coverage, err
}

const syncRunSelect = `
	SELECT run_id::text, sync_type, status, requested_at, started_at, finished_at,
	       requested_date::text, parameters, COALESCE(summary, '{}'::jsonb),
	       error_message, log_path,
	       CASE WHEN sync_type IN ('MVP_SYNC', 'ALL_DATA') AND EXISTS (
	           SELECT 1 FROM football.product_history_sync_queue
	           WHERE sync_run_id = product_sync_runs.run_id
	       ) THEN (
	           SELECT jsonb_build_object(
	               'total', count(*),
	               'pending', count(*) FILTER (WHERE job_status = 'PENDING'),
	               'running', count(*) FILTER (WHERE job_status = 'RUNNING'),
	               'succeeded', count(*) FILTER (WHERE job_status = 'SUCCEEDED'),
	               'failed', count(*) FILTER (WHERE job_status = 'FAILED')
	           )
	           FROM football.product_history_sync_queue
	           WHERE sync_run_id = product_sync_runs.run_id
	       ) END
	FROM football.product_sync_runs`

type rowScanner interface {
	Scan(...interface{}) error
}

func scanSyncRun(row rowScanner) (SyncRun, error) {
	var run SyncRun
	var parameters []byte
	var summary []byte
	var historyQueue []byte
	err := row.Scan(
		&run.ID,
		&run.Type,
		&run.Status,
		&run.RequestedAt,
		&run.StartedAt,
		&run.FinishedAt,
		&run.RequestedDate,
		&parameters,
		&summary,
		&run.ErrorMessage,
		&run.LogPath,
		&historyQueue,
	)
	if err != nil {
		return SyncRun{}, err
	}
	if err = json.Unmarshal(parameters, &run.Parameters); err != nil {
		return SyncRun{}, err
	}
	if err = json.Unmarshal(summary, &run.Summary); err != nil {
		return SyncRun{}, err
	}
	if len(historyQueue) > 0 {
		run.HistoryQueue = &HistoryQueueProgress{}
		if err = json.Unmarshal(historyQueue, run.HistoryQueue); err != nil {
			return SyncRun{}, err
		}
	}
	return run, nil
}

func syncCommandArgs(request SyncRequest) ([]string, error) {
	command := map[SyncType]string{
		SyncMVP:                 "sync",
		SyncOpenFootball:        "backfill-openfootball",
		SyncFootballDataUK:      "backfill-football-data-uk",
		SyncHistoryBackfill:     "backfill-history",
		SyncForecastRefresh:     "refresh-forecasts",
		SyncExternalPredictions: "external-predictions",
		SyncFotMob:              "fotmob-sync",
		SyncPitchAPI:            "pitchapi-sync",
		SyncAllData:             "sync-all",
	}[request.Type]
	if command == "" {
		return nil, fmt.Errorf("unsupported sync type %q", request.Type)
	}
	args := []string{".tools/bin/uv", "run", "python", "-m", "football.product.cli", command}
	args = appendSyncDateArgs(args, request)
	args = appendSyncSelectorArgs(args, request)
	return args, nil
}

func appendSyncDateArgs(args []string, request SyncRequest) []string {
	dateTypes := map[SyncType]bool{
		SyncMVP: true, SyncExternalPredictions: true, SyncFotMob: true,
		SyncPitchAPI: true, SyncAllData: true,
	}
	if request.Date != "" && dateTypes[request.Type] {
		args = append(args, "--date", request.Date)
	}
	fromDateTypes := map[SyncType]bool{
		SyncMVP: true, SyncFotMob: true, SyncPitchAPI: true, SyncAllData: true,
	}
	if request.FromDate != "" && fromDateTypes[request.Type] {
		args = append(args, "--from-date", request.FromDate)
	}
	return args
}

func appendSyncSelectorArgs(args []string, request SyncRequest) []string {
	if request.Competition != "" && (request.Type == SyncFotMob || request.Type == SyncPitchAPI) {
		args = append(args, "--competition", request.Competition)
	}
	selectorTypes := map[SyncType]bool{
		SyncOpenFootball: true, SyncFootballDataUK: true, SyncHistoryBackfill: true,
	}
	if selectorTypes[request.Type] {
		for _, selector := range []struct{ name, value string }{
			{name: "--season", value: request.Season},
			{name: "--competition", value: request.Competition},
			{name: "--country", value: request.Country},
		} {
			if selector.value != "" {
				args = append(args, selector.name, selector.value)
			}
		}
	}
	return args
}

func (application *App) listSyncRuns(response http.ResponseWriter, request *http.Request) {
	runs, err := application.syncRunner.List(request.Context())
	if err != nil {
		application.writeSyncError(response, err)
		return
	}
	coverage, err := application.syncRunner.Coverage(request.Context())
	if err != nil {
		application.writeSyncError(response, err)
		return
	}
	application.writeJSON(response, http.StatusOK, map[string]interface{}{
		"runs": runs, "coverage": coverage,
		"provider_configuration": map[string]interface{}{
			"fotmob_enabled":            application.config.FotMobEnabled,
			"pitchapi_enabled":          application.config.PitchAPIEnabled,
			"operational_sync_interval": application.config.OperationalSyncInterval.String(),
		},
	})
}

func (application *App) getSyncRun(response http.ResponseWriter, request *http.Request) {
	run, err := application.syncRunner.Get(request.Context(), request.PathValue("run_id"))
	if err != nil {
		application.writeSyncError(response, err)
		return
	}
	application.writeJSON(response, http.StatusOK, run)
}

func (application *App) stopSyncRun(response http.ResponseWriter, request *http.Request) {
	run, err := application.syncRunner.Stop(request.Context(), request.PathValue("run_id"))
	if err != nil {
		application.writeSyncError(response, err)
		return
	}
	application.writeJSON(response, http.StatusOK, run)
}

func (application *App) retrySyncRun(response http.ResponseWriter, request *http.Request) {
	run, err := application.syncRunner.Retry(request.Context(), request.PathValue("run_id"))
	if err != nil {
		application.writeSyncError(response, err)
		return
	}
	application.writeJSON(response, http.StatusAccepted, run)
}

func (application *App) startSync(syncType SyncType) http.HandlerFunc {
	return func(response http.ResponseWriter, request *http.Request) {
		var input struct {
			Date        string `json:"date"`
			FromDate    string `json:"from_date"`
			Season      string `json:"season"`
			Competition string `json:"competition"`
			Country     string `json:"country"`
		}
		decoder := json.NewDecoder(io.LimitReader(request.Body, 64*1024))
		decoder.DisallowUnknownFields()
		if request.ContentLength != 0 {
			if err := decoder.Decode(&input); err != nil {
				application.writeJSON(response, http.StatusBadRequest, map[string]string{"error": "invalid JSON request"})
				return
			}
		}
		run, err := application.syncRunner.Start(request.Context(), SyncRequest{
			Type: syncType, Date: input.Date, FromDate: input.FromDate, Season: input.Season,
			Competition: input.Competition, Country: input.Country,
		})
		if err != nil {
			application.writeSyncError(response, err)
			return
		}
		application.writeJSON(response, http.StatusAccepted, run)
	}
}

func (application *App) writeSyncError(response http.ResponseWriter, err error) {
	status := http.StatusInternalServerError
	message := "data synchronization failed"
	if errors.Is(err, errSyncAlreadyRunning) {
		status = http.StatusConflict
		message = err.Error()
		var conflict syncConflictError
		if errors.As(err, &conflict) {
			application.writeJSON(response, status, map[string]interface{}{
				"error": message, "active_run": conflict.ActiveRun,
			})
			return
		}
	} else if errors.Is(err, errSyncRunNotFound) {
		status = http.StatusNotFound
		message = err.Error()
	} else if errors.Is(err, errSyncRunNotActive) || errors.Is(err, errSyncRunNotRetryable) {
		status = http.StatusConflict
		message = err.Error()
	} else if errors.Is(err, errProductUnavailable) {
		status = http.StatusServiceUnavailable
		message = "data synchronization is unavailable"
	}
	application.writeJSON(response, status, map[string]string{"error": message})
}
