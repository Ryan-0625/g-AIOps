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
    switch (p.action) {
      case "disk.usage": {
        const usage = p.data?.usage_pct;
        return `Disk usage: ${usage}%`;
      }
      case "service.status": {
        const st = p.data?.status;
        return `Service status: ${st}`;
      }
      case "ping.icmp": {
        const target = p.data?.target;
        const reachable = p.data?.reachable;
        return `Ping ${target}: ${reachable ? "reachable" : "unreachable"}`;
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
      default:
        return {};
    }
  }
}
