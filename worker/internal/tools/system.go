package tools

import (
	"context"
	"fmt"
	"os"
	"runtime"
	"time"

	"github.com/gaiops/worker/internal/registry"
)

func init() {
	registry.Global.Register(registry.Tool{
		Action:       "system.info",
		Timeout:      5 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeSystemInfo,
	})
}

func executeSystemInfo(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	hostname, _ := os.Hostname()

	result := map[string]interface{}{
		"os":         runtime.GOOS,
		"arch":       runtime.GOARCH,
		"hostname":   hostname,
		"go_version": runtime.Version(),
		"cpu_cores":  runtime.NumCPU(),
	}

	// Uptime via /proc/uptime (Linux).
	uptime, err := readUptime()
	if err == nil {
		result["uptime_seconds"] = uptime
	}

	// Memory via /proc/meminfo (Linux).
	memTotal, memAvail, err := readMemInfo()
	if err == nil {
		totalGB := float64(memTotal) / (1024 * 1024)
		usedGB := float64(memTotal-memAvail) / (1024 * 1024)
		result["memory_total_gb"] = roundTo2(totalGB)
		result["memory_used_gb"] = roundTo2(usedGB)
		result["memory_usage_pct"] = roundTo2(float64(memTotal-memAvail) / float64(memTotal) * 100)
	}

	return result, nil
}

func readUptime() (int64, error) {
	data, err := os.ReadFile("/proc/uptime")
	if err != nil {
		return 0, err
	}
	var secs float64
	if _, err := fmt.Sscanf(string(data), "%f", &secs); err != nil {
		return 0, err
	}
	return int64(secs), nil
}

func readMemInfo() (total, avail uint64, err error) {
	data, err := os.ReadFile("/proc/meminfo")
	if err != nil {
		return 0, 0, err
	}
	content := string(data)
	fmt.Sscanf(content, "MemTotal: %d kB", &total)
	fmt.Sscanf(content, "MemAvailable: %d kB", &avail)
	return
}

func roundTo2(v float64) float64 {
	return float64(int64(v*100)) / 100
}
