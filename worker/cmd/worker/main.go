package main

import (
	"context"
	"flag"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gaiops/worker/internal/config"
	"github.com/gaiops/worker/internal/connection"
	"github.com/gaiops/worker/internal/executor"
	"github.com/gaiops/worker/internal/logger"
	"github.com/gaiops/worker/internal/registry"
	"github.com/gaiops/worker/internal/reporter"
	"github.com/gaiops/worker/internal/server"
	"github.com/gaiops/worker/internal/tools"
)

var log = logger.New("worker")

func main() {
	configPath := flag.String("config", "worker.yaml", "path to config file")
	flag.Parse()

	log.Info("Worker starting", logger.WithData(map[string]interface{}{"config": *configPath}))

	cfg, errs := config.Load(*configPath)
	if errs != nil {
		for _, e := range errs {
			log.Error("config validation failed", logger.WithData(map[string]interface{}{"error": e.Error()}))
		}
		os.Exit(1)
	}
	log.Info("Configuration loaded", logger.WithData(map[string]interface{}{
		"worker_id": cfg.WorkerID,
		"master":    cfg.MasterURL,
	}))

	// Apply allowed commands from config (must happen before any exec.run call).
	tools.SetAllowedCommands(cfg.Tools.Exec.AllowedCommands)

	exec := executor.New(registry.Global, cfg.MaxConcurrentTools)
	log.Info("Executor initialised", logger.WithData(map[string]interface{}{
		"tools":       len(registry.Global.Actions()),
		"max_concurr": cfg.MaxConcurrentTools,
	}))

	client := connection.New(connection.Config{
		WorkerID:          cfg.WorkerID,
		MasterURL:         cfg.MasterURL,
		ClusterToken:      cfg.ClusterToken,
		HeartbeatInterval: cfg.HeartbeatInterval,
		ReconnectBase:     cfg.Reconnect.BaseDelay,
		ReconnectMax:      cfg.Reconnect.MaxDelay,
		Actions:           registry.Global.Actions(),
		RiskLevels:        registry.Global.RiskLevels(),
		MaxConcurrent:     cfg.MaxConcurrentTools,
		WorkerVersion:     "0.1.0",
		TLSSkipVerify:     cfg.TLSSkipVerify,
	}, exec, log)

	// Reporter sends periodic heartbeat envelopes to Master.
	rep := reporter.New(cfg.HeartbeatInterval, len(registry.Global.Actions()), client.SendEnvelope, log)
	client.SetReporter(rep)

	// Dynamic tool manager — enables runtime tool.create and tool.delete.
	dm := tools.NewDynamicManager(cfg.DataDir, func() {
		client.ReAdvertise()
	})
	tools.SetDynamicManager(dm)
	log.Info("Dynamic tool manager initialised", logger.WithData(map[string]interface{}{
		"data_dir": cfg.DataDir,
	}))

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	// Run client in background (blocks on reconnect loop).
	go func() {
		if err := client.Run(ctx); err != nil && err != context.Canceled {
			log.Error("Client exited", logger.WithData(map[string]interface{}{"error": err.Error()}))
		}
	}()

	// Start periodic health reporting.
	go rep.Start(ctx)

	// HTTP health endpoint.
	healthMux := http.NewServeMux()
	healthMux.HandleFunc("/health", server.HealthHandler)
	healthServer := &http.Server{Addr: ":9090", Handler: healthMux}
	go func() {
		log.Info("Health endpoint listening", logger.WithData(map[string]interface{}{"addr": ":9090"}))
		if err := healthServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Error("Health server failed", logger.WithData(map[string]interface{}{"error": err.Error()}))
		}
	}()

	// Wait for shutdown signal.
	sig := <-sigCh
	log.Info("Shutting down", logger.WithData(map[string]interface{}{"signal": sig.String()}))

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
		log.Info("All tools completed")
	case <-time.After(30 * time.Second):
		log.Warn("Drain timeout, forcing exit")
	}

	log.Info("Worker stopped")
}
