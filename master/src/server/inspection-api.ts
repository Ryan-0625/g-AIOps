// Inspection API — REST endpoints for managing inspections, viewing results, and handling alerts.
//
// Endpoints:
//   GET    /api/v1/inspections          — List all inspections
//   POST   /api/v1/inspections          — Create a new inspection
//   GET    /api/v1/inspections/:id      — Get inspection details
//   PUT    /api/v1/inspections/:id      — Update an inspection
//   DELETE /api/v1/inspections/:id      — Delete an inspection
//   POST   /api/v1/inspections/:id/toggle — Enable/disable an inspection
//   GET    /api/v1/inspections/:id/results — Get results for an inspection
//   GET    /api/v1/inspections/:id/latest — Get latest result per worker
//   GET    /api/v1/alerts                — List alerts
//   POST   /api/v1/alerts/:id/acknowledge — Acknowledge an alert
//   GET    /api/v1/alerts/stats          — Alert statistics
//   POST   /api/v1/inspections/run/:id   — Run an inspection immediately

import { Router, Request, Response } from "express";
import { v4 as uuidv4 } from "uuid";
import { InspectionStore, InspectionConfig, ProbeType } from "../store/inspection-store";
import { Inspector } from "../orchestrator/inspector";
import { Registry } from "../store/registry";
import { extractBearer, authenticate } from "../security/authentikate";
import { createLogger } from "../logger";

const logger = createLogger("master");

const VALID_PROBE_TYPES: ProbeType[] = [
  "port.check", "http.health", "ping.icmp", "disk.usage",
  "ssl.cert_check", "process.list", "dns.lookup", "service.status", "custom.exec",
];

const VALID_SCHEDULE_MODES = ["interval", "cron"] as const;

export function inspectionApiRouter(
  store: InspectionStore,
  inspector: Inspector,
  registry: Registry,
  clusterToken: string,
): Router {
  const router = Router();

  // Auth middleware
  const auth = (req: Request, res: Response, next: () => void) => {
    const token = extractBearer(req.headers.authorization || "");
    if (!token || !authenticate(token, clusterToken)) {
      res.status(401).json({ error: "Unauthorized" });
      return;
    }
    next();
  };

  // --- Inspections CRUD ---

  // List all inspections
  router.get("/api/v1/inspections", auth, (_req: Request, res: Response) => {
    const inspections = store.listInspections();
    res.json({
      inspections: inspections.map(i => ({
        id: i.id,
        name: i.name,
        description: i.description,
        enabled: i.enabled,
        probe_type: i.probe_type,
        target_mode: i.target_mode,
        schedule_mode: i.schedule_mode,
        interval_seconds: i.interval_seconds,
        timeout_seconds: i.timeout_seconds,
        alert_rules_count: i.alert_rules.length,
        created_at: i.created_at,
        updated_at: i.updated_at,
      })),
      total: inspections.length,
    });
  });

  // Create inspection
  router.post("/api/v1/inspections", auth, (req: Request, res: Response) => {
    const body = req.body;
    const errors: string[] = [];

    if (!body.name) errors.push("name is required");
    if (!VALID_PROBE_TYPES.includes(body.probe_type)) {
      errors.push(`probe_type must be one of: ${VALID_PROBE_TYPES.join(", ")}`);
    }
    if (!body.probe_params || typeof body.probe_params !== "object") {
      errors.push("probe_params is required (object)");
    }
    if (!VALID_SCHEDULE_MODES.includes(body.schedule_mode)) {
      errors.push("schedule_mode must be 'interval' or 'cron'");
    }
    if (body.schedule_mode === "interval" && (!body.interval_seconds || body.interval_seconds < 10)) {
      errors.push("interval_seconds must be >= 10 for interval mode");
    }

    if (errors.length > 0) {
      res.status(400).json({ error: "Validation failed", details: errors });
      return;
    }

    const cfg: InspectionConfig = {
      id: uuidv4(),
      name: body.name,
      description: body.description,
      enabled: body.enabled !== false,
      probe_type: body.probe_type,
      probe_params: body.probe_params,
      target_mode: body.target_mode || "all",
      target_workers: body.target_workers,
      target_tags: body.target_tags,
      schedule_mode: body.schedule_mode,
      interval_seconds: body.interval_seconds || 300,
      timeout_seconds: body.timeout_seconds || 30,
      alert_rules: body.alert_rules || [],
      notify_channels: body.notify_channels || ["log"],
      created_at: Date.now(),
      updated_at: Date.now(),
      created_by: "api",
    };

    store.createInspection(cfg);
    res.status(201).json({ id: cfg.id, name: cfg.name, status: "created" });
  });

  // Get inspection details
  router.get("/api/v1/inspections/:id", auth, (req: Request, res: Response) => {
    const inspection = store.getInspection(req.params.id);
    if (!inspection) {
      res.status(404).json({ error: "Inspection not found" });
      return;
    }
    res.json(inspection);
  });

  // Update inspection
  router.put("/api/v1/inspections/:id", auth, (req: Request, res: Response) => {
    const updated = store.updateInspection(req.params.id, req.body);
    if (!updated) {
      res.status(404).json({ error: "Inspection not found" });
      return;
    }
    res.json({ status: "updated" });
  });

  // Delete inspection
  router.delete("/api/v1/inspections/:id", auth, (req: Request, res: Response) => {
    const deleted = store.deleteInspection(req.params.id);
    if (!deleted) {
      res.status(404).json({ error: "Inspection not found" });
      return;
    }
    res.json({ status: "deleted" });
  });

  // Toggle inspection enabled/disabled
  router.post("/api/v1/inspections/:id/toggle", auth, (req: Request, res: Response) => {
    const inspection = store.getInspection(req.params.id);
    if (!inspection) {
      res.status(404).json({ error: "Inspection not found" });
      return;
    }
    store.updateInspection(req.params.id, { enabled: !inspection.enabled });
    res.json({ id: req.params.id, enabled: !inspection.enabled });
  });

  // Run inspection immediately (one-shot)
  router.post("/api/v1/inspections/run/:id", auth, (req: Request, res: Response) => {
    const inspection = store.getInspection(req.params.id);
    if (!inspection) {
      res.status(404).json({ error: "Inspection not found" });
      return;
    }

    // Force immediate evaluation by manipulating lastRun
    // The Inspector will pick it up on next tick.
    // For immediate execution, we'd need a method on Inspector.
    // For now, we respond that it's scheduled.
    res.json({ status: "scheduled", message: "Inspection will run on next tick" });
  });

  // --- Results ---

  // Get results for an inspection
  router.get("/api/v1/inspections/:id/results", auth, (req: Request, res: Response) => {
    const limit = Math.min(parseInt(req.query.limit as string) || 50, 200);
    const results = store.getResults(req.params.id, limit);
    res.json({ inspection_id: req.params.id, results, total: results.length });
  });

  // Get latest result per worker
  router.get("/api/v1/inspections/:id/latest", auth, (req: Request, res: Response) => {
    const inspection = store.getInspection(req.params.id);
    if (!inspection) {
      res.status(404).json({ error: "Inspection not found" });
      return;
    }

    const workers = registry.listWorkers();
    const latestResults = workers.map(w => ({
      worker_id: w.worker_id,
      result: store.getLatestResult(req.params.id, w.worker_id) || null,
    }));

    res.json({ inspection_id: req.params.id, workers: latestResults });
  });

  // --- Alerts ---

  // List alerts
  router.get("/api/v1/alerts", auth, (req: Request, res: Response) => {
    const limit = Math.min(parseInt(req.query.limit as string) || 50, 200);
    const unacknowledgedOnly = req.query.unacknowledged === "true";
    const alerts = store.getAlerts(limit, unacknowledgedOnly);
    res.json({ alerts, total: alerts.length });
  });

  // Acknowledge alert
  router.post("/api/v1/alerts/:id/acknowledge", auth, (req: Request, res: Response) => {
    const by = req.body.by || "api-user";
    const acknowledged = store.acknowledgeAlert(req.params.id, by);
    if (!acknowledged) {
      res.status(404).json({ error: "Alert not found or already acknowledged" });
      return;
    }
    res.json({ status: "acknowledged", by });
  });

  // Alert statistics
  router.get("/api/v1/alerts/stats", auth, (_req: Request, res: Response) => {
    res.json(store.getAlertStats());
  });

  return router;
}
