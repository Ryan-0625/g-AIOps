import { Summarizer } from "../summarizer";
import { Envelope } from "../../protocol/types";

function makeEnvelope(overrides?: Partial<Envelope>): Envelope {
  return {
    proto_version: "1.0",
    trace_id: "trace-1",
    msg_id: "msg-1",
    msg_type: "response",
    timestamp: 1715000000,
    source: "worker",
    target: "master",
    payload: {
      action: "disk.usage",
      status: "success",
      data: { usage_pct: "42.5", avail_bytes: 50000000000 },
    },
    ...overrides,
  };
}

describe("Summarizer", () => {
  const summarizer = new Summarizer();

  it("summarizes disk.usage success", () => {
    const env = makeEnvelope();
    const result = summarizer.summarize(env);
    expect(result.summary).toContain("42.5");
    expect(result.hasError).toBe(false);
    expect(result.hasTruncation).toBe(false);
    expect(result.keyMetrics).toEqual({
      usagePct: "42.5",
      availBytes: 50000000000,
    });
  });

  it("summarizes service.status success", () => {
    const env = makeEnvelope({
      payload: {
        action: "service.status",
        status: "success",
        data: { status: "active", running: true },
      },
    });
    const result = summarizer.summarize(env);
    expect(result.summary).toContain("active");
    expect(result.keyMetrics).toEqual({ status: "active", running: true });
  });

  it("summarizes ping.icmp success", () => {
    const env = makeEnvelope({
      payload: {
        action: "ping.icmp",
        status: "success",
        data: { target: "localhost", reachable: true, avg_rtt_ms: 1.2 },
      },
    });
    const result = summarizer.summarize(env);
    expect(result.summary).toContain("reachable");
    expect(result.keyMetrics).toEqual({ reachable: true, avgRttMs: 1.2 });
  });

  it("summarizes failure with error", () => {
    const env = makeEnvelope({
      payload: {
        action: "exec.run",
        status: "failure",
        error: { code: "COMMAND_NOT_ALLOWED", message: "command not in whitelist" },
      },
    });
    const result = summarizer.summarize(env);
    expect(result.summary).toContain("COMMAND_NOT_ALLOWED");
    expect(result.hasError).toBe(true);
    expect(result.errorCode).toBe("COMMAND_NOT_ALLOWED");
    expect(result.errorMessage).toBe("command not in whitelist");
  });

  it("summarizes pending with progress", () => {
    const env = makeEnvelope({
      payload: {
        action: "disk.cleanup",
        status: "pending",
        progress: { percent: 45, message: "cleaning /tmp/cache" },
      },
    });
    const result = summarizer.summarize(env);
    expect(result.summary).toContain("45%");
    expect(result.summary).toContain("/tmp/cache");
  });

  it("flags truncation and appends to summary", () => {
    const env = makeEnvelope({
      payload: {
        action: "log.tail",
        status: "success",
        data: { lines: ["a", "b"] },
        truncated: true,
        truncated_at: 1048576,
      },
    });
    const result = summarizer.summarize(env);
    expect(result.hasTruncation).toBe(true);
    expect(result.summary).toContain("truncated at 1048576");
  });

  it("handles unknown action with generic summary", () => {
    const env = makeEnvelope({
      payload: { action: "custom.thing", status: "success", data: {} },
    });
    const result = summarizer.summarize(env);
    expect(result.summary).toContain("custom.thing");
  });

  it("extracts trace_id and action", () => {
    const env = makeEnvelope({ trace_id: "my-trace" });
    const result = summarizer.summarize(env);
    expect(result.traceId).toBe("my-trace");
    expect(result.action).toBe("disk.usage");
  });
});
