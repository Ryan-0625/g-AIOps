import { Registry, WorkerCapability } from "../registry";
import { MetricsCollector } from "../metrics";

function makeCaps(actions: string[]): WorkerCapability {
  return {
    actions,
    riskLevels: {},
    timeouts: {},
    maxConcurrent: 5,
    workerVersion: "1.0",
    heartbeatInterval: 15,
  };
}

describe("Registry", () => {
  it("registers and finds workers", () => {
    const reg = new Registry();
    reg.register("w1", makeCaps(["ping.icmp"]));
    expect(reg.onlineCount()).toBe(1);
    expect(reg.findWorker("ping.icmp")).not.toBeNull();
    expect(reg.findWorker("disk.usage")).toBeNull();
  });

  it("marks worker offline", () => {
    const reg = new Registry();
    reg.register("w1", makeCaps(["ping.icmp"]));
    reg.markOffline("w1", "test");
    expect(reg.onlineCount()).toBe(0);
    expect(reg.isOnline("w1")).toBe(false);
  });

  it("updates load", () => {
    const reg = new Registry();
    reg.register("w1", makeCaps(["ping.icmp"]));
    reg.updateLoad("w1", 3);
    const worker = reg.findWorker("ping.icmp")!;
    expect(worker.currentLoad).toBe(3);
  });

  it("selects least-loaded worker", () => {
    const reg = new Registry();
    reg.register("busy", { ...makeCaps(["ping.icmp"]), maxConcurrent: 5 });
    reg.register("idle", { ...makeCaps(["ping.icmp"]), maxConcurrent: 5 });
    reg.updateLoad("busy", 4);
    reg.updateLoad("idle", 1);
    const selected = reg.findWorker("ping.icmp")!;
    expect(selected.workerId).toBe("idle");
  });

  it("returns null when all workers at capacity", () => {
    const reg = new Registry();
    reg.register("w1", { ...makeCaps(["ping.icmp"]), maxConcurrent: 2 });
    reg.updateLoad("w1", 2);
    expect(reg.findWorker("ping.icmp")).toBeNull();
  });
});

describe("MetricsCollector", () => {
  it("starts with zero counts", () => {
    const m = new MetricsCollector();
    const snap = m.snapshot(0, 0, 0, 0);
    expect(snap.totalProcessed).toBe(0);
  });

  it("records request counts", () => {
    const m = new MetricsCollector();
    m.recordRequest("success", false);
    m.recordRequest("failure", true);
    const snap = m.snapshot(2, 1, 0, 0);
    expect(snap.totalProcessed).toBe(2);
    expect(snap.truncatedCount).toBe(1);
    expect(snap.errorCount).toBe(1);
  });
});
