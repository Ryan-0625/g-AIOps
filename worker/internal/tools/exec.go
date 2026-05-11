package tools

import (
	"context"
	"fmt"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/gaiops/worker/internal/executor"
	"github.com/gaiops/worker/internal/registry"
)

func init() {
	registry.Global.Register(registry.Tool{
		Action:       "exec.run",
		Timeout:      60 * time.Second,
		IsIdempotent: false,
		RiskLevel:    "dangerous",
		Execute:      executeExecRun,
	})
}

// AllowedCommands is the set of permitted command paths, set from config.
var AllowedCommands struct {
	mu   sync.RWMutex
	list []string
}

// SetAllowedCommands sets the command whitelist. Called from main.go after config load.
func SetAllowedCommands(cmds []string) {
	AllowedCommands.mu.Lock()
	defer AllowedCommands.mu.Unlock()
	AllowedCommands.list = cmds
}

// GetAllowedCommands returns a copy of the current whitelist.
func GetAllowedCommands() []string {
	AllowedCommands.mu.RLock()
	defer AllowedCommands.mu.RUnlock()
	out := make([]string, len(AllowedCommands.list))
	copy(out, AllowedCommands.list)
	return out
}

func isCommandAllowed(cmdPath string) bool {
	AllowedCommands.mu.RLock()
	defer AllowedCommands.mu.RUnlock()
	if len(AllowedCommands.list) == 0 {
		return false
	}
	abs, err := filepath.Abs(cmdPath)
	if err != nil {
		return false
	}
	for _, allowed := range AllowedCommands.list {
		allowedAbs, err := filepath.Abs(allowed)
		if err != nil {
			continue
		}
		if abs == allowedAbs {
			return true
		}
	}
	return false
}

// Shell metacharacters that are rejected in args.
var shellMetachars = []string{";", "|", "&", "`", "$", "(", ")", "{", "}", "<", ">"}

func containsShellMeta(s string) bool {
	for _, ch := range shellMetachars {
		if strings.Contains(s, ch) {
			return true
		}
	}
	return false
}

func executeExecRun(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	command, _ := params["command"].(string)
	if command == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "command is required")
	}

	// Whitelist check.
	if !isCommandAllowed(command) {
		return nil, executor.NewErr("COMMAND_NOT_ALLOWED",
			fmt.Sprintf("command %q is not in the allowed list", command))
	}

	// Args.
	argsRaw, _ := params["args"].([]interface{})
	args := make([]string, 0, len(argsRaw))
	for _, a := range argsRaw {
		s, ok := a.(string)
		if !ok {
			continue
		}
		// Reject shell metacharacters in each arg.
		if containsShellMeta(s) {
			return nil, executor.NewErr("INVALID_ARGS",
				fmt.Sprintf("arg %q contains shell metacharacters", s))
		}
		args = append(args, s)
	}

	// timeout_seconds: override default timeout from params.
	timeout := 60 * time.Second
	if t, ok := params["timeout_seconds"].(int); ok && t > 0 && t <= 300 {
		timeout = time.Duration(t) * time.Second
	}

	execCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	// Use exec.CommandContext — never through a shell.
	cmd := exec.CommandContext(execCtx, command, args...)

	out, err := cmd.CombinedOutput()
	if err != nil {
		if execCtx.Err() != nil {
			return nil, executor.NewErr("EXECUTION_TIMEOUT",
				fmt.Sprintf("command %q timed out after %v", command, timeout))
		}
		return map[string]interface{}{
			"command":  command,
			"args":     args,
			"exit_code": 1,
			"stdout":    string(out),
			"error":     err.Error(),
		}, nil
	}

	return map[string]interface{}{
		"command":   command,
		"args":      args,
		"exit_code": 0,
		"stdout":    string(out),
	}, nil
}
