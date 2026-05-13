import { Envelope, Payload } from "../protocol/types";

export interface SummarizedResult {
  traceId: string;
  action: string;
  status: string;
  summary: string;
  keyMetrics: Record<string, unknown>;
  hasTruncation: boolean;
  hasError: boolean;
  errorCode?: string;
  errorMessage?: string;
}

/**
 * Summarizer condenses a raw Worker response into a compact form for Brain,
 * reducing LLM token consumption.  Truncation and error flags are always
 * preserved separately — never folded into summary text where LLM might miss them.
 */
export class Summarizer {
  summarize(env: Envelope): SummarizedResult {
    const p = env.payload;
    const result: SummarizedResult = {
      traceId: env.trace_id,
      action: p.action,
      status: p.status,
      summary: "",
      keyMetrics: {},
      hasTruncation: p.truncated ?? false,
      hasError: p.status === "failure",
    };

    // Build a human-readable one-liner for LLM consumption.
    if (p.status === "success") {
      result.summary = this.buildSuccessSummary(p);
      result.keyMetrics = this.extractMetrics(p);
    } else if (p.status === "failure" && p.error) {
      result.errorCode = p.error.code;
      result.errorMessage = p.error.message;
      result.summary = `Failed: ${p.error.code} — ${p.error.message}`;
    } else if (p.status === "pending" && p.progress) {
      result.summary = `In progress: ${p.progress.percent}% — ${p.progress.message}`;
    }

    // Append truncation signal — never hidden inside summary.
    if (p.truncated) {
      result.summary += ` [truncated at ${p.truncated_at} bytes]`;
    }

    return result;
  }

  private buildSuccessSummary(p: Payload): string {
    const d = p.data;

    switch (p.action) {
      case "system.info": {
        const host = d?.hostname;
        const os_name = d?.os;
        const uptime = typeof d?.uptime_seconds === "number" ? `${Math.floor(d.uptime_seconds / 3600)}h` : "?";
        return `System: ${host || "?"} running ${os_name || "?"} (up ${uptime})`;
      }
      case "cpu.usage": {
        const cores = d?.cpu_cores || "?";
        const l1 = d?.load_1min ?? "?";
        const l5 = d?.load_5min ?? "?";
        return `CPU: ${cores} cores, load: ${l1} / ${l5}`;
      }
      case "memory.usage": {
        const total = d?.total_gb || "?";
        const avail = d?.available_gb || "?";
        const pct = total !== "?" && avail !== "?" ? `${Math.round((1 - Number(avail) / Number(total)) * 100)}%` : "?";
        return `Memory: ${avail}GB free / ${total}GB total (${pct} used)`;
      }
      case "disk.usage": {
        const usage = d?.usage_pct;
        return `Disk usage: ${usage}%`;
      }
      case "network.connections": {
        const list = d?.connections;
        const count = Array.isArray(list) ? list.length : 0;
        return `Network: ${count} active connections`;
      }
      case "dns.lookup": {
        const addr = d?.addresses || d?.address;
        const addrs = Array.isArray(addr) ? addr.join(", ") : String(addr || "?");
        return `DNS: ${d?.query || "?"} → ${addrs}`;
      }
      case "http.get":
      case "http.post": {
        const sc = d?.status_code ?? d?.status ?? "?";
        const len = d?.body_length ?? "";
        return `HTTP ${p.action === "http.get" ? "GET" : "POST"}: status ${sc}${len ? ` (${len} bytes)` : ""}`;
      }
      case "ping.icmp": {
        const target = d?.target;
        const reachable = d?.reachable;
        const rtt = d?.avg_rtt_ms ? ` ${d.avg_rtt_ms}ms` : "";
        return `Ping ${target}: ${reachable ? `reachable${rtt}` : "unreachable"}`;
      }
      case "service.status": {
        const st = d?.status;
        return `Service status: ${st}`;
      }
      case "service.restart": {
        const name = d?.service || d?.name || "?";
        return `Service ${name} restarted`;
      }
      case "service.stop": {
        const name = d?.service || d?.name || "?";
        return `Service ${name} stopped`;
      }
      case "process.list": {
        const list = d?.processes || d?.list;
        const count = Array.isArray(list) ? list.length : 0;
        return `Processes: ${count} running`;
      }
      case "process.kill": {
        const pid = d?.pid || "?";
        return `Process ${pid} killed`;
      }
      case "file.read": {
        const path = d?.path || p.params?.path || "?";
        const bytes = typeof d?.size === "number" ? `${d.size}B` : "";
        return `File read: ${path}${bytes ? ` (${bytes})` : ""}`;
      }
      case "file.write": {
        const path = d?.path || p.params?.path || "?";
        return `File written: ${path}`;
      }
      case "file.list": {
        const path = d?.path || p.params?.path || "?";
        const files = d?.files;
        const count = Array.isArray(files) ? files.length : 0;
        return `Directory ${path}: ${count} entries`;
      }
      case "container.list": {
        const dd = d as any;
        const list = Array.isArray(d) ? d : dd?.containers || [];
        const running = list.filter((c: any) => c.status === "running").length;
        return `Containers: ${list.length} total, ${running} running`;
      }
      case "container.logs": {
        const dd = d as any;
        const name = dd?.container || p.params?.container || p.params?.name || "?";
        const lines = dd?.lines || dd?.logs || "";
        const count = typeof lines === "string" ? lines.split("\n").length : Array.isArray(lines) ? lines.length : "?";
        return `Container ${name}: ${count} log lines`;
      }
      case "log.tail": {
        const path = (d as any)?.path || p.params?.path || "?";
        const count = typeof (d as any)?.lines === "number" ? (d as any).lines : typeof (d as any)?.content === "string" ? (d as any).content.split("\n").length : "?";
        return `Log ${path}: ${count} lines`;
      }
      case "exec.run": {
        const cmd = (d as any)?.command || p.params?.command || "?";
        const exitCode = (d as any)?.exit_code ?? "?";
        return `Exec "${cmd}": exit code ${exitCode}`;
      }
      default:
        return `Success (${p.action})`;
    }
  }

  private extractMetrics(p: Payload): Record<string, unknown> {
    if (!p.data) return {};
    const { action, data } = p;

    switch (action) {
      case "disk.usage":
        return { usagePct: data.usage_pct, availBytes: data.avail_bytes };
      case "ping.icmp":
        return { reachable: data.reachable, avgRttMs: data.avg_rtt_ms };
      case "service.status":
        return { status: data.status, running: data.running };
      case "system.info":
        return { hostname: data.hostname, os: data.os, uptime: data.uptime_seconds, cores: data.cpu_cores };
      case "cpu.usage":
        return { cores: data.cpu_cores, load1: data.load_1min, load5: data.load_5min };
      case "memory.usage":
        return { totalGb: data.total_gb, availGb: data.available_gb };
      case "http.get":
      case "http.post":
        return { statusCode: data.status_code ?? data.status };
      default:
        return {};
    }
  }
}
