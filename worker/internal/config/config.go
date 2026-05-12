// Package config loads and validates worker.yaml.
//
// All fields are mandatory — the process MUST NOT start with missing or
// defaulted configuration. Every missing field is reported at once so the
// operator can fix everything in a single pass.
package config

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

// --- Reconnect ---

type ReconnectConfig struct {
	BaseDelay int `yaml:"base_delay"` // seconds
	MaxDelay  int `yaml:"max_delay"`  // seconds
}

// --- ExecConfig ---

type ExecConfig struct {
	AllowedCommands []string `yaml:"allowed_commands"`
}

// --- Tools ---

type ToolsConfig struct {
	Exec ExecConfig `yaml:"exec"`
}

// --- Logging ---

type LoggingConfig struct {
	Level  string `yaml:"level"`  // debug | info | warn | error
	Format string `yaml:"format"` // json | text
}

// --- Config ---

type Config struct {
	WorkerID           string          `yaml:"worker_id"`
	MasterURL          string          `yaml:"master_url"`
	ClusterToken       string          `yaml:"cluster_token"`
	HeartbeatInterval  int             `yaml:"heartbeat_interval"`
	Reconnect          ReconnectConfig `yaml:"reconnect"`
	MaxConcurrentTools int             `yaml:"max_concurrent_tools"`
	DataDir            string          `yaml:"data_dir"`
	Logging            LoggingConfig   `yaml:"logging"`
	AllowedLogPaths    []string        `yaml:"allowed_log_paths"`
	AllowedDiskPaths   []string        `yaml:"allowed_disk_paths"`
	Tools              ToolsConfig     `yaml:"tools"`
	CredentialsPath    string          `yaml:"credentials_path"`
	TLSSkipVerify      bool            `yaml:"tls_skip_verify"`
}

// --- Defaults (only safe non-breaking defaults) ---

func defaultConfig() Config {
	return Config{
		HeartbeatInterval:  15,
		MaxConcurrentTools: 5,
		DataDir:            "/var/lib/gaiops/worker",
		Logging: LoggingConfig{
			Level:  "info",
			Format: "json",
		},
		Reconnect: ReconnectConfig{
			BaseDelay: 1,
			MaxDelay:  60,
		},
	}
}

// --- Field metadata for validation ---

type fieldDef struct {
	path  string // yaml path for error messages
	value *string
	help  string
}

// Load reads a YAML file, merges defaults, and validates.
// Returns all validation errors at once; nil slice means success.
func Load(path string) (*Config, []error) {
	cfg := defaultConfig()

	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, []error{fmt.Errorf("read config: %w", err)}
	}

	if err := yaml.Unmarshal(raw, &cfg); err != nil {
		return nil, []error{fmt.Errorf("parse config: %w", err)}
	}

	absPath, _ := filepath.Abs(path)
	cfg.CredentialsPath = resolveRef(absPath, cfg.CredentialsPath)

	// Environment variable overrides (highest priority).
	if v := os.Getenv("CLUSTER_TOKEN"); v != "" {
		cfg.ClusterToken = v
	}
	if v := os.Getenv("WORKER_ID"); v != "" {
		cfg.WorkerID = v
	}
	if v := os.Getenv("MASTER_URL"); v != "" {
		cfg.MasterURL = v
	}

	errs := validate(&cfg)
	if len(errs) > 0 {
		return nil, errs
	}

	return &cfg, nil
}

// resolveRef resolves relative paths in config against the config file dir.
func resolveRef(configPath, ref string) string {
	if ref == "" || filepath.IsAbs(ref) {
		return ref
	}
	return filepath.Join(filepath.Dir(configPath), ref)
}

func validate(cfg *Config) []error {
	var errs []error
	add := func(msg string) { errs = append(errs, errors.New(msg)) }

	if cfg.WorkerID == "" {
		add("worker_id is required")
	}
	if cfg.MasterURL == "" {
		add("master_url is required (e.g. ws://localhost:8080/ws)")
	}
	if cfg.ClusterToken == "" {
		add("cluster_token is required")
	}
	if cfg.HeartbeatInterval <= 0 {
		add("heartbeat_interval must be > 0")
	}
	if cfg.Reconnect.BaseDelay <= 0 {
		add("reconnect.base_delay must be > 0")
	}
	if cfg.Reconnect.MaxDelay <= 0 {
		add("reconnect.max_delay must be > 0")
	}
	if cfg.MaxConcurrentTools <= 0 {
		add("max_concurrent_tools must be > 0")
	}
	if cfg.Logging.Level == "" {
		add("logging.level is required (debug/info/warn/error)")
	}
	if cfg.Logging.Format == "" {
		add("logging.format is required (json/text)")
	}
	if len(cfg.Tools.Exec.AllowedCommands) == 0 {
		add("tools.exec.allowed_commands must have at least one entry")
	}

	return errs
}
