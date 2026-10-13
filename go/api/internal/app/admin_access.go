package app

import (
	"crypto/sha256"
	"crypto/subtle"
	"mime"
	"net"
	"net/http"
	"strings"
)

// Administrative routes require private-local access and either the trusted
// browser Origin or the owner-approved credential for origin-less automation.
func (application *App) adminAccess(next http.Handler) http.Handler {
	return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if !strings.HasPrefix(request.URL.Path, "/v1/admin/") ||
			request.Method == http.MethodOptions {
			next.ServeHTTP(response, request)
			return
		}
		if !application.localAdminRequest(request) {
			application.writeJSON(response, http.StatusForbidden, map[string]string{"error": "administrative access denied"})
			return
		}
		if request.Method != http.MethodGet && request.Method != http.MethodHead {
			mediaType, _, err := mime.ParseMediaType(request.Header.Get("Content-Type"))
			if err != nil || mediaType != "application/json" {
				application.writeJSON(response, http.StatusUnsupportedMediaType, map[string]string{"error": "Content-Type must be application/json"})
				return
			}
		}
		next.ServeHTTP(response, request)
	})
}

func (application *App) localAdminRequest(request *http.Request) bool {
	address := valueOrDefault(application.config.Address, defaultAPIAddress)
	configuredHost, port, err := net.SplitHostPort(address)
	if err != nil || !loopbackHost(configuredHost) {
		return false
	}
	host, requestPort, err := net.SplitHostPort(request.Host)
	if err != nil || !loopbackHost(host) || requestPort != port {
		return false
	}
	peer, _, err := net.SplitHostPort(request.RemoteAddr)
	if err != nil || !loopbackHost(peer) {
		return false
	}
	origin := request.Header.Get("Origin")
	if origin != "" {
		return application.config.AllowedOrigin != "" && origin == application.config.AllowedOrigin
	}
	return validAdminToken(application.config.AdminCLIToken, request.Header.Get("Authorization"))
}

func validAdminToken(secret, authorization string) bool {
	if secret == "" || !strings.HasPrefix(authorization, "Bearer ") {
		return false
	}
	expected := sha256.Sum256([]byte(secret))
	supplied := sha256.Sum256([]byte(strings.TrimPrefix(authorization, "Bearer ")))
	return subtle.ConstantTimeCompare(expected[:], supplied[:]) == 1
}

func loopbackHost(host string) bool {
	if host == "localhost" {
		return true
	}
	address := net.ParseIP(host)
	return address != nil && address.IsLoopback()
}

func valueOrDefault(value, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}
