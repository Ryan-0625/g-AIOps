import { Inspector } from "../inspector";
import { InspectionStore, InspectionConfig, ProbeType, InspectionResult } from "../../store/inspection-store";
import { Registry } from "../../store/registry";
import { WebSocketServer } from "../../server/ws-server";
import { Envelope } from "../../protocol/types";
import { newRequest, marshal } from "../../protocol/envelope";

// ============================================================
// Full-chain integration test for the Inspector
// ============================================================

jest.mock("../../server/ws-server");

function makeInspection(id: string, overrides: Partial<InspectionConfig> = {}): InspectionConfig {
  return {
    id,
    name: "Inspection-" + id,
    description: "",
    enabled: true,
    probe_type: "port.check" as ProbeType,
    probe_params: { host: "localhost", port: 80 },
    target_mode: "all",
    schedule_mode: "interval",
    interval_seconds: 300,
    timeout_seconds: 30,
    alert_rules: [
      { metric: "reachable", operator: "==", threshold: false, severity: "critical", message: "Port unreachable" },
    ],
    notify_channels: ["log"],
    created_at: Date.now(),
    updated_at: Date.now(),
    created_by: "test",
    ...overrides,
  };
}

describe("Inspector Full-Chain Integration", () => {
  let store: InspectionStore;
  let registry: Registry;
  let wsServer: jest.Mocked<WebSocketServer>;
  let inspector: Inspector;

  beforeEach(() => {
    store = new InspectionStore();
    registry = new Registry();
    wsServer = new WebSocketServer({} as any, {} as any, {} as any, {} as any, "test-token") as jest.Mocked<WebSocketServer>;
    wsServer.sendToWorker = jest.fn();
    inspector = new Inspector(store, registry, wsServer);
  });

  afterEach(() => {
    inspector.stop();
  });

  // --- Lifecycle ---

  describe("Lifecycle", () => {
    it("starts and stops the tick timer", () => {
      jest.useFakeTimers();
      inspector.start(1000);
      expect(inspector.getActiveInspectionsCount()).toBe(0);
      inspector.stop();
      jest.useRealTimers();
    });

    it("tick dispatches probes for enabled inspections", () => {
      jest.useFakeTimers();
      store.createInspection(makeInspection("insp-1"));
      registry.register("worker-1", {
        actions: ["port.check"],
        riskLevels: {},
        maxConcurrent: 5,
        workerVersion: "1.0",
        timeouts: {},
        heartbeatInterval: 30,
      });

      inspector.start(1000);
      jest.advanceTimersByTime(1000);

      expect(wsServer.sendToWorker).toHaveBeenCalled();
      inspector.stop();
      jest.useRealTimers();
    });

    it("tick skips disabled inspections", () => {
      jest.useFakeTimers();
      store.createInspection(makeInspection("insp-2", { enabled: false }));
      registry.register("worker-1", {
        actions: ["port.check"],
        riskLevels: {},
        maxConcurrent: 5,
        workerVersion: "1.0",
        timeouts: {},
        heartbeatInterval: 30,
      });

      inspector.start(1000);
      jest.advanceTimersByTime(1000);

      expect(wsServer.sendToWorker).not.toHaveBeenCalled();
      inspector.stop();
      jest.useRealTimers();
    });

    it("tick skips when interval has not elapsed", () => {
      jest.useFakeTimers();
      store.createInspection(makeInspection("insp-3"));
      inspector.start(10000);
      jest.advanceTimersByTime(5000);
      expect(wsServer.sendToWorker).not.toHaveBeenCalled();
      inspector.stop();
      jest.useRealTimers();
    });
  });

  // --- Probe Response Handling ---

  describe("Probe Response Handling", () => {
    it("handles successful probe response", () => {
      store.createInspection(makeInspection("insp-resp-1"));
      const env = {
        msg_id: "msg-success",
        trace_id: "trace-success",
        correlation_id: "corr-success",
        payload: { action: "port.check", status: "success" as const, data: { reachable: true } },
      } as any;
      (inspector as any).pendingProbes.set("corr-success", {
        inspectionId: "insp-resp-1",
        workerId: "worker-1",
        timestamp: Date.now() - 100,
        envelope: env,
      });

      inspector.handleProbeResponse(env);
      const results = store.getResults("insp-resp-1");
      expect(results).toHaveLength(1);
      expect(results[0].status).toBe("pass");
      expect(results[0].success).toBe(true);
      expect((inspector as any).pendingProbes.has("corr-success")).toBe(false);
    });

    it("handles failed probe response", () => {
      store.createInspection(makeInspection("insp-fail-1"));
      const env = {
        msg_id: "msg-fail",
        trace_id: "trace-fail",
        correlation_id: "corr-fail",
        payload: { action: "port.check", status: "failure" as const, error: { code: "ECONNREFUSED", message: "Connection refused" }, data: {} },
      } as any;
      (inspector as any).pendingProbes.set("corr-fail", {
        inspectionId: "insp-fail-1",
        workerId: "worker-1",
        timestamp: Date.now() - 50,
        envelope: env,
      });

      inspector.handleProbeResponse(env);
      const results = store.getResults("insp-fail-1");
      expect(results).toHaveLength(1);
      expect(results[0].status).toBe("error");
      expect(results[0].error).toBe("Connection refused");
    });

    it("handles probe response that triggers alert", () => {
      store.createInspection(makeInspection("insp-alert-1"));
      const env = {
        msg_id: "msg-alert",
        trace_id: "trace-alert",
        correlation_id: "corr-alert",
        payload: { action: "port.check", status: "success" as const, data: { reachable: false } },
      } as any;
      (inspector as any).pendingProbes.set("corr-alert", {
        inspectionId: "insp-alert-1",
        workerId: "worker-1",
        timestamp: Date.now() - 30,
        envelope: env,
      });

      inspector.handleProbeResponse(env);
      const results = store.getResults("insp-alert-1");
      expect(results).toHaveLength(1);
      expect(results[0].status).toBe("fail");
      expect(results[0].alerts_triggered.some((a: any) => a.triggered)).toBe(true);
    });

    it("ignores response for unknown correlation ID", () => {
      store.createInspection(makeInspection("insp-stale"));
      const env = {
        msg_id: "msg-unknown",
        trace_id: "trace-unknown",
        correlation_id: "nonexistent",
        payload: { action: "port.check", status: "success" as const, data: {} },
      } as any;
      inspector.handleProbeResponse(env);
      expect(store.getResults("insp-stale")).toHaveLength(0);
    });

    it("ignores response when inspection was deleted", () => {
      store.createInspection(makeInspection("insp-deleted"));
      const env = {
        msg_id: "msg-deleted",
        trace_id: "trace-deleted",
        correlation_id: "corr-deleted",
        payload: { action: "port.check", status: "success" as const, data: {} },
      } as any;
      (inspector as any).pendingProbes.set("corr-deleted", {
        inspectionId: "insp-deleted",
        workerId: "worker-1",
        timestamp: Date.now(),
        envelope: env,
      });
      store.deleteInspection("insp-deleted");

      inspector.handleProbeResponse(env);
      expect(store.getResults("insp-deleted")).toHaveLength(0);
    });
  });

  // --- Stale Probe Cleanup ---

  describe("Stale Probe Cleanup", () => {
    it("cleans up probes older than 60 seconds", () => {
      jest.useFakeTimers();
      const now = Date.now();
      (inspector as any).pendingProbes.set("stale-1", {
        inspectionId: "insp-stale-1",
        workerId: "worker-1",
        timestamp: now - 120000,
        envelope: {},
      });

      expect((inspector as any).pendingProbes.size).toBe(1);
      (inspector as any).cleanupStaleProbes(now);
      expect((inspector as any).pendingProbes.size).toBe(0);
      jest.useRealTimers();
    });

    it("keeps recent probes", () => {
      const now = Date.now();
      (inspector as any).pendingProbes.set("recent-1", {
        inspectionId: "insp-recent",
        workerId: "worker-1",
        timestamp: now - 10000,
        envelope: {},
      });

      (inspector as any).cleanupStaleProbes(now);
      expect((inspector as any).pendingProbes.size).toBe(1);
    });
  });

  // --- Target Resolution ---

  describe("Worker Target Resolution", () => {
    it("resolves 'all' target mode to all workers", () => {
      registry.register("w1", { actions: ["port.check"], riskLevels: {}, maxConcurrent: 5, workerVersion: "1.0", timeouts: {}, heartbeatInterval: 30 });
      registry.register("w2", { actions: ["port.check"], riskLevels: {}, maxConcurrent: 5, workerVersion: "1.0", timeouts: {}, heartbeatInterval: 30 });
      registry.register("w3", { actions: ["port.check"], riskLevels: {}, maxConcurrent: 5, workerVersion: "1.0", timeouts: {}, heartbeatInterval: 30 });

      const workers = (inspector as any).resolveTargetWorkers(
        makeInspection("insp-all", { target_mode: "all" })
      );
      expect(workers).toHaveLength(3);
    });

    it("resolves 'worker_ids' target mode to specific workers", () => {
      registry.register("w1", { actions: ["port.check"], riskLevels: {}, maxConcurrent: 5, workerVersion: "1.0", timeouts: {}, heartbeatInterval: 30 });
      registry.register("w2", { actions: ["port.check"], riskLevels: {}, maxConcurrent: 5, workerVersion: "1.0", timeouts: {}, heartbeatInterval: 30 });
      registry.register("w3", { actions: ["port.check"], riskLevels: {}, maxConcurrent: 5, workerVersion: "1.0", timeouts: {}, heartbeatInterval: 30 });

      const workers = (inspector as any).resolveTargetWorkers(
        makeInspection("insp-ids", { target_mode: "worker_ids", target_workers: ["w1", "w3", "w4"] })
      );
      // All 3 registered workers are "online" since registry.isOnline returns true for registered workers
      // But resolveTargetWorkers for "worker_ids" mode uses target_workers list and checks isOnline
      // Since all are online, it should return w1 and w3 (w4 doesn't exist)
      expect(workers).toHaveLength(2);
      expect(workers[0].workerId).toBe("w1");
    });

    it("returns empty when no workers registered", () => {
      const workers = (inspector as any).resolveTargetWorkers(
        makeInspection("insp-nobody", { target_mode: "all" })
      );
      expect(workers).toHaveLength(0);
    });

    it("returns empty for unknown target mode", () => {
      const workers = (inspector as any).resolveTargetWorkers(
        makeInspection("insp-unknown", { target_mode: "unknown" as any })
      );
      expect(workers).toHaveLength(0);
    });
  });

  // --- Probe Param Mapping ---

  describe("Probe Parameter Mapping", () => {
    it("adds timeout for http.health probes", () => {
      const params = (inspector as any).mapProbeParams(
        makeInspection("http", { probe_type: "http.health" as ProbeType, timeout_seconds: 15 })
      );
      expect(params.timeout_seconds).toBe(15);
    });

    it("adds count default for ping.icmp probes", () => {
      const params = (inspector as any).mapProbeParams(
        makeInspection("ping", { probe_type: "ping.icmp" as ProbeType })
      );
      expect(params.count).toBe(2);
    });

    it("preserves existing probe params", () => {
      const params = (inspector as any).mapProbeParams(
        makeInspection("preserve", { probe_params: { custom: "value" } })
      );
      expect(params.custom).toBe("value");
    });
  });

  // --- Utility ---

  describe("Utility", () => {
    it("returns pending probe count", () => {
      (inspector as any).pendingProbes.set("p1", {});
      (inspector as any).pendingProbes.set("p2", {});
      expect(inspector.getPendingCount()).toBe(2);
    });

    it("returns active inspection count", () => {
      store.createInspection(makeInspection("i1", { enabled: true }));
      store.createInspection(makeInspection("i2", { enabled: true }));
      store.createInspection(makeInspection("i3", { enabled: false }));
      expect(inspector.getActiveInspectionsCount()).toBe(2);
    });
  });
});
