import { Router, Request, Response } from "express";
import { Registry } from "../store/registry";
import { Tracker } from "../orchestrator/tracker";
import { PriorityQueue } from "../orchestrator/priority-queue";
import { Approver } from "../security/approver";
import { MetricsCollector } from "../store/metrics";

export function metricsRouter(
  registry: Registry,
  tracker: Tracker,
  queue: PriorityQueue,
  approver: Approver,
  collector: MetricsCollector,
): Router {
  const router = Router();

  router.get("/metrics", (_req: Request, res: Response) => {
    const snap = collector.snapshot(
      registry.onlineCount(),
      tracker.pendingCount(),
      queue.size(),
      approver.pendingCount(),
    );

    const lines: string[] = [];

    // Gauges
    lines.push("# HELP gaiops_workers_online Connected workers");
    lines.push("# TYPE gaiops_workers_online gauge");
    lines.push(`gaiops_workers_online ${snap.workerCount}`);

    lines.push("# HELP gaiops_requests_pending Requests awaiting dispatch");
    lines.push("# TYPE gaiops_requests_pending gauge");
    lines.push(`gaiops_requests_pending ${snap.pendingCount}`);

    lines.push("# HELP gaiops_queue_depth Priority queue depth");
    lines.push("# TYPE gaiops_queue_depth gauge");
    lines.push(`gaiops_queue_depth ${snap.queueDepth}`);

    lines.push("# HELP gaiops_approvals_pending Pending approval requests");
    lines.push("# TYPE gaiops_approvals_pending gauge");
    lines.push(`gaiops_approvals_pending ${snap.approvalCount}`);

    lines.push("# HELP gaiops_uptime_seconds Process uptime");
    lines.push("# TYPE gaiops_uptime_seconds counter");
    lines.push(`gaiops_uptime_seconds ${snap.uptimeSeconds}`);

    // Counters
    lines.push("# HELP gaiops_requests_total Total processed requests");
    lines.push("# TYPE gaiops_requests_total counter");
    lines.push(`gaiops_requests_total ${snap.totalProcessed}`);

    lines.push("# HELP gaiops_requests_per_minute Requests in current minute");
    lines.push("# TYPE gaiops_requests_per_minute gauge");
    lines.push(`gaiops_requests_per_minute ${snap.requestsThisMinute}`);

    lines.push("# HELP gaiops_responses_truncated Truncated response count");
    lines.push("# TYPE gaiops_responses_truncated counter");
    lines.push(`gaiops_responses_truncated ${snap.truncatedCount}`);

    lines.push("# HELP gaiops_errors_total Error response count");
    lines.push("# TYPE gaiops_errors_total counter");
    lines.push(`gaiops_errors_total ${snap.errorCount}`);

    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    res.send(lines.join("\n") + "\n");
  });

  return router;
}
