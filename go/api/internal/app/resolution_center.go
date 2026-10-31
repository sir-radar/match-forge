package app

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"unicode/utf8"
)

type resolutionRequest struct {
	Operation string               `json:"operation"`
	View      string               `json:"view"`
	Query     map[string]any       `json:"query,omitempty"`
	Request   *resolutionDecision  `json:"request,omitempty"`
	Requests  []resolutionDecision `json:"requests,omitempty"`
	Actor     string               `json:"actor,omitempty"`
}

type resolutionResult struct {
	StatusCode int             `json:"status_code"`
	Data       json.RawMessage `json:"data"`
	Error      string          `json:"error,omitempty"`
}

type resolutionRunner interface {
	Resolution(context.Context, resolutionRequest) (resolutionResult, error)
}

func (application *App) resolutionRead(response http.ResponseWriter, request *http.Request) {
	view := request.PathValue("view")
	switch view {
	case "identity", "fixtures", "missing", "parity", "cutover", "history", "detail":
	default:
		application.publicError(response, http.StatusBadRequest, "unsupported resolution view")
		return
	}
	page, err := operationPagination(request)
	if err != nil {
		application.publicError(response, http.StatusBadRequest, "invalid pagination")
		return
	}
	query := map[string]any{"page": page.Page, "page_size": page.PageSize}
	for _, key := range []string{"provider", "status", "kind", "q", "case_key"} {
		if utf8.RuneCountInString(request.URL.Query().Get(key)) > 256 {
			application.publicError(response, http.StatusBadRequest, "filter is too long")
			return
		}
		query[key] = request.URL.Query().Get(key)
	}
	application.runResolution(response, request, resolutionRequest{Operation: "read", View: view, Query: query})
}

func (application *App) runResolution(response http.ResponseWriter, request *http.Request, input resolutionRequest) {
	response.Header().Set("Cache-Control", "no-store")
	runner, ok := application.syncRunner.(resolutionRunner)
	if !ok {
		application.respondOperation(response, nil, errProductUnavailable)
		return
	}
	result, err := runner.Resolution(request.Context(), input)
	if err != nil {
		application.respondOperation(response, nil, errProductUnavailable)
		return
	}
	if result.StatusCode == http.StatusOK && json.Valid(result.Data) {
		if input.Operation == "apply" || input.Operation == "batch_apply" {
			if notifier, ok := application.syncRunner.(interface{ WakeResolutionRecovery() }); ok {
				notifier.WakeResolutionRecovery()
			}
		}
		application.writeJSON(response, http.StatusOK, result.Data)
		return
	}
	if result.StatusCode == http.StatusBadRequest || result.StatusCode == http.StatusConflict {
		application.publicError(response, result.StatusCode, result.Error)
		return
	}
	application.respondOperation(response, nil, errProductUnavailable)
}

func (runner *CommandSyncRunner) Resolution(ctx context.Context, input resolutionRequest) (resolutionResult, error) {
	payload, err := json.Marshal(input)
	if err != nil {
		return resolutionResult{}, err
	}
	command := exec.CommandContext(ctx, filepath.Join(runner.repoRoot, ".tools/bin/uv"),
		"run", "--locked", "python", "-m", "football.product.resolution_center", "--repo-root", runner.repoRoot)
	command.Dir = runner.repoRoot
	command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	command.Cancel = func() error {
		if command.Process == nil {
			return os.ErrProcessDone
		}
		return syscall.Kill(-command.Process.Pid, syscall.SIGKILL)
	}
	command.Stdin = bytes.NewReader(payload)
	command.Env = append(os.Environ(), "DATABASE_URL="+runner.pool.Config().ConnConfig.ConnString())
	var output resolutionOutput
	command.Stdout = &output
	if command.Run() != nil {
		return resolutionResult{}, errProductUnavailable
	}
	var result resolutionResult
	if json.Unmarshal(output.buffer.Bytes(), &result) != nil {
		return result, errProductUnavailable
	}
	return result, nil
}

type resolutionOutput struct{ buffer bytes.Buffer }

func (output *resolutionOutput) Write(payload []byte) (int, error) {
	if output.buffer.Len()+len(payload) > 2*1024*1024 {
		return 0, errors.New("resolution response too large")
	}
	return output.buffer.Write(payload)
}
