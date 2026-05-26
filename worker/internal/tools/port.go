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
		Action:       "port.check",
		Timeout:      10 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executePortCheck,
	})
	registry.Global.Register(registry.Tool{
		Action:       "port.scan",
		Timeout:      30 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executePortScan,
	})
}

func executePortCheck(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	host, _ := params["host"].(string)
	if host == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "host is required")
	}
	port := 80
	if p, ok := params["port"].(int); ok && p > 0 && p < 65536 {
		port = p
	}
	timeout := 5
	if t, ok := params["timeout_seconds"].(int); ok && t > 0 && t <= 30 {
		timeout = t
	}

	addr := net.JoinHostPort(host, fmt.Sprintf("%d", port))
	var dialer net.Dialer
	dialer.Timeout = time.Duration(timeout) * time.Second

	start := time.Now()
	conn, err := dialer.DialContext(ctx, "tcp", addr)
	elapsed := time.Since(start).Milliseconds()

	result := map[string]interface{}{
		"host":       host,
		"port":       port,
		"reachable":  false,
		"latency_ms": elapsed,
	}

	if err == nil {
		conn.Close()
		result["reachable"] = true
		return result, nil
	}

	if ctx.Err() != nil {
		return nil, executor.NewErr("CHECK_TIMEOUT",
			fmt.Sprintf("port check to %s timed out after %ds", addr, timeout))
	}

	return result, nil
}

func executePortScan(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	host, _ := params["host"].(string)
	if host == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "host is required")
	}

	portsRaw, ok := params["ports"].([]interface{})
	if !ok || len(portsRaw) == 0 {
		return nil, executor.NewErr("INVALID_PARAMS", "ports list is required (e.g. [22,80,443])")
	}

	timeout := 3
	if t, ok := params["timeout_seconds"].(int); ok && t > 0 && t <= 10 {
		timeout = t
	}

	var openPorts []int
	var closedPorts []int

	for _, p := range portsRaw {
		port, ok := p.(int)
		if !ok || port < 1 || port > 65535 {
			continue
		}

		select {
		case <-ctx.Done():
			return map[string]interface{}{
				"host":         host,
				"open_ports":   openPorts,
				"closed_ports": closedPorts,
				"total":        len(portsRaw),
				"scanned":      len(openPorts) + len(closedPorts),
				"truncated":    true,
			}, nil
		default:
		}

		addr := net.JoinHostPort(host, fmt.Sprintf("%d", port))
		var dialer net.Dialer
		dialer.Timeout = time.Duration(timeout) * time.Second

		conn, err := dialer.DialContext(ctx, "tcp", addr)
		if err == nil {
			conn.Close()
			openPorts = append(openPorts, port)
		} else {
			closedPorts = append(closedPorts, port)
		}
	}

	return map[string]interface{}{
		"host":         host,
		"open_ports":   openPorts,
		"closed_ports": closedPorts,
		"total":        len(portsRaw),
		"scanned":      len(openPorts) + len(closedPorts),
	}, nil
}
