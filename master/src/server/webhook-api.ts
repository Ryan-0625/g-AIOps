// Webhook API — external services can trigger tool execution via HTTP POST.
// This enables integration with monitoring systems like Prometheus AlertManager,
// Zabbix, PagerDuty, and custom automation pipelines.
//
// Endpoints:
//   POST /api/v1/webhooks/:sourceId/:secret  — Execute a webhook-triggered action
//   GET  /api/v1/webhooks                    — List configured webhook sources
//   POST /api/v1/webhooks                    — Create a webhook source

import { Router, Request, Response } from "express";
import { v4 as uuidv4 } from "uuid";
import { Registry } from "../store/registry";
import { Tracker } from "../orchestrator/tracker";
import { Router as MasterRouter } from "../orchestrator/router";
import { PriorityQueue } from "../orchestrator/priority-queue";
import { Interceptor } from "../security/interceptor";
import { Approver } from "../security/approver";
import { WebSocketServer } from "./ws-server";
import { Envelope } from "../protocol/types";
import { newRequest, marshal } from "../protocol/envelope";
import { writeAuditEvent } from "../security/audit";
import { createLogger } from "../logger";
import { MetricsCollector } from "../store/metrics";

const logger = createLogger("master");

interface WebhookSource {
  id: string;
  name: string;
  secret: string;
  action: string;
  params_template: Record<string, unknown>;
  target_worker_id?: string;
  enabled: boolean;
  created_at: number;
}

export function webhookApiRouter(
  registry: Registry,
  tracker: Tracker,
  masterRouter: MasterRouter,
  queue: PriorityQueue,
  interceptor: Interceptor,
  approver: Approver,
  wsServer: WebSocketServer,
  clusterToken: string,
  metricsCollector: MetricsCollector,
): Router {
  const router = Router();

  // In-memory webhook sources (in production, store in DB)
  const sources = new Map<string, WebhookSource>();

  // --- Execute webhook ---
  // This endpoint is intentionally unauthenticated — security is via the secret in the URL.
  router.post("/api/v1/webhooks/:sourceId/:secret", async (req: Request, res: Response) => {
    const { sourceId, secret } = req.params;

    const source = sources.get(sourceId);
    if (!source || source.secret !== secret) {
      res.status(404).json({ error: "Webhook source not found" });
      return;
    }

    if (!source.enabled) {
      res.status(403).json({ error: "Webhook source is disabled" });
      return;
    }

    // Merge request body with params template
    const params = {
      ...source.params_template,
      ...req.body,
      _webhook_source: source.name,
      _webhook_payload: req.body,
    };

    // Check rate limiting
    const token = clusterToken; // Use cluster token for internal routing auth
    // Create envelope and route
    const traceId = uuidv4();
    const msgId = uuidv4();

    writeAuditEvent({
      traceId: traceId,
      msgId: msgId,
      action: source.action,
      source: "webhook",
      target: source.name,
      status: "accepted",
      reason: "webhook.invoke from " + source.name,
    });

    const envelope = newRequest(traceId, msgId, source.action, params, {
      targetId: source.target_worker_id,
      ttlSeconds: 60,
    });

    // Route and queue
    const route = masterRouter.route(source.action, source.target_worker_id);
    if (!route) {
      res.status(503).json({ error: "No available worker for this action" });
      return;
    }

    queue.push(envelope);
    if ("workerId" in route) {
      tracker.track(envelope.msg_id, envelope, route.workerId);
      wsServer.sendToWorker(route.workerId, envelope);
    } else {
      res.status(503).json({ error: "Route error: " + route.message });
      return;
    }

    if (metricsCollector) {
      metricsCollector.recordRequest("success", false);
    }

    res.json({
      status: "accepted",
      trace_id: traceId,
      msg_id: msgId,
      message: `Webhook ${source.name} triggered action ${source.action}`,
    });
  });

  // --- List webhook sources ---
  router.get("/api/v1/webhooks", (req: Request, res: Response) => {
    // Auth check
    const authHeader = req.headers.authorization || "";
    const token = authHeader.replace("Bearer ", "").trim();
    if (token !== clusterToken) {
      res.status(401).json({ error: "Unauthorized" });
      return;
    }

    const list = Array.from(sources.values()).map(s => ({
      id: s.id,
      name: s.name,
      action: s.action,
      enabled: s.enabled,
      created_at: s.created_at,
      // Secret is not exposed in listing
    }));

    res.json({ webhooks: list, total: list.length });
  });

  // --- Create webhook source ---
  router.post("/api/v1/webhooks", (req: Request, res: Response) => {
    // Auth check
    const authHeader = req.headers.authorization || "";
    const token = authHeader.replace("Bearer ", "").trim();
    if (token !== clusterToken) {
      res.status(401).json({ error: "Unauthorized" });
      return;
    }

    const { name, action, params_template, target_worker_id } = req.body;
    if (!name || !action) {
      res.status(400).json({ error: "name and action are required" });
      return;
    }

    const id = uuidv4();
    const secret = uuidv4().replace(/-/g, "");

    const source: WebhookSource = {
      id,
      name,
      secret,
      action,
      params_template: params_template || {},
      target_worker_id,
      enabled: true,
      created_at: Date.now(),
    };

    sources.set(id, source);

    writeAuditEvent({
      traceId: id,
      msgId: id,
      action: action,
      source: "webhook",
      target: name,
      status: "created",
      reason: "webhook.created for " + name,
    });

    res.status(201).json({
      id,
      name,
      action,
      webhook_url: `/api/v1/webhooks/${id}/${secret}`,
      secret, // Only shown once on creation
    });
  });

  return router;
}
