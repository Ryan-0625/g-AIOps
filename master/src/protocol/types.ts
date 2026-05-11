// Envelope Protocol v1 — TypeScript types
// Maps 1:1 from proto/envelope.schema.json

export type MsgType = "request" | "response" | "event" | "ack" | "heartbeat";
export type Role = "brain" | "master" | "worker" | "broadcast";
export type Status = "success" | "failure" | "pending" | "cancelled";
export type Priority = 0 | 1 | 2;

export interface Progress {
  percent: number;  // 0–100
  message: string;  // ≤200 chars
}

export interface ErrorInfo {
  code: string;
  message: string;
  raw?: string;
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
}
