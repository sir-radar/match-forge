package app

import (
	"fmt"
	"net"
	"os"
	"path/filepath"
	"time"
)

const (
	defaultAPIAddress       = "127.0.0.1:8080"
	defaultDependencyWait   = 500 * time.Millisecond
	defaultReadHeaderWait   = 5 * time.Second
	defaultShutdownDeadline = 5 * time.Second
)

// Config contains the operational API settings owned by this process.
type Config struct {
	Address                 string
	DatabaseURL             string
	AllowedOrigin           string
	AdminCLIToken           string
	PostgresAddress         string
	RedisAddress            string
	Version                 string
	RepoRoot                string
	DependencyTimeout       time.Duration
	ReadHeaderTimeout       time.Duration
	ReadTimeout             time.Duration
	HandlerTimeout          time.Duration
	WriteTimeout            time.Duration
	IdleTimeout             time.Duration
	ShutdownTimeout         time.Duration
	OperationalSyncInterval time.Duration
	HistorySyncEnabled      bool
	HistorySyncInterval     time.Duration
	FotMobEnabled           bool
	PitchAPIEnabled         bool
}

// ConfigFromEnv loads and validates process configuration.
func ConfigFromEnv(version string) (Config, error) {
	databaseURL, err := requiredEnv("DATABASE_URL")
	if err != nil {
		return Config{}, err
	}
	postgresAddress, err := requiredEnv("POSTGRES_ADDR")
	if err != nil {
		return Config{}, err
	}
	redisAddress, err := requiredEnv("REDIS_ADDR")
	if err != nil {
		return Config{}, err
	}
	dependencyTimeout, readHeaderTimeout, shutdownTimeout, err := runtimeDurationsFromEnv()
	if err != nil {
		return Config{}, err
	}
	operationalSyncInterval, fotMobEnabled, pitchAPIEnabled, err := operationalConfigFromEnv()
	if err != nil {
		return Config{}, err
	}
	historySyncInterval, err := historySyncIntervalFromEnv()
	if err != nil {
		return Config{}, err
	}
	repoRoot, err := resolveRepoRoot(os.Getenv("MATCHFORGE_REPO_ROOT"))
	if err != nil {
		return Config{}, err
	}
	config := Config{
		Address:                 valueFromEnv("API_ADDR", defaultAPIAddress),
		DatabaseURL:             databaseURL,
		AllowedOrigin:           valueFromEnv("WEB_ORIGIN", "http://127.0.0.1:3000"),
		AdminCLIToken:           os.Getenv("MATCHFORGE_ADMIN_CLI_TOKEN"),
		PostgresAddress:         postgresAddress,
		RedisAddress:            redisAddress,
		Version:                 version,
		RepoRoot:                repoRoot,
		DependencyTimeout:       dependencyTimeout,
		ReadHeaderTimeout:       readHeaderTimeout,
		ShutdownTimeout:         shutdownTimeout,
		OperationalSyncInterval: operationalSyncInterval,
		HistorySyncEnabled:      os.Getenv("MATCHFORGE_HISTORY_SYNC_ENABLED") == "true",
		HistorySyncInterval:     historySyncInterval,
		FotMobEnabled:           fotMobEnabled,
		PitchAPIEnabled:         pitchAPIEnabled,
	}
	if err := validateRuntimeConfig(&config); err != nil {
		return Config{}, err
	}
	return config, nil
}

func validateRuntimeConfig(config *Config) error {
	if err := loadServingDurations(config); err != nil {
		return err
	}
	addresses := []struct {
		name  string
		value string
	}{
		{name: "API_ADDR", value: config.Address},
		{name: "POSTGRES_ADDR", value: config.PostgresAddress},
		{name: "REDIS_ADDR", value: config.RedisAddress},
	}
	for _, address := range addresses {
		if _, _, err := net.SplitHostPort(address.value); err != nil {
			return fmt.Errorf("%s must be host:port: %w", address.name, err)
		}
	}
	return nil
}

func historySyncIntervalFromEnv() (time.Duration, error) {
	interval, err := durationFromEnv("MATCHFORGE_HISTORY_SYNC_INTERVAL", time.Hour)
	if err != nil {
		return 0, err
	}
	if interval < time.Hour {
		return 0, fmt.Errorf("MATCHFORGE_HISTORY_SYNC_INTERVAL must be at least 1h")
	}
	return interval, nil
}

func runtimeDurationsFromEnv() (time.Duration, time.Duration, time.Duration, error) {
	dependency, err := durationFromEnv("DEPENDENCY_TIMEOUT", defaultDependencyWait)
	if err != nil {
		return 0, 0, 0, err
	}
	readHeader, err := durationFromEnv("READ_HEADER_TIMEOUT", defaultReadHeaderWait)
	if err != nil {
		return 0, 0, 0, err
	}
	shutdown, err := durationFromEnv("SHUTDOWN_TIMEOUT", defaultShutdownDeadline)
	return dependency, readHeader, shutdown, err
}

func operationalConfigFromEnv() (time.Duration, bool, bool, error) {
	interval, err := optionalDurationFromEnv("MATCHFORGE_OPERATIONAL_SYNC_INTERVAL")
	return interval,
		os.Getenv("MATCHFORGE_FOTMOB_ENABLED") == "true",
		os.Getenv("MATCHFORGE_PITCHAPI_ENABLED") == "true",
		err
}

func optionalDurationFromEnv(name string) (time.Duration, error) {
	value := os.Getenv(name)
	if value == "" || value == "0" {
		return 0, nil
	}
	duration, err := time.ParseDuration(value)
	if err != nil || duration < 30*time.Second {
		return 0, fmt.Errorf("%s must be zero or at least 30s", name)
	}
	return duration, nil
}

func resolveRepoRoot(configured string) (string, error) {
	if configured != "" {
		absolute, err := filepath.Abs(configured)
		if err != nil {
			return "", fmt.Errorf("MATCHFORGE_REPO_ROOT: %w", err)
		}
		if isRepoRoot(absolute) {
			return absolute, nil
		}
		return "", fmt.Errorf("MATCHFORGE_REPO_ROOT does not identify the MatchForge repository")
	}
	current, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("resolve repository root: %w", err)
	}
	for {
		if isRepoRoot(current) {
			return current, nil
		}
		parent := filepath.Dir(current)
		if parent == current {
			return "", fmt.Errorf("cannot resolve MatchForge repository root; set MATCHFORGE_REPO_ROOT")
		}
		current = parent
	}
}

func isRepoRoot(path string) bool {
	for _, required := range []string{"Makefile", "python", "go", "web"} {
		if _, err := os.Stat(filepath.Join(path, required)); err != nil {
			return false
		}
	}
	return true
}

func valueFromEnv(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}

func requiredEnv(name string) (string, error) {
	value := os.Getenv(name)
	if value == "" {
		return "", fmt.Errorf("%s is required", name)
	}
	return value, nil
}

func durationFromEnv(name string, fallback time.Duration) (time.Duration, error) {
	value := os.Getenv(name)
	if value == "" {
		return fallback, nil
	}
	duration, err := time.ParseDuration(value)
	if err != nil || duration <= 0 {
		return 0, fmt.Errorf("%s must be a positive duration", name)
	}
	return duration, nil
}

func loadServingDurations(config *Config) error {
	settings := []struct {
		name     string
		target   *time.Duration
		fallback time.Duration
	}{
		{"READ_TIMEOUT", &config.ReadTimeout, defaultReadTimeout},
		{"HANDLER_TIMEOUT", &config.HandlerTimeout, defaultHandlerTimeout},
		{"WRITE_TIMEOUT", &config.WriteTimeout, defaultWriteTimeout},
		{"IDLE_TIMEOUT", &config.IdleTimeout, defaultIdleTimeout},
	}
	for _, setting := range settings {
		value, err := durationFromEnv(setting.name, setting.fallback)
		if err != nil {
			return err
		}
		*setting.target = value
	}
	if config.WriteTimeout <= config.HandlerTimeout {
		return fmt.Errorf("WRITE_TIMEOUT must exceed HANDLER_TIMEOUT")
	}
	return nil
}
