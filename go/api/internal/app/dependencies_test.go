package app

import (
	"context"
	"io"
	"net"
	"testing"
	"time"
)

func protocolListener(t *testing.T, reply string) string {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	done := make(chan struct{})
	t.Cleanup(func() { close(done); _ = listener.Close() })
	go func() {
		for {
			connection, err := listener.Accept()
			if err != nil {
				return
			}
			go func() {
				defer connection.Close()
				if reply == "" {
					select {
					case <-done:
					case <-time.After(time.Second):
					}
					return
				}
				request := make([]byte, 14)
				_, _ = io.ReadFull(connection, request)
				_, _ = io.WriteString(connection, reply)
			}()
		}
	}()
	return listener.Addr().String()
}

func TestRedisReadinessRequiresBoundedProtocolPong(t *testing.T) {
	for _, reply := range []string{"+PONG\r\n", "NOTREDIS", ""} {
		address := protocolListener(t, reply)
		ctx, cancel := context.WithTimeout(context.Background(), 40*time.Millisecond)
		started := time.Now()
		err := redisReady(ctx, address)
		cancel()
		if (err == nil) != (reply == "+PONG\r\n") {
			t.Fatalf("protocol %q: %v", reply, err)
		}
		if time.Since(started) > time.Second {
			t.Fatal("Redis readiness unbounded")
		}
	}
}
