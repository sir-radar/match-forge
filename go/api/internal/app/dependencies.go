package app

import (
	"context"
	"fmt"
	"net"
	"time"
)

// ReadinessChecker reports whether required runtime dependencies are reachable.
type ReadinessChecker interface {
	Ready(context.Context) error
}

// TCPReadiness checks the PostgreSQL and Redis TCP endpoints without owning data access.
type TCPReadiness struct {
	addresses []string
	timeout   time.Duration
}

// NewTCPReadiness creates a bounded dependency checker.
func NewTCPReadiness(config Config) TCPReadiness {
	return TCPReadiness{
		addresses: []string{config.PostgresAddress, config.RedisAddress},
		timeout:   config.DependencyTimeout,
	}
}

// Ready succeeds only when every required dependency accepts a TCP connection.
func (readiness TCPReadiness) Ready(ctx context.Context) error {
	dialer := net.Dialer{Timeout: readiness.timeout}
	for _, address := range readiness.addresses {
		connection, err := dialer.DialContext(ctx, "tcp", address)
		if err != nil {
			return fmt.Errorf("dependency %s unavailable: %w", address, err)
		}
		if err := connection.Close(); err != nil {
			return fmt.Errorf("close dependency %s connection: %w", address, err)
		}
	}
	return nil
}
