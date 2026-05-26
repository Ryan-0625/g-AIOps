import express, { Request, Response, NextFunction } from "express";
import http from "http";
import https from "https";
import fs from "fs";
import { load as loadConfig, validate as validateConfig } from "./config";
import { Registry } from "./store/registry";
import { Tracker } from "./orchestrator/tracker";
import { PriorityQueue } from "./orchestrator/priority-queue";
import { Router } from "./orchestrator/router";
import { Summarizer } from "./orchestrator/summarizer";
import { Interceptor } from "./security/interceptor";
import { Approver } from "./security/approver";
import { WebSocketServer } from "./server/ws-server";
import { brainApiRouter } from "./server/brain-api";
import { healthRouter } from "./server/health";
import { traceRouter } from "./server/trace";
import { createLogger } from "./logger";
import { configureAudit } from "./security/audit";
import { MetricsCollector } from "./store/metrics";
import { metricsRouter } from "./server/metrics";
import { InspectionStore } from "./store/inspection-store";
import { Inspector } from "./orchestrator/inspector";
import { inspectionApiRouter } from "./server/inspection-api";
import { webhookApiRouter } from "./server/webhook-api";

const logger = createLogger("master");

// Process-level crash handlers 鈥?must be registered before main().
process.on("uncaughtException", (err) => {
  logger.error("Uncaught exception", {
    data: { message: err.message, stack: err.stack },
  });
  process.exit(1);
});

process.on("unhandledRejection", (reason) => {
  logger.error("Unhandled rejection", {
    data: { reason: reason instanceof Error ? reason.message : String(reason) },
  });
});

const cfg = loadConfig();

// Validate config 鈥?log warnings, exit on errors.
const { warnings, errors } = validateConfig(cfg);
for (const w of warnings) {
  logger.warn("Config: " + w.message, { data: { field: w.field } });
}
if (errors.length > 0) {
  for (const e of errors) {
    logger.error("Config: " + e.message, { data: { field: e.field } });
  }
  logger.error("Config validation failed 鈥?exiting", { data: { error_count: errors.length } });
  process.exit(1);
}

// TLS config (consumed directly from env for cert file paths)
const TLS_CERT = process.env.TLS_CERT_PATH;
const TLS_KEY = process.env.TLS_KEY_PATH;
const useTls = !!(TLS_CERT && TLS_KEY);

function main(): void {
  const port = useTls ? cfg.server.api_port : cfg.server.ws_port;
  logger.info("Master starting", { data: { port } });

  // 鈹€鈹€ Store 鈹€鈹€
  const registry = new Registry();
  const tracker = new Tracker();
  const queue = new PriorityQueue();
  const metricsCollector = new MetricsCollector();
  const inspectionStore = new InspectionStore();

  // 鈹€鈹€ Audit 鈹€鈹€
  configureAudit({
    logPath: cfg.audit.log_path || undefined,
    enabled: cfg.audit.enabled,
  });

  // 鈹€鈹€ Orchestrator 鈹€鈹€
  const masterRouter = new Router(registry);
  const summarizer = new Summarizer();

  // 鈹€鈹€ Security 鈹€鈹€
  const interceptor = new Interceptor(registry, cfg.security.high_risk_actions);

  // 鈹€鈹€ Server 鈹€鈹€
  const app = express();
  app.use(express.json({ limit: cfg.server.api.body_limit }));

  const server = useTls
    ? https.createServer(
        { cert: fs.readFileSync(TLS_CERT!), key: fs.readFileSync(TLS_KEY!) },
        app,
      )
    : http.createServer(app);

  const wsServer = new WebSocketServer(registry, tracker, masterRouter, queue, cfg.cluster_token, cfg.server.ws);
  wsServer.attach(server);

  // ││ Inspection System ││
  const inspector = new Inspector(inspectionStore, registry, wsServer);
  if (cfg.inspection.enabled) {
    inspector.start(cfg.inspection.tick_interval_ms);
  }

  // Approver needs wsServer for the onApprove callback.
  const approver = new Approver(
    registry,
    (req) => {
      logger.warn("Approval rejected or expired", {
        msg_id: req.id,
        data: { action: req.envelope.payload.action, status: req.status },
      });
    },
    (req) => {
      req.envelope.source = "master";
      req.envelope.source_id = "master";
      wsServer.sendToWorker(req.targetWorkerId, req.envelope);
    },
  );

  // 鈹€鈹€ Routes 鈹€鈹€
  app.use(healthRouter(registry, tracker, approver, cfg));
  app.use(metricsRouter(registry, tracker, queue, approver, metricsCollector));
  app.use(brainApiRouter(registry, queue, masterRouter, tracker, summarizer, interceptor, approver, wsServer, cfg.cluster_token, metricsCollector));
  app.use(traceRouter(tracker));
  app.use(inspectionApiRouter(inspectionStore, inspector, registry, cfg.cluster_token));
  app.use(webhookApiRouter(registry, tracker, masterRouter, queue, interceptor, approver, wsServer, cfg.cluster_token, metricsCollector));

  // Catch-all Express error middleware 鈥?must be last app.use().
  app.use((err: any, _req: Request, res: Response, _next: NextFunction) => {
    const status = err.status || err.statusCode || 500;
    const message = err.message || "Internal Server Error";
    logger.error("Unhandled error", {
      data: { status, message, stack: err.stack },
    });
    res.status(status).json({ error: message, status: "error" });
  });

  // 鈹€鈹€ Periodic maintenance 鈹€鈹€
  setInterval(() => {
    const orphans = tracker.reapOrphans();
    if (orphans > 0) logger.debug("Reaped orphans", { data: { count: orphans } });
  }, cfg.orchestrator.pending_ttl * 100);

  setInterval(() => {
    const chunks = tracker.reapChunks();
    if (chunks > 0) logger.debug("Reaped chunk groups", { data: { count: chunks } });
  }, 15_000);

  // 鈹€鈹€ Start 鈹€鈹€
  server.listen(port, cfg.server.host, () => {
    logger.info("Master listening", { data: { port, tls: useTls } });
  });

  // 鈹€鈹€ Graceful shutdown 鈹€鈹€
  const shutdown = async (signal: string) => {
    logger.info("Shutting down", { data: { signal } });
    inspector.stop();
    // Drain in-flight requests before closing server.
    await tracker.drain(8000);
    server.close(() => {
      logger.info("Master stopped", { data: {} });
      process.exit(0);
    });
    setTimeout(() => process.exit(1), 10_000);
  };

  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));
}

main();


