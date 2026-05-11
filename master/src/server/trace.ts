import { Router, Request, Response } from "express";
import { Tracker } from "../orchestrator/tracker";

export function traceRouter(tracker: Tracker): Router {
  const router = Router();

  // GET /api/v1/traces — list recent pending traces (max 100)
  router.get("/api/v1/traces", (_req: Request, res: Response) => {
    const pending = tracker.getPending();
    const traces = [];
    for (const [msgId, entry] of pending) {
      if (traces.length >= 100) break;
      traces.push({
        msg_id: msgId,
        trace_id: entry.envelope.trace_id,
        action: entry.envelope.payload.action,
        target_worker_id: entry.targetWorkerId,
        sent_at: entry.sentAt,
        status: "pending",
      });
    }
    res.json({ traces });
  });

  // GET /api/v1/trace/:trace_id — return entries for a specific trace
  router.get("/api/v1/trace/:trace_id", (req: Request, res: Response) => {
    const traceId = req.params.trace_id;
    const pending = tracker.getPending();
    const entries = [];
    for (const [msgId, entry] of pending) {
      if (entry.envelope.trace_id === traceId) {
        entries.push({
          msg_id: msgId,
          trace_id: entry.envelope.trace_id,
          action: entry.envelope.payload.action,
          target_worker_id: entry.targetWorkerId,
          sent_at: entry.sentAt,
          status: "pending",
        });
      }
    }
    if (entries.length === 0) {
      res.status(404).json({ error: { code: "TRACE_NOT_FOUND", message: `No entries for trace: ${traceId}` } });
      return;
    }
    res.json({ trace_id: traceId, entries });
  });

  return router;
}
