import { v4 as uuidv4 } from "uuid";
import { Envelope, MsgType, Role, Status, Priority, Payload, ErrorInfo } from "./types";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const VERSION_RE = /^\d+\.\d+$/;
const ACTION_RE = /^[a-z]+\.[a-z]+$/;

export interface EnvelopeOptions {
  targetId?: string;
  correlationId?: string;
  priority?: Priority;
  ttlSeconds?: number;
  sourceId?: string;
}

// ── Constructor ───────────────────────────────────────────────────────

export function newRequest(
  traceId: string,
  msgId: string,
  action: string,
  params: Record<string, unknown> | undefined,
  opts: EnvelopeOptions = {},
): Envelope {
  return {
    proto_version: "1.0",
    trace_id: traceId,
    msg_id: msgId,
    msg_type: "request",
    timestamp: Math.floor(Date.now() / 1000),
    source: "master",
    source_id: opts.sourceId,
    target: "worker",
    target_id: opts.targetId ?? "*",
    correlation_id: opts.correlationId ?? "",
    priority: opts.priority ?? 0,
    ttl_seconds: opts.ttlSeconds ?? 30,
    payload: {
      action,
      params,
      status: "pending",
    },
  };
}

export function newResponse(
  req: Envelope,
  status: Status,
  data: Record<string, unknown> | undefined,
  error?: ErrorInfo,
): Envelope {
  return {
    proto_version: req.proto_version,
    trace_id: req.trace_id,
    msg_id: uuidv4(),
    msg_type: "response",
    timestamp: Math.floor(Date.now() / 1000),
    source: "worker" as Role,
    target: req.source,
    correlation_id: req.msg_id,
    payload: {
      action: req.payload.action,
      status,
      data,
      error,
    },
  };
}

// ── Validation ────────────────────────────────────────────────────────

export interface ValidationError {
  field: string;
  message: string;
}

export function validateEnvelope(e: Envelope): ValidationError[] {
  const errs: ValidationError[] = [];
  const add = (field: string, msg: string) => errs.push({ field, message: msg });

  if (!VERSION_RE.test(e.proto_version)) add("proto_version", "must match semver (e.g. 1.0)");
  if (!UUID_RE.test(e.trace_id)) add("trace_id", "must be a valid UUID");
  if (!UUID_RE.test(e.msg_id)) add("msg_id", "must be a valid UUID");

  const validTypes: MsgType[] = ["request", "response", "event", "ack", "heartbeat"];
  if (!validTypes.includes(e.msg_type)) add("msg_type", `invalid: ${e.msg_type}`);

  const validRoles: Role[] = ["brain", "master", "worker", "broadcast"];
  if (!validRoles.includes(e.source)) add("source", `invalid: ${e.source}`);
  if (e.target !== "broadcast" && !validRoles.includes(e.target)) add("target", `invalid: ${e.target}`);

  if (e.correlation_id && !UUID_RE.test(e.correlation_id)) add("correlation_id", "must be valid UUID or empty");
  if (e.priority !== undefined && ![0, 1, 2].includes(e.priority)) add("priority", "must be 0, 1, or 2");
  if (e.ttl_seconds !== undefined && (e.ttl_seconds < 1 || e.ttl_seconds > 300))
    add("ttl_seconds", "must be 1–300");
  if (e.timestamp < 1_000_000_000) add("timestamp", "looks invalid");

  // Payload
  const { payload } = e;
  if (!payload.action) add("payload.action", "is required");
  else if (!ACTION_RE.test(payload.action)) add("payload.action", "must be namespace.format (e.g. ping.icmp)");

  const validStatuses: Status[] = ["success", "failure", "pending", "cancelled"];
  if (!validStatuses.includes(payload.status)) add("payload.status", `invalid: ${payload.status}`);
  if (payload.status === "failure" && !payload.error) add("payload.error", "is required when status=failure");
  if (payload.truncated && (payload.truncated_at === undefined || payload.truncated_at <= 0))
    add("payload.truncated_at", "must be >0 when truncated=true");

  return errs;
}

// ── Serialization ─────────────────────────────────────────────────────

export function marshal(e: Envelope): string {
  return JSON.stringify(e);
}

export function unmarshal(data: string): Envelope {
  return JSON.parse(data) as Envelope;
}

export function mustMarshal(e: Envelope): string {
  const errs = validateEnvelope(e);
  if (errs.length > 0) throw new Error(`Envelope validation failed: ${JSON.stringify(errs)}`);
  return marshal(e);
}
