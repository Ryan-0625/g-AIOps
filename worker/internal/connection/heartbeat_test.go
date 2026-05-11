package connection_test

import (
	"testing"
	"time"

	"github.com/gaiops/worker/internal/connection"
)

func TestNewHeartbeatDefaultInterval(t *testing.T) {
	h := connection.NewHeartbeat(0)
	if h == nil {
		t.Fatal("expected non-nil heartbeat")
	}
}

func TestNewHeartbeatCustomInterval(t *testing.T) {
	h := connection.NewHeartbeat(30)
	if h == nil {
		t.Fatal("expected non-nil heartbeat")
	}
}

// Start exits cleanly when done channel is closed (verifies no deadlock).
func TestHeartbeatStartExitsOnDone(t *testing.T) {
	h := connection.NewHeartbeat(1)
	done := make(chan struct{})

	exited := make(chan struct{})
	go func() {
		defer func() { recover() }() // ignore nil conn panic
		h.Start(nil, done)
		close(exited)
	}()

	close(done)

	select {
	case <-exited:
		// ok
	case <-time.After(5 * time.Second):
		t.Fatal("heartbeat did not stop after done was closed")
	}
}
