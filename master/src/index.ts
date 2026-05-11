import express from "express";
import http from "http";
import https from "https";
import fs from "fs";
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
import { createLogger } from "./logger";
import { configureAudit } from "./security/audit";

const logger = createLogger("master");
const PORT = parseInt(process.env.MASTER_PORT || "8080", 10);
const CLUSTER_TOKEN = process.env.CLUSTER_TOKEN || "dev-token-change-in-production";

// TLS config
const TLS_CERT = process.env.TLS_CERT_PATH;
const TLS_KEY = process.env.TLS_KEY_PATH;
const useTls = !!(TLS_CERT && TLS_KEY);

function main(): void {
  logger.info("Master starting", { data: { port: PORT } });

  // ── Store ──
  const registry = new Registry();
  const tracker = new Tracker();
  const queue = new PriorityQueue();

  // ── Audit ──
  configureAudit({
    logPath: process.env.AUDIT_LOG_PATH || undefined,
    enabled: process.env.AUDIT_ENABLED !== "false",
  });

  // ── Orchestrator ──
  const masterRouter = new Router(registry);
  const summarizer = new Summarizer();

  // ── Security ──
  const interceptor = new Interceptor(registry);
  const approver = new Approver(registry, (req) => {
    logger.warn("Approval rejected or expired", {
      msg_id: req.id,
      data: { action: req.envelope.payload.action, status: req.status },
    });
  });

  // ── Server ──
  const app = express();
  app.use(express.json({ limit: "5mb" }));

  const server = useTls
    ? https.createServer(
        { cert: fs.readFileSync(TLS_CERT!), key: fs.readFileSync(TLS_KEY!) },
        app,
      )
    : http.createServer(app);

  const wsServer = new WebSocketServer(registry, tracker, masterRouter, queue, CLUSTER_TOKEN);
  wsServer.attach(server);

  // ── Routes ──
  app.use(healthRouter(registry, tracker, approver));
  app.use(brainApiRouter(registry, queue, masterRouter, tracker, summarizer, interceptor, approver, wsServer, CLUSTER_TOKEN));

  // ── Periodic maintenance ──
  setInterval(() => {
    const orphans = tracker.reapOrphans();
    if (orphans > 0) logger.debug("Reaped orphans", { data: { count: orphans } });
  }, 30_000);

  setInterval(() => {
    const chunks = tracker.reapChunks();
    if (chunks > 0) logger.debug("Reaped chunk groups", { data: { count: chunks } });
  }, 15_000);

  // ── Start ──
  server.listen(PORT, "0.0.0.0", () => {
    logger.info("Master listening", { data: { port: PORT, tls: useTls } });
  });

  // ── Graceful shutdown ──
  const shutdown = (signal: string) => {
    logger.info("Shutting down", { data: { signal } });
    server.close(() => {
      logger.info("Master stopped", { data: {} });
      process.exit(0);
    });
    // Force exit after 10s
    setTimeout(() => process.exit(1), 10_000);
  };

  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));
}

main();
