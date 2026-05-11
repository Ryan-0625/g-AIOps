package connection

import (
	"time"

	"github.com/gorilla/websocket"
)

// Heartbeat sends WebSocket Ping frames at a fixed interval.
//
// Runs in its own goroutine so long tool executions never block it.
type Heartbeat struct {
	interval time.Duration
}

func NewHeartbeat(intervalSec int) *Heartbeat {
	if intervalSec <= 0 {
		intervalSec = 15
	}
	return &Heartbeat{interval: time.Duration(intervalSec) * time.Second}
}

// Start begins sending Ping frames. Stops when doneCh is closed.
// Blocks the caller; call in a separate goroutine.
func (h *Heartbeat) Start(conn *websocket.Conn, doneCh <-chan struct{}) {
	ticker := time.NewTicker(h.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			// Use WriteControl — bypasses the message queue, works even during
			// concurrent ReadMessage/WriteMessage calls.
			if err := conn.WriteControl(websocket.PingMessage, []byte("heartbeat"), time.Now().Add(5*time.Second)); err != nil {
				return
			}
		case <-doneCh:
			return
		}
	}
}
