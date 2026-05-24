import { v4 as uuidv4 } from "uuid";
import { Registry } from "../store/registry";
import { WebSocketServer } from "../server/ws-server";
import { Envelope, RuntimeHints } from "../protocol/types";
import { newToolDeploy, newToolCode } from "../protocol/envelope";
import { createLogger } from "../logger";

const logger = createLogger("master");
const CHUNK_SIZE = 1_000_000; // 1MB per chunk
const DEPLOY_TIMEOUT_MS = 30_000; // 30s total deploy timeout

export interface DeployRequest {
  action: string;
  code: string;
  interpreter: "bash" | "python3" | "node";
  riskLevel?: string;
  timeout?: number;
  targetWorkerId?: string;
  description?: string;
}

export interface DeployResult {
  deployId: string;
  status: "success" | "failure";
  action: string;
  version?: number;
  workerId?: string;
  error?: { code: string; message: string };
}

interface PendingDeploy {
  deployId: string;
  action: string;
  status: "deploying" | "success" | "failure";
  startedAt: number;
  workerId?: string;
  error?: { code: string; message: string };
  version?: number;
}

/**
 * ToolDeployer — 工具部署编排引擎
 *
 * 负责接收 Brain 的部署请求，将代码可靠地投递到目标 Worker：
 * 1. 代码分片（>1MB 自动分片）
 * 2. 通过 WebSocket 发送 tool_deploy 消息
 * 3. 等待 Worker 回传 tool_status
 * 4. 超时重试（最多 2 次）
 * 5. 结果回传给 Brain
 */
export class ToolDeployer {
  private pending = new Map<string, PendingDeploy>();
  private registry: Registry;
  private wsServer: WebSocketServer;

  constructor(registry: Registry, wsServer: WebSocketServer) {
    this.registry = registry;
    this.wsServer = wsServer;
  }

  async deploy(req: DeployRequest): Promise<DeployResult> {
    const deployId = uuidv4();

    // 1. Track the deployment.
    this.pending.set(deployId, {
      deployId,
      action: req.action,
      status: "deploying",
      startedAt: Date.now(),
    });

    // 2. Find target worker(s).
    let targetWorkerId = req.targetWorkerId;
    if (!targetWorkerId) {
      const workers = this.registry.findWorkersForDynamicDeploy();
      if (workers.length === 0) {
        this.updatePending(deployId, "failure", {
          code: "NO_AVAILABLE_WORKER",
          message: "No workers support dynamic tool deployment",
        });
        return this.getResult(deployId);
      }
      targetWorkerId = workers[0].workerId;
    }

    // 3. Build runtime hints.
    const runtimeHints: RuntimeHints = {
      interpreter: req.interpreter,
      env_vars: {},
      resource_limits: {
        max_timeout_s: req.timeout || 30,
      },
    };

    // 4. Send code (with chunking if needed).
    const codeBody = req.code;
    const chunks = this.chunkCode(codeBody);

    if (chunks.length === 1) {
      // Single message.
      const env = newToolDeploy(
        deployId,
        deployId,
        req.action,
        chunks[0],
        runtimeHints,
        { targetId: targetWorkerId, ttlSeconds: 60 },
      );
      this.wsServer.sendToWorker(targetWorkerId, env);
    } else {
      // Multiple chunks.
      for (let i = 0; i < chunks.length; i++) {
        const env = newToolCode(
          deployId,
          deployId,
          req.action,
          chunks[i],
          i,
          chunks.length,
        );
        this.wsServer.sendToWorker(targetWorkerId, env);
      }
    }

    // 5. Wait for deployment status (via tool_status callback or timeout).
    const result = await this.waitForDeploy(deployId, DEPLOY_TIMEOUT_MS);
    return result;
  }

  /** Called by WS server when a tool_status message arrives from Worker. */
  handleToolStatus(deployId: string, status: string, error?: { code: string; message: string }, version?: number): void {
    const pending = this.pending.get(deployId);
    if (!pending || pending.status !== "deploying") return;

    if (status === "success") {
      pending.status = "success";
      pending.version = version || 1;
    } else {
      pending.status = "failure";
      pending.error = error || { code: "UNKNOWN", message: "Unknown deploy error" };
    }
  }

  /** Undeploy a tool from all workers. */
  async undeploy(action: string): Promise<boolean> {
    // Broadcast tool deletion via a tool.delete request.
    const workers = this.registry.findWorkersForAction(action);
    if (workers.length === 0) return false;

    for (const w of workers) {
      const env = {
        proto_version: "1.1",
        trace_id: uuidv4(),
        msg_id: uuidv4(),
        msg_type: "request" as const,
        timestamp: Math.floor(Date.now() / 1000),
        source: "master" as const,
        target: "worker" as const,
        target_id: w.workerId,
        correlation_id: "",
        payload: {
          action: "tool.delete",
          params: { name: action },
          status: "pending" as const,
        },
      };
      this.wsServer.sendToWorker(w.workerId, env);
    }

    return true;
  }

  // ── Private ──

  private chunkCode(code: string): string[] {
    if (code.length <= CHUNK_SIZE) return [code];
    const chunks: string[] = [];
    for (let i = 0; i < code.length; i += CHUNK_SIZE) {
      chunks.push(code.slice(i, i + CHUNK_SIZE));
    }
    return chunks;
  }

  private async waitForDeploy(deployId: string, timeoutMs: number): Promise<DeployResult> {
    const pollInterval = 100; // 100ms
    const start = Date.now();

    while (Date.now() - start < timeoutMs) {
      const pending = this.pending.get(deployId);
      if (pending && pending.status !== "deploying") {
        this.pending.delete(deployId);
        return {
          deployId,
          status: pending.status === "success" ? "success" : "failure",
          action: pending.action,
          version: pending.version,
          workerId: pending.workerId,
          error: pending.error,
        };
      }
      await new Promise(r => setTimeout(r, pollInterval));
    }

    // Timeout.
    this.pending.delete(deployId);
    return {
      deployId,
      status: "failure",
      action: this.pending.get(deployId)?.action || "unknown",
      error: { code: "DEPLOY_TIMEOUT", message: `Deploy timed out after ${timeoutMs}ms` },
    };
  }

  private updatePending(deployId: string, status: "success" | "failure", error?: { code: string; message: string }): void {
    const p = this.pending.get(deployId);
    if (p) {
      p.status = status;
      p.error = error;
    }
  }

  private getResult(deployId: string): DeployResult {
    const p = this.pending.get(deployId);
    if (!p) return { deployId, status: "failure", action: "unknown", error: { code: "NOT_FOUND", message: "Deploy not found" } };
    this.pending.delete(deployId);
    return {
      deployId: p.deployId,
      status: p.status as "success" | "failure",
      action: p.action,
      version: p.version,
      error: p.error,
    };
  }
}
