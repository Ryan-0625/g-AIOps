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
