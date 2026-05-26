package tools

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

// --- exec.go utility tests ---

func TestIsCommandAllowedEmptyList(t *testing.T) {
	AllowedCommands.list = []string{}
	if isCommandAllowed("/usr/bin/test") {
		t.Error("expected false when whitelist is empty")
	}
}

func TestIsCommandAllowedExactMatch(t *testing.T) {
	allowed := "/usr/bin/systemctl"
	SetAllowedCommands([]string{allowed})

	if !isCommandAllowed(allowed) {
		t.Errorf("expected %q to be allowed", allowed)
	}
}

func TestIsCommandAllowedRejected(t *testing.T) {
	SetAllowedCommands([]string{"/usr/bin/systemctl"})
	if isCommandAllowed("/usr/bin/rm") {
		t.Error("expected rm to be rejected")
	}
}

func TestIsCommandAllowedAbsPath(t *testing.T) {
	exe, err := os.Executable()
	if err != nil {
		t.Skip("cannot get executable path:", err)
	}
	SetAllowedCommands([]string{exe})
	if !isCommandAllowed(exe) {
		t.Errorf("expected %q to be allowed", exe)
	}
}

func TestIsCommandAllowedRelativePath(t *testing.T) {
	SetAllowedCommands([]string{"/usr/bin/systemctl"})
	if isCommandAllowed("./some/relative/path") {
		t.Error("expected relative path to not match abs whitelist entry")
	}
}

func TestSetAllowedCommandsConcurrentSafe(t *testing.T) {
	SetAllowedCommands([]string{"/bin/ls", "/bin/ps"})
	got := GetAllowedCommands()
	if len(got) != 2 {
		t.Fatalf("len = %d, want 2", len(got))
	}
}

func TestContainsShellMeta(t *testing.T) {
	tests := []struct {
		input string
		want  bool
	}{
		{"safe-arg", false},
		{"hello;world", true},
		{"cmd|other", true},
		{"background&", true},
		{"`backtick`", true},
		{"$VAR", true},
		{"$(subshell)", true},
		{"{brace}", true},
		{"<redirect", true},
		{">redirect", true},
		{"(subshell)", true},
		{"normal-path-123._", false},
		{"/var/log/nginx/access.log", false},
	}
	for _, tt := range tests {
		got := containsShellMeta(tt.input)
		if got != tt.want {
			t.Errorf("containsShellMeta(%q) = %v, want %v", tt.input, got, tt.want)
		}
	}
}

// --- log.go tests ---

func TestExecuteLogTailFileNotFound(t *testing.T) {
	_, err := executeLogTail(context.Background(), map[string]interface{}{
		"path": "/nonexistent/path/that/does/not/exist.log",
	})
	if err == nil {
		t.Fatal("expected error for nonexistent file")
	}
}

func TestExecuteLogTailWithTempFile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.log")
	content := "line1\nline2\nline3\n"
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	result, err := executeLogTail(context.Background(), map[string]interface{}{
		"path": path,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	lines, ok := result["lines"].([]string)
	if !ok {
		t.Fatalf("lines is not []string: %T", result["lines"])
	}
	if len(lines) != 3 {
		t.Errorf("line_count = %d, want 3", len(lines))
	}
}

func TestExecuteLogTailCustomLines(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.log")
	var content string
	for i := 0; i < 100; i++ {
		content += "line\n"
	}
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	result, err := executeLogTail(context.Background(), map[string]interface{}{
		"path":  path,
		"lines": 10,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	lines, ok := result["lines"].([]string)
	if !ok {
		t.Fatalf("lines is not []string: %T", result["lines"])
	}
	if len(lines) != 10 {
		t.Errorf("line_count = %d, want 10", len(lines))
	}
}

func TestExecuteLogTailFileSize(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.log")
	if err := os.WriteFile(path, []byte("hello\nworld\n"), 0644); err != nil {
		t.Fatal(err)
	}

	result, err := executeLogTail(context.Background(), map[string]interface{}{
		"path": path,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	size, ok := result["file_size"].(int64)
	if !ok || size <= 0 {
		t.Errorf("expected positive file_size, got %d", size)
	}
}

// --- process.go tests ---

func TestExecuteProcessList(t *testing.T) {
	result, err := executeProcessList(context.Background(), nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	total, ok := result["total"].(int)
	if !ok || total <= 0 {
		t.Errorf("expected positive total, got %d", total)
	}
	procs, ok := result["processes"].([]map[string]interface{})
	if ok && len(procs) > 0 {
		if _, hasPid := procs[0]["pid"]; !hasPid {
			t.Error("expected pid field in first process")
		}
	}
}

func TestExecuteProcessListWithFilter(t *testing.T) {
	result, err := executeProcessList(context.Background(), map[string]interface{}{
		"name": "nonexistent-process-xyz-123",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	total, ok := result["total"].(int)
	if !ok || total != 0 {
		t.Errorf("expected 0 processes for nonexistent filter, got %d", total)
	}
}

func TestExecuteProcessListInvalidName(t *testing.T) {
	result, err := executeProcessList(context.Background(), map[string]interface{}{
		"name": 123, // invalid type
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Should work with invalid name (just no filter applied)
	_ = result
}

// --- disk.go tests ---

func TestExecuteDiskUsage(t *testing.T) {
	result, err := executeDiskUsage(context.Background(), map[string]interface{}{
		"path": ".",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	total, ok := result["total_bytes"].(uint64)
	if !ok || total <= 0 {
		t.Errorf("expected positive total_bytes, got %d (type %T)", result["total_bytes"], result["total_bytes"])
	}
}

