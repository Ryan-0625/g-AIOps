import { newRequest, newResponse, validateEnvelope, marshal, unmarshal, mustMarshal } from "../envelope";
import { Envelope, ErrorInfo } from "../types";

const validUUID = "550e8400-e29b-41d4-a716-446655440000";
const validUUID2 = "660e8400-e29b-41d4-a716-446655440001";

function validRequest(): Envelope {
  return newRequest(validUUID, validUUID2, "ping.icmp", { target: "localhost" });
}

describe("newRequest", () => {
  it("creates a request with defaults", () => {
    const env = validRequest();
    expect(env.msg_type).toBe("request");
    expect(env.proto_version).toBe("1.1");
    expect(env.payload.action).toBe("ping.icmp");
    expect(env.payload.status).toBe("pending");
    expect(env.priority).toBe(0);
    expect(env.ttl_seconds).toBe(30);
    expect(env.target).toBe("worker");
    expect(env.target_id).toBe("*");
  });

  it("applies options", () => {
    const env = newRequest(validUUID, validUUID2, "disk.usage", { path: "/" }, {
      targetId: "worker-01",
      priority: 1,
      ttlSeconds: 60,
      correlationId: validUUID,
    });
    expect(env.target_id).toBe("worker-01");
    expect(env.priority).toBe(1);
    expect(env.ttl_seconds).toBe(60);
    expect(env.correlation_id).toBe(validUUID);
  });
});

describe("newResponse", () => {
  it("creates a success response", () => {
    const req = validRequest();
    const resp = newResponse(req, "success", { usage: 75 });
    expect(resp.msg_type).toBe("response");
    expect(resp.trace_id).toBe(req.trace_id);
    expect(resp.correlation_id).toBe(req.msg_id);
    expect(resp.payload.status).toBe("success");
    expect(resp.payload.data).toEqual({ usage: 75 });
  });

  it("creates a failure response with error", () => {
    const req = validRequest();
    const err: ErrorInfo = { code: "PING_FAILED", message: "host unreachable" };
    const resp = newResponse(req, "failure", undefined, err);
    expect(resp.payload.status).toBe("failure");
    expect(resp.payload.error).toEqual(err);
  });
});

describe("validateEnvelope", () => {
  it("passes for a valid request", () => {
    expect(validateEnvelope(validRequest())).toHaveLength(0);
  });

  it("rejects missing trace_id", () => {
    const env = validRequest();
    env.trace_id = "not-a-uuid";
    const errs = validateEnvelope(env);
    expect(errs.some((e) => e.field === "trace_id")).toBe(true);
  });

  it("rejects invalid msg_type", () => {
    const env = validRequest();
    (env as any).msg_type = "invalid";
    const errs = validateEnvelope(env);
    expect(errs.some((e) => e.field === "msg_type")).toBe(true);
  });

  it("rejects failure without error", () => {
    const env = validRequest();
    env.payload.status = "failure";
    env.payload.error = undefined;
    const errs = validateEnvelope(env);
    expect(errs.some((e) => e.field === "payload.error")).toBe(true);
  });

  it("rejects truncated without truncated_at", () => {
    const env = validRequest();
    env.payload.truncated = true;
    env.payload.truncated_at = undefined;
    const errs = validateEnvelope(env);
    expect(errs.some((e) => e.field === "payload.truncated_at")).toBe(true);
  });
});

describe("marshal / unmarshal", () => {
  it("round-trips successfully", () => {
    const env = validRequest();
    const json = marshal(env);
    const parsed = unmarshal(json);
    expect(parsed.trace_id).toBe(env.trace_id);
    expect(parsed.payload.action).toBe(env.payload.action);
  });
});

describe("mustMarshal", () => {
  it("throws for invalid envelope", () => {
    const env = validRequest();
    (env as any).msg_type = "bad";
    expect(() => mustMarshal(env)).toThrow("Envelope validation failed");
  });
});
