package tools

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/gaiops/worker/internal/executor"
	"github.com/gaiops/worker/internal/registry"
	"github.com/gaiops/worker/internal/safety"
)

// DynamicManager manages dynamically created tools at runtime.
type DynamicManager struct {
	mu          sync.RWMutex
	dynamic     map[string]bool // set of dynamically registered tool names
	dataDir     string
	reAdvertise func()
}

// NewDynamicManager creates a DynamicManager.
// dataDir is the directory for storing dynamic tool scripts.
// reAdvertise is called after tool.create or tool.delete to re-announce capabilities.
func NewDynamicManager(dataDir string, reAdvertise func()) *DynamicManager {
	return &DynamicManager{
		dynamic:     make(map[string]bool),
		dataDir:     dataDir,
		reAdvertise: reAdvertise,
	}
}

// IsDynamic returns true if the tool was registered dynamically.
func (dm *DynamicManager) IsDynamic(name string) bool {
	dm.mu.RLock()
	defer dm.mu.RUnlock()
	return dm.dynamic[name]
}

func init() {
	registry.Global.Register(registry.Tool{
		Action:       "tool.create",
		Timeout:      30 * time.Second,
		IsIdempotent: false,
		RiskLevel:    "dangerous",
		Execute:      executeToolCreate,
	})
	registry.Global.Register(registry.Tool{
		Action:       "tool.delete",
		Timeout:      10 * time.Second,
		IsIdempotent: false,
		RiskLevel:    "dangerous",
		Execute:      executeToolDelete,
	})
}

// The global DynamicManager instance is set by main.go via SetDynamicManager.
// tool.create and tool.delete use this to coordinate registration and re-advertise.
var globalDM *DynamicManager
var dmMu sync.Mutex

// SetDynamicManager sets the global DynamicManager instance. Must be called
// from main.go before any tool.create or tool.delete requests arrive.
func SetDynamicManager(dm *DynamicManager) {
	dmMu.Lock()
	defer dmMu.Unlock()
	globalDM = dm
}

func getDynamicManager() (*DynamicManager, error) {
	dmMu.Lock()
	defer dmMu.Unlock()
	if globalDM == nil {
		return nil, executor.NewErr("DYNAMIC_MANAGER_NOT_READY", "dynamic tool manager not initialised")
	}
	return globalDM, nil
}

// ── tool.create ─────────────────────────────────────────────────────────

type toolCreateParams struct {
	Name         string `json:"name"`
	Description  string `json:"description"`
	Script       string `json:"script"`
	Interpreter  string `json:"interpreter"`
	ParamsSchema string `json:"params_schema"`
	Timeout      int    `json:"timeout"`
	RiskLevel    string `json:"risk_level"`
}

func executeToolCreate(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	dm, err := getDynamicManager()
	if err != nil {
		return nil, err
	}

	var p toolCreateParams
	if err := mapToStruct(params, &p); err != nil {
		return nil, executor.NewErr("INVALID_PARAMS", fmt.Sprintf("invalid params: %v", err))
	}

	// Validate.
	if p.Name == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "name is required")
	}
	if p.Script == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "script is required")
	}
	switch p.Interpreter {
	case "bash", "python3", "node":
		// Valid.
	case "":
		p.Interpreter = "bash"
	default:
		return nil, executor.NewErr("INVALID_PARAMS", fmt.Sprintf("unsupported interpreter: %s (use bash, python3, or node)", p.Interpreter))
	}
	if p.Timeout <= 0 || p.Timeout > 300 {
		p.Timeout = 30
	}
	if p.RiskLevel == "" {
		p.RiskLevel = "dangerous"
	}
	switch p.RiskLevel {
	case "readonly", "write", "dangerous":
		// Valid.
	default:
		return nil, executor.NewErr("INVALID_PARAMS", fmt.Sprintf("invalid risk_level: %s", p.RiskLevel))
	}

	// Create tool directory.
	toolDir := filepath.Join(dm.dataDir, "tools", p.Name)
	if err := os.MkdirAll(toolDir, 0755); err != nil {
		return nil, executor.NewErr("CREATE_FAILED", fmt.Sprintf("cannot create tool directory: %v", err))
	}

	// Write script.
	scriptPath := filepath.Join(toolDir, "script")
	if err := os.WriteFile(scriptPath, []byte(p.Script), 0755); err != nil {
		return nil, executor.NewErr("CREATE_FAILED", fmt.Sprintf("cannot write script: %v", err))
	}

	// Build dynamic tool function.
	toolTimeout := time.Duration(p.Timeout) * time.Second
	execFn := buildDynamicToolFn(p.Name, scriptPath, p.Interpreter, toolTimeout)

	tool := registry.Tool{
		Action:       p.Name,
		Timeout:      toolTimeout,
		IsIdempotent: false,
		RiskLevel:    p.RiskLevel,
		Execute:      execFn,
	}

	// Register in global registry.
	registry.Global.RegisterDynamic(tool)

	// Track as dynamic.
	dm.mu.Lock()
	dm.dynamic[p.Name] = true
	dm.mu.Unlock()

	// Re-advertise capabilities to Master.
	if dm.reAdvertise != nil {
		dm.reAdvertise()
	}

	result := map[string]interface{}{
		"status":      "created",
		"name":        p.Name,
		"interpreter": p.Interpreter,
		"risk_level":  p.RiskLevel,
		"timeout":     p.Timeout,
	}
	if p.Description != "" {
		result["description"] = p.Description
	}
	return result, nil
}

// buildDynamicToolFn creates a ToolFn that executes a script.
//
// Contract:
//   - Tool params are passed as JSON via the TOOL_PARAMS environment variable
//   - The script writes a JSON result to stdout on success
//   - Exit code 0 = success, non-zero = failure (stderr is used as error message)
func buildDynamicToolFn(name, scriptPath, interpreter string, timeout time.Duration) registry.ToolFn {
	return func(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
		// Serialize params to JSON for the script.
		paramsJSON, err := json.Marshal(params)
		if err != nil {
			return nil, executor.NewErr("PARAMS_ERROR", fmt.Sprintf("cannot marshal params: %v", err))
		}

		execCtx, cancel := context.WithTimeout(ctx, timeout)
		defer cancel()

		cmd := exec.CommandContext(execCtx, interpreter, scriptPath)

		// Filter out sensitive env vars before passing to external script.
		var cleanEnv []string
		for _, env := range os.Environ() {
			eq := strings.IndexByte(env, '=')
			if eq == -1 {
				continue
			}
			key := env[:eq]
			if !safety.IsSecretEnvVar(key) {
				cleanEnv = append(cleanEnv, env)
			}
		}
		cmd.Env = append(cleanEnv,
			fmt.Sprintf("TOOL_PARAMS=%s", string(paramsJSON)),
			fmt.Sprintf("TOOL_NAME=%s", name),
		)

		var stdout, stderr bytes.Buffer
		cmd.Stdout = &stdout
		cmd.Stderr = &stderr

		if err := cmd.Run(); err != nil {
			errMsg := strings.TrimSpace(stderr.String())
			if errMsg == "" {
				errMsg = fmt.Sprintf("execution failed: %v", err)
			}
			return nil, executor.NewErr("DYNAMIC_TOOL_FAILED", truncateString(errMsg, 1024))
		}

		// Parse JSON output.
		output := strings.TrimSpace(stdout.String())
		if output == "" {
			return map[string]interface{}{"status": "completed"}, nil
		}

		var result map[string]interface{}
		if err := json.Unmarshal([]byte(output), &result); err != nil {
			return nil, executor.NewErr("INVALID_OUTPUT", fmt.Sprintf("script output is not valid JSON: %v", err))
		}
		return result, nil
	}
}

// ── tool.delete ─────────────────────────────────────────────────────────

type toolDeleteParams struct {
	Name string `json:"name"`
}

func executeToolDelete(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	dm, err := getDynamicManager()
	if err != nil {
		return nil, err
	}

	name, _ := params["name"].(string)
	if name == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "name is required")
	}

	// Check it's a dynamic tool.
	if !dm.IsDynamic(name) {
		return nil, executor.NewErr("NOT_FOUND", fmt.Sprintf("dynamic tool '%s' not found", name))
	}

	// Unregister from global registry.
	registry.Global.Unregister(name)

	// Remove from dynamic tracking.
	dm.mu.Lock()
	delete(dm.dynamic, name)
	dm.mu.Unlock()

	// Optionally remove script files.
	toolDir := filepath.Join(dm.dataDir, "tools", name)
	os.RemoveAll(toolDir) // Best-effort; ignore error.

	// Re-advertise capabilities.
	if dm.reAdvertise != nil {
		dm.reAdvertise()
	}

	return map[string]interface{}{
		"status": "deleted",
		"name":   name,
	}, nil
}

// ── Helpers ─────────────────────────────────────────────────────────────

// mapToStruct unmarshals a map into a struct via JSON round-trip.
func mapToStruct(in map[string]interface{}, out interface{}) error {
	data, err := json.Marshal(in)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, out)
}
