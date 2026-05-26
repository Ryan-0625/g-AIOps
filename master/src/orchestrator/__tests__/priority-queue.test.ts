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

  it("handles mixed priorities with FIFO within each level", () => {
    const q = new PriorityQueue();
    q.push(makeEnv(2, "urgent-1"));
    q.push(makeEnv(0, "normal-1"));
    q.push(makeEnv(2, "urgent-2"));
    q.push(makeEnv(1, "important-1"));
    q.push(makeEnv(0, "normal-2"));

    expect(q.pop()!.msg_id).toBe("urgent-1");
    expect(q.pop()!.msg_id).toBe("urgent-2");
    expect(q.pop()!.msg_id).toBe("important-1");
    expect(q.pop()!.msg_id).toBe("normal-1");
    expect(q.pop()!.msg_id).toBe("normal-2");
  });

  it("aging mechanism does not crash with mixed priorities", () => {
    const q = new PriorityQueue();
    q.push(makeEnv(0, "low"));
    q.push(makeEnv(2, "high"));
    q.push(makeEnv(1, "mid"));
    // Should still return P2 first, then P1, then P0
    expect(q.pop()!.msg_id).toBe("high");
    expect(q.pop()!.msg_id).toBe("mid");
    expect(q.pop()!.msg_id).toBe("low");
  });

  it("handles empty queue gracefully", () => {
    const q = new PriorityQueue();
    expect(q.pop()).toBeNull();
    expect(q.size()).toBe(0);
  });

  it("maintains order after many push-pop cycles", () => {
    const q = new PriorityQueue();
    const results: string[] = [];

    for (let i = 0; i < 100; i++) {
      q.push(makeEnv(i % 3, `item-${i}`));
    }

    for (let i = 0; i < 100; i++) {
      const item = q.pop();
      if (item) results.push(item.msg_id);
    }

    expect(results).toHaveLength(100);
    // All P2 items come first, then P1, then P0
    const p2Items = results.filter(id => id.startsWith("item-") && parseInt(id.split("-")[1]) % 3 === 2);
    const p1Items = results.filter(id => id.startsWith("item-") && parseInt(id.split("-")[1]) % 3 === 1);
    const p0Items = results.filter(id => id.startsWith("item-") && parseInt(id.split("-")[1]) % 3 === 0);

    const firstP1Index = results.indexOf(p1Items[0]);
    const lastP2Index = results.lastIndexOf(p2Items[p2Items.length - 1]);
    const firstP0Index = results.indexOf(p0Items[0]);
    const lastP1Index = results.lastIndexOf(p1Items[p1Items.length - 1]);

    expect(lastP2Index).toBeLessThan(firstP1Index);
    expect(lastP1Index).toBeLessThan(firstP0Index);
  });
});


