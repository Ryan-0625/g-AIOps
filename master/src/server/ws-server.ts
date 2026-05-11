import { WebSocketServer as WSS, WebSocket } from "ws";
import { IncomingMessage } from "http";
import { v4 as uuidv4 } from "uuid";
import { Envelope } from "../protocol/types";
import { unmarshal, marshal } from "../protocol/envelope";
import { negotiate, VersionRange } from "../protocol/version";
import { extractBearer, authenticate } from "../security/authentikate";
import { Registry, WorkerCapability } from "../store/registry";
import { Tracker } from "../orchestrator/tracker";
import { Router } from "../orchestrator/router";
import { PriorityQueue } from "../orchestrator/priority-queue";
import { SlidingWindowRateLimiter } from "./flow-control";
import { createLogger } from "../logger";

const logger = createLogger("master");

const LOCAL_VERSION_RANGE: VersionRange = { min: "1.0", max: "1.0" };

// Rate limiter for incoming connections (anti-thundering-herd).
class ConnRateLimiter {
  private tokens: number;
  private lastRefill: number;

  constructor(private maxPerSecond: number) {
    this.tokens = maxPerSecond;
    this.lastRefill = Date.now();
  }

  tryAcquire(): boolean {
    this.refill();
    if (this.tokens > 0) {
      this.tokens--;
      return true;
    }
    return false;
  }

  private refill(): void {
    const now = Date.now();
    const elapsed = (now - this.lastRefill) / 1000;
    this.tokens = Math.min(this.maxPerSecond, this.tokens + elapsed * this.maxPerSecond);
    this.lastRefill = now;
  }
}

interface WorkerSocket {
  ws: WebSocket;
  workerId: string;
  lastPong: number;
}

export class WebSocketServer {
  private wss: WSS | null = null;
  private connections = new Map<string, WorkerSocket>();
  private rateLimiter: ConnRateLimiter;
  private flowControl = new SlidingWindowRateLimiter(1000, 100); // 100 msg/s per worker
  private readonly PONG_TIMEOUT_MS = 60_000; // 60s no pong → zombie

  constructor(
    private registry: Registry,
    private tracker: Tracker,
    private router: Router,
    private queue: PriorityQueue,
    private clusterToken: string,
    wsConfig?: { max_connections: number; connection_rate_limit: number; heartbeat_check_interval: number },
  ) {
    this.rateLimiter = new ConnRateLimiter(wsConfig?.connection_rate_limit ?? 50);
  }

  attach(server: import("http").Server): void {
    this.wss = new WSS({ server });

    this.wss.on("connection", (ws: WebSocket, req: IncomingMessage) => {
      // Rate limit.
      if (!this.rateLimiter.tryAcquire()) {
        ws.close(1013, "rate limited");
        return;
      }

      // Authenticate.
      const token = extractBearer(req.headers.authorization);
      if (!token || !authenticate(token, this.clusterToken)) {
        ws.close(4001, "AUTH_FAILED");
        return;
      }

      // Version negotiation - expect a version.advertise as first message.
      let versionNegotiated = false;

      ws.on("message", (raw: Buffer) => {
        const text = raw.toString("utf-8");
        let env: Envelope;
        try {
          env = unmarshal(text);
        } catch {
          ws.send(marshal(errorEnvelope("", "", "INVALID_ENVELOPE", "Failed to parse JSON")));
          return;
        }

        // First message must be capability.advertise.
        if (!versionNegotiated) {
          if (env.payload.action !== "capability.advertise") {
            ws.close(4002, "Expected capability.advertise first");
            return;
          }
          versionNegotiated = true;

          const workerId = env.source_id || env.payload.params?.worker_id as string || uuidv4();
          this.handleCapabilityAdvertise(ws, workerId, env);
          return;
        }

        // Sliding-window flow control — drop if worker exceeds limit.
        const wsEntry = findEntry(this.connections, ws);
        const wid = wsEntry?.workerId;
        if (wid && !this.flowControl.allow(wid)) {
          logger.warn("Worker rate limited", {
            msg_id: env.msg_id,
            data: { workerId: wid, action: env.payload.action },
          });
          return;
        }

        // Route incoming messages.
        switch (env.msg_type) {
          case "heartbeat":
          case "ack":
            break; // no-op, pong tracked via ws "pong" event
          case "response":
            this.handleWorkerResponse(env);
            break;
          case "event":
            this.handleWorkerEvent(env);
            break;
        }
      });

      ws.on("pong", () => {
        const entry = findEntry(this.connections, ws);
        if (entry) entry.lastPong = Date.now();
      });

      ws.on("close", () => {
        const entry = findEntry(this.connections, ws);
        if (entry) {
          this.connections.delete(entry.workerId);
          this.flowControl.reset(entry.workerId);
          this.registry.markOffline(entry.workerId, "disconnect");
          logger.info("Worker disconnected", { msg_id: "", data: { workerId: entry.workerId } });
        }
      });

      ws.on("error", (err) => {
        logger.error("WebSocket error", { data: { error: err.message } });
      });
    });

    // Zombie reaper (every 30s).
    setInterval(() => this.reapZombies(), 30_000);
  }

  /** Send an envelope to a specific worker. */
  sendToWorker(workerId: string, env: Envelope): boolean {
    const conn = this.connections.get(workerId);
    if (!conn || conn.ws.readyState !== WebSocket.OPEN) return false;
    conn.ws.send(marshal(env));
    return true;
  }

  /** Broadcast to all connected workers. */
  broadcast(env: Envelope): number {
    let count = 0;
    const data = marshal(env);
    for (const conn of this.connections.values()) {
      if (conn.ws.readyState === WebSocket.OPEN) {
        conn.ws.send(data);
        count++;
      }
    }
    return count;
  }

  // ── Private ────────────────────────────────────────────────────────

  private handleCapabilityAdvertise(ws: WebSocket, workerId: string, env: Envelope): void {
    const p = env.payload.params || {};
    const caps: WorkerCapability = {
      actions: (p.actions as string[]) || [],
      riskLevels: (p.risk_levels as Record<string, string>) || {},
      timeouts: (p.timeouts as Record<string, number>) || {},
      maxConcurrent: (p.max_concurrent as number) || 5,
      workerVersion: (p.worker_version as string) || "0.1.0",
      heartbeatInterval: (p.heartbeat_interval as number) || 15,
    };

    this.connections.set(workerId, { ws, workerId, lastPong: Date.now() });
    this.registry.register(workerId, caps);

    // Re-route any pending requests for this worker.
    const pending = this.tracker.getPendingForWorker(workerId);
    for (const entry of pending) {
      this.sendToWorker(workerId, entry.envelope);
    }

    logger.info("Worker connected", {
      msg_id: env.msg_id,
      data: { workerId, actions: caps.actions.length },
    });
  }

  private handleWorkerResponse(env: Envelope): void {
    if (env.correlation_id) this.tracker.resolve(env.correlation_id);
    // The response will be forwarded to Brain via the tracker's callback
    // mechanism. For now, responses are logged and summarised.
    logger.info("Worker response", {
      msg_id: env.msg_id,
      data: { action: env.payload.action, status: env.payload.status },
    });
  }

  private handleWorkerEvent(env: Envelope): void {
    logger.info("Worker event", {
      msg_id: env.msg_id,
      data: { action: env.payload.action },
    });
  }

  private reapZombies(): void {
    const now = Date.now();
    let reaped = 0;
    for (const [workerId, conn] of this.connections.entries()) {
      if (now - conn.lastPong > this.PONG_TIMEOUT_MS) {
        conn.ws.terminate();
        this.connections.delete(workerId);
        this.registry.markOffline(workerId, "zombie");
        reaped++;
      }
    }
    if (reaped > 0) {
      logger.warn("Zombie workers reaped", { msg_id: "", data: { count: reaped } });
    }
  }
}

// ── Helpers ───────────────────────────────────────────────────────────

function findEntry(m: Map<string, WorkerSocket>, ws: WebSocket): WorkerSocket | undefined {
  for (const entry of m.values()) {
    if (entry.ws === ws) return entry;
  }
  return undefined;
}

function errorEnvelope(traceId: string, msgId: string, code: string, message: string): Envelope {
  return {
    proto_version: "1.0",
    trace_id: traceId,
    msg_id: msgId || uuidv4(),
    msg_type: "response",
    timestamp: Math.floor(Date.now() / 1000),
    source: "master",
    target: "brain",
    payload: {
      action: "",
      status: "failure",
      error: { code, message },
    },
  };
}
