package main

import (
	"context"
	"encoding/json"
	"flag"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gaiops/worker/internal/config"
	"github.com/gaiops/worker/internal/connection"
	"github.com/gaiops/worker/internal/executor"
	"github.com/gaiops/worker/internal/registry"
	"github.com/gaiops/worker/internal/reporter"
	"github.com/gaiops/worker/internal/server"
	"github.com/gaiops/worker/internal/tools"
)

type logEntry struct {
	Timestamp string      `json:"timestamp"`
	Level     string      `json:"level"`
	Module    string      `json:"module"`
	TraceID   string      `json:"trace_id"`
	Message   string      `json:"message"`
	PID       int         `json:"pid"`
	Data      interface{} `json:"data,omitempty"`
}

func jsonLog(level, msg string, data map[string]interface{}) {
	entry := logEntry{
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Level:     level,
		Module:    "worker",
		TraceID:   "no-trace",
		Message:   msg,
		PID:       os.Getpid(),
		Data:      data,
	}
	json.NewEncoder(os.Stdout).Encode(entry)
}

func main() {
	configPath := flag.String("config", "worker.yaml", "path to config file")
	flag.Parse()

	jsonLog("info", "Worker starting", map[string]interface{}{"config": *configPath})

	cfg, errs := config.Load(*configPath)
	if errs != nil {
		for _, e := range errs {
			jsonLog("error", "config validation failed", map[string]interface{}{"error": e.Error()})
		}
		os.Exit(1)
	}
	jsonLog("info", "Configuration loaded", map[string]interface{}{
		"worker_id": cfg.WorkerID,
		"master":    cfg.MasterURL,
	})

	// Apply allowed commands from config (must happen before any exec.run call).
	tools.SetAllowedCommands(cfg.Tools.Exec.AllowedCommands)

	exec := executor.New(registry.Global, cfg.MaxConcurrentTools)
	jsonLog("info", "Executor initialised", map[string]interface{}{
		"tools":       len(registry.Global.Actions()),
		"max_concurr": cfg.MaxConcurrentTools,
	})

	client := connection.New(connection.Config{
		MasterURL:         cfg.MasterURL,
		ClusterToken:      cfg.ClusterToken,
		HeartbeatInterval: cfg.HeartbeatInterval,
		ReconnectBase:     cfg.Reconnect.BaseDelay,
		ReconnectMax:      cfg.Reconnect.MaxDelay,
	}, exec)

	// Reporter sends periodic heartbeat envelopes to Master.
	rep := reporter.New(cfg.HeartbeatInterval, len(registry.Global.Actions()), client.SendEnvelope)
	client.SetReporter(rep)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	// Run client in background (blocks on reconnect loop).
	go func() {
		if err := client.Run(ctx); err != nil && err != context.Canceled {
			jsonLog("error", "Client exited", map[string]interface{}{"error": err.Error()})
		}
	}()

	// Start periodic health reporting.
	go rep.Start(ctx)

	// HTTP health endpoint.
	healthMux := http.NewServeMux()
	healthMux.HandleFunc("/health", server.HealthHandler)
	healthServer := &http.Server{Addr: ":9090", Handler: healthMux}
	go func() {
		jsonLog("info", "Health endpoint listening", map[string]interface{}{"addr": ":9090"})
		if err := healthServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			jsonLog("error", "Health server failed", map[string]interface{}{"error": err.Error()})
		}
	}()

	// Wait for shutdown signal.
	sig := <-sigCh
	jsonLog("info", "Shutting down", map[string]interface{}{"signal": sig.String()})

	cancel()

	// Shutdown health server gracefully.
	ctxHealth, shutdownHealth := context.WithTimeout(context.Background(), 5*time.Second)
	defer shutdownHealth()
	healthServer.Shutdown(ctxHealth)

	done := make(chan struct{})
	go func() {
		exec.WaitForDrain()
		close(done)
	}()
	select {
	case <-done:
		jsonLog("info", "All tools completed", nil)
	case <-time.After(30 * time.Second):
		jsonLog("warn", "Drain timeout, forcing exit", nil)
	}

	jsonLog("info", "Worker stopped", nil)
}
