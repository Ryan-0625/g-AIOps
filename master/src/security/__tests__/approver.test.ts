import { Approver } from "../approver";
import { Registry } from "../../store/registry";
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
    payload: { action: "service.restart", status: "pending", params: {} },
    ...overrides,
  };
}

describe("Approver", () => {
  let registry: Registry;
  let approver: Approver;

  beforeEach(() => {
    registry = new Registry();
    registry.register("worker-1", {
      actions: ["service.restart"],
      riskLevels: { "service.restart": "dangerous" },
      timeouts: {},
      maxConcurrent: 5,
      workerVersion: "1.0.0",
      heartbeatInterval: 15,
    });
    approver = new Approver(registry);
  });

  it("requests approval with pending status", () => {
    const env = makeEnvelope();
    const req = approver.requestApproval(env, "worker-1");
    expect(req.status).toBe("pending");
    expect(req.id).toBe("msg-1");
    expect(approver.pendingCount()).toBe(1);
  });

  it("approves a pending request", () => {
    const env = makeEnvelope();
    approver.requestApproval(env, "worker-1");
    const result = approver.approve("msg-1");
    expect(result.success).toBe(true);
    expect(result.workerStillOnline).toBe(true);
    expect(approver.pendingCount()).toBe(0);
  });

  it("rejects a pending request", () => {
    const env = makeEnvelope();
    approver.requestApproval(env, "worker-1");
    const ok = approver.reject("msg-1");
    expect(ok).toBe(true);
    expect(approver.pendingCount()).toBe(0);
  });

  it("rejects non-existent approval", () => {
    const ok = approver.reject("nonexistent");
    expect(ok).toBe(false);
  });

  it("approves non-existent returns false", () => {
    const result = approver.approve("nonexistent");
    expect(result.success).toBe(false);
  });

  it("fails approval when worker is offline", () => {
    registry.markOffline("worker-1", "disconnect");
    const env = makeEnvelope();
    approver.requestApproval(env, "worker-1");
    const result = approver.approve("msg-1");
    expect(result.success).toBe(false);
    expect(result.workerStillOnline).toBe(false);
  });

  it("rejects already-approved requests", () => {
    const env = makeEnvelope();
    approver.requestApproval(env, "worker-1");
    approver.approve("msg-1");
    const ok = approver.reject("msg-1");
    expect(ok).toBe(false);
  });

  it("invokes onReject callback when rejecting", () => {
    let rejected: any = null;
    const approverWithCb = new Approver(registry, (req) => {
      rejected = req;
    });

    const env = makeEnvelope();
    approverWithCb.requestApproval(env, "worker-1");
    approverWithCb.reject("msg-1");
    expect(rejected).not.toBeNull();
    expect(rejected!.status).toBe("rejected");
  });

  it("pendingCount returns active requests", () => {
    approver.requestApproval(makeEnvelope(), "worker-1");
    approver.requestApproval(makeEnvelope({ msg_id: "msg-2" }), "worker-1");
    expect(approver.pendingCount()).toBe(2);
  });
});
