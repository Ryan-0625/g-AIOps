package dynamic

import (
	"context"
	"fmt"
	"log"
	"strings"
	"sync"
	"time"

	"github.com/gaiops/worker/internal/registry"
)

// ── Constants ────────────────────────────────────────────────────────────

// ToolState represents the lifecycle state of a dynamic tool.
type ToolState string

const (
	StatePending     ToolState = "pending"
	StateCompiling   ToolState = "compiling"
	StateDeployed    ToolState = "deployed"
	StateRunning     ToolState = "running"
	StateFailed      ToolState = "failed"
	StateUninstalled ToolState = "uninstalled"
)

// ── DynamicTool ──────────────────────────────────────────────────────────

// DynamicTool holds metadata for a dynamically deployed tool.
type DynamicTool struct {
	Action       string                 `json:"action"`
	Language     string                 `json:"language"`      // bash | python3 | node
	CodeHash     string                 `json:"code_hash"`     // SHA-256 of source
	RiskLevel    string                 `json:"risk_level"`    // readonly | write | dangerous
	State        ToolState              `json:"state"`
	DeployedAt   int64                  `json:"deployed_at"`   // unix timestamp
	LastUsed     int64                  `json:"last_used"`
	ExecuteCount int64                  `json:"execute_count"`
	FailCount    int64                  `json:"fail_count"`
	Version      int                    `json:"version"`       // incremented on re-deploy
}

// ── Config ───────────────────────────────────────────────────────────────

// LifecycleConfig controls dynamic tool lifecycle behaviour.
type LifecycleConfig struct {
	MaxTools            int           // max concurrent dynamic tools
	AutoCleanupInterval time.Duration // how often to check for stale tools
	PersistOnDisk       bool          // persist tool code across restarts
	TempDir             string        // root temp dir for scripts
}

// DefaultLifecycleConfig returns sensible defaults.
func DefaultLifecycleConfig() LifecycleConfig {
	return LifecycleConfig{
		MaxTools:            20,
		AutoCleanupInterval: 1 * time.Hour,
		PersistOnDisk:       false,
		TempDir:             "/tmp/gaiops-dynamic",
	}
}

// ── LifecycleManager ─────────────────────────────────────────────────────

// LifecycleManager orchestrates the full lifecycle of dynamic tools:
//  1. Receive code from Brain (via Master relay)
//  2. Compile & syntax-check via Compiler
//  3. Security-scan via registered CodeScanners
//  4. Register with the global Tool registry
//  5. Track usage metrics
//  6. Auto-cleanup stale tools
//  7. Unregister on demand
type LifecycleManager struct {
	mu       sync.RWMutex
	tools    map[string]*DynamicTool // action → metadata
	code     map[string]string       // action → source code (for re-register on reconnect)
	config   LifecycleConfig
	compiler *Compiler
	sandbox  *SandboxExecutor

	// injected dependencies
	registry    *registry.Registry
	reAdvertise func() // callback to re-announce capabilities to Master
}

// NewLifecycleManager creates a new lifecycle manager.
func NewLifecycleManager(
	cfg LifecycleConfig,
	compiler *Compiler,
	sandbox *SandboxExecutor,
	toolRegistry *registry.Registry,
	reAdvertiseFn func(),
) *LifecycleManager {
	return &LifecycleManager{
		tools:       make(map[string]*DynamicTool),
		code:        make(map[string]string),
		config:      cfg,
		compiler:    compiler,
		sandbox:     sandbox,
		registry:    toolRegistry,
		reAdvertise: reAdvertiseFn,
	}
}

// StartCleanupLoop runs background GC for stale tools.
// Run in a separate goroutine.
func (lm *LifecycleManager) StartCleanupLoop(ctx context.Context) {
	ticker := time.NewTicker(lm.config.AutoCleanupInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			reaped := lm.cleanupStale()
			if reaped > 0 {
				log.Printf("[dynamic] auto-cleanup reaped %d stale tools", reaped)
			}
		case <-ctx.Done():
			return
		}
	}
}

// Deploy compiles, security-scans, and registers a dynamic tool.
//
// Parameters:
//   - action: tool action name (e.g. "custom.healthcheck")
//   - code: script source code
//   - lang: "bash", "python3", or "node"
//   - riskLevel: "readonly", "write", or "dangerous"
//   - timeoutSec: max execution time in seconds
//
// Returns the DeployResult with status and any errors.
func (lm *LifecycleManager) Deploy(
	action string,
	code string,
	lang string,
	riskLevel string,
	timeoutSec int,
) *DeployResult {
	lm.mu.Lock()
	if len(lm.tools) >= lm.config.MaxTools {
		lm.mu.Unlock()
		return &DeployResult{
			Status: "failure",
			Error: &DeployError{
				Code:    "TOOL_LIMIT_REACHED",
				Message: fmt.Sprintf("max dynamic tools (%d) reached", lm.config.MaxTools),
			},
		}
	}
	lm.mu.Unlock()

	// 1. Compile & syntax check.
	lm.setState(action, StateCompiling)
	result := lm.compiler.Compile(code, lang)
	if !result.Valid {
		lm.setState(action, StateFailed)
		return &DeployResult{
			Status: "failure",
			Error: &DeployError{
				Code:    "TOOL_COMPILE_ERROR",
				Message: stringsJoin(result.Errors, "; "),
				Details: result,
			},
		}
	}

	// 2. If there were warnings but no errors, log them.
	if len(result.Warnings) > 0 {
		log.Printf("[dynamic] tool %s compile warnings: %v", action, result.Warnings)
	}

	// 3. Create the executor function (closure over code + language).
	codeCopy := code
	langCopy := lang
	execFn := func(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
		lm.recordUsage(action)
		return lm.sandbox.Execute(ctx, codeCopy, langCopy, params)
	}

	// 4. Register via RegisterDynamic (replaces any existing entry).
	timeout := time.Duration(timeoutSec) * time.Second
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	lm.registry.RegisterDynamic(registry.Tool{
		Action:       action,
		Timeout:      timeout,
		IsIdempotent: false,
		RiskLevel:    riskLevel,
		Execute:      execFn,
		Source:       "dynamic",
	})

	// 5. Record metadata.
	codeHash := SHA256(code)
	lm.mu.Lock()
	existing := lm.tools[action]
	version := 1
	if existing != nil {
		version = existing.Version + 1
	}
	lm.tools[action] = &DynamicTool{
		Action:     action,
		Language:   lang,
		CodeHash:   codeHash,
		RiskLevel:  riskLevel,
		State:      StateDeployed,
		DeployedAt: time.Now().Unix(),
		Version:    version,
	}
	lm.code[action] = code // keep for potential re-registration
	lm.mu.Unlock()

	// 6. Re-advertise capabilities so Master knows about this tool.
	if lm.reAdvertise != nil {
		lm.reAdvertise()
	}

	log.Printf("[dynamic] tool deployed: %s (lang=%s, risk=%s, v%d)", action, lang, riskLevel, version)
	return &DeployResult{Status: "success", Action: action, Version: version}
}

// Unregister removes a dynamic tool and unregisters it from the registry.
func (lm *LifecycleManager) Unregister(action string) bool {
	lm.mu.Lock()
	defer lm.mu.Unlock()

	if _, exists := lm.tools[action]; !exists {
		return false
	}

	lm.registry.Unregister(action)
	delete(lm.tools, action)
	delete(lm.code, action)

	if lm.reAdvertise != nil {
		lm.reAdvertise()
	}

	log.Printf("[dynamic] tool unregistered: %s", action)
	return true
}

// ReRegisterAll re-deploys all previously deployed tools (used on Worker
// reconnect when the registry is reset).
func (lm *LifecycleManager) ReRegisterAll() int {
	lm.mu.RLock()
	count := len(lm.code)
	lm.mu.RUnlock()

	if count == 0 {
		return 0
	}

	lm.mu.RLock()
	for action, code := range lm.code {
		tool := lm.tools[action]
		if tool == nil {
			continue
		}
		// Re-register without re-compiling (already verified).
		codeCopy := code
		langCopy := tool.Language
		execFn := func(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
			return lm.sandbox.Execute(ctx, codeCopy, langCopy, params)
		}
		lm.registry.RegisterDynamic(registry.Tool{
			Action:    action,
			Timeout:   30 * time.Second,
			RiskLevel: tool.RiskLevel,
			Execute:   execFn,
			Source:    "dynamic",
		})
	}
	lm.mu.RUnlock()

	if lm.reAdvertise != nil {
		lm.reAdvertise()
	}

	return count
}

// GetTool returns metadata for a deployed tool, or nil.
func (lm *LifecycleManager) GetTool(action string) *DynamicTool {
	lm.mu.RLock()
	defer lm.mu.RUnlock()
	return lm.tools[action]
}

// ListTools returns all deployed tool metadata.
func (lm *LifecycleManager) ListTools() []*DynamicTool {
	lm.mu.RLock()
	defer lm.mu.RUnlock()
	list := make([]*DynamicTool, 0, len(lm.tools))
	for _, t := range lm.tools {
		list = append(list, t)
	}
	return list
}

// ToolCount returns the number of currently deployed tools.
func (lm *LifecycleManager) ToolCount() int {
	lm.mu.RLock()
	defer lm.mu.RUnlock()
	return len(lm.tools)
}

// ── Internal ─────────────────────────────────────────────────────────────

func (lm *LifecycleManager) setState(action string, state ToolState) {
	lm.mu.Lock()
	defer lm.mu.Unlock()
	if t, ok := lm.tools[action]; ok {
		t.State = state
	}
}

func (lm *LifecycleManager) recordUsage(action string) {
	lm.mu.Lock()
	defer lm.mu.Unlock()
	if t, ok := lm.tools[action]; ok {
		t.LastUsed = time.Now().Unix()
		t.ExecuteCount++
		t.State = StateRunning
	}
}

// cleanupStale removes tools that haven't been used recently.
// Returns the number of tools cleaned up.
func (lm *LifecycleManager) cleanupStale() int {
	lm.mu.Lock()
	defer lm.mu.Unlock()

	now := time.Now().Unix()
	staleThreshold := int64(24 * time.Hour.Seconds()) // 24 hours
	var toRemove []string

	for action, t := range lm.tools {
		if now-t.LastUsed > staleThreshold && t.ExecuteCount == 0 {
			toRemove = append(toRemove, action)
		}
	}

	for _, action := range toRemove {
		lm.registry.Unregister(action)
		delete(lm.tools, action)
		delete(lm.code, action)
	}

	return len(toRemove)
}

// ── Result types ─────────────────────────────────────────────────────────

// DeployResult carries the outcome of a Deploy call.
type DeployResult struct {
	Status  string       `json:"status"`  // "success" | "failure"
	Action  string       `json:"action,omitempty"`
	Version int          `json:"version,omitempty"`
	Error   *DeployError `json:"error,omitempty"`
}

// DeployError carries structured error info for deploy failures.
type DeployError struct {
	Code    string         `json:"code"`
	Message string         `json:"message"`
	Details *CompileResult `json:"details,omitempty"`
}

func (e *DeployError) Error() string {
	return fmt.Sprintf("[%s] %s", e.Code, e.Message)
}

// ── Helper ───────────────────────────────────────────────────────────────

func stringsJoin(elems []string, sep string) string {
	switch len(elems) {
	case 0:
		return ""
	case 1:
		return elems[0]
	}
	var n int
	for _, e := range elems {
		n += len(e)
	}
	var b strings.Builder
	b.Grow(n + len(sep)*(len(elems)-1))
	for i, e := range elems {
		if i > 0 {
			b.WriteString(sep)
		}
		b.WriteString(e)
	}
	return b.String()
}
