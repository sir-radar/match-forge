package app

import (
	"bufio"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func limitsApp(config Config) *App {
	return New(config, slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{})
}

func TestServingDefaults(t *testing.T) {
	application := limitsApp(Config{})
	server := application.httpServer()
	if server.ReadTimeout != 15*time.Second || application.config.HandlerTimeout != 30*time.Second || server.WriteTimeout != 35*time.Second || server.IdleTimeout != 60*time.Second || server.ReadHeaderTimeout != 5*time.Second {
		t.Fatalf("unapproved serving defaults: %+v", server)
	}
}

func TestHandlerExecutionCancellation(t *testing.T) {
	application := limitsApp(Config{HandlerTimeout: 20 * time.Millisecond})
	cancelled := make(chan struct{})
	handler := application.requestDeadline(http.HandlerFunc(func(_ http.ResponseWriter, request *http.Request) { <-request.Context().Done(); close(cancelled) }))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/", nil))
	if response.Code != http.StatusGatewayTimeout || response.Header().Get("Content-Type") != "application/json" || !strings.Contains(response.Body.String(), "request timed out") {
		t.Fatalf("timeout: %d %s %s", response.Code, response.Header(), response.Body)
	}
	select {
	case <-cancelled:
	case <-time.After(time.Second):
		t.Fatal("handler context not cancelled")
	}
}

func serveLimits(t *testing.T, application *App) string {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	server := application.httpServer()
	go func() { _ = server.Serve(listener) }()
	t.Cleanup(func() { _ = server.Close() })
	return listener.Addr().String()
}

func TestSlowBodyAndIdleConnectionAreBounded(t *testing.T) {
	application := limitsApp(Config{ReadTimeout: 40 * time.Millisecond, IdleTimeout: 40 * time.Millisecond, WriteTimeout: time.Second, HandlerTimeout: time.Second})
	application.handler = application.requestDeadline(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		_, err := io.ReadAll(request.Body)
		if err != nil {
			response.WriteHeader(http.StatusRequestTimeout)
			return
		}
		response.WriteHeader(http.StatusNoContent)
	}))
	address := serveLimits(t, application)
	connection, err := net.Dial("tcp", address)
	if err != nil {
		t.Fatal(err)
	}
	defer connection.Close()
	_ = connection.SetDeadline(time.Now().Add(time.Second))
	_, err = io.WriteString(connection, "POST / HTTP/1.1\r\nHost: "+address+"\r\nContent-Length: 100\r\n\r\n{")
	if err != nil {
		t.Fatal(err)
	}
	response, err := http.ReadResponse(bufio.NewReader(connection), nil)
	if err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if response.StatusCode != http.StatusRequestTimeout {
		t.Fatalf("slow body status %d", response.StatusCode)
	}
}

func TestResponseWriteDeadlineStopsBlockedHandlerWrites(t *testing.T) {
	application := limitsApp(Config{WriteTimeout: 30 * time.Millisecond, HandlerTimeout: time.Second})
	finished := make(chan error, 1)
	application.handler = http.HandlerFunc(func(response http.ResponseWriter, _ *http.Request) {
		_, err := response.Write([]byte(strings.Repeat("x", 16*1024*1024)))
		finished <- err
	})
	address := serveLimits(t, application)
	connection, err := net.Dial("tcp", address)
	if err != nil {
		t.Fatal(err)
	}
	defer connection.Close()
	if _, err := io.WriteString(connection, "GET / HTTP/1.1\r\nHost: "+address+"\r\n\r\n"); err != nil {
		t.Fatal(err)
	}
	select {
	case err := <-finished:
		if err == nil {
			t.Fatal("blocked response ignored write deadline")
		}
	case <-time.After(2 * time.Second):
		t.Fatal("blocked response continued")
	}
}

func TestIdleConnectionClosesAfterKeepAliveResponse(t *testing.T) {
	application := limitsApp(Config{IdleTimeout: 30 * time.Millisecond})
	address := serveLimits(t, application)
	connection, err := net.Dial("tcp", address)
	if err != nil {
		t.Fatal(err)
	}
	defer connection.Close()
	_ = connection.SetDeadline(time.Now().Add(time.Second))
	if _, err := io.WriteString(connection, "GET /healthz HTTP/1.1\r\nHost: "+address+"\r\n\r\n"); err != nil {
		t.Fatal(err)
	}
	reader := bufio.NewReader(connection)
	response, err := http.ReadResponse(reader, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := io.Copy(io.Discard, response.Body); err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if _, err := reader.ReadByte(); err != io.EOF {
		t.Fatalf("idle connection not closed: %v", err)
	}
}

func TestAdminBodyCapRejectsOversizeAndTrailingJSON(t *testing.T) {
	for _, body := range []string{`{}` + strings.Repeat(" ", 64*1024), `{} {}`} {
		requests := make(chan SyncRequest, 1)
		application := NewWithSyncRunner(Config{Address: "127.0.0.1:8080", AllowedOrigin: "http://127.0.0.1:3000"}, slog.New(slog.NewTextHandler(io.Discard, nil)), readinessStub{}, unavailableProductStore{}, scheduleRunner{requests: requests})
		request := httptest.NewRequest(http.MethodPost, "http://127.0.0.1:8080/v1/admin/sync/mvp", strings.NewReader(body))
		request.RemoteAddr = "127.0.0.1:1234"
		request.Header.Set("Origin", "http://127.0.0.1:3000")
		request.Header.Set("Content-Type", "application/json")
		response := httptest.NewRecorder()
		application.Handler().ServeHTTP(response, request)
		if response.Code != http.StatusBadRequest {
			t.Fatalf("body accepted: %d %s", response.Code, response.Body)
		}
		select {
		case <-requests:
			t.Fatal("invalid body submitted work")
		default:
		}
	}
}
