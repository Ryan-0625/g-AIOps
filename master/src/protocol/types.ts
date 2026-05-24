// Envelope Protocol v1.1 — TypeScript types
// Maps 1:1 from proto/envelope.schema.json
// v1.1 adds: tool_deploy/tool_code/tool_status msg_type, code_body, deploy_id, runtime_hints

export type MsgType = "request" | "response" | "event" | "ack" | "heartbeat"
                    | "tool_deploy" | "tool_code" | "tool_status";
export type Role = "brain" | "master" | "worker" | "broadcast";
export type Status = "success" | "failure" | "pending" | "cancelled";
export type Priority = 0 | 1 | 2;
export type Interpreter = "bash" | "python3" | "node";

export interface Progress {
  percent: number;  // 0–100
  message: string;  // ≤200 chars
}

export interface ErrorInfo {
  code: string;
  message: string;
  raw?: string;
}

export interface ResourceLimits {
  max_memory_mb?: number;
  max_cpu_cores?: number;
  max_timeout_s?: number;
}

export interface RuntimeHints {
  interpreter?: Interpreter;
  entrypoint?: string;
  env_vars?: Record<string, string>;
  resource_limits?: ResourceLimits;
}

export interface Payload {
  action: string;
  params?: Record<string, unknown>;
  status: Status;
  data?: Record<string, unknown>;
  truncated?: boolean;
  truncated_at?: number;
  progress?: Progress;
  error?: ErrorInfo;
}

export interface Envelope {
  proto_version: string;
  trace_id: string;
  msg_id: string;
  msg_type: MsgType;
  timestamp: number;
  source: Role;
  source_id?: string;
  target: Role;
  target_id?: string;
  correlation_id?: string;
  priority?: Priority;
  ttl_seconds?: number;
  payload: Payload;

  // v1.1 fields (optional — backward compatible)
  code_body?: string;
  deploy_id?: string;
  runtime_hints?: RuntimeHints;
}
