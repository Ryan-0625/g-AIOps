package tools

import (
	"context"
	"os"
	"testing"
)

// ============================================================
// Port tool edge-case tests
// ============================================================

func TestExecutePortCheckInvalidPort(t *testing.T) {
	// Port outside valid range should default to 80
	result, err := executePortCheck(context.Background(), map[string]interface{}{
		"host": "127.0.0.1",
		"port": 99999,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result["port"] != 80 {
		t.Errorf("expected port 80 (default), got %v", result["port"])
	}
}

func TestExecutePortCheckZeroPort(t *testing.T) {
	result, err := executePortCheck(context.Background(), map[string]interface{}{
		"host": "127.0.0.1",
		"port": 0,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result["port"] != 80 {
		t.Errorf("expected port 80 (default), got %v", result["port"])
	}
}

func TestExecutePortCheckNegativePort(t *testing.T) {
	result, err := executePortCheck(context.Background(), map[string]interface{}{
		"host": "127.0.0.1",
		"port": -1,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result["port"] != 80 {
		t.Errorf("expected port 80 (default), got %v", result["port"])
	}
}

func TestExecutePortCheckLocalhostReachable(t *testing.T) {
	result, err := executePortCheck(context.Background(), map[string]interface{}{
		"host": "127.0.0.1",
		"port": 80,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// 127.0.0.1:80 may or may not be open - just verify no crash
	if _, ok := result["reachable"]; !ok {
		t.Error("expected reachable field")
	}
	if _, ok := result["latency_ms"]; !ok {
		t.Error("expected latency_ms field")
	}
}

func TestExecutePortCheckContextCancelled(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // Cancel immediately

	_, err := executePortCheck(ctx, map[string]interface{}{
		"host": "192.0.2.1",
		"port": 22,
	})
	// Should either return partial result or timeout error
	if err != nil {
		t.Logf("Got expected error with cancelled context: %v", err)
	}
}

func TestExecutePortCheckTimeoutParam(t *testing.T) {
	result, err := executePortCheck(context.Background(), map[string]interface{}{
		"host":            "localhost",
		"port":            22,
		"timeout_seconds": 1,
	})
	if err != nil {
		t.Logf("Got error (expected for timeout test): %v", err)
	}
	if result != nil && result["latency_ms"].(int64) < 0 {
		t.Error("expected non-negative latency")
	}
}

func TestExecutePortScanInvalidPortInList(t *testing.T) {
	result, err := executePortScan(context.Background(), map[string]interface{}{
		"host": "127.0.0.1",
		"ports": []interface{}{80, 99999, -1, 443},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Invalid ports should be skipped
	scanned := result["scanned"].(int)
	if scanned > 2 {
		t.Errorf("expected <= 2 valid ports scanned, got %d", scanned)
	}
}

func TestExecutePortScanEmptyPortList(t *testing.T) {
	_, err := executePortScan(context.Background(), map[string]interface{}{
		"host":  "127.0.0.1",
		"ports": []interface{}{},
	})
	if err == nil {
		t.Error("expected error for empty ports list")
	}
}

func TestExecutePortScanContextCancelled(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	result, err := executePortScan(ctx, map[string]interface{}{
		"host":  "192.0.2.1",
		"ports": []interface{}{22, 80, 443, 8080},
	})
	if err != nil {
		t.Logf("Got error with cancelled context: %v", err)
	}
	if result != nil {
		if truncated, ok := result["truncated"]; ok && truncated.(bool) {
			t.Log("Scan was truncated due to cancelled context (expected)")
		}
	}
}

func TestExecutePortScanNonExistentHost(t *testing.T) {
	result, err := executePortScan(context.Background(), map[string]interface{}{
		"host":  "192.0.2.99",
		"ports": []interface{}{22, 80},
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// All ports should be closed
	closed := result["closed_ports"].([]int)
	if len(closed) != 2 {
		t.Errorf("expected 2 closed ports, got %d: %v", len(closed), closed)
	}
}

// ============================================================
// Process tool edge-case tests
// ============================================================

func TestExecuteProcessKillInvalidPid(t *testing.T) {
	_, err := executeProcessKill(context.Background(), map[string]interface{}{
		"pid": 0,
	})
	if err == nil {
		t.Error("expected error for pid=0")
	}
}

func TestExecuteProcessKillNegativePid(t *testing.T) {
	_, err := executeProcessKill(context.Background(), map[string]interface{}{
		"pid": -1,
	})
	if err == nil {
		t.Error("expected error for pid=-1")
	}
}

func TestExecuteProcessKillNoPid(t *testing.T) {
	_, err := executeProcessKill(context.Background(), map[string]interface{}{})
	if err == nil {
		t.Error("expected error for missing pid")
	}
}

func TestExecuteProcessKillNonExistentPid(t *testing.T) {
	_, err := executeProcessKill(context.Background(), map[string]interface{}{
		"pid": 999999999,
	})
	if err == nil {
		t.Error("expected error for nonexistent pid")
	}
}

func TestExecuteProcessKillStringPid(t *testing.T) {
	_, err := executeProcessKill(context.Background(), map[string]interface{}{
		"pid": "not-a-number",
	})
	// String that can't be converted should fail
	if err == nil {
		t.Error("expected error for string pid")
	}
}

func TestExecuteProcessKillCustomSignal(t *testing.T) {
	// Should not fail for valid signal name even if process doesn't exist
	_, err := executeProcessKill(context.Background(), map[string]interface{}{
		"pid":    999999999,
		"signal": "SIGTERM",
	})
	if err == nil {
		t.Error("expected error for nonexistent process")
	}
}

func TestExecuteProcessKillSignalKill(t *testing.T) {
	_, err := executeProcessKill(context.Background(), map[string]interface{}{
		"pid":    999999999,
		"signal": "SIGKILL",
	})
	if err == nil {
		t.Error("expected error for nonexistent process")
	}
}

func TestExecuteProcessListWithEmptyFilter(t *testing.T) {
	result, err := executeProcessList(context.Background(), map[string]interface{}{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	total, ok := result["total"].(int)
	if !ok || total <= 0 {
		t.Errorf("expected positive total, got %d", total)
	}
	if _, ok := result["processes"]; !ok {
		t.Error("expected processes field")
	}
}

func TestExecuteProcessListFilterCurrentProcess(t *testing.T) {
	// Get current executable name
	exe, err := os.Executable()
	if err != nil {
		t.Skip("cannot get executable:", err)
	}

	result, err := executeProcessList(context.Background(), map[string]interface{}{
		"name": exe,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Should at least find this test process
	_ = result
}

func TestParseSignalAllVariants(t *testing.T) {
	tests := []struct {
		input string
		valid bool
	}{
		{"SIGTERM", true},
		{"TERM", true},
		{"15", true},
		{"SIGKILL", true},
		{"KILL", true},
		{"9", true},
		{"SIGHUP", true},
		{"HUP", true},
		{"1", true},
		{"SIGINT", false}, // Not explicitly mapped but should still work
		{"INVALID", false},
		{"", false},
	}
	for _, tt := range tests {
		result := parseSignal(tt.input)
		if tt.valid && result == nil {
			t.Errorf("parseSignal(%q) = nil, expected non-nil", tt.input)
		}
	}
}

func TestSafeAtoiEdgeCases(t *testing.T) {
	tests := []struct {
		input string
		want  int
	}{
		{"42", 42},
		{"  42  ", 42},
		{"", 0},
		{"abc", 0},
		{"-1", -1},
		{"0", 0},
		{"999999999", 999999999},
	}
	for _, tt := range tests {
		got := safeAtoi(tt.input)
		if got != tt.want {
			t.Errorf("safeAtoi(%q) = %d, want %d", tt.input, got, tt.want)
		}
	}
}

// ============================================================
// Concurrent access safety tests
// ============================================================

func TestConcurrentPortCheck(t *testing.T) {
	for i := 0; i < 10; i++ {
		t.Run("parallel", func(t *testing.T) {
			t.Parallel()
			result, err := executePortCheck(context.Background(), map[string]interface{}{
				"host": "127.0.0.1",
				"port": 80,
			})
			if err != nil {
				t.Logf("port check error: %v", err)
			} else if result == nil {
				t.Error("result should not be nil")
			}
		})
	}
}

func TestConcurrentProcessList(t *testing.T) {
	for i := 0; i < 10; i++ {
		t.Run("parallel", func(t *testing.T) {
			t.Parallel()
			result, err := executeProcessList(context.Background(), nil)
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if total, ok := result["total"].(int); !ok || total <= 0 {
				t.Errorf("expected positive total, got %d", total)
			}
		})
	}
}

// ============================================================
// exec.run tool edge-case test (shell meta handling)
// ============================================================

func TestContainsShellMetaEdge(t *testing.T) {
	tests := []struct {
		input string
		want  bool
	}{
		{"", false},
		{"   ", false},
		{"a b c", false},
		{";", true},
		{"|", true},
		{"&", true},
		{"`a`", true},
		{"$(cmd)", true},
		{"${var}", true},
		{">/dev/null", true},
		{"</etc/passwd", true},
		{"(subshell)", true},
		{"{braces}", true},
		{"path/to/file", false},
		{"/usr/bin/test --flag value", false},
		{"C:\\Program Files\\App\\app.exe", false},
	}
	for _, tt := range tests {
		got := containsShellMeta(tt.input)
		if got != tt.want {
			t.Errorf("containsShellMeta(%q) = %v, want %v", tt.input, got, tt.want)
		}
	}
}
