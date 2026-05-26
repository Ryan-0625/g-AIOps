/**
 * ToolRegistry 鈥?闆嗙兢绾у姩鎬佸伐鍏风洰褰? *
 * 缁存姢鏁翠釜闆嗙兢涓墍鏈?Worker 涓婇儴缃茬殑鍔ㄦ€佸伐鍏锋竻鍗曘€? * Brain 鍜?Master 鍙€氳繃姝ゆā鍧楁煡璇㈠摢浜涘伐鍏峰湪鍝簺 Worker 涓婂彲鐢ㄣ€? */
import { createLogger } from "../logger";

const logger = createLogger("master");

export interface DynamicToolEntry {
  action: string;
  workerId: string;
  language: "bash" | "python3" | "node";
  riskLevel: string;
  deployedAt: number;
  state: "deployed" | "running" | "failed" | "uninstalled";
  version: number;
  codeHash: string;
  lastUsed: number;
  executeCount: number;
}

/**
 * Cluster-wide dynamic tool directory.
 *
 * Key structure: Map<action, Map<workerId, DynamicToolEntry>>
 * This allows quick lookups by action name across all workers.
 */
export class ToolRegistry {
  private tools = new Map<string, Map<string, DynamicToolEntry>>();

  /** Register a deployed dynamic tool on a specific worker. */
  register(
    workerId: string,
    action: string,
    meta: {
      language: "bash" | "python3" | "node";
      riskLevel: string;
      codeHash: string;
    },
  ): void {
    if (!this.tools.has(action)) {
      this.tools.set(action, new Map());
    }

    const byWorker = this.tools.get(action)!;
    const existing = byWorker.get(workerId);
    const version = (existing?.version || 0) + 1;

    byWorker.set(workerId, {
      action,
      workerId,
      language: meta.language,
      riskLevel: meta.riskLevel,
      deployedAt: Date.now(),
      state: "deployed",
      version,
      codeHash: meta.codeHash,
      lastUsed: Date.now(),
      executeCount: existing?.executeCount || 0,
    });

    logger.info("Dynamic tool registered", {
      action,
      data: { workerId, language: meta.language, version },
    });
  }

  /** Mark a tool as uninstalled (removed from worker). */
  unregister(workerId: string, action: string): boolean {
    const byWorker = this.tools.get(action);
    if (!byWorker) return false;

    const entry = byWorker.get(workerId);
    if (!entry) return false;

    entry.state = "uninstalled";
    byWorker.delete(workerId);

    if (byWorker.size === 0) {
      this.tools.delete(action);
    }

    logger.info("Dynamic tool unregistered", { action, data: { workerId } });
    return true;
  }

  /** Find all workers that have a specific dynamic tool. */
  findWorkersForAction(action: string): DynamicToolEntry[] {
    const byWorker = this.tools.get(action);
    if (!byWorker) return [];
    return Array.from(byWorker.values())
      .filter(e => e.state === "deployed" || e.state === "running");
  }

  /** Check if any worker has a specific dynamic tool deployed. */
  isDeployed(action: string): boolean {
    return this.findWorkersForAction(action).length > 0;
  }

  /** List all dynamic tools with their worker distribution. */
  listAll(): Record<string, DynamicToolEntry[]> {
    const result: Record<string, DynamicToolEntry[]> = {};
    for (const [action, byWorker] of this.tools) {
      result[action] = Array.from(byWorker.values())
        .filter(e => e.state === "deployed" || e.state === "running");
    }
    return result;
  }

  /** List all distinct dynamic tool actions across the cluster. */
  listActions(): string[] {
    return Array.from(this.tools.keys())
      .filter(action => {
        const byWorker = this.tools.get(action);
        return byWorker && Array.from(byWorker.values()).some(e => e.state === "deployed" || e.state === "running");
      });
  }

  /** Get execution stats for all dynamic tools. */
  getStats(): { totalTools: number; totalDeployments: number; actions: number } {
    let totalDeployments = 0;
    for (const byWorker of this.tools.values()) {
      for (const entry of byWorker.values()) {
        if (entry.state === "deployed" || entry.state === "running") totalDeployments++;
      }
    }
    return {
      totalTools: this.tools.size,
      totalDeployments,
      actions: this.listActions().length,
    };
  }

  /** Record a tool execution (update lastUsed and executeCount). */
  recordExecution(workerId: string, action: string): void {
    const byWorker = this.tools.get(action);
    if (!byWorker) return;
    const entry = byWorker.get(workerId);
    if (!entry) return;
    entry.lastUsed = Date.now();
    entry.executeCount++;
    entry.state = "deployed";
  }

  /** Clean up stale entries for a disconnected worker. */
  removeWorker(workerId: string): number {
    let count = 0;
    for (const [action, byWorker] of this.tools) {
      if (byWorker.has(workerId)) {
        byWorker.delete(workerId);
        count++;
        if (byWorker.size === 0) {
          this.tools.delete(action);
        }
      }
    }
    return count;
  }
}

