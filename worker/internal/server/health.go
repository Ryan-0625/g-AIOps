package server

import (
	"encoding/json"
	"net/http"
	"os"
	"sync"
	"time"
)

var startTime = time.Now()
var masterConnected bool
var mcMu sync.RWMutex

// SetMasterConnected updates the Master connection status for health reporting.
func SetMasterConnected(connected bool) {
	mcMu.Lock()
	defer mcMu.Unlock()
	masterConnected = connected
}

// HealthHandler responds with {"status":"ok","uptime":N,"pid":N,"dependencies":{...}}.
func HealthHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}

	mcMu.RLock()
	mc := masterConnected
	mcMu.RUnlock()

	masterStatus := "disconnected"
	if mc {
		masterStatus = "connected"
	}

	w.Header().Set("Content-Type", "application/json")
	resp := map[string]interface{}{
		"status": "ok",
		"uptime": int(time.Since(startTime).Seconds()),
		"pid":    os.Getpid(),
		"dependencies": map[string]interface{}{
			"master": masterStatus,
		},
	}
	json.NewEncoder(w).Encode(resp)
}
