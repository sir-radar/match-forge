package app

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"time"
)

// App owns the operational HTTP surface and lifecycle.
type App struct {
	config     Config
	logger     *slog.Logger
	readiness  ReadinessChecker
	product    ProductStore
	syncRunner SyncRunner
	handler    http.Handler
}

// New constructs the operational API without starting network listeners.
func New(config Config, logger *slog.Logger, readiness ReadinessChecker, stores ...ProductStore) *App {
	var product ProductStore = unavailableProductStore{}
	if len(stores) > 0 && stores[0] != nil {
		product = stores[0]
	}
	return NewWithSyncRunner(config, logger, readiness, product, unavailableSyncRunner{})
}

// NewWithSyncRunner constructs the API with an injected fixed-action synchronization runner.
func NewWithSyncRunner(
	config Config,
	logger *slog.Logger,
	readiness ReadinessChecker,
	product ProductStore,
	syncRunner SyncRunner,
) *App {
	config = config.servingDefaults()
	application := &App{
		config: config, logger: logger, readiness: readiness,
		product: product, syncRunner: syncRunner,
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", application.health)
	mux.HandleFunc("GET /readyz", application.ready)
	mux.HandleFunc("GET /version", application.version)
	mux.HandleFunc("GET /v1/competitions", application.listCompetitions)
	mux.HandleFunc("GET /v1/fixtures", application.listFixtures)
	mux.HandleFunc("GET /v1/fixtures/{fixture_id}/live", application.liveFixture)
	mux.HandleFunc("GET /v1/fixtures/{fixture_id}/context", application.fixtureContext)
	mux.HandleFunc("GET /v1/fixtures/{fixture_id}/forecasts", application.forecastHistory)
	mux.HandleFunc("GET /v1/fixtures/{fixture_id}/forecasts/{forecast_id}", application.forecast)
	mux.HandleFunc("GET /v1/competitions/{competition_id}/standings", application.standings)
	mux.HandleFunc("GET /v1/competitions/{competition_id}/performance", application.performance)
	mux.HandleFunc("GET /v1/performance", application.listPerformance)
	mux.HandleFunc("GET /v1/external-predictions", application.externalPredictions)
	mux.HandleFunc("GET /v1/fixtures/{fixture_id}/external-predictions", application.fixtureExternalPredictions)
	mux.HandleFunc("GET /v1/external-prediction-sources", application.externalPredictionSources)
	mux.HandleFunc("GET /v1/admin/operations/{domain}", application.operations)
	mux.HandleFunc("GET /v1/admin/resolution/{view}", application.resolutionRead)
	mux.HandleFunc("POST /v1/admin/resolution/preview", application.resolutionPreview)
	mux.HandleFunc("POST /v1/admin/resolution/apply", application.resolutionApply)
	mux.HandleFunc("POST /v1/admin/resolution/{operation}", application.resolutionBatch)
	mux.HandleFunc("GET /v1/admin/work", application.listWork)
	mux.HandleFunc("GET /v1/admin/work/{work_id}", application.getWork)
	mux.HandleFunc("POST /v1/admin/work/{work_id}/cancel", application.controlWork("cancel"))
	mux.HandleFunc("POST /v1/admin/work/{work_id}/retry", application.controlWork("retry"))
	mux.HandleFunc("GET /v1/admin/sync-runs", application.listSyncRuns)
	mux.HandleFunc("GET /v1/admin/sync-runs/{run_id}", application.getSyncRun)
	mux.HandleFunc("POST /v1/admin/sync-runs/{run_id}/stop", application.stopSyncRun)
	mux.HandleFunc("POST /v1/admin/sync-runs/{run_id}/retry", application.retrySyncRun)
	mux.HandleFunc("POST /v1/admin/sync/mvp", application.startSync(SyncMVP))
	mux.HandleFunc("POST /v1/admin/sync/openfootball", application.startSync(SyncOpenFootball))
	mux.HandleFunc("POST /v1/admin/sync/football-data-uk", application.startSync(SyncFootballDataUK))
	mux.HandleFunc("POST /v1/admin/sync/history", application.startSync(SyncHistoryBackfill))
	mux.HandleFunc("POST /v1/admin/sync/forecast-refresh", application.startSync(SyncForecastRefresh))
	mux.HandleFunc("POST /v1/admin/sync/external-predictions", application.startSync(SyncExternalPredictions))
	mux.HandleFunc("POST /v1/admin/sync/fotmob", application.startSync(SyncFotMob))
	mux.HandleFunc("POST /v1/admin/sync/pitchapi", application.startSync(SyncPitchAPI))
	mux.HandleFunc("POST /v1/admin/sync/all", application.startSync(SyncAllData))
	application.handler = application.requestDeadline(application.cors(application.adminAccess(mux)))
	return application
}

// Handler exposes the HTTP contract for tests and servers.
func (application *App) Handler() http.Handler {
	return application.handler
}

// Run serves until the context is cancelled, then performs bounded graceful shutdown.
func (application *App) Run(ctx context.Context) error {
	if application.config.OperationalSyncInterval > 0 {
		go application.runOperationalSyncSchedule(ctx)
	}
	if application.config.HistorySyncEnabled {
		go application.runHistorySyncSchedule(ctx)
	}
	if _, ok := application.syncRunner.(pendingForecastRefreshRunner); ok {
		go application.runForecastRefreshSchedule(ctx)
	}
	if _, ok := application.syncRunner.(pendingPublicReportsRunner); ok {
		go application.runPublicReportSchedule(ctx)
	}
	stopRecovery := application.startResolutionRecovery(ctx)
	defer stopRecovery()
	server := application.httpServer()

	errorsChannel := make(chan error, 1)
	go func() {
		application.logger.Info("api listening", "address", application.config.Address)
		errorsChannel <- server.ListenAndServe()
	}()

	select {
	case err := <-errorsChannel:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	case <-ctx.Done():
		shutdownContext, cancel := context.WithTimeout(context.Background(), application.config.ShutdownTimeout)
		defer cancel()
		if runner, ok := application.syncRunner.(syncRunnerShutdown); ok {
			runner.Shutdown(shutdownContext)
		}
		return server.Shutdown(shutdownContext)
	}
}

func (application *App) runOperationalSyncSchedule(ctx context.Context) {
	ticker := time.NewTicker(application.config.OperationalSyncInterval)
	defer ticker.Stop()
	types := []SyncType{}
	if application.config.PitchAPIEnabled {
		types = append(types, SyncPitchAPI)
	}
	if application.config.FotMobEnabled {
		types = append(types, SyncFotMob)
	}
	if len(types) == 0 {
		return
	}
	for {
		for _, syncType := range types {
			lagos := time.FixedZone("Africa/Lagos", 60*60)
			now := time.Now().In(lagos)
			_, err := application.syncRunner.Start(ctx, SyncRequest{
				Type: syncType, Date: now.Format("2006-01-02"),
				FromDate: now.AddDate(0, 0, -1).Format("2006-01-02"),
			})
			if err != nil && !errors.Is(err, errSyncAlreadyRunning) {
				application.logger.Warn("scheduled provider sync failed to start", "sync_type", syncType, "error", err)
			}
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (application *App) runHistorySyncSchedule(ctx context.Context) {
	if !application.config.HistorySyncEnabled ||
		(!application.config.PitchAPIEnabled && !application.config.FotMobEnabled) {
		return
	}
	ticker := time.NewTicker(application.config.HistorySyncInterval)
	defer ticker.Stop()
	for {
		_, err := application.syncRunner.Start(ctx, SyncRequest{
			Type: SyncHistoryBackfill, ScheduledHistory: true,
		})
		if err != nil && !errors.Is(err, errSyncAlreadyRunning) {
			application.logger.Warn("scheduled history failed to start", "error", err)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (application *App) runForecastRefreshSchedule(ctx context.Context) {
	runner := application.syncRunner.(pendingForecastRefreshRunner)
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()
	for {
		pending, err := runner.PendingForecastRefresh(ctx)
		if err != nil {
			if ctx.Err() == nil {
				application.logger.Warn("check pending forecast refresh", "error", err)
			}
		} else if pending {
			_, err = application.syncRunner.Start(ctx, SyncRequest{
				Type: SyncForecastRefresh, PendingOnly: true,
			})
			if err != nil && !errors.Is(err, errSyncAlreadyRunning) {
				application.logger.Warn("scheduled forecast refresh failed to start", "error", err)
			}
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (application *App) runPublicReportSchedule(ctx context.Context) {
	runner := application.syncRunner.(pendingPublicReportsRunner)
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()
	for {
		pending, err := runner.PendingPublicReports(ctx)
		if err != nil {
			if ctx.Err() == nil {
				application.logger.Warn("check pending public reports", "error", err)
			}
		} else if pending {
			_, err = application.syncRunner.Start(ctx, SyncRequest{Type: SyncPublicReports})
			if err != nil && !errors.Is(err, errSyncAlreadyRunning) {
				application.logger.Warn("scheduled public report refresh failed to start", "error", err)
			}
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (application *App) health(response http.ResponseWriter, _ *http.Request) {
	application.writeJSON(response, http.StatusOK, map[string]string{"status": "ok"})
}

func (application *App) ready(response http.ResponseWriter, request *http.Request) {
	if err := application.readiness.Ready(request.Context()); err != nil {
		application.logger.Warn("readiness failed", "error", err)
		application.writeJSON(response, http.StatusServiceUnavailable, map[string]string{"status": "unavailable"})
		return
	}
	application.writeJSON(response, http.StatusOK, map[string]string{"status": "ready"})
}

// Set by the repository build, never inferred from a mutable runtime checkout.
var buildCommitSHA = "unknown"
var buildDependencyLockSHA256 = "unknown"
var buildWorktreeState = "unknown"

func (application *App) version(response http.ResponseWriter, _ *http.Request) {
	application.writeJSON(response, http.StatusOK, map[string]string{
		"version": application.config.Version, "code_commit_sha": buildCommitSHA,
		"dependency_lock_sha256": buildDependencyLockSHA256, "worktree_state": buildWorktreeState,
	})
}

func (application *App) writeJSON(response http.ResponseWriter, status int, value any) {
	response.Header().Set("Content-Type", "application/json")
	response.WriteHeader(status)
	if err := json.NewEncoder(response).Encode(value); err != nil {
		application.logger.Error("write JSON response", "error", err)
	}
}

func (application *App) cors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if request.Header.Get("Origin") == application.config.AllowedOrigin {
			response.Header().Set("Access-Control-Allow-Origin", application.config.AllowedOrigin)
			response.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
			response.Header().Set("Access-Control-Allow-Headers", "Accept, Content-Type, Authorization")
			response.Header().Set("Vary", "Origin")
		}
		if request.Method == http.MethodOptions {
			response.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(response, request)
	})
}
