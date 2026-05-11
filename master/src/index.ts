import express from "express";
import http from "http";
import https from "https";
import fs from "fs";
import { load as loadConfig } from "./config";
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

const logger = createLogger("master");
const cfg = loadConfig();

// TLS config (consumed directly from env for cert file paths)
const TLS_CERT = process.env.TLS_CERT_PATH;
const TLS_KEY = process.env.TLS_KEY_PATH;
const useTls = !!(TLS_CERT && TLS_KEY);

function main(): void {
  const port = useTls ? cfg.server.api_port : cfg.server.ws_port;
  logger.info("Master starting", { data: { port } });

  // ── Store ──
  const registry = new Registry();
  const tracker = new Tracker();
  const queue = new PriorityQueue();
  const metricsCollector = new MetricsCollector();

  // ── Audit ──
  configureAudit({
    logPath: cfg.audit.log_path || undefined,
    enabled: cfg.audit.enabled,
  });

  // ── Orchestrator ──
  const masterRouter = new Router(registry);
  const summarizer = new Summarizer();

  // ── Security ──
  const interceptor = new Interceptor(registry, cfg.security.high_risk_actions);
  const approver = new Approver(registry, (req) => {
    logger.warn("Approval rejected or expired", {
      msg_id: req.id,
      data: { action: req.envelope.payload.action, status: req.status },
    });
  });

  // ── Server ──
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

  // ── Routes ──
  app.use(healthRouter(registry, tracker, approver));
  app.use(metricsRouter(registry, tracker, queue, approver, metricsCollector));
  app.use(brainApiRouter(registry, queue, masterRouter, tracker, summarizer, interceptor, approver, wsServer, cfg.cluster_token, metricsCollector));
  app.use(traceRouter(tracker));

  // ── Periodic maintenance ──
  setInterval(() => {
    const orphans = tracker.reapOrphans();
    if (orphans > 0) logger.debug("Reaped orphans", { data: { count: orphans } });
  }, cfg.orchestrator.pending_ttl * 100);

  setInterval(() => {
    const chunks = tracker.reapChunks();
    if (chunks > 0) logger.debug("Reaped chunk groups", { data: { count: chunks } });
  }, 15_000);

  // ── Start ──
  server.listen(port, cfg.server.host, () => {
    logger.info("Master listening", { data: { port, tls: useTls } });
  });

  // ── Graceful shutdown ──
  const shutdown = (signal: string) => {
    logger.info("Shutting down", { data: { signal } });
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
