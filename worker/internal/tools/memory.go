package tools

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/gaiops/worker/internal/registry"
)

func init() {
	registry.Global.Register(registry.Tool{
		Action:       "memory.usage",
		Timeout:      5 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeMemoryUsage,
	})
}

func executeMemoryUsage(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	result := map[string]interface{}{}

	// Memory from /proc/meminfo.
	memTotal, memAvail, memFree, buffers, cached, swapTotal, swapFree, err := readDetailedMemInfo()
	if err == nil {
		totalGB := float64(memTotal) / (1024 * 1024)
		usedGB := float64(memTotal-memAvail) / (1024 * 1024)
		freeGB := float64(memFree) / (1024 * 1024)
		buffersMB := float64(buffers) / 1024
		cachedMB := float64(cached) / 1024

		result["total_gb"] = roundTo2(totalGB)
		result["used_gb"] = roundTo2(usedGB)
		result["free_gb"] = roundTo2(freeGB)
		result["available_gb"] = roundTo2(float64(memAvail) / (1024 * 1024))
		result["usage_pct"] = roundTo2(float64(memTotal-memAvail) / float64(memTotal) * 100)
		result["buffers_mb"] = roundTo2(buffersMB)
		result["cached_mb"] = roundTo2(cachedMB)

		// Swap.
		if swapTotal > 0 {
			swapUsedGB := float64(swapTotal-swapFree) / (1024 * 1024)
			swapTotalGB := float64(swapTotal) / (1024 * 1024)
			result["swap_total_gb"] = roundTo2(swapTotalGB)
			result["swap_used_gb"] = roundTo2(swapUsedGB)
			result["swap_usage_pct"] = roundTo2(float64(swapTotal-swapFree) / float64(swapTotal) * 100)
		}
	}

	return result, nil
}

func readDetailedMemInfo() (total, avail, free, buffers, cached, swapTotal, swapFree uint64, err error) {
	data, err := os.ReadFile("/proc/meminfo")
	if err != nil {
		return 0, 0, 0, 0, 0, 0, 0, err
	}
	for _, line := range strings.Split(string(data), "\n") {
		switch {
		case strings.HasPrefix(line, "MemTotal:"):
			fmt.Sscanf(line, "MemTotal: %d kB", &total)
		case strings.HasPrefix(line, "MemFree:"):
			fmt.Sscanf(line, "MemFree: %d kB", &free)
		case strings.HasPrefix(line, "MemAvailable:"):
			fmt.Sscanf(line, "MemAvailable: %d kB", &avail)
		case strings.HasPrefix(line, "Buffers:"):
			fmt.Sscanf(line, "Buffers: %d kB", &buffers)
		case strings.HasPrefix(line, "Cached:"):
			fmt.Sscanf(line, "Cached: %d kB", &cached)
		case strings.HasPrefix(line, "SwapTotal:"):
			fmt.Sscanf(line, "SwapTotal: %d kB", &swapTotal)
		case strings.HasPrefix(line, "SwapFree:"):
			fmt.Sscanf(line, "SwapFree: %d kB", &swapFree)
		}
	}
	return total, avail, free, buffers, cached, swapTotal, swapFree, nil
}
