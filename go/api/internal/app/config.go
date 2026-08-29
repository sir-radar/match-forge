package app

import (
	"fmt"
	"net"
	"os"
	"time"
)

const (
	defaultAPIAddress       = "127.0.0.1:8080"
	defaultPostgresAddress  = "127.0.0.1:55433"
	defaultRedisAddress     = "127.0.0.1:56379"
	defaultDependencyWait   = 500 * time.Millisecond
	defaultReadHeaderWait   = 5 * time.Second
	defaultShutdownDeadline = 5 * time.Second
)

// Config contains the operational API settings owned by this process.
type Config struct {
	Address           string
	PostgresAddress   string
	RedisAddress      string
	Version           string
	DependencyTimeout time.Duration
	ReadHeaderTimeout time.Duration
	ShutdownTimeout   time.Duration
}

// ConfigFromEnv loads and validates process configuration.
func ConfigFromEnv(version string) (Config, error) {
	dependencyTimeout, err := durationFromEnv("DEPENDENCY_TIMEOUT", defaultDependencyWait)
	if err != nil {
		return Config{}, err
	}
	readHeaderTimeout, err := durationFromEnv("READ_HEADER_TIMEOUT", defaultReadHeaderWait)
	if err != nil {
		return Config{}, err
	}
	shutdownTimeout, err := durationFromEnv("SHUTDOWN_TIMEOUT", defaultShutdownDeadline)
	if err != nil {
		return Config{}, err
	}
	config := Config{
		Address:           valueFromEnv("API_ADDR", defaultAPIAddress),
		PostgresAddress:   valueFromEnv("POSTGRES_ADDR", defaultPostgresAddress),
		RedisAddress:      valueFromEnv("REDIS_ADDR", defaultRedisAddress),
		Version:           version,
		DependencyTimeout: dependencyTimeout,
		ReadHeaderTimeout: readHeaderTimeout,
		ShutdownTimeout:   shutdownTimeout,
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
			return Config{}, fmt.Errorf("%s must be host:port: %w", address.name, err)
		}
	}
	return config, nil
}

func valueFromEnv(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
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
