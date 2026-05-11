package tools

import (
	"context"
	"fmt"
	"net"
	"time"

	"github.com/gaiops/worker/internal/executor"
	"github.com/gaiops/worker/internal/registry"
)


func init() {
	registry.Global.Register(registry.Tool{
		Action:       "ping.icmp",
		Timeout:      10 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executePing,
	})
}

func executePing(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	target, _ := params["target"].(string)
	if target == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "target is required")
	}
	count := 3
	if c, ok := params["count"].(int); ok && c > 0 && c <= 10 {
		count = c
	}

	loss, min, avg, max, err := probeICMPWithContext(ctx, target, count)
	if err != nil {
		return nil, executor.NewErr("PING_FAILED", fmt.Sprintf("ping %s failed: %v", target, err))
	}

	return map[string]interface{}{
		"target":      target,
		"reachable":   loss < 100,
		"packet_loss": loss,
		"min_rtt_ms":  min,
		"avg_rtt_ms":  avg,
		"max_rtt_ms":  max,
	}, nil
}

func probeICMPWithContext(ctx context.Context, target string, count int) (loss float64, min, avg, max float64, err error) {
	// Use TCP dial as a portable ping substitute.
	// (ICMP requires raw sockets which need privileges.)
	start := time.Now()
	var dialer net.Dialer
	conn, err := dialer.DialContext(ctx, "tcp", net.JoinHostPort(target, "80"))
	if err != nil {
		return 100, 0, 0, 0, err
	}
	conn.Close()
	rtt := time.Since(start).Seconds() * 1000
	return 0, rtt, rtt, rtt, nil
}
