import { Envelope } from "../protocol/types";
import { createWriteStream, mkdirSync, WriteStream } from "fs";
import { dirname } from "path";

export interface AuditConfig {
  logPath?: string;
  enabled: boolean;
}

export interface AuditEntry {
  timestamp: string;
  traceId: string;
  msgId: string;
  action: string;
  source: string;
  target: string;
  status: string;
  errorCode?: string;
  approvalId?: string;
  /** For non-envelope events: reason for the audit entry */
  reason?: string;
}

let auditStream: WriteStream | null = null;

export function configureAudit(cfg: AuditConfig): void {
  if (!cfg.enabled) return;
  if (cfg.logPath) {
    mkdirSync(dirname(cfg.logPath), { recursive: true });
    auditStream = createWriteStream(cfg.logPath, { flags: "a" });
    auditStream.write(`# audit started ${new Date().toISOString()}\n`);
  }
}

function emit(entry: AuditEntry): void {
  const line = JSON.stringify({ _audit: entry }) + "\n";
  process.stdout.write(line);
  if (auditStream) {
    auditStream.write(line);
  }
}

/**
 * Audit an Envelope-based operation (request, forward, completion).
 */
export function writeAudit(env: Envelope, extras?: Partial<AuditEntry>): void {
  const entry: AuditEntry = {
    timestamp: new Date().toISOString(),
    traceId: env.trace_id,
    msgId: env.msg_id,
    action: env.payload.action,
    source: env.source,
    target: env.target,
    status: env.payload.status,
    errorCode: env.payload.error?.code,
    ...extras,
  };
  emit(entry);
}

/**
 * Audit a standalone event that has no Envelope (auth failure, rate-limit, etc.).
 */
export function writeAuditEvent(event: Omit<AuditEntry, "timestamp">): void {
  emit({ timestamp: new Date().toISOString(), ...event });
}
