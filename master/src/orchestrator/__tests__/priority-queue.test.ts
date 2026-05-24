import { PriorityQueue } from "../priority-queue";
import { Envelope } from "../../protocol/types";

function makeEnv(priority: number, id: string = ""): Envelope {
  return {
    proto_version: "1.1",
    trace_id: "t1",
    msg_id: id || `msg-${Math.random()}`,
    msg_type: "request",
    timestamp: Math.floor(Date.now() / 1000),
    source: "brain",
    target: "worker",
    priority: priority as 0 | 1 | 2,
    ttl_seconds: 30,
    payload: { action: "ping.icmp", params: {}, status: "pending" },
  };
}

describe("PriorityQueue", () => {
  it("dequeues P2 before P1 before P0", () => {
    const q = new PriorityQueue();
    q.push(makeEnv(0, "p0"));
    q.push(makeEnv(2, "p2"));
    q.push(makeEnv(1, "p1"));
    expect(q.pop()!.msg_id).toBe("p2");
    expect(q.pop()!.msg_id).toBe("p1");
    expect(q.pop()!.msg_id).toBe("p0");
  });

  it("returns null when empty", () => {
    const q = new PriorityQueue();
    expect(q.pop()).toBeNull();
  });

  it("reports correct size", () => {
    const q = new PriorityQueue();
    expect(q.size()).toBe(0);
    q.push(makeEnv(0));
    expect(q.size()).toBe(1);
    q.push(makeEnv(1));
    expect(q.size()).toBe(2);
    q.pop();
    expect(q.size()).toBe(1);
  });

  it("clears all items", () => {
    const q = new PriorityQueue();
    q.push(makeEnv(0));
    q.push(makeEnv(2));
    q.clear();
    expect(q.size()).toBe(0);
    expect(q.pop()).toBeNull();
  });

  it("preserves FIFO order within same priority", () => {
    const q = new PriorityQueue();
    q.push(makeEnv(1, "a"));
    q.push(makeEnv(1, "b"));
    q.push(makeEnv(1, "c"));
    expect(q.pop()!.msg_id).toBe("a");
    expect(q.pop()!.msg_id).toBe("b");
    expect(q.pop()!.msg_id).toBe("c");
  });

  i