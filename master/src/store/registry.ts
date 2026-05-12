import { createLogger } from "../logger";

const logger = createLogger("master");

export interface WorkerCapability {
  actions: string[];
  riskLevels: Record<string, string>;
  timeouts: Record<string, number>;
  maxConcurrent: number;
  workerVersion: string;
  heartbeatInterval: number;
}

export interface WorkerNode {
  workerId: string;
  caps: WorkerCapability;
  currentLoad: number;
  lastSeen: number;
  connectedAt: number;
}

/**
 * Registry maintains the set of online Workers and their capabilities.
 * Workers register on connect via capability.advertise and are removed on
 * disconnect or heartbeat timeout.
 */
export class Registry {
  private workers = new Map<string, WorkerNode>();

  register(workerId: string, caps: WorkerCapability): void {
    const existing = this.workers.get(workerId);
    if (existing) {
      // Detect capability changes.
      const old = existing.caps.actions.sort().join(",");
      const next = caps.actions.sort().join(",");
      if (old !== next) {
        logger.info("Worker capabilities changed", {
          workerId,
          data: { old: existing.caps.actions, new: caps.actions },
        });
      }
    }

    this.workers.set(workerId, {
      workerId,
      caps,
      currentLoad: 0,
      lastSeen: Date.now(),
      connectedAt: Date.now(),
    });

    logger.info("Worker registered", {
      workerId,
      data: { actions: caps.actions.length, maxConcurrent: caps.maxConcurrent },
    });
  }

  markOffline(workerId: string, reason: string): void {
    this.workers.delete(workerId);
    logger.info("Worker removed", { workerId, data: { reason } });
  }

  updateLoad(workerId: string, load: number): void {
    const w = this.workers.get(workerId);
    if (w) {
      w.currentLoad = load;
      w.lastSeen = Date.now();
    }
  }

  /** Find the best Worker for a given action using least-loaded. */
  findWorker(action: string, preferWorkerId?: string): WorkerNode | null {
    const candidates: WorkerNode[] = [];
    for (const w of this.workers.values()) {
      if (w.caps.actions.includes(action) && w.currentLoad < w.caps.maxConcurrent) {
        candidates.push(w);
      }
    }
    if (candidates.length === 0) return null;

    // If preferred worker is available and has capacity.
    if (preferWorkerId) {
      const preferred = candidates.find((w) => w.workerId === preferWorkerId);
      if (preferred) return preferred;
    }

    // Least-loaded.
    candidates.sort((a, b) => a.currentLoad / a.caps.maxConcurrent - b.currentLoad / b.caps.maxConcurrent);
    return candidates[0];
  }

  /** Find all Workers that can handle an action (for broadcast). */
  findWorkersForAction(action: string): WorkerNode[] {
    const result: WorkerNode[] = [];
    for (const w of this.workers.values()) {
      if (w.caps.actions.includes(action) && w.currentLoad < w.caps.maxConcurrent) {
        result.push(w);
      }
    }
    return result;
  }

  isOnline(workerId: string): boolean {
    return this.workers.has(workerId);
  }

  onlineCount(): number {
    return this.workers.size;
  }

  /** List all registered workers (for Brain discovery). */
  listWorkers(): Array<{
    worker_id: string;
    actions: string[];
    risk_levels: Record<string, string>;
    max_concurrent: number;
    current_load: number;
    worker_version: string;
    uptime_seconds: number;
  }> {
    const now = Date.now();
    const result: Array<{
      worker_id: string;
      actions: string[];
      risk_levels: Record<string, string>;
      max_concurrent: number;
      current_load: number;
      worker_version: string;
      uptime_seconds: number;
    }> = [];
    for (const w of this.workers.values()) {
      result.push({
        worker_id: w.workerId,
        actions: w.caps.actions,
        risk_levels: w.caps.riskLevels,
        max_concurrent: w.caps.maxConcurrent,
        current_load: w.currentLoad,
        worker_version: w.caps.workerVersion,
        uptime_seconds: Math.floor((now - w.connectedAt) / 1000),
      });
    }
    return result;
  }

  /** Get risk level for a specific action.
   *
   * Returns "unknown" when no worker has advertised a risk level for this
   * action, so the Interceptor can apply its fallback high-risk list.
   */
  getRiskLevel(action: string): string {
    if (this.workers.size === 0) return "unknown";
    for (const w of this.workers.values()) {
      if (w.caps.riskLevels[action]) return w.caps.riskLevels[action];
    }
    return "readonly";
  }
}
