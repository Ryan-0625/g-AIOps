package server

import (
	"encoding/json"
	"net/http"
	"os"
	"time"
)

var startTime = time.Now()

// HealthHandler responds with {"status":"ok","uptime":N,"pid":N}.
func HealthHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	resp := map[string]interface{}{
		"status": "ok",
		"uptime": int(time.Since(startTime).Seconds()),
		"pid":    os.Getpid(),
	}
	json.NewEncoder(w).Encode(resp)
}
