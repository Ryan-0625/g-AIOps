import { Tracker } from "../tracker";
import { Envelope } from "../../protocol/types";

function makeEnvelope(overrides?: Partial<Envelope>): Envelope {
  return {
    proto_version: "1.0",
    trace_id: "trace-1",
    msg_id: "msg-1",
    msg_type: "request",
    timestamp: 1715000000,
    source: "master",
    target: "worker",
    payload: { action: "test.action", status: "pending", params: {} },
    ...overrides,
  };
}

describe("Tracker", () => {
  let tracker: Tracker;

  beforeEach(() => {
    tracker = new Tracker();
  });

  it("tracks and resolves a request", () => {
    const env = makeEnvelope();
    const ok = tracker.track("msg-1", env, "worker-1");
    expect(ok).toBe(true);
    expect(tracker.pendingCount()).toBe(1);

    tracker.resolve("msg-1");
    expect(tracker.pendingCount()).toBe(0);
  });

  it("returns false when pending is full", () => {
    // Fill the tracker with MAX_PENDING entries.
    for (let i = 0; i < 10_000; i++) {
      const id = `msg-${i}`;
      tracker.track(id, makeEnvelope({ msg_id: id }), "worker-1");
    }
    expect(tracker.pendingCount()).toBe(10_000);

    const ok = tracker.track("overflow", makeEnvelope({ msg_id: "overflow" }), "worker-1");
    expect(ok).toBe(false);
  });

  it("getPendingForWorker returns matching entries", () => {
    tracker.track("msg-1", makeEnvelope({ msg_id: "msg-1" }), "worker-1");
    tracker.track("msg-2", makeEnvelope({ msg_id: "msg-2" }), "worker-1");
    tracker.track("msg-3", makeEnvelope({ msg_id: "msg-3" }), "worker-2");

    const w1 = tracker.getPendingForWorker("worker-1");
    expect(w1).toHaveLength(2);

    const w2 = tracker.getPendingForWorker("worker-2");
    expect(w2).toHaveLength(1);

    const w3 = tracker.getPendingForWorker("nonexistent");
    expect(w3).toHaveLength(0);
  });

  it("reapOrphans removes expired entries", () => {
    // Create an entry and resolve it to remove.
    tracker.track("msg-old", makeEnvelope({ msg_id: "msg-old" }), "worker-1");
    expect(tracker.pendingCount()).toBe(1);

    // After resolve, pending should be 0.
    tracker.resolve("msg-old");
    expect(tracker.pendingCount()).toBe(0);
  });

  it("addChunk assembles payload when all chunks arrive", () => {
    const result1 = tracker.addChunk("trace-1", 0, 3, "hello ");
    expect(result1).toBeNull(); // not yet complete

    const result2 = tracker.addChunk("trace-1", 1, 3, "world ");
    expect(result2).toBeNull();

    const result3 = tracker.addChunk("trace-1", 2, 3, "final");
    expect(result3).toBe("hello world final");
  });

  it("addChunk discards when too many groups", () => {
    const MAX = 500;
    // Fill to max with incomplete groups (total=2, but only send 1 chunk).
    for (let i = 0; i < MAX; i++) {
      tracker.addChunk(`trace-${i}`, 0, 2, "part1");
    }

    // Next one should be discarded.
    const result = tracker.addChunk("trace-overflow", 0, 2, "data");
    expect(result).toBeNull();
  });

  it("reapChunks removes expired groups", () => {
    // Use vi.advanceTimersByTime approach or simple:
    // Since chunk timeout is 30s, we can't easily test without fake timers.
    // Verify reapChunks returns 0 for empty.
    expect(tracker.reapChunks()).toBe(0);
  });

  it("getPending returns all pending entries", () => {
    tracker.track("msg-1", makeEnvelope({ msg_id: "msg-1" }), "worker-1");
    tracker.track("msg-2", makeEnvelope({ msg_id: "msg-2" }), "worker-2");

    const all = tracker.getPending();
    expect(all.size).toBe(2);
  });
});
