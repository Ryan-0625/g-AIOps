import { v4 as uuidv4 } from "uuid";
import { Envelope, MsgType, Role, Status, Priority, Payload, ErrorInfo, RuntimeHints } from "./types";

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
    proto_version: "1.1",
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

/**
 * newToolDeploy — 创建工具部署请求消息
 *
 * Brain→Master→Worker 传递工具代码和运行时提示。
 * 大代码会自动在 Master 层分片为多个 tool_code 消息。
 */
export function newToolDeploy(
  traceId: string,
  deployId: string,
  action: string,
  codeBody: string,
  runtimeHints: RuntimeHints,
  opts: EnvelopeOptions = {},
): Envelope {
  return {
    proto_version: "1.1",
    trace_id: traceId,
    msg_id: uuidv4(),
    msg_type: "tool_deploy",
    timestamp: Math.floor(Date.now() / 1000),
    source: "master",
    source_id: opts.sourceId,
    target: "worker",
    target_id: opts.targetId ?? "*",
    correlation_id: "",
    priority: opts.priority ?? 0,
    ttl_seconds: opts.ttlSeconds ?? 60,
    deploy_id: deployId,
    code_body: codeBody,
    runtime_hints: runtimeHints,
    payload: {
      action,
      params: {},
      status: "pending",
    },
  };
}

/**
 * newToolCode — 创建分片代码传输消息
 * 当代码体超过 1MB 时，拆分为多个 tool_code 消息。
 */
export function newToolCode(
  traceId: string,
  deployId: string,
  action: string,
  chunk: string,
  chunkIndex: number,
  chunkTotal: number,
): Envelope {
  return {
    proto_version: "1.1",
    trace_id: traceId,
    msg_id: uuidv4(),
    msg_type: "tool_code",
    timestamp: Math.floor(Date.now() / 1000),
    source: "master",
    target: "worker",
    correlation_id: "",
    deploy_id: deployId,
    code_body: chunk,
    payload: {
      action,
      params: { _chunk_index: chunkIndex, _chunk_total: chunkTotal },
      status: "pending",
    },
  };
}

/**
 * newToolStatus — 创建工具状态上报消息
 * Worker→Master→Brain 回传工具部署/执行状态。
 */
export function newToolStatus(
  deployId: string,
  action: string,
  status: Status,
  error?: ErrorInfo,
): Envelope {
  return {
    proto_version: "1.1",
    trace_id: deployId,
    msg_id: uuidv4(),
    msg_type: "tool_status",
    timestamp: Math.floor(Date.now() / 1000),
    source: "worker",
    target: "master",
    correlation_id: "",
    deploy_id: deployId,
    payload: {
      action,
      status,
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

  if (!VERSION_RE.test(e.proto_version)) add("proto_version", "must match semver (e.g. 1.1)");
  if (!UUID_RE.test(e.trace_id)) add("trace_id", "must be a valid UUID");
  if (!UUID_RE.test(e.msg_id)) add("msg_id", "must be a valid UUID");

  const validTypes: MsgType[] = [
    "request", "response", "event", "ack", "heartbeat",
    "tool_deploy", "tool_code", "tool_status",
  ];
  if (!validTypes.includes(e.msg_type)) add("msg_type", `invalid: ${e.msg_type}`);

  // v1.0 backward compat: v1.0 nodes see new msg_type and report warning but don't crash
  const v1Types: MsgType[] = ["request", "response", "event", "ack", "heartbeat"];
  if (!v1Types.includes(e.msg_type) && e.proto_version === "1.0") {
    add("msg_type", `v1.0 does not support ${e.msg_type}; upgrade to v1.1`);
  }

  const validRoles: Role[] = ["brain", "master", "worker", "broadcast"];
  if (!validRoles.includes(e.source)) add("source", `invalid: ${e.source}`);
  if (e.target !== "broadcast" && !validRoles.includes(e.target)) add("target", `invalid: ${e.target}`);

  if (e.correlation_id && !UUID_RE.test(e.correlation_id)) add("correlation_id", "must be valid UUID or empty");
  if (e.priority !== undefined && ![0, 1, 2].includes(e.priority)) add("priority", "must be 0, 1, or 2");
  if (e.ttl_seconds !== undefined && (e.ttl_seconds < 1 || e.ttl_seconds > 300))
    add("ttl_seconds", "must be 1–300");
  if (e.timestamp < 1_000_000_000) add("timestamp", "looks invalid");

  // v1.1 fields validation
  if (e.msg_type === "tool_deploy" || e.msg_type === "tool_code") {
    if (!e.code_body) add("code_body", "required for tool_deploy/tool_code messages");
    if (!e.deploy_id) add("deploy_id", "required for tool_deploy/tool_code messages");
  }
  if (e.msg_type === "tool_deploy" && !e.runtime_hints?.interpreter) {
    add("runtime_hints.interpreter", "required for tool_deploy messages");
  }
  if (e.deploy_id && !UUID_RE.test(e.deploy_id)) add("deploy_id", "must be a valid UUID");

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
