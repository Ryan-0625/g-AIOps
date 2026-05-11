package tools

import (
	"context"
	"fmt"
	"time"

	"github.com/gaiops/worker/internal/executor"
	"github.com/gaiops/worker/internal/registry"
)

func init() {
	// disk.usage — query disk usage for a mount point. Readonly, idempotent.
	registry.Global.Register(registry.Tool{
		Action:       "disk.usage",
		Timeout:      5 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeDiskUsage,
	})
}

func executeDiskUsage(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	path, _ := params["path"].(string)
	if path == "" {
		path = "/"
	}

	total, used, avail, files, ffree, err := getDiskStats(path)
	if err != nil {
		return nil, executor.NewErr("DISK_READ_ERROR", fmt.Sprintf("disk stats for %q failed: %v", path, err))
	}

	var usagePct float64
	if total > 0 {
		usagePct = float64(used) / float64(total) * 100
	}

	return map[string]interface{}{
		"path":         path,
		"total_bytes":  total,
		"used_bytes":   used,
		"free_bytes":   total - used,
		"avail_bytes":  avail,
		"usage_pct":    fmt.Sprintf("%.1f", usagePct),
		"inodes_total": files,
		"inodes_free":  ffree,
	}, nil
}
