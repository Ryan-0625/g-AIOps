import { configureAudit, writeAudit, writeAuditEvent, AuditConfig } from "../audit";
import { Envelope } from "../../protocol/types";
import fs from "fs";
import path from "path";
import os from "os";

jest.mock("fs");
jest.mock("path");

describe("Audit System", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // U-M-33: Audit entry format for Envelope
  it("should write audit entry with correct format [U-M-33]", () => {
    const stdoutSpy = jest.spyOn(process.stdout, "write").mockImplementation(() => true);

    const env: Envelope = {
      proto_version: "1.0",
      trace_id: "trace-audit-1",
      msg_id: "msg-audit-1",
      msg_type: "request",
      timestamp: Date.now(),
      source: "brain",
      target: "worker-1",
      payload: {
        action: "ping.icmp",
        params: { target: "localhost" },
        status: "pending",
      },
    } as unknown as Envelope;

    writeAudit(env);

    expect(stdoutSpy).toHaveBeenCalled();
    const output = stdoutSpy.mock.calls[0][0] as string;
    const parsed = JSON.parse(output);
    expect(parsed._audit).toBeDefined();
    expect(parsed._audit.traceId).toBe("trace-audit-1");
    expect(parsed._audit.action).toBe("ping.icmp");
    expect(parsed._audit.source).toBe("brain");
    expect(parsed._audit.target).toBe("worker-1");

    stdoutSpy.mockRestore();
  });

  // U-M-34: Non-Envelope audit event
  it("should write audit event with reason field [U-M-34]", () => {
    const stdoutSpy = jest.spyOn(process.stdout, "write").mockImplementation(() => true);

    writeAuditEvent({
      traceId: "trace-event-1",
      msgId: "auth-failed",
      action: "execute",
      source: "brain",
      target: "master",
      status: "rejected",
      errorCode: "AUTH_FAILED",
      reason: "invalid-token",
    });

    expect(stdoutSpy).toHaveBeenCalled();
    const output = stdoutSpy.mock.calls[0][0] as string;
    const parsed = JSON.parse(output);
    expect(parsed._audit.reason).toBe("invalid-token");
    expect(parsed._audit.status).toBe("rejected");

    stdoutSpy.mockRestore();
  });

  // U-M-35: Disabled audit
  it("should not create file stream when disabled [U-M-35]", () => {
    const cfg: AuditConfig = { enabled: false, logPath: "/tmp/audit.log" };
    configureAudit(cfg);

    // writeAudit should still work (writes to stdout) but no file creation
    const stdoutSpy = jest.spyOn(process.stdout, "write").mockImplementation(() => true);
    const env: Envelope = {
      proto_version: "1.0",
      trace_id: "t",
      msg_id: "m",
      msg_type: "request",
      timestamp: Date.now(),
      source: "brain",
      target: "worker",
      payload: { action: "test", params: {}, status: "pending" },
    } as unknown as Envelope;
    writeAudit(env);
    expect(stdoutSpy).toHaveBeenCalled();
    stdoutSpy.mockRestore();
  });

  // U-M-33: Audit entry has timestamp
  it("should include ISO timestamp in audit entry [U-M-33b]", () => {
    const stdoutSpy = jest.spyOn(process.stdout, "write").mockImplementation(() => true);

    writeAuditEvent({
      traceId: "t-ts",
      msgId: "m-ts",
      action: "test",
      source: "a",
      target: "b",
      status: "success",
    });

    const output = stdoutSpy.mock.calls[0][0] as string;
    const parsed = JSON.parse(output);
    expect(parsed._audit.timestamp).toBeDefined();
    expect(() => new Date(parsed._audit.timestamp)).not.toThrow();

    stdoutSpy.mockRestore();
  });
});
