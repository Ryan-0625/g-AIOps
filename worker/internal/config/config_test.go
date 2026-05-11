package config_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/gaiops/worker/internal/config"
)

func writeConfig(t *testing.T, content string) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "worker.yaml")
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestLoadValidConfig(t *testing.T) {
	yaml := `
worker_id: "test-worker"
master_url: "ws://localhost:8080/ws"
cluster_token: "test-token"
heartbeat_interval: 15
reconnect:
  base_delay: 1
  max_delay: 60
max_concurrent_tools: 5
logging:
  level: info
  format: json
allowed_log_paths:
  - /var/log
allowed_disk_paths:
  - /
tools:
  exec:
    allowed_commands:
      - /usr/bin/systemctl
credentials_path: ./keys
`
	path := writeConfig(t, yaml)
	cfg, errs := config.Load(path)
	if errs != nil {
		t.Fatalf("expected no errors, got: %v", errs)
	}
	if cfg.WorkerID != "test-worker" {
		t.Errorf("WorkerID = %q", cfg.WorkerID)
	}
}

func TestLoadMissingRequiredFields(t *testing.T) {
	yaml := `
worker_id: ""
master_url: ""
cluster_token: ""
heartbeat_interval: 0
reconnect:
  base_delay: 0
  max_delay: 0
max_concurrent_tools: 0
logging:
  level: ""
  format: ""
tools:
  exec:
    allowed_commands: []
`
	path := writeConfig(t, yaml)
	_, errs := config.Load(path)
	if len(errs) == 0 {
		t.Fatal("expected validation errors, got none")
	}
	// Should report all missing fields, not just the first one
	if len(errs) < 5 {
		t.Fatalf("expected at least 5 errors for missing fields, got %d: %v", len(errs), errs)
	}
}

func TestLoadFileNotFound(t *testing.T) {
	_, errs := config.Load("/nonexistent/path/worker.yaml")
	if len(errs) == 0 {
		t.Fatal("expected error for missing file")
	}
}

func TestLoadInvalidYAML(t *testing.T) {
	path := writeConfig(t, `broken: [yaml: :`)
	_, errs := config.Load(path)
	if len(errs) == 0 {
		t.Fatal("expected parse error")
	}
}
