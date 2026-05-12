import { Router, Request, Response } from "express";
import rateLimit from "express-rate-limit";
import { v4 as uuidv4 } from "uuid";
import { extractBearer, authenticate } from "../security/authentikate";
import { Envelope, Payload, Status, ErrorInfo } from "../protocol/types";
import { validateEnvelope } from "../protocol/envelope";
import { PriorityQueue } from "../orchestrator/priority-queue";
import { Router as MasterRouter } from "../orchestrator/router";
import { Tracker } from "../orchestrator/tracker";
import { Summarizer, SummarizedResult } from "../orchestrator/summarizer";
import { Interceptor } from "../security/interceptor";
import { Approver } from "../security/approver";
import { Registry, WorkerNode } from "../store/registry";
import { writeAudit, writeAuditEvent } from "../security/audit";
import { createLogger } from "../logger";
import { WebSocketServer } from "./ws-server";
import { MetricsCollector } from "../store/metrics";

const logger = createLogger("master");

// ── Request/Response types ────────────────────────────────────────────

interface BrainRequest {
  action: string;
  params: Record<string, unknown>;
  trace_id: string;
  priority?: 0 | 1 | 2;
  ttl_seconds?: number;
  target_worker_id?: string;
}

interface BrainResponse {
  trace_id: string;
  msg_id: string;
  status: string;
  action: string;
  data?: Record<string, unknown>;
  truncated?: boolean;
  truncated_at?: number;
  error?: { code: string; message: string; raw?: string };
  summary?: SummarizedResult;
}

// ── Router factory ────────────────────────────────────────────────────

export function brainApiRouter(
  registry: Registry,
  queue: PriorityQueue,
  masterRouter: MasterRouter,
  tracker: Tracker,
  summarizer: Summarizer,
  interceptor: Interceptor,
  approver: Approver,
  wsServer: WebSocketServer,
  clusterToken: string,
  metricsCollector?: MetricsCollector,
): Router {
  const router = Router();

  // Rate limit: 120 req/min per Brain instance (configurable via RATE_LIMIT_MAX env).
  const rateLimitMax = parseInt(process.env.RATE_LIMIT_MAX || "120", 10);
  const limiter = rateLimit({
    windowMs: 60_000,
    max: rateLimitMax,
    message: { status: "failure", error: { code: "RATE_LIMITED", message: "Too many requests" } },
    handler: (req: Request, res: Response) => {
      writeAuditEvent({
        traceId: (req.body as BrainRequest)?.trace_id || "no-trace",
        msgId: "rate-limited",
        action: (req.body as BrainRequest)?.action || "unknown",
        source: "brain",
        target: "master",
        status: "rejected",
        errorCode: "RATE_LIMITED",
        reason: "rate-limit",
      });
      res.status(429).json({ status: "failure", error: { code: "RATE_LIMITED", message: "Too many requests" } });
    },
  });

  // ── Approval endpoints ──
  router.post("/api/v1/approve/:id", (req: Request, res: Response) => {
    const result = approver.approve(req.params.id);
    writeAuditEvent({
      traceId: "approval",
      msgId: req.params.id,
      action: "approve",
      source: "brain",
      target: "master",
      status: result.success ? "approved" : "rejected",
      reason: result.success
        ? result.workerStillOnline ? "approved" : "worker-offline"
        : "not-found-or-expired",
    });
    if (!result.success) {
      res.status(404).json({ status: "failure", error: { code: "APPROVAL_NOT_FOUND", message: "Approval request not found or expired" } });
      return;
    }
    res.json({ status: "success", message: "Approved", workerStillOnline: result.workerStillOnline });
  });

  router.post("/api/v1/reject/:id", (req: Request, res: Response) => {
    const ok = approver.reject(req.params.id);
    writeAuditEvent({
      traceId: "approval",
      msgId: req.params.id,
      action: "reject",
      source: "brain",
      target: "master",
      status: ok ? "rejected" : "not_found",
      reason: ok ? "rejected" : "not-found-or-expired",
    });
    if (!ok) {
      res.status(404).json({ status: "failure", error: { code: "APPROVAL_NOT_FOUND", message: "Approval request not found" } });
      return;
    }
    res.json({ status: "success", message: "Rejected" });
  });

  // ── Worker discovery ──
  router.get("/api/v1/workers", (req: Request, res: Response) => {
    const token = extractBearer(req.headers.authorization);
    if (!token || !authenticate(token, clusterToken)) {
      res.status(401).json({ status: "failure", error: { code: "AUTH_FAILED", message: "Invalid token" } });
      return;
    }
    const workers = registry.listWorkers();
    res.json({ workers });
  });

  // ── Result polling ──
  router.get("/api/v1/result/:msg_id", (req: Request, res: Response) => {
    const token = extractBearer(req.headers.authorization);
    if (!token || !authenticate(token, clusterToken)) {
      res.status(401).json({ status: "failure", error: { code: "AUTH_FAILED", message: "Invalid token" } });
      return;
    }

    const entry = tracker.getCompleted(req.params.msg_id);
    if (!entry) {
      res.status(404).json({ status: "failure", error: { code: "RESULT_NOT_FOUND", message: "Result not found or expired" } });
      return;
    }
    res.json(entry.response);
  });

  router.post("/api/v1/execute", limiter, (req: Request, res: Response) => {
    // ── Auth ──
    const token = extractBearer(req.headers.authorization);
    if (!token || !authenticate(token, clusterToken)) {
      writeAuditEvent({
        traceId: (req.body as BrainRequest)?.trace_id || "no-trace",
        msgId: "auth-failed",
        action: (req.body as BrainRequest)?.action || "unknown",
        source: "brain",
        target: "master",
        status: "rejected",
        errorCode: "AUTH_FAILED",
        reason: "auth-failure",
      });
      res.status(401).json({ status: "failure", error: { code: "AUTH_FAILED", message: "Invalid token" } });
      return;
    }

    // ── Parse ──
    const body = req.body as BrainRequest;
    if (!body.trace_id) {
      res.status(400).json({ status: "failure", error: { code: "MISSING_TRACE_ID", message: "trace_id is required" } });
      return;
    }
    if (!body.action) {
      res.status(400).json({ status: "failure", error: { code: "MISSING_ACTION", message: "action is required" } });
      return;
    }

    // ── Build envelope ──
    const msgId = uuidv4();
    const env: Envelope = {
      proto_version: "1.0",
      trace_id: body.trace_id,
      msg_id: msgId,
      msg_type: "request",
      timestamp: Math.floor(Date.now() / 1000),
      source: "brain",
      source_id: "brain",
      target: "worker",
      target_id: body.target_worker_id ?? "*",
      correlation_id: "",
      priority: body.priority ?? 0,
      ttl_seconds: body.ttl_seconds ?? 30,
      payload: {
        action: body.action,
        params: body.params,
        status: "pending",
      },
    };

    // Validate.
    const vErr = validateEnvelope(env);
    if (vErr.length > 0) {
      res.status(400).json({ status: "failure", error: { code: "INVALID_ENVELOPE", message: JSON.stringify(vErr) } });
      return;
    }

    // ── Security intercept ──
    const intercept = interceptor.intercept(body.action);
    if (intercept.requiresApproval) {
      // Route first to know target worker.
      const route = masterRouter.route(body.action, body.target_worker_id);
      if ("code" in route) {
        res.json({ trace_id: body.trace_id, msg_id: msgId, status: "failure", action: body.action, error: route });
        return;
      }

      const approval = approver.requestApproval(env, route.workerId);
      writeAudit(env, { approvalId: approval.id });

      logger.warn("Approval required — use POST /api/v1/approve/:id or /reject/:id", {
        msg_id: msgId,
        data: { action: body.action, approvalId: approval.id, workerId: route.workerId },
      });

      res.json({
        trace_id: body.trace_id,
        msg_id: msgId,
        status: "pending",
        action: body.action,
        data: { approval: "requested", approval_id: approval.id },
      });
      return;
    }

    // ── Route ──
    const route = masterRouter.route(body.action, body.target_worker_id);
    if ("code" in route) {
      res.json({
        trace_id: body.trace_id,
        msg_id: msgId,
        status: "failure",
        action: body.action,
        error: route,
      });
      return;
    }

    // ── Queue & forward ──
    env.source = "master";
    env.source_id = "master";
    queue.push(env);
    tracker.track(msgId, env, route.workerId);
    wsServer.sendToWorker(route.workerId, env);
    writeAudit(env);
    metricsCollector?.recordRequest("success", false);

    // ── Response ──
    const response: BrainResponse = {
      trace_id: body.trace_id,
      msg_id: msgId,
      status: "pending",
      action: body.action,
    };
    res.json(response);
  });

  return router;
}
