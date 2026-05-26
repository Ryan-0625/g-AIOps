// Inspector — the heart of the inspection system.
// Schedules periodic inspections, dispatches probe requests to Workers,
// collects results, evaluates alert rules, and triggers notifications.
//
// Architecture:
//   Inspector
//   ├── Scheduler (setInterval-based tick loop)
//   ├── Probe Dispatcher (sends requests via WebSocket)
//   ├── Result Collector (processes responses)
//   ├── Alert Evaluator (threshold checking)
//   └── Notification Dispatcher (webhook, log, future: IM)

import { v4 as uuidv4 } from "uuid";
import {
  InspectionStore,
  InspectionConfig,
  InspectionResult,
  AlertEvalResult,
  ProbeType,
} from "../store/inspection-store";
import { Registry } from "../store/registry";
import { Envelope } from "../protocol/types";
import { newRequest, marshal } from "../protocol/envelope";
import { WebSocketServer } from "../server/ws-server";
import { createLogger } from "../logger";

const logger = createLogger("master");

// Map probe types to worker actions
const PROBE_ACTION_MAP: Record<ProbeType, string> = {
  "port.check": "port.check",
  "http.health": "http.get",
  "ping.icmp": "ping.icmp",
  "disk.usage": "disk.usage",
  "ssl.cert_check": "ssl.cert_check",
  "process.list": "process.list",
  "dns.lookup": "dns.lookup",
  "service.status": "service.status",
  "custom.exec": "exec.run",
};

interface PendingProbe {
  inspectionId: string;
  workerId: string;
  timestamp: number;
  envelope: Envelope;
}

export class Inspector {
  private store: InspectionStore;
  private registry: Registry;
  private wsServer: WebSocketServer;
  private tickTimer: ReturnType<typeof setInterval> | null = null;
  private pendingProbes = new Map<string, PendingProbe>(); // msg_id -> probe
  private lastTick: number = 0;

  // Track last execution per inspection for interval scheduling
  private lastRun = new Map<string, number>();

  constructor(
    store: InspectionStore,
    registry: Registry,
    wsServer: WebSocketServer,
  ) {
    this.store = store;
    this.registry = registry;
    this.wsServer = wsServer;
  }

  // --- Lifecycle ---

  start(tickIntervalMs = 10000): void {
    this.lastTick = Date.now();
    this.tickTimer = setInterval(() => this.tick(), tickIntervalMs);
    logger.info("Inspector started", { data: { tickIntervalMs } });
  }

  stop(): void {
    if (this.tickTimer) {
      clearInterval(this.tickTimer);
      this.tickTimer = null;
    }
    logger.info("Inspector stopped");
  }

  // --- Tick: evaluate all inspections ---

  private tick(): void {
    const now = Date.now();
    const inspections = this.store.listInspections(true); // enabled only

    for (const inspection of inspections) {
      this.evaluateInspection(inspection, now);
    }

    // Clean up stale pending probes
    this.cleanupStaleProbes(now);
  }

  private evaluateInspection(inspection: InspectionConfig, now: number): void {
    // Check if it's time to run
    if (inspection.schedule_mode === "interval") {
      const interval = (inspection.interval_seconds ?? 60) * 1000;
      const lastRun = this.lastRun.get(inspection.id) || 0;
      if (now - lastRun < interval) return;
    }

    // Determine target workers
    const workers = this.resolveTargetWorkers(inspection);
    if (workers.length === 0) {
      logger.debug("No workers for inspection", { data: { id: inspection.id } });
      return;
    }

    this.lastRun.set(inspection.id, now);

    // Dispatch probe to each worker
    for (const worker of workers) {
      this.dispatchProbe(inspection, worker.workerId, now);
    }
  }

  private resolveTargetWorkers(inspection: InspectionConfig) {
    switch (inspection.target_mode) {
      case "all":
        return this.registry.listWorkers().map(w => ({
          workerId: w.worker_id,
        }));
      case "worker_ids":
        return (inspection.target_workers || [])
          .map(id => ({ workerId: id }))
          .filter(w => this.registry.isOnline(w.workerId));
      case "tags":
        // Tags not yet implemented in registry — fallback to all
        return this.registry.listWorkers().map(w => ({
          workerId: w.worker_id,
        }));
      default:
        return [];
    }
  }

  private dispatchProbe(inspection: InspectionConfig, workerId: string, now: number): void {
    const action = PROBE_ACTION_MAP[inspection.probe_type] || inspection.probe_type;

    // Map probe params appropriately
    const params = this.mapProbeParams(inspection);

    const env = newRequest(
      uuidv4(),
      uuidv4(),
      action,
      params,
      {
        targetId: workerId,
        priority: 0,
        ttlSeconds: inspection.timeout_seconds || 30,
      },
    );

    // Track pending probe
    this.pendingProbes.set(env.msg_id, {
      inspectionId: inspection.id,
      workerId,
      timestamp: now,
      envelope: env,
    });

    // Send via WebSocket
    this.wsServer.sendToWorker(workerId, env);
  }

  private mapProbeParams(inspection: InspectionConfig): Record<string, unknown> {
    const params = { ...inspection.probe_params };

    // Add type-specific defaults
    switch (inspection.probe_type) {
      case "http.health":
        params.timeout_seconds = inspection.timeout_seconds || 10;
        // http.get already handles this via params.url
        break;
      case "port.check":
        params.timeout_seconds = inspection.timeout_seconds || 5;
        break;
      case "ping.icmp":
        params.count = params.count || 2;
        break;
      case "ssl.cert_check":
        params.timeout_seconds = inspection.timeout_seconds || 10;
        break;
    }
    return params;
  }

  // --- Handle probe response from Worker ---

  handleProbeResponse(envelope: Envelope): void {
    const probe = this.pendingProbes.get(envelope.correlation_id || "");
    if (!probe) return; // Might be a delayed response for an already-processed probe

    this.pendingProbes.delete(envelope.correlation_id || "");

    const inspection = this.store.getInspection(probe.inspectionId);
    if (!inspection) return;

    const result: InspectionResult = {
      id: envelope.msg_id,
      inspection_id: inspection.id,
      worker_id: probe.workerId,
      timestamp: Date.now(),
      duration_ms: (Date.now() - probe.timestamp),
      probe_type: inspection.probe_type,
      probe_params: inspection.probe_params,
      success: envelope.payload.status === "success",
      error: envelope.payload.error?.message,
      data: envelope.payload.data || {},
      alerts_triggered: [],
      status: "pass",
    };

    // Evaluate alert rules
    if (envelope.payload.status === "success") {
      result.alerts_triggered = this.store.evaluateAlerts(
        inspection,
        probe.workerId,
        result.data,
        result.id,
      );

      const hasAlerts = result.alerts_triggered.some(a => a.triggered);
      result.status = hasAlerts ? "fail" : "pass";
    } else {
      result.status = "error";
    }

    this.store.storeResult(result);

    logger.info("Inspection result", {
      data: {
        inspection: inspection.name,
        worker: probe.workerId,
        status: result.status,
        alerts: result.alerts_triggered.filter(a => a.triggered).length,
        duration_ms: result.duration_ms,
      },
    });
  }

  // --- Cleanup ---

  private cleanupStaleProbes(now: number): void {
    const staleTimeout = 60000; // 60 seconds
    for (const [msgId, probe] of this.pendingProbes) {
      if (now - probe.timestamp > staleTimeout) {
        this.pendingProbes.delete(msgId);
        logger.debug("Stale probe cleaned up", {
          data: { inspectionId: probe.inspectionId, workerId: probe.workerId },
        });
      }
    }
  }

  // --- Utility ---

  getPendingCount(): number {
    return this.pendingProbes.size;
  }

  getActiveInspectionsCount(): number {
    return this.store.listInspections(true).length;
  }
}
