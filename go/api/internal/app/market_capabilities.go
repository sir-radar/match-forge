package app

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"time"
)

type marketScope struct {
	CompetitionID   string
	SeasonID        string
	KnowledgeCutoff time.Time
}

type marketCapabilityReader interface {
	MarketCapabilities(context.Context, marketScope) (json.RawMessage, error)
}

func parseMarketScope(request *http.Request) (marketScope, error) {
	query := request.URL.Query()
	allowed := map[string]bool{"competition_id": true, "season_id": true, "knowledge_cutoff": true}
	for key, values := range query {
		if len(values) != 1 || !allowed[key] {
			return marketScope{}, errors.New("invalid market scope parameters")
		}
	}
	scope := marketScope{CompetitionID: query.Get("competition_id"), SeasonID: query.Get("season_id")}
	cutoff, err := time.Parse(time.RFC3339Nano, query.Get("knowledge_cutoff"))
	if err != nil || cutoff.Nanosecond()%1000 != 0 || !canonicalIDPattern.MatchString(scope.CompetitionID) || !canonicalIDPattern.MatchString(scope.SeasonID) || cutoff.After(time.Now()) {
		return scope, errors.New("market scope requires canonical competition/season IDs and a nonfuture timezone-aware knowledge cutoff with at most microsecond precision")
	}
	scope.KnowledgeCutoff = cutoff
	return scope, nil
}

func (application *App) marketCapabilities(response http.ResponseWriter, request *http.Request) {
	response.Header().Set("Cache-Control", "no-store")
	scope, err := parseMarketScope(request)
	if err != nil {
		application.publicError(response, http.StatusBadRequest, err.Error())
		return
	}
	reader, ok := application.syncRunner.(marketCapabilityReader)
	if !ok {
		application.respondOperation(response, nil, errProductUnavailable)
		return
	}
	report, err := reader.MarketCapabilities(request.Context(), scope)
	if err == nil {
		err = validateMarketSummary(report, scope)
	}
	if err != nil {
		application.respondOperation(response, nil, errProductUnavailable)
		return
	}
	application.writeJSON(response, http.StatusOK, report)
}

func validateMarketSummary(report []byte, scope marketScope) error {
	var envelope struct {
		Contract      string            `json:"contract"`
		Version       string            `json:"contract_version"`
		CompetitionID string            `json:"competition_id"`
		SeasonID      string            `json:"season_id"`
		Cutoff        time.Time         `json:"knowledge_cutoff"`
		ReadOnly      string            `json:"read_only"`
		Authoritative *bool             `json:"authoritative"`
		Markets       []json.RawMessage `json:"markets"`
	}
	if json.Unmarshal(report, &envelope) != nil {
		return errProductUnavailable
	}
	if envelope.Contract != "MarketCapabilitySummary" || envelope.Version != "1" || [2]string{envelope.CompetitionID, envelope.SeasonID} != [2]string{scope.CompetitionID, scope.SeasonID} || !envelope.Cutoff.Equal(scope.KnowledgeCutoff) || envelope.ReadOnly != "on" || envelope.Authoritative == nil || *envelope.Authoritative || envelope.Markets == nil {
		return errProductUnavailable
	}
	return nil
}

func (runner *CommandSyncRunner) MarketCapabilities(ctx context.Context, scope marketScope) (json.RawMessage, error) {
	var exists bool
	err := runner.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM football.seasons WHERE id=$1 AND competition_id=$2)`, scope.SeasonID, scope.CompetitionID).Scan(&exists)
	if err != nil || !exists {
		return nil, errProductUnavailable
	}
	command := exec.CommandContext(ctx, filepath.Join(runner.repoRoot, ".tools/bin/uv"),
		"run", "--locked", "football", "models", "market-capabilities", "--summary",
		"--competition-id", scope.CompetitionID, "--season-id", scope.SeasonID,
		"--knowledge-cutoff", scope.KnowledgeCutoff.Format(time.RFC3339Nano),
		"--model-registration", filepath.Join(runner.repoRoot, "config/models/current-champion.json"))
	command.Dir = runner.repoRoot
	command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	command.Cancel = func() error {
		if command.Process == nil {
			return os.ErrProcessDone
		}
		return syscall.Kill(-command.Process.Pid, syscall.SIGKILL)
	}
	command.Env = append(os.Environ(), "DATABASE_URL="+runner.pool.Config().ConnConfig.ConnString())
	var output boundedCommandOutput
	command.Stdout = &output
	if command.Run() != nil {
		return nil, errProductUnavailable
	}
	report := json.RawMessage(output.buffer.Bytes())
	if validateMarketSummary(report, scope) != nil {
		return nil, errProductUnavailable
	}
	return report, nil
}
