package app

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
)

// App owns the operational HTTP surface and lifecycle.
type App struct {
	config    Config
	logger    *slog.Logger
	readiness ReadinessChecker
	handler   http.Handler
}

// New constructs the operational API without starting network listeners.
func New(config Config, logger *slog.Logger, readiness ReadinessChecker) *App {
	application := &App{config: config, logger: logger, readiness: readiness}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", application.health)
	mux.HandleFunc("GET /readyz", application.ready)
	mux.HandleFunc("GET /version", application.version)
	application.handler = mux
	return application
}

// Handler exposes the HTTP contract for tests and servers.
func (application *App) Handler() http.Handler {
	return application.handler
}

// Run serves until the context is cancelled, then performs bounded graceful shutdown.
func (application *App) Run(ctx context.Context) error {
	server := &http.Server{
		Addr:              application.config.Address,
		Handler:           application.handler,
		ReadHeaderTimeout: application.config.ReadHeaderTimeout,
	}
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
		return server.Shutdown(shutdownContext)
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

func (application *App) version(response http.ResponseWriter, _ *http.Request) {
	application.writeJSON(response, http.StatusOK, map[string]string{"version": application.config.Version})
}

func (application *App) writeJSON(response http.ResponseWriter, status int, value map[string]string) {
	response.Header().Set("Content-Type", "application/json")
	response.WriteHeader(status)
	if err := json.NewEncoder(response).Encode(value); err != nil {
		application.logger.Error("write JSON response", "error", err)
	}
}
