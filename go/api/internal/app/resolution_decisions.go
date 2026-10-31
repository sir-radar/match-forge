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
	if !validResolutionApproval(decision) {
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

func (application *App) decodeResolution(response http.ResponseWriter, request *http.Request, body any) bool {
	decoder := json.NewDecoder(http.MaxBytesReader(response, request.Body, 128*1024))
	decoder.DisallowUnknownFields()
	if decoder.Decode(body) != nil {
		application.publicError(response, http.StatusBadRequest, "invalid resolution request")
		return false
	}
	if decoder.Decode(&struct{}{}) != io.EOF {
		application.publicError(response, http.StatusBadRequest, "one JSON request required")
		return false
	}
	return true
}

func (application *App) resolutionBatch(response http.ResponseWriter, request *http.Request) {
	operationName := map[string]string{"batch-preview": "batch_preview", "batch-apply": "batch_apply"}[request.PathValue("operation")]
	if operationName == "" {
		application.publicError(response, http.StatusBadRequest, "unsupported batch operation")
		return
	}
	applying := operationName == "batch_apply"
	if applying && !validAdminToken(application.config.AdminCLIToken, request.Header.Get("Authorization")) {
		application.publicError(response, http.StatusForbidden, "authenticated owner approval required")
		return
	}
	var body struct {
		Requests []resolutionDecision `json:"requests"`
	}
	if !application.decodeResolution(response, request, &body) {
		return
	}
	if len(body.Requests) < 1 || len(body.Requests) > 20 {
		application.publicError(response, http.StatusBadRequest, "review between 1 and 20 cases")
		return
	}
	operation, actor := "batch_preview", ""
	if applying {
		operation = "batch_apply"
		for _, decision := range body.Requests {
			if !validResolutionApproval(decision) {
				application.publicError(response, http.StatusBadRequest, "explicit per-case approval and preview version required")
				return
			}
		}
		identity := sha256.Sum256([]byte(application.config.AdminCLIToken))
		actor = "owner:" + hex.EncodeToString(identity[:8])
	}
	application.runResolution(response, request, resolutionRequest{Operation: operation, Requests: body.Requests, Actor: actor})
}

func validResolutionApproval(decision resolutionDecision) bool {
	return decision.Approved && canonicalIDPattern.MatchString(decision.RequestID) && resolutionDigest(decision.EvidenceVersion)
}
