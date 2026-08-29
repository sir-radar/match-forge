package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"football-forecasting/go/api/internal/app"
)

var version = "dev"

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	config, err := app.ConfigFromEnv(version)
	if err != nil {
		logger.Error("invalid configuration", "error", err)
		os.Exit(2)
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	application := app.New(config, logger, app.NewTCPReadiness(config))
	if err := application.Run(ctx); err != nil {
		logger.Error("api stopped", "error", err)
		os.Exit(1)
	}
}
