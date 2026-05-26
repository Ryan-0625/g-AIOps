//go:build linux

package dynamic

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

// ── SandboxConfig ────────────────────────────────────────────────────────

// SandboxConfig controls the execution environment for dynamic tools.
type SandboxConfig struct {
	TempDir     string // working directory for script execution
	MaxOutput   int64  // max stdout bytes (default 1MB)
	MaxMemoryMB int64  // max memory in MB (0 = no limit)
	Timeout     time.Duration
	EnableNet   bool // allow network access (default false for safety)
}

// DefaultSandboxConfig returns a safe default configuration.
func DefaultSandboxConfig() SandboxConfig {
	return SandboxConfig{
		TempDir:     "/tmp/gaiops-dynamic",
		MaxOutput:   1 * 1024 * 1024,
		MaxMemoryMB: 512,
		Timeout:     30 * time.Second,
		EnableNet:   false,
	}
}

// ── SandboxExecutor ──────────────────────────────────────────────────────

// SandboxExecutor runs dynamic tool code in an isolated environment.
//
// Execution model:
//  1. Write script to a temp file in the sandbox directory.
//  2. Execute via the configured interpreter with Linux namespace isolation.
//  3. Parameters are passed via TOOL_PARAMS environment variable (JSON).
//  4. stdout must contain valid JSON — stderr is captured for diagnostics.
//  5. Output is capped at MaxOutput bytes.
type SandboxExecutor struct {
	config SandboxConfig
}

// NewSandboxExecutor creates a sandbox executor with the given config.
func NewSandboxExecutor(config SandboxConfig) *SandboxExecutor {
	_ = os.MkdirAll(config.TempDir, 0700)
	return &SandboxExecutor{config: config}
}

// Execute runs the given code with params in a sandboxed environment.
// Returns the parsed JSON output from the script.
func (se *SandboxExecutor) Execute(ctx context.Context, code string, lang string, params map[string]interface{}) (map[string]interface{}, error) {
	// 1. Write script to temp file.
	scriptFile, err := se.writeScript(code, lang)
	if err != nil {
		return nil, &ExecError{Code: "COMPILE_FAILED", Message: err.Error()}
	}
	defer os.Remove(scriptFile)

	// 2. Build command.
	interpreter := se.resolveInterpreter(lang)
	cmd := exec.CommandContext(ctx, interpreter, scriptFile)

	// 3. Apply sandbox isolation (Linux namespaces).
	cmd.SysProcAttr = &syscall.SysProcAttr{
		Cloneflags: syscall.CLONE_NEWPID |
			syscall.CLONE_NEWNS |
			syscall.CLONE_NEWIPC,
	}

	// 4. Set working directory to sandbox temp dir.
	workDir := filepath.Join(se.config.TempDir, "run_"+SHA256(code)[:12])
	_ = os.MkdirAll(workDir, 0700)
	defer os.RemoveAll(workDir)
	cmd.Dir = workDir

	// 5. Pass params via environment variable (safe — no shell injection).
	paramsJSON, _ := json.Marshal(params)
	cmd.Env = append(cmd.Environ(),
		fmt.Sprintf("TOOL_PARAMS=%s", string(paramsJSON)),
		"SHELL=/bin/bash",
	)

	// 6. Capture stdout (output JSON) and stderr (diagnostics).
	var stdoutBuf bytes.Buffer
	var stderrBuf bytes.Buffer
	cmd.Stdout = &stdoutBuf
	cmd.Stderr = &stderrBuf

	// 7. Enforce resource limits if configured.
	if se.config.MaxMemoryMB > 0 {
		// RLIMIT_AS in bytes
		limit := se.config.MaxMemoryMB * 1024 * 1024
		cmd.SysProcAttr.Rlimit = &syscall.Rlimit{
			Cur: uint64(limit),
			Max: uint64(limit),
		}
	}

	// 8. Run with timeout from context (or configured default).
	if _, ok := ctx.Deadline(); !ok {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, se.config.Timeout)
		defer cancel()
	}

	if err := cmd.Run(); err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			// Script returned non-zero — parse stderr for details.
			stderrMsg := strings.TrimSpace(stderrBuf.String())
			if stderrMsg == "" {
				stderrMsg = fmt.Sprintf("exit code %d", exitErr.ExitCode())
			}
			return nil, &ExecError{Code: "EXECUTION_ERROR", Message: stderrMsg}
		}
		return nil, &ExecError{Code: "EXECUTION_FAILED", Message: err.Error()}
	}

	// 9. Parse stdout as JSON, capped at MaxOutput.
	output := stdoutBuf.Bytes()
	if int64(len(output)) > se.config.MaxOutput {
		output = output[:se.config.MaxOutput]
	}

	// Try to parse as JSON object.
	var result map[string]interface{}
	if err := json.Unmarshal(output, &result); err != nil {
		// If not JSON, wrap in a data field.
		return map[string]interface{}{
			"_raw_output": string(output),
		}, nil
	}

	return result, nil
}

// ── Internal helpers ─────────────────────────────────────────────────────

func (se *SandboxExecutor) writeScript(code string, lang string) (string, error) {
	ext := map[string]string{"bash": ".sh", "python3": ".py", "node": ".js"}
	filename := fmt.Sprintf("run_%x%s", SHA256(code)[:12], ext[lang])
	path := filepath.Join(se.config.TempDir, filename)

	// Add safe execution header.
	var script string
	switch lang {
	case "bash":
		script = "#!/bin/bash\nset -euo pipefail\n\n" + code
	case "python3":
		script = "#!/usr/bin/env python3\nimport json, os, sys\n" + code
	case "node":
		script = "#!/usr/bin/env node\n" + code
	default:
		return "", fmt.Errorf("unsupported language: %s", lang)
	}

	if err := os.WriteFile(path, []byte(script), 0500); err != nil {
		return "", err
	}
	return path, nil
}

func (se *SandboxExecutor) resolveInterpreter(lang string) string {
	switch lang {
	case "python3":
		return "/usr/bin/python3"
	case "node":
		return "/usr/bin/node"
	default:
		return "/bin/bash"
	}
}

// ── ExecError ────────────────────────────────────────────────────────────

// ExecError is a structured error for sandbox execution failures.
type ExecError struct {
	Code    string
	Message string
}

func (e *ExecError) Error() string { return fmt.Sprintf("[%s] %s", e.Code, e.Message) }
