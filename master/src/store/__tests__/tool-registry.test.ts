import { ToolRegistry, DynamicToolEntry } from "../tool-registry";

describe("ToolRegistry", () => {
  let registry: ToolRegistry;

  beforeEach(() => {
    registry = new ToolRegistry();
  });

  it("registers and finds a dynamic tool", () => {
    registry.register("worker-1", "custom.hello", {
      language: "bash",
      riskLevel: "readonly",
      codeHash: "abc123",
    });

    const workers = registry.findWorkersForAction("custom.hello");
    expect(workers).toHaveLength(1);
    expect(workers[0].workerId).toBe("worker-1");
    expect(workers[0].language).toBe("bash");
    expect(workers[0].state).toBe("deployed");
  });

  it("returns empty list for unknown action", () => {
    const workers = registry.findWorkersForAction("nonexistent");
    expect(workers).toHaveLength(0);
  });

  it("unregisters a tool", () => {
    registry.register("worker-1", "custom.test", {
      language: "python3",
      riskLevel: "write",
      codeHash: "def456",
    });

    expect(registry.isDeployed("custom.test")).toBe(true);

    registry.unregister("worker-1", "custom.test");
    expect(registry.isDeployed("custom.test")).toBe(false);
  });

  it("supports multiple workers for same action", () => {
    registry.register("worker-1", "custom.health", {
      language: "bash",
      riskLevel: "readonly",
      codeHash: "a1",
    });
    registry.register("worker-2", "custom.health", {
      language: "bash",
      riskLevel: "readonly",
      codeHash: "a1",
    });

    const workers = registry.findWorkersForAction("custom.health");
    expect(workers).toHaveLength(2);
  });

  it("increments version on re-registration", () => {
    registry.register("worker-1", "custom.test", {
      language: "bash",
      riskLevel: "readonly",
      codeHash: "v1",
    });
    const v1 = registry.findWorkersForAction("custom.test")[0].version;

    registry.register("worker-1", "custom.test", {
      language: "bash",
      riskLevel: "readonly",
      codeHash: "v2",
    });
    const v2 = registry.findWorkersForAction("custom.test")[0].version;

    expect(v2).toBe(v1 + 1);
  });

  it("lists all actions", () => {
    registry.register("w1", "tool.a", { language: "bash", riskLevel: "readonly", codeHash: "a" });
    registry.register("w1", "tool.b", { language: "python3", riskLevel: "write", codeHash: "b" });

    const actions = registry.listActions();
    expect(actions).toContain("tool.a");
    expect(actions).toContain("tool.b");
  });

  it("removes worker entries on disconnect", () => {
    registry.register("worker-1", "custom.test", {
      language: "bash",
      riskLevel: "readonly",
      codeHash: "h1",
    });
    registry.register("worker-2", "custom.test", {
      language: "bash",
      riskLevel: "readonly",
      codeHash: "h2",
    });

    expect(registry.findWorkersForAction("custom.test")).toHaveLength(2);

    const removed = registry.removeWorker("worker-1");
    expect(removed).toBe(1);
    expect(registry.findWorkersForAction("custom.test")).toHaveLength(1);
  });

  it("reports correct stats", () => {
    registry.register("w1", "tool.x", { language: "bash", riskLevel: "readonly", codeHash: "x" });
    registry.register("w2", "tool.x", { language: "bash", riskLevel: "readonly", codeHash: "x" });
    registry.register("w1", "tool.y", { language: "python3", riskLevel: "write", codeHash: "y" });

    const stats = registry.getStats();
    expect(stats.totalTools).toBe(2);   // 2 distinct actions
    expect(stats.totalDeployments).toBe(3); // 3 total deployments
    expect(stats.actions).toBe(2);
  });

  it("tracks execution stats", () => {
    registry.register("w1", "custom.test", {
      language: "bash",
      riskLevel: "readonly",
      codeHash: "h",
    });

    registry.recordExecution("w1", "custom.test");
    registry.recordExecution("w1", "custom.test");
    registry.recordExecution("w1", "custom.test");

    const entry = registry.findWorkersForAction("custom.test")[0];
    expect(entry.executeCount).toBe(3);
    expect(entry.state).toBe("deployed");
  });
});


