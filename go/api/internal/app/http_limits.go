package app

import (
	"context"
	"net/http"
	"time"
)

const (
	defaultReadTimeout    = 15 * time.Second
	defaultHandlerTimeout = 30 * time.Second
	defaultWriteTimeout   = 35 * time.Second
	defaultIdleTimeout    = 60 * time.Second
)

func (config Config) servingDefaults() Config {
	if config.ReadHeaderTimeout == 0 {
		config.ReadHeaderTimeout = defaultReadHeaderWait
	}
	if config.ShutdownTimeout == 0 {
		config.ShutdownTimeout = defaultShutdownDeadline
	}
	if config.ReadTimeout == 0 {
		config.ReadTimeout = defaultReadTimeout
	}
	if config.HandlerTimeout == 0 {
		config.HandlerTimeout = defaultHandlerTimeout
	}
	if config.WriteTimeout == 0 {
		config.WriteTimeout = defaultWriteTimeout
	}
	if config.IdleTimeout == 0 {
		config.IdleTimeout = defaultIdleTimeout
	}
	return config
}

func (application *App) requestDeadline(handler http.Handler) http.Handler {
	timeout := http.TimeoutHandler(handler, application.config.HandlerTimeout, `{"error":"request timed out"}`)
	return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		ctx, cancel := context.WithTimeout(request.Context(), application.config.HandlerTimeout)
		defer cancel()
		writer := &timeoutResponseWriter{ResponseWriter: response, ctx: ctx}
		timeout.ServeHTTP(writer, request.WithContext(ctx))
		if writer.cancelled && !writer.bodyWritten {
			_, _ = response.Write([]byte(`{"error":"request cancelled"}`))
		}
	})
}

// The standard timeout handler cancels handler/query contexts and buffers writes.
// Keep the operational API's JSON timeout contract when its deadline expires.
type timeoutResponseWriter struct {
	http.ResponseWriter
	ctx         context.Context
	cancelled   bool
	bodyWritten bool
}

func (writer *timeoutResponseWriter) WriteHeader(status int) {
	if status == http.StatusServiceUnavailable && writer.ctx.Err() != nil {
		status = http.StatusRequestTimeout
		writer.cancelled = true
		if writer.ctx.Err() == context.DeadlineExceeded {
			status = http.StatusGatewayTimeout
			writer.cancelled = false
		}
		writer.Header().Set("Content-Type", "application/json")
	}
	writer.ResponseWriter.WriteHeader(status)
}
func (writer *timeoutResponseWriter) Unwrap() http.ResponseWriter { return writer.ResponseWriter }

func (application *App) httpServer() *http.Server {
	return &http.Server{Addr: application.config.Address, Handler: application.handler,
		ReadHeaderTimeout: application.config.ReadHeaderTimeout, ReadTimeout: application.config.ReadTimeout,
		WriteTimeout: application.config.WriteTimeout, IdleTimeout: application.config.IdleTimeout}
}

func (writer *timeoutResponseWriter) Write(value []byte) (int, error) {
	writer.bodyWritten = true
	return writer.ResponseWriter.Write(value)
}
