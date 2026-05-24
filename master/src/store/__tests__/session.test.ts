import { SessionStore, BrainSession } from "../session";

describe("SessionStore", () => {
  let store: SessionStore;

  beforeEach(() => {
    store = new SessionStore();
  });

  it("stores and retrieves a session", () => {
    const session: BrainSession = {
      traceId: "t1",
      status: "running",
      action: "ping.icmp",
      workerId: "w1",
      createdAt: Date.now(),
    };

    const ok = store.set(session);
    expect(ok).toBe(true);

    const retrieved = store.get("t1");
    expect(retrieved).toBeDefined();
    expect(retrieved!.action).toBe("ping.icmp");
    expect(retrieved!.status).toBe("running");
  });

  it("returns undefined for missing session", () => {
    expect(store.get("nonexistent")).toBeUndefined();
  });

  it("updates an existing session", () => {
    store.set({
      traceId: "t1", status: "pending", action: "disk.usage",
      workerId: "w1", createdAt: Date.now(),
    });

    store.update("t1", { status: "completed", completedAt: Date.now() });

    const session = store.get("t1");
    expect(session!.status).toBe("completed");
    expect(session!.completedAt).toBeDefined();
  });

  it("update on nonexistent session does nothing", () => {
    expect(() => store.update("ghost", { status: "failed" })).not.toThrow();
  });

  it("lists all sessions", () => {
    store.set({
      traceId: "t1", status: "pending", action: "a",
      workerId: "w1", createdAt: Date.now(),
    });
    store.set({
      traceId: "t2", status: "running", action: "b",
      workerId: "w2", createdAt: Date.now(),
    });

    expect(store.list()).toHaveLength(2);
  });

  it("lists sessions filtered by status", () => {
    store.set({
      traceId: "t1", status: "pending", action: "a",
      workerId: "w1", createdAt: Date.now(),
    });
    store.set({
      traceId: "t2", status: "completed", action: "b",
      workerId: "w2", createdAt: Date.now(),
    });
    store.set({
      traceId: "t3", status: "completed", action: "c",
      workerId: "w3", createdAt: Date.now(),
    });

    const completed = store.list({ status: "completed" });
    expect(completed).toHaveLength(2);
    expect(completed.every(s => s.status === "completed")).toBe(true);
  });

  it("reaps old completed sessions", () => {
    const now = Date.now();
    store.set({
      traceId: "old", status: "completed", action: "a",
      workerId: "w1", createdAt: now - 100_000, completedAt: now - 100_000,
    });
    store.set({
      traceId: "new", status: "completed", action: "b",
      workerId: "w2", createdAt: now - 1000, completedAt: now - 1000,
    });

    const reaped = store.reap(50_000); // 50s max age
    expect(reaped).toBe(1);
    expect(store.get("old")).toBeUndefined();
    expect(store.get("new")).toBeDefined();
  });

  it("rejects when exceeding MAX_SESSIONS", () => {
    const fullStore = new (SessionStore as any)();
    // Set max to a small number via prototype manipulation
    Object.defineProperty(fullStore, "MAX_SESSIONS", { value: 2 });

    fullStore.set({
      traceId: "a", status: "pending", action: "x",
      workerId: "w", createdAt: Date.now(),
    });
    fullStore.set({
      traceId: "b", status: "pending", action: "x",
      workerId: "w", createdAt: Date.now(),
    });
    const rejected = fullStore.set({
      traceId: "c", status: "pending", action: "x",
      workerId: "w", createdAt: Date.now(),
    });

    expect(rejected).toBe(false);
  });

  it("tracks session count via size getter", () => {
    expect(store.size).toBe(0);
    store.set({
      traceId: "t1", status: "pending", action: "a",
      workerId: "w1", createdAt: Date.now(),
    });
    expect(store.size).toBe(1);
    store.set({
      traceId: "t2", status: "pending", action: "b",
      workerId: "w2", createdAt: Date.now(),
    });
    expect(store.size).toBe(2);
  });
});
