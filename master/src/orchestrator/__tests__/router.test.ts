import { Registry, WorkerCapability } from "../../store/registry";
import { Router } from "../router";

function makeCaps(actions: string[], riskLevels?: Record<string, string>): WorkerCapability {
  return {
    actions,
    riskLevels: riskLevels ?? {},
    timeouts: {},
    maxConcurrent: 5,
    workerVersion: "1.0",
    heartbeatInterval: 15,
  };
}

describe("Router", () => {
  it("routes to the only capable worker", () => {
    const reg = new Registry();
    reg.register("w1", makeCaps(["ping.icmp", "disk.usage"]));
    const router = new Router(reg);
    const result = router.route("ping.icmp");
    expect(result).toHaveProperty("workerId", "w1");
  });

  it("prefers least-loaded worker", () => {
    const reg = new Registry();
    reg.register("busy", makeCaps(["ping.icmp"]));
    reg.register("idle", makeCaps(["ping.icmp"]));
    reg.updateLoad("busy", 4); // 4/5
    reg.updateLoad("idle", 1); // 1/5

    const router = new Router(reg);
    const result = router.route("ping.icmp") as any;
    expect(result.workerId).toBe("idle");
  });

  it("respects preferred worker", () => {
    const reg = new Registry();
    reg.register("w1", makeCaps(["ping.icmp"]));
    reg.register("w2", makeCaps(["ping.icmp"]));
    const router = new Router(reg);
    const result = router.route("ping.icmp", "w2") as any;
    expect(result.workerId).toBe("w2");
  });

  it("returns error when no workers", () => {
    const reg = new Registry();
    const router = new Router(reg);
    const result = router.route("ping.icmp") as any;
    expect(result.code).toBe("NO_AVAILABLE_WORKER");
  });

  it("routes broadcast to all capable workers", () => {
    const reg = new Registry();
    reg.register("w1", makeCaps(["ping.icmp"]));
    reg.register("w2", makeCaps(["ping.icmp", "disk.usage"]));
    reg.register("w3", makeCaps(["disk.usage"]));
    const router = new Router(reg);
    const workers = router.routeBroadcast("ping.icmp");
    expect(workers).toHaveLength(2);
    expect(workers.map((w) => w.workerId).sort()).toEqual(["w1", "w2"]);
  });
});
