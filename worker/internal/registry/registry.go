// Package registry maintains the mapping from action names to tool
// implementations. Tools register themselves via init() or Register().
package registry

import (
	"context"
	"sync"
	"time"
)

// ToolFn executes a tool and returns data + an optional error.
// The error should be a descriptive message; the executor wraps it into
// a structured ToolError with an error code.
type ToolFn func(ctx context.Context, params map[string]interface{}) (data map[string]interface{}, err error)

// Tool metadata. Each tool declares its characteristics at registration time.
type Tool struct {
	Action       string        `json:"action"`
	Timeout      time.Duration `json:"timeout"`
	IsIdempotent bool          `json:"is_idempotent"`
	RiskLevel    string        `json:"risk_level"` // readonly | write | dangerous
	Execute      ToolFn        `json:"-"`
}

// Registry maps action names to Tool metadata.
type Registry struct {
	mu    sync.RWMutex
	tools map[string]*Tool
}

// Global is the default registry used by tool init() functions.
var Global = New()

func New() *Registry {
	return &Registry{tools: make(map[string]*Tool)}
}

func (r *Registry) Register(t Tool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, exists := r.tools[t.Action]; exists {
		panic("duplicate tool registration: " + t.Action)
	}
	if t.Timeout <= 0 {
		t.Timeout = 30 * time.Second
	}
	if t.RiskLevel == "" {
		t.RiskLevel = "readonly"
	}
	r.tools[t.Action] = &t
}

// RegisterDynamic registers or updates a tool at runtime. Unlike Register,
// it does not panic on duplicates — it replaces the existing entry.
// Safe for concurrent use.
func (r *Registry) RegisterDynamic(t Tool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if t.Timeout <= 0 {
		t.Timeout = 30 * time.Second
	}
	if t.RiskLevel == "" {
		t.RiskLevel = "readonly"
	}
	r.tools[t.Action] = &t
}

// Unregister removes a tool from the registry. Used for dynamic tool cleanup.
func (r *Registry) Unregister(action string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	delete(r.tools, action)
}

func (r *Registry) Lookup(action string) (*Tool, bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	t, ok := r.tools[action]
	return t, ok
}

func (r *Registry) List() []Tool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	list := make([]Tool, 0, len(r.tools))
	for _, t := range r.tools {
		list = append(list, *t)
	}
	return list
}

func (r *Registry) Actions() []string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	actions := make([]string, 0, len(r.tools))
	for name := range r.tools {
		actions = append(actions, name)
	}
	return actions
}

func (r *Registry) RiskLevels() map[string]string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	levels := make(map[string]string, len(r.tools))
	for name, t := range r.tools {
		levels[name] = t.RiskLevel
	}
	return levels
}
