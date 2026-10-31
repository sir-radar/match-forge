package app

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
)

type resolutionDecision struct {
	CaseKey         string            `json:"case_key"`
	Action          string            `json:"action"`
	Reason          string            `json:"reason"`
	Candidate       map[string]string `json:"candidate,omitempty"`
	EvidenceVersion string            `json:"evidence_version,omitempty"`
	RequestID       string            `json:"request_id,omitempty"`
	Approved        bool              `json:"approved,omitempty"`
}

func (application *App) resolutionPreview(response http.ResponseWriter, request *http.Request) {
	var decision resolutionDecision
	if !application.decodeResolution(response, request, &decision) {
		return
	}
	application.runResolution(response, request, resolutionRequest{Operation: "preview", Request: &decision})
}

func (application *App) resolutionApply(response http.ResponseWriter, request *http.Request) {
	if !validAdminToken(application.config.AdminCLIToken, request.Header.Get("Authorization")) {
		application.publicError(response, http.StatusForbidden, "authenticated owner approval required")
		return
	}
	var decision resolutionDecision
	if !application.decodeResolution(response, request, &decision) {
		return
	}
	if !decision.Approved || !canonicalIDPattern.MatchString(decision.RequestID) || !resolutionDigest(decision.EvidenceVersion) {
		application.publicError(response, http.StatusBadRequest, "explicit approval and preview version required")
		return
	}
	identity := sha256.Sum256([]byte(application.config.AdminCLIToken))
	application.runResolution(response, request, resolutionRequest{Operation: "apply", Request: &decision, Actor: "owner:" + hex.EncodeToString(identity[:8])})
}

func resolutionDigest(value string) bool {
	decoded, err := hex.DecodeString(value)
	return err == nil && len(decoded) == sha256.Size && hex.EncodeToString(decoded) == value
}

func (application *App) decodeResolution(response http.ResponseWriter, request *http.Request, body *resolutionDecision) bool {
	decoder := json.NewDecoder(http.MaxBytesReader(response, request.Body, 128*1024))
	decoder.DisallowUnknownFields()
	if decoder.Decode(body) != nil || body.CaseKey == "" || body.Action == "" || body.Reason == "" {
		application.publicError(response, http.StatusBadRequest, "invalid resolution request")
		return false
	}
	if decoder.Decode(&struct{}{}) != io.EOF {
		application.publicError(response, http.StatusBadRequest, "one JSON request required")
		return false
	}
	return true
}
