package tools

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/gaiops/worker/internal/executor"
	"github.com/gaiops/worker/internal/registry"
)

// Blocked path prefixes — reading or writing to these is rejected.
var blockedPaths = []string{
	"/etc/shadow",
	"/etc/gshadow",
	"/etc/ssh/",
	"/root/.ssh/",
	"/root/.gnupg/",
	"/var/lib/gaiops/",
}

func init() {
	registry.Global.Register(registry.Tool{
		Action:       "file.read",
		Timeout:      10 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeFileRead,
	})
	registry.Global.Register(registry.Tool{
		Action:       "file.write",
		Timeout:      10 * time.Second,
		IsIdempotent: false,
		RiskLevel:    "dangerous",
		Execute:      executeFileWrite,
	})
	registry.Global.Register(registry.Tool{
		Action:       "file.list",
		Timeout:      10 * time.Second,
		IsIdempotent: true,
		RiskLevel:    "readonly",
		Execute:      executeFileList,
	})
}

func executeFileRead(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	path, _ := params["path"].(string)
	if path == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "path is required")
	}

	// Security: resolve and check path.
	absPath, err := filepath.Abs(path)
	if err != nil {
		return nil, executor.NewErr("INVALID_PATH", fmt.Sprintf("cannot resolve path: %v", err))
	}

	if isBlockedPath(absPath) {
		return nil, executor.NewErr("PATH_BLOCKED", "access to this path is not allowed")
	}

	// Max bytes (default 4096, max 65536).
	maxBytes := 4096
	if mb, ok := params["max_bytes"].(int); ok {
		if mb > 0 && mb <= 65536 {
			maxBytes = mb
		}
	}

	data, err := os.ReadFile(absPath)
	if err != nil {
		return nil, executor.NewErr("READ_FAILED", fmt.Sprintf("cannot read file: %v", err))
	}

	size := len(data)
	truncated := false
	if size > maxBytes {
		data = data[:maxBytes]
		truncated = true
	}

	return map[string]interface{}{
		"path":       absPath,
		"content":    string(data),
		"size_bytes": size,
		"truncated":  truncated,
	}, nil
}

func executeFileWrite(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	path, _ := params["path"].(string)
	if path == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "path is required")
	}
	content, _ := params["content"].(string)
	if content == "" {
		return nil, executor.NewErr("INVALID_PARAMS", "content is required")
	}

	// Security: resolve and check path.
	absPath, err := filepath.Abs(path)
	if err != nil {
		return nil, executor.NewErr("INVALID_PATH", fmt.Sprintf("cannot resolve path: %v", err))
	}

	if isBlockedPath(absPath) {
		return nil, executor.NewErr("PATH_BLOCKED", "access to this path is not allowed")
	}

	// Limit writes to /tmp/ or a work directory for safety.
	allowed := false
	for _, prefix := range []string{"/tmp/", "/var/tmp/"} {
		if strings.HasPrefix(absPath, prefix) {
			allowed = true
			break
		}
	}
	if !allowed {
		return nil, executor.NewErr("PATH_NOT_ALLOWED", "writes are only allowed to /tmp/ and /var/tmp/")
	}

	// Ensure parent directory exists.
	parent := filepath.Dir(absPath)
	if err := os.MkdirAll(parent, 0755); err != nil {
		return nil, executor.NewErr("WRITE_FAILED", fmt.Sprintf("cannot create directory: %v", err))
	}

	// Parse mode.
	mode := os.FileMode(0644)
	if modeStr, ok := params["mode"].(string); ok {
		if m, err := strconv.ParseInt(modeStr, 8, 32); err == nil {
			mode = os.FileMode(m)
		}
	}

	append_ := false
	if a, ok := params["append"].(bool); ok {
		append_ = a
	}

	action := "written"
	if append_ {
		f, err := os.OpenFile(absPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, mode)
		if err != nil {
			return nil, executor.NewErr("WRITE_FAILED", fmt.Sprintf("cannot append: %v", err))
		}
		defer f.Close()
		if _, err := f.WriteString(content); err != nil {
			return nil, executor.NewErr("WRITE_FAILED", fmt.Sprintf("append failed: %v", err))
		}
		action = "appended"
	} else {
		if err := os.WriteFile(absPath, []byte(content), mode); err != nil {
			return nil, executor.NewErr("WRITE_FAILED", fmt.Sprintf("cannot write: %v", err))
		}
	}

	return map[string]interface{}{
		"path":       absPath,
		"size_bytes": len(content),
		"action":     action,
	}, nil
}

func executeFileList(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
	path, _ := params["path"].(string)
	if path == "" {
		path = "/"
	}

	absPath, err := filepath.Abs(path)
	if err != nil {
		return nil, executor.NewErr("INVALID_PATH", fmt.Sprintf("cannot resolve path: %v", err))
	}

	entries, err := os.ReadDir(absPath)
	if err != nil {
		return nil, executor.NewErr("READ_FAILED", fmt.Sprintf("cannot list directory: %v", err))
	}

	items := make([]map[string]interface{}, 0, len(entries))
	for _, e := range entries {
		info, _ := e.Info()
		size := int64(0)
		modTime := ""
		if info != nil {
			size = info.Size()
			modTime = info.ModTime().Format(time.RFC3339)
		}
		items = append(items, map[string]interface{}{
			"name":       e.Name(),
			"is_dir":     e.IsDir(),
			"size_bytes": size,
			"mod_time":   modTime,
		})
	}

	return map[string]interface{}{
		"path":  absPath,
		"items": items,
		"count": len(items),
	}, nil
}

func isBlockedPath(absPath string) bool {
	lower := strings.ToLower(absPath)
	for _, blocked := range blockedPaths {
		if strings.HasPrefix(lower, strings.ToLower(blocked)) {
			return true
		}
	}
	// Block files with sensitive extensions.
	sensitiveExts := []string{".pem", ".key", ".pkcs12", ".pfx", ".ovpn"}
	ext := strings.ToLower(filepath.Ext(absPath))
	for _, se := range sensitiveExts {
		if ext == se {
			return true
		}
	}
	return false
}
