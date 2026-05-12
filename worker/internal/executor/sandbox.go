// Package executor runs tool functions with concurrency control, timeout, and
// panic recovery. Every tool invocation goes through this sandbox.
package executor

import (
	"context"
	"fmt"
	"os"
	"sync"
	"time"

	"github.com/gaiops/worker/internal/registry"
	"github.com/gaiops/worker/internal/safety"
)

// ToolResult is the unified return type for every tool execution.
type ToolResult struct {
	Success     bool
	Data        map[string]interface{}
	Error       *ToolError
	Truncated   bool
	TruncatedAt int64
}

// ToolError carries structured error info back to the envelope.
type ToolError struct {
	Code    string
	Message string
	Raw     string
}

// ToolErr is a convenience wrapper tools can return when they need a specific
// error code (e.g. PING_FAILED, SERVICE_NOT_FOUND).
type ToolErr struct {
	Code    string
	Message string
}

func (e *ToolErr) Error() string { return e.Message }

// NewErr builds a ToolErr with the given code and message.
func NewErr(code, message string) *ToolErr {
	return &ToolErr{Code: code, Message: message}
}

// Executor runs tools through a concurrency-limited sandbox.
//
// Each Run call acquires a slot from the semaphore, enforces the tool's
// declared timeout, and recovers panics so a single misbehaving tool cannot
// crash the Worker process.
type Executor struct {
	reg        *registry.Registry
	semaphore  chan struct{}
	wg         sync.WaitGroup
}

func New(reg *registry.Registry, maxConcurrent int) *Executor {
	if maxConcurrent <= 0 {
		maxConcurrent = 5
	}
	return &Executor{
		reg:       reg,
		semaphore: make(chan struct{}, maxConcurrent),
	}
}

// Run executes a tool with full sandboxing.
//
//  1. Looks up the tool in the registry.
//  2. Acquires a concurrency slot (blocks until one is free or ctx done).
//  3. Enforces timeout via context.WithTimeout.
//  4. Recovers panics.
func (e *Executor) Run(ctx context.Context, action string, params map[string]interface{}) (result ToolResult) {
	tool, ok := e.reg.Lookup(action)
	if !ok || tool == nil {
		return ToolResult{
			Success: false,
			Error: &ToolError{
				Code:    "UNKNOWN_ACTION",
				Message: fmt.Sprintf("no tool registered for action: %s", action),
			},
		}
	}

	// Concurrency slot: either acquire or honour ctx cancellation.
	select {
	case e.semaphore <- struct{}{}:
		defer func() { <-e.semaphore }()
	case <-ctx.Done():
		return ToolResult{
			Success: false,
			Error:   &ToolError{Code: "EXECUTION_TIMEOUT", Message: "cancelled while waiting for concurrency slot"},
		}
	}

	// Timeout.
	timeout := tool.Timeout
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	toolCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	// Panic guard.
	defer func() {
		if r := recover(); r != nil {
			raw := fmt.Sprintf("%v", r)
			truncatedRaw, _, _ := safety.TruncateErrorRaw(raw)
			result = ToolResult{
				Success: false,
				Error: &ToolError{
					Code:    "TOOL_PANIC",
					Message: fmt.Sprintf("tool %s panicked", action),
					Raw:     truncatedRaw,
				},
			}
			fmt.Fprintf(os.Stderr, "[PANIC] tool=%s panic=%v\n", action, r)
		}
	}()

	e.wg.Add(1)
	defer e.wg.Done()

	type toolOutput struct {
		data map[string]interface{}
		err  error
	}

	done := make(chan toolOutput, 1)
	go func() {
		var out toolOutput
		defer func() {
			if r := recover(); r != nil {
				out = toolOutput{nil, &ToolErr{Code: "TOOL_PANIC", Message: fmt.Sprintf("tool %s panicked", action)}}
				fmt.Fprintf(os.Stderr, "[PANIC] tool=%s panic=%v\n", action, r)
			}
			done <- out
		}()
		data, err := tool.Execute(toolCtx, params)
		out = toolOutput{data, err}
	}()

	select {
	case out := <-done:
		if out.err != nil {
			code := "TOOL_EXECUTION_ERROR"
			msg := out.err.Error()
			if te, ok := out.err.(*ToolErr); ok {
				code = te.Code
				msg = te.Message
			}
			truncatedRaw, _, _ := safety.TruncateErrorRaw(msg)
			return ToolResult{
				Success: false,
				Error: &ToolError{
					Code:    code,
					Message: msg,
					Raw:     truncatedRaw,
				},
			}
		}
		return ToolResult{Success: true, Data: out.data}

	case <-toolCtx.Done():
		return ToolResult{
			Success: false,
			Error: &ToolError{
				Code:    "EXECUTION_TIMEOUT",
				Message: fmt.Sprintf("tool %s timed out after %v", action, timeout),
			},
		}
	}
}

// WaitForDrain blocks until all in-flight tools complete.
func (e *Executor) WaitForDrain() {
	e.wg.Wait()
}

// MaxConcurrent returns the configured concurrency limit.
func (e *Executor) MaxConcurrent() int {
	return cap(e.semaphore)
}
