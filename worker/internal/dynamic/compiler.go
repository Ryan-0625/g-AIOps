// Package dynamic provides the dynamic tool engine — runtime compilation,
// sandboxed execution, process pooling, and lifecycle management for
// script-based tools deployed by Brain at runtime.
//
// Architecture:
//
//	Compiler (syntax check + security scan)
//	     ↓
//	SandboxExecutor (namespace-isolated execution)
//	     ↓
//	RuntimePool (pre-warmed interpreter processes)
//	     ↓
//	LifecycleManager (register → track → GC)
package dynamic

import (
	"crypto/sha256"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
)

// ── CompileResult ────────────────────────────────────────────────────────

// CompileResult carries the outcome of a code pre-check.
type CompileResult struct {
	Valid    bool
	Language string   // bash | python3 | node
	Errors   []string // syntax errors (empty = valid)
	Warnings []string // security warnings
}

// ── Compiler ─────────────────────────────────────────────────────────────

// Compiler performs syntax checking and security scanning on tool code.
// All tools go through the compiler before being registered for execution.
type Compiler struct {
	tempDir  string
	scanners []CodeScanner
}

// CodeScanner is a pluggable security scanner (strategy pattern).
type CodeScanner interface {
	Scan(code string, language string) ([]string, error)
	Name() string
}

// NewCompiler creates a Compiler with the given temp directory and scanners.
func NewCompiler(tempDir string, scanners ...CodeScanner) *Compiler {
	if tempDir == "" {
		tempDir = "/tmp/gaiops-compile"
	}
	_ = os.MkdirAll(tempDir, 0700)
	return &Compiler{
		tempDir:  tempDir,
		scanners: scanners,
	}
}

// Compile runs the full pre-check pipeline: syntax check → security scan.
func (c *Compiler) Compile(code string, lang string) *CompileResult {
	result := &CompileResult{Valid: false, Language: lang}

	tmpFile, err := c.writeTemp(code, lang)
	if err != nil {
		result.Errors = append(result.Errors, fmt.Sprintf("cannot write temp file: %v", err))
		return result
	}
	defer os.Remove(tmpFile)

	switch lang {
	case "bash":
		errs := c.checkBashSyntax(tmpFile)
		if len(errs) > 0 {
			result.Errors = append(result.Errors, errs...)
			return result
		}
	case "python3":
		errs := c.checkPythonSyntax(tmpFile)
		if len(errs) > 0 {
			result.Errors = append(result.Errors, errs...)
			return result
		}
	case "node":
		errs := c.checkNodeSyntax(tmpFile)
		if len(errs) > 0 {
			result.Errors = append(result.Errors, errs...)
			return result
		}
	default:
		result.Errors = append(result.Errors, fmt.Sprintf("unsupported language: %s", lang))
		return result
	}

	// Run all registered security scanners.
	for _, scanner := range c.scanners {
		warnings, err := scanner.Scan(code, lang)
		if err != nil {
			result.Warnings = append(result.Warnings,
				fmt.Sprintf("[%s] scan error: %v", scanner.Name(), err))
			continue
		}
		result.Warnings = append(result.Warnings, warnings...)
	}

	result.Valid = true
	return result
}

// SHA256 returns the hex-encoded SHA-256 hash of the code.
func SHA256(code string) string {
	h := sha256.Sum256([]byte(code))
	return fmt.Sprintf("%x", h)
}

// ── Internal helpers ─────────────────────────────────────────────────────

func (c *Compiler) writeTemp(code string, lang string) (string, error) {
	ext := map[string]string{"bash": ".sh", "python3": ".py", "node": ".js"}
	filename := fmt.Sprintf("tool_%x%s", SHA256(code)[:12], ext[lang])
	path := filepath.Join(c.tempDir, filename)
	if err := os.WriteFile(path, []byte(code), 0500); err != nil {
		return "", err
	}
	return path, nil
}

func (c *Compiler) checkBashSyntax(path string) []string {
	cmd := exec.Command("bash", "-n", path)
	out, err := cmd.CombinedOutput()
	if err == nil {
		return nil
	}
	return []string{strings.TrimSpace(string(out))}
}

func (c *Compiler) checkPythonSyntax(path string) []string {
	cmd := exec.Command("python3", "-m", "py_compile", path)
	out, err := cmd.CombinedOutput()
	if err == nil {
		return nil
	}
	return []string{strings.TrimSpace(string(out))}
}

func (c *Compiler) checkNodeSyntax(path string) []string {
	cmd := exec.Command("node", "--check", path)
	out, err := cmd.CombinedOutput()
	if err == nil {
		return nil
	}
	return []string{strings.TrimSpace(string(out))}
}

// ── Built-in security scanners ───────────────────────────────────────────

// ShellInjectionScanner detects dangerous shell patterns.
type ShellInjectionScanner struct{}

func (s *ShellInjectionScanner) Name() string { return "shell-injection" }

func (s *ShellInjectionScanner) Scan(code string, _ string) ([]string, error) {
	var warnings []string
	patterns := map[string]*regexp.Regexp{
		"recursive-delete":        regexp.MustCompile(`rm\s+(-rf?|--recursive)\s+/`),
		"format-disk":             regexp.MustCompile(`mkfs\.\w+|dd\s+if=.*of=\/dev\/`),
		"reverse-shell":           regexp.MustCompile(`(bash|sh|nc|perl|python).*(-i|>&/dev/tcp/)`),
		"crypto-miner":            regexp.MustCompile(`(stratum|minerd|xmrig|cryptonight)`),
		"etc-shadow-access":       regexp.MustCompile(`/etc/(shadow|passwd|sudoers)`),
		"ssh-key-access":          regexp.MustCompile(`/root/\.ssh/`),
	}
	for name, pattern := range patterns {
		if pattern.MatchString(code) {
			warnings = append(warnings, fmt.Sprintf("suspicious pattern: %s", name))
		}
	}
	return warnings, nil
}

// ResourceAbuseScanner detects fork bombs and infinite loops.
type ResourceAbuseScanner struct{}

func (s *ResourceAbuseScanner) Name() string { return "resource-abuse" }

func (s *ResourceAbuseScanner) Scan(code string, _ string) ([]string, error) {
	var warnings []string
	if regexp.MustCompile(`:\{\s*\|:\s*&\s*\};:`).MatchString(code) {
		warnings = append(warnings, "fork bomb detected")
	}
	if regexp.MustCompile(`while\s+(true|1)\s*;?\s*do`).MatchString(code) {
		warnings = append(warnings, "potential infinite loop")
	}
	return warnings, nil
}

// NetworkAccessScanner detects unexpected network calls in what should be
// a local-only script.
type NetworkAccessScanner struct{}

func (s *NetworkAccessScanner) Name() string { return "network-access" }

func (s *NetworkAccessScanner) Scan(code string, _ string) ([]string, error) {
	var warnings []string
	patterns := []*regexp.Regexp{
		regexp.MustCompile(`curl\s+`),
		regexp.MustCompile(`wget\s+`),
		regexp.MustCompile(`nc\s+`),
		regexp.MustCompile(`netcat\s+`),
	}
	for _, p := range patterns {
		if p.MatchString(code) {
			warnings = append(warnings, "unexpected network access detected")
			break
		}
	}
	return warnings, nil
}
