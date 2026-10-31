package app

import (
	"context"
	"encoding/json"
	"testing"
	"time"
)

type recoveryScheduleStub struct {
	syncRunnerStub
	started chan struct{}
	stopped chan struct{}
}

func (runner recoveryScheduleStub) RecoverResolution(ctx context.Context) (bool, error) {
	close(runner.started)
	<-ctx.Done()
	close(runner.stopped)
	return false, ctx.Err()
}
func TestResolutionRecoveryShutdownCancelsAndWaits(t *testing.T) {
	runner := &recoveryScheduleStub{started: make(chan struct{}), stopped: make(chan struct{})}
	application := newAdminTestApp(runner)
	application.config.ShutdownTimeout = time.Second
	stop := application.startResolutionRecovery(context.Background())
	select {
	case <-runner.started:
	case <-time.After(time.Second):
		t.Fatal("scheduler did not start")
	}
	stop()
	select {
	case <-runner.stopped:
	default:
		t.Fatal("worker not stopped before shutdown returned")
	}
}

func TestResolutionRecoveryRejectsUnknownOutcomes(t *testing.T) {
	for _, payload := range []string{`{}`, `{"status":"SUCCESS"}`, `[]`} {
		if _, err := resolutionRecoveryContinues(json.RawMessage(payload)); err == nil {
			t.Fatal("unknown outcome accepted")
		}
	}
	more, err := resolutionRecoveryContinues(json.RawMessage(`{"status":"PROCESSED_WITH_BLOCKERS"}`))
	if err != nil || !more {
		t.Fatal("processed page did not allow fair continuation")
	}
	more, err = resolutionRecoveryContinues(json.RawMessage(`{"status":"RETRY_WAIT"}`))
	if err != nil || more {
		t.Fatal("failed step would spin")
	}
}
