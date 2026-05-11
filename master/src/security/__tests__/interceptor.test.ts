import { Registry, WorkerCapability } from "../../store/registry";
import { Interceptor } from "../interceptor";

function makeCaps(actions: string[], riskLevels: Record<string, string>): WorkerCapability {
  return {
    actions,
    riskLevels,
    timeouts: {},
    maxConcurrent: 5,
    workerVersion: "1.0",
    heartbeatInterval: 15,
  };
}

describe("Interceptor", () => {
  it("allows readonly actions", () => {
    const reg = new Registry();
    reg.register("w1", makeCaps(["disk.usage"], { "disk.usage": "readonly" }));
    const interceptor = new Interceptor(reg);
    const result = interceptor.intercept("disk.usage");
    expect(result.allowed).toBe(true);
    expect(result.requiresApproval).toBe(false);
  });

  it("requires approval for write actions", () => {
    const reg = new Registry();
    reg.register("w1", makeCaps(["service.restart"], { "service.restart": "write" }));
    const interceptor = new Interceptor(reg);
    const result = interceptor.intercept("service.restart");
    expect(result.allowed).toBe(false);
    expect(result.requiresApproval).toBe(true);
  });

  it("uses fallback high-risk list when no worker registered", () => {
    const reg = new Registry();
    const interceptor = new Interceptor(reg);
    const result = interceptor.intercept("service.restart");
    expect(result.requiresApproval).toBe(true);
  });

  it("allows unknown actions without fallback", () => {
    const reg = new Registry();
    const interceptor = new Interceptor(reg);
    const result = interceptor.intercept("some.new.action");
    expect(result.allowed).toBe(true);
    expect(result.requiresApproval).toBe(false);
  });
});
