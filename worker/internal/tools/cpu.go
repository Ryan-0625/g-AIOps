package tools

import (
	"context"
	"fmt"
	"os"
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/gaiops/worker/internal/registry"
)

func init() {
	registry.Global.Register(registry.Tool{
		Action:       "cpu.usage",
		Timeout:      5 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeCPUUsage,
	})
}

func executeCPUUsage(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	result := map[string]interface{}{
		"cpu_cores": runtime.NumCPU(),
	}

	// Load average from /proc/loadavg (Linux).
	if load, err := readLoadAvg(); err == nil {
		result["load_1min"], result["load_5min"], result["load_15min"] = load[0], load[1], load[2]
	}

	// CPU usage percentages from /proc/stat.
	if usage, err := readCPUUsage(ctx, params); err == nil {
		result["user_pct"] = usage["user"]
		result["system_pct"] = usage["system"]
		result["idle_pct"] = usage["idle"]
		result["iowait_pct"] = usage["iowait"]
	}

	return result, nil
}

func readLoadAvg() ([]float64, error) {
	data, err := os.ReadFile("/proc/loadavg")
	if err != nil {
		return nil, err
	}
	parts := strings.Fields(string(data))
	if len(parts) < 3 {
		return nil, fmt.Errorf("unexpected /proc/loadavg format")
	}
	loads := make([]float64, 3)
	for i := 0; i < 3; i++ {
		loads[i], _ = strconv.ParseFloat(parts[i], 64)
	}
	return loads, nil
}

func readCPUUsage(ctx context.Context, _ map[string]interface{}) (map[string]float64, error) {
	// Sample 1: read /proc/stat
	stat1, err := readProcStat()
	if err != nil {
		return nil, err
	}

	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	case <-time.After(500 * time.Millisecond):
	}

	// Sample 2: read /proc/stat again
	stat2, err := readProcStat()
	if err != nil {
		return nil, err
	}

	total1 := stat1["user"] + stat1["nice"] + stat1["system"] + stat1["idle"] + stat1["iowait"]
	total2 := stat2["user"] + stat2["nice"] + stat2["system"] + stat2["idle"] + stat2["iowait"]
	deltaTotal := total2 - total1
	if deltaTotal == 0 {
		return map[string]float64{"user": 0, "system": 0, "idle": 100, "iowait": 0}, nil
	}

	return map[string]float64{
		"user":   roundTo2((stat2["user"] - stat1["user"]) / deltaTotal * 100),
		"system": roundTo2((stat2["system"] - stat1["system"]) / deltaTotal * 100),
		"idle":   roundTo2((stat2["idle"] - stat1["idle"]) / deltaTotal * 100),
		"iowait": roundTo2((stat2["iowait"] - stat1["iowait"]) / deltaTotal * 100),
	}, nil
}

func readProcStat() (map[string]float64, error) {
	data, err := os.ReadFile("/proc/stat")
	if err != nil {
		return nil, err
	}
	for _, line := range strings.Split(string(data), "\n") {
		if strings.HasPrefix(line, "cpu ") {
			fields := strings.Fields(line)
			if len(fields) < 5 {
				continue
			}
			return map[string]float64{
				"user":   parseFloat(fields[1]),
				"nice":   parseFloat(fields[2]),
				"system": parseFloat(fields[3]),
				"idle":   parseFloat(fields[4]),
				"iowait": parseFloat(fields[5]),
			}, nil
		}
	}
	return nil, fmt.Errorf("cpu line not found in /proc/stat")
}

func parseFloat(s string) float64 {
	v, _ := strconv.ParseFloat(s, 64)
	return v
}
