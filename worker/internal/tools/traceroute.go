package tools

import (
	"context"
	"fmt"
	"os/exec"
	"strings"
	"time"

	"github.com/gaiops/worker/internal/registry"
)

func init() {
	registry.Global.Register(registry.Tool{
		Action:       "traceroute",
		Timeout:      30 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeTraceroute,
	})
}

func executeTraceroute(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	target, _ := params["target"].(string)
	if target == "" {
		return nil, fmt.Errorf("target is required")
	}

	maxHops := 15
	if m, ok := params["max_hops"].(int); ok && m > 0 && m <= 30 {
		maxHops = m
	}

	cmd := exec.CommandContext(ctx, "traceroute", "-n", "-m", fmt.Sprintf("%d", maxHops), target)
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("traceroute failed: %w", err)
	}

	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	var hops []map[string]interface{}
	for _, line := range lines {
		fields := strings.Fields(line)
		if len(fields) >= 2 {
			hop := map[string]interface{}{
				"hop": fields[0],
				"ip":  strings.TrimRight(fields[1], ":"),
			}
			// Parse RTT if available
			for _, f := range fields[2:] {
				if strings.HasSuffix(f, "ms") {
					rtt := strings.TrimSuffix(f, "ms")
					hop["rtt_ms"] = rtt
					break
				}
			}
			hops = append(hops, hop)
		}
	}

	return map[string]interface{}{
		"target":    target,
		"hops":      hops,
		"hop_count": len(hops),
	}, nil
}
