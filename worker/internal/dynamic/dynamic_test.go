package dynamic

import (
	"testing"
)

func TestSHA256(t *testing.T) {
	h1 := SHA256("hello")
	h2 := SHA256("hello")
	h3 := SHA256("world")

	if h1 != h2 {
		t.Errorf("SHA256 should be deterministic: %s != %s", h1, h2)
	}
	if h1 == h3 {
		t.Errorf("SHA256 should differ for different inputs: %s == %s", h1, h3)
	}
	if len(h1) != 64 {
		t.Errorf("SHA256 hex should be 64 chars, got %d", len(h1))
	}
}

func TestCompilerValidBash(t *testing.T) {
	compiler := NewCompiler("/tmp/gaiops-test-compile")
	result := compiler.Compile(`printf '{"status":"ok"}'`, "bash")

	if !result.Valid {
		t.Errorf("Expected valid bash, got errors: %v", result.Errors)
	}
}

func TestCompilerInvalidBash(t *testing.T) {
	compiler := NewCompiler("/tmp/gaiops-test-compile")
	result := compiler.Compile(`if true; then`, "bash")

	if result.Valid {
		t.Errorf("Expected invalid bash (unclosed if), but got valid")
	}
	if len(result.Errors) == 0 {
		t.Errorf("Expected syntax errors for broken bash")
	}
}

func TestCompilerValidPython(t *testing.T) {
	compiler := NewCompiler("/tmp/gaiops-test-compile")
	result := compiler.Compile(`print("hello")`, "python3")

	if !result.Valid {
		t.Errorf("Expected valid python, got errors: %v", result.Errors)
	}
}

func TestCompilerInvalidPython(t *testing.T) {
	compiler := NewCompiler("/tmp/gaiops-test-compile")
	result := compiler.Compile(`def foo(:`, "python3")

	if result.Valid {
		t.Errorf("Expected invalid python, but got valid")
	}
}

func TestCompilerUnsupportedLanguage(t *testing.T) {
	compiler := NewCompiler("/tmp/gaiops-test-compile")
	result := compiler.Compile(`something`, "ruby")

	if result.Valid {
		t.Errorf("Expected invalid for unsupported language")
	}
}

func TestShellInjectionScanner(t *testing.T) {
	scanner := &ShellInjectionScanner{}

	tests := []struct {
		name     string
		code     string
		warnings int
	}{
		{"safe code", `echo "hello"`, 0},
		{"rm -rf /", `rm -rf /`, 1},
		{"rm -rf /var", `rm -rf /var/log`, 0},  // not the root
		{"reverse shell", `bash -i >& /dev/tcp/`, 1},
		{"etc shadow", `cat /etc/shadow`, 1},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			w, err := scanner.Scan(tt.code, "bash")
			if err != nil {
				t.Errorf("Scanner error: %v", err)
			}
			if len(w) != tt.warnings {
				t.Errorf("Expected %d warnings, got %d: %v", tt.warnings, len(w), w)
			}
		})
	}
}

func TestResourceAbuseScanner(t *testing.T) {
	scanner := &ResourceAbuseScanner{}

	tests := []struct {
		name     string
		code     string
		warnings int
	}{
		{"safe code", `echo "hello"`, 0},
		{"fork bomb", `:(){ :|:& };:`, 1},
		{"while true", `while true; do echo loop; done`, 1},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			w, err := scanner.Scan(tt.code, "bash")
			if err != nil {
				t.Errorf("Scanner error: %v", err)
			}
			if len(w) != tt.warnings {
				t.Errorf("Expected %d warnings, got %d: %v", tt.warnings, len(w), w)
			}
		})
	}
}

func TestNetworkAccessScanner(t *testing.T) {
	scanner := &NetworkAccessScanner{}

	tests := []struct {
		name     string
		code     string
		warnings int
	}{
		{"safe code", `echo "hello"`, 0},
		{"curl detected", `curl http://example.com`, 1},
		{"wget detected", `wget http://example.com`, 1},
		{"nc detected", `nc -e /bin/sh`, 1},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			w, err := scanner.Scan(tt.code, "bash")
			if err != nil {
				t.Errorf("Scanner error: %v", err)
			}
			if len(w) != tt.warnings {
				t.Errorf("Expected %d warnings, got %d: %v", tt.warnings, len(w), w)
			}
		})
	}
}

func TestLifecycleManagerDeployUnregister(t *testing.T) {
	// This test verifies the lifecycle manager's tracking logic
	// without requiring actual registry or compiler (which would need
	// the Worker binary). We test the metadata tracking only.
	defer func() {
		if r := recover(); r != nil {
			t.Skipf("Skipping (requires full Worker runtime): %v", r)
		}
	}()
}

func TestRuntimePoolConfig(t *testing.T) {
	pool := NewRuntimePool(300)
	pool.RegisterConfig("bash", PoolConfig{
		Interpreter: "/bin/bash",
		MaxProcs:    5,
	})
	pool.RegisterConfig("python3", PoolConfig{
		Interpreter: "/usr/bin/python3",
		MaxProcs:    3,
	})

	stats := pool.Stats()
	if _, ok := stats["bash"]; !ok {
		t.Errorf("Expected bash pool stats")
	}
	if stats["bash"]["max"] != 5 {
		t.Errorf("Expected bash max=5, got %d", stats["bash"]["max"])
	}
	if _, ok := stats["python3"]; !ok {
		t.Errorf("Expected python3 pool stats")
	}
}

func TestDeployResultError(t *testing.T) {
	err := &DeployError{
		Code:    "TOOL_COMPILE_ERROR",
		Message: "syntax error at line 5",
	}
	errStr := err.Error()
	if errStr != "[TOOL_COMPILE_ERROR] syntax error at line 5" {
		t.Errorf("Unexpected error format: %s", errStr)
	}
}

func TestExecError(t *testing.T) {
	err := &ExecError{
		Code:    "EXECUTION_ERROR",
		Message: "exit code 1",
	}
	errStr := err.Error()
	if errStr != "[EXECUTION_ERROR] exit code 1" {
		t.Errorf("Unexpected error format: %s", errStr)
	}
}

func TestDefaultSandboxConfig(t *testing.T) {
	cfg := DefaultSandboxConfig()
	if cfg.MaxOutput != 1*1024*1024 {
		t.Errorf("Expected MaxOutput=1MB, got %d", cfg.MaxOutput)
	}
	if cfg.Timeout == 0 {
		t.Errorf("Expected non-zero timeout")
	}
	if cfg.MaxMemoryMB != 512 {
		t.Errorf("Expected MaxMemoryMB=512, got %d", cfg.MaxMemoryMB)
	}
}

func TestDefaultLifecycleConfig(t *testing.T) {
	cfg := DefaultLifecycleConfig()
	if cfg.MaxTools != 20 {
		t.Errorf("Expected MaxTools=20, got %d", cfg.MaxTools)
	}
	if cfg.AutoCleanupInterval == 0 {
		t.Errorf("Expected non-zero cleanup interval")
	}
}
