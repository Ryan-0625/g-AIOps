import { WebSocketServer } from "../ws-server";
import { Registry } from "../../store/registry";
import { Tracker } from "../../orchestrator/tracker";
import { Router } from "../../orchestrator/router";
import { PriorityQueue } from "../../orchestrator/priority-queue";
import { Envelope } from "../../protocol/types";

describe("WebSocketServer - Unit", () => {
  let registry: Registry;
  let wsServer: WebSocketServer;

  beforeEach(() => {
    registry = new Registry();
    const tracker = new Tracker();
    const router = new Router(registry);
    const queue = new PriorityQueue();
    wsServer = new WebSocketServer(registry, tracker, router, queue, "test-token");
  });

  // U-M-15: Send to offline worker
  it("should handle send to offline worker without panic [U-M-15]", () => {
    const env = { msg_id: "test-msg", trace_id: "t-1" } as Envelope;
    expect(() => { wsServer.sendToWorker("non-existent-worker", env); }).not.toThrow();
  });

  // CHAOS-03: Duplicate message send
  it("should handle duplicate send to offline worker [CHAOS-03]", () => {
    const env = { msg_id: "dup-001", trace_id: "t-dup" } as Envelope;
    expect(() => {
      wsServer.sendToWorker("nonexistent", env);
      wsServer.sendToWorker("nonexistent", env);
    }).not.toThrow();
  });

  // U-M-15: Send to offline returns undefined
  it("should return undefined for offline worker [U-M-15b]", () => {
    const result = wsServer.sendToWorker("no-such-worker", { msg_id: "m1" } as Envelope);
    expect(result).toBe(false);
  });
});
