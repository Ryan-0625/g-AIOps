package tools

import (
	"context"
	"fmt"
	"os/exec"
	"strings"
	"time"

	"github.com/gaiops/worker/internal/executor"
	"github.com/gaiops/worker/internal/registry"
)

func init() {
	registry.Global.Register(registry.Tool{
		Action:       "service.status",
		Timeout:      5 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeServiceStatus,
	})
	registry.Global.Register(registry.Tool{
		Action:       "service.restart",
		Timeout:      30 * time.Second,
		IsIdempotent: false,
		RiskLevel:    "high",
		Execute:      executeServiceRestart,
	})
	registry.Global.Register(registry.Tool{
		Action:       "service.stop",
		Timeout:      30 * time.Second,
		IsIdempotent: false,
		RiskLevel:    "high",
		Execute:      executeServiceStop,
	})
	registry.Global.Register(registry.Tool{
		Action:       "service.start",
		Timeout:      30 * time.Second,
		IsIdempotent: false,
		RiskLevel:    "high",
		Execute:      executeServiceStart,
	})
}

func executeServiceStatus(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	name, _ := params["name"].(string)
	if name == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "service name is required")
	}

	// Use systemctl is-active as a portable single-command check.
	out, err := exec.CommandContext(ctx, "systemctl", "is-active", name).Output()
	if err != nil {
		// If the service doesn't exist, systemctl exits non-zero.
		return nil, executor.NewErr("SERVICE_NOT_FOUND",
			fmt.Sprintf("service %q not found or inactive: %v", name, err))
	}

	status := strings.TrimSpace(string(out))
	running := status == "active"

	return map[string]interface{}{
		"name":    name,
		"status":  status,
		"running": running,
	}, nil
}

func executeServiceRestart(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	name, _ := params["name"].(string)
	if name == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "service name is required")
	}

	cmd := exec.CommandContext(ctx, "systemctl", "restart", name)
	if err := cmd.Run(); err != nil {
		return nil, executor.NewErr("SERVICE_NOT_FOUND",
			fmt.Sprintf("failed to restart service %q: %v", name, err))
	}

	return map[string]interface{}{
		"name":    name,
		"status":  "restarted",
		"running": true,
	}, nil
}

func executeServiceStop(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	name, _ := params["name"].(string)
	if name == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "service name is required")
	}

	cmd := exec.CommandContext(ctx, "systemctl", "stop", name)
	if err := cmd.Run(); err != nil {
		return nil, executor.NewErr("SERVICE_NOT_FOUND",
			fmt.Sprintf("failed to stop service %q: %v", name, err))
	}

	return map[string]interface{}{
		"name":    name,
		"status":  "inactive",
		"running": false,
	}, nil
}

func executeServiceStart(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	name, _ := params["name"].(string)
	if name == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "service name is required")
	}

	cmd := exec.CommandContext(ctx, "systemctl", "start", name)
	if err := cmd.Run(); err != nil {
		return nil, executor.NewErr("SERVICE_NOT_FOUND",
			fmt.Sprintf("failed to start service %q: %v", name, err))
	}

	return map[string]interface{}{
		"name":    name,
		"status":  "active",
		"running": true,
	}, nil
}
