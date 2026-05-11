import { Registry, WorkerNode } from "../store/registry";
import { createLogger } from "../logger";

const logger = createLogger("master");

export interface RouteResult {
  workerId: string;
  worker: WorkerNode;
}

export interface RouteError {
  code: string;
  message: string;
}

/**
 * Router selects the optimal Worker for a given action.
 *
 * Selection criteria (in order):
 * 1. Action must be in Worker's capability list.
 * 2. Worker must have spare capacity (currentLoad < maxConcurrent).
 * 3. If Brain specified a preferred worker, use it (if capable and has capacity).
 * 4. Otherwise, least-loaded among candidates.
 */
export class Router {
  constructor(private registry: Registry) {}

  route(action: string, preferWorkerId?: string): RouteResult | RouteError {
    const worker = this.registry.findWorker(action, preferWorkerId);
    if (!worker) {
      // Check if any Worker is registered at all.
      if (this.registry.onlineCount() === 0) {
        return { code: "NO_AVAILABLE_WORKER", message: "No workers connected" };
      }

      // Check if any Worker supports this action.
      return {
        code: "NO_AVAILABLE_WORKER",
        message: `No worker available for action: ${action}`,
      };
    }

    return { workerId: worker.workerId, worker };
  }

  /** For broadcast: get all capable workers. */
  routeBroadcast(action: string): WorkerNode[] {
    const workers = this.registry.findWorkersForAction(action);
    if (workers.length === 0) {
      logger.warn("Broadcast found no workers", { action });
    }
    return workers;
  }
}
