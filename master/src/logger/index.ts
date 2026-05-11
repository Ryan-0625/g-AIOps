type LogLevel = "debug" | "info" | "warn" | "error";

interface LogData {
  [key: string]: unknown;
}

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  module: "master";
  trace_id: string;
  msg_id?: string;
  action?: string;
  message: string;
  error_code?: string;
  data?: LogData;
  duration_ms?: number;
  pid: number;
}

export function createLogger(_module: "master") {
  function log(level: LogLevel, message: string, opts?: {
    trace_id?: string;
    msg_id?: string;
    action?: string;
    error_code?: string;
    data?: LogData;
    duration_ms?: number;
  }): void {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      module: "master",
      trace_id: opts?.trace_id || "no-trace",
      message,
      pid: process.pid,
    };
    if (opts?.msg_id) entry.msg_id = opts.msg_id;
    if (opts?.action) entry.action = opts.action;
    if (opts?.error_code) entry.error_code = opts.error_code;
    if (opts?.data) entry.data = opts.data;
    if (opts?.duration_ms !== undefined) entry.duration_ms = opts.duration_ms;

    // stdout for all levels; stderr reserved for crashes/uncaught
    process.stdout.write(JSON.stringify(entry) + "\n");
  }

  return {
    debug: (msg: string, opts?: LogData) => log("debug", msg, { data: opts }),
    info: (msg: string, opts?: LogData) => log("info", msg, { data: opts }),
    warn: (msg: string, opts?: LogData & { error_code?: string }) =>
      log("warn", msg, { error_code: opts?.error_code, data: opts }),
    error: (msg: string, opts?: LogData & { error_code?: string }) =>
      log("error", msg, { error_code: opts?.error_code, data: opts }),
  };
}
