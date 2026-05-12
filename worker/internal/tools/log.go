package tools

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"time"

	"github.com/gaiops/worker/internal/executor"
	"github.com/gaiops/worker/internal/registry"
	"github.com/gaiops/worker/internal/safety"
)

func init() {
	registry.Global.Register(registry.Tool{
		Action:       "log.tail",
		Timeout:      15 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeLogTail,
	})
}

func executeLogTail(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	path, _ := params["path"].(string)
	if path == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "path is required")
	}

	lines := 50
	if n, ok := params["lines"].(int); ok && n > 0 && n <= 5000 {
		lines = n
	}

	file, err := os.Open(path)
	if err != nil {
		return nil, executor.NewErr("LOG_READ_ERROR",
			fmt.Sprintf("cannot open %q: %v", path, err))
	}
	defer file.Close()

	// Scan all lines, keep only the last N.
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 1024*64), 1024*64) // 64KB line buffer

	var ring []string
	for scanner.Scan() {
		select {
		case <-ctx.Done():
			return nil, executor.NewErr("EXECUTION_TIMEOUT",
				"log.tail cancelled: context done")
		default:
		}
		ring = append(ring, safety.FilterSensitive(scanner.Text()))
		if len(ring) > lines {
			ring = ring[1:]
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, executor.NewErr("LOG_READ_ERROR",
			fmt.Sprintf("error reading %q: %v", path, err))
	}

	// Stat for file metadata.
	info, _ := file.Stat()
	var sizeBytes int64
	if info != nil {
		sizeBytes = info.Size()
	}

	return map[string]interface{}{
		"path":       path,
		"lines":      ring,
		"line_count": len(ring),
		"file_size":  sizeBytes,
	}, nil
}
